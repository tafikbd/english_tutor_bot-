import os
import asyncio
import logging
import threading
import random
from datetime import datetime, timedelta

from flask import Flask
from groq import Groq

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
)
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
    PreCheckoutQueryHandler,
)

import asyncpg


# ==========================================================
# CONFIG
# ==========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
PORT = int(os.getenv("PORT", "10000"))

ADMIN_IDS = [
    int(x) for x in os.getenv("ADMIN_IDS", "").split(",")
    if x.strip().isdigit()
]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is missing.")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing.")


logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

groq_client = Groq(api_key=GROQ_API_KEY)
db_pool = None

REFERRAL_REWARD = 10
DAILY_BONUS = 5
STREAK_BONUS = 2
PREMIUM_STARS = 50
PREMIUM_DAYS = 30


# ==========================================================
# DATABASE
# ==========================================================
async def init_db():
    global db_pool
    
    # URL ফিক্স: postgres:// কে postgresql:// করে দেবে
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    
    try:
        logger.info("Connecting to database...")
        db_pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS t_users (
                    user_id BIGINT PRIMARY KEY,
                    name VARCHAR(100),
                    language VARCHAR(5) DEFAULT 'bn',
                    level VARCHAR(20) DEFAULT 'beginner',
                    coins INTEGER DEFAULT 0,
                    streak INTEGER DEFAULT 0,
                    last_practice DATE,
                    words_learned INTEGER DEFAULT 0,
                    quizzes_taken INTEGER DEFAULT 0,
                    quiz_score INTEGER DEFAULT 0,
                    is_premium BOOLEAN DEFAULT FALSE,
                    premium_until TIMESTAMP,
                    referred_by BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS t_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role VARCHAR(20),
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_history_user ON t_history(user_id);
                CREATE TABLE IF NOT EXISTS t_words (
                    id SERIAL PRIMARY KEY,
                    word VARCHAR(100) UNIQUE,
                    meaning TEXT,
                    example TEXT
                );
                CREATE TABLE IF NOT EXISTS t_reports (
                    id SERIAL PRIMARY KEY,
                    reporter_id BIGINT,
                    reported_id BIGINT,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS t_users (
                user_id BIGINT PRIMARY KEY,
                name VARCHAR(100),
                language VARCHAR(5) DEFAULT 'bn',
                level VARCHAR(20) DEFAULT 'beginner',
                coins INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_practice DATE,
                words_learned INTEGER DEFAULT 0,
                quizzes_taken INTEGER DEFAULT 0,
                quiz_score INTEGER DEFAULT 0,
                is_premium BOOLEAN DEFAULT FALSE,
                premium_until TIMESTAMP,
                referred_by BIGINT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS t_history (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                role VARCHAR(20),
                content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_history_user ON t_history(user_id);
            CREATE TABLE IF NOT EXISTS t_words (
                id SERIAL PRIMARY KEY,
                word VARCHAR(100) UNIQUE,
                meaning TEXT,
                example TEXT
            );
            CREATE TABLE IF NOT EXISTS t_reports (
                id SERIAL PRIMARY KEY,
                reporter_id BIGINT,
                reported_id BIGINT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
    logger.info("Database initialized.")


async def close_db():
    if db_pool:
        await db_pool.close()


async def get_user(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM t_users WHERE user_id = $1", uid)
        return dict(row) if row else None


async def create_user(uid, name):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO t_users (user_id, name) VALUES ($1, $2) ON CONFLICT (user_id) DO NOTHING",
            uid, name,
        )


async def update_user(uid, **kwargs):
    if not kwargs:
        return
    cols = list(kwargs.keys())
    vals = list(kwargs.values())
    sets = ", ".join([f"{c} = ${i+2}" for i, c in enumerate(cols)])
    async with db_pool.acquire() as conn:
        await conn.execute(f"UPDATE t_users SET {sets} WHERE user_id = $1", uid, *vals)


async def add_coins(uid, amount):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE t_users SET coins = coins + $1 WHERE user_id = $2", amount, uid)


async def get_coins(uid):
    async with db_pool.acquire() as conn:
        c = await conn.fetchval("SELECT coins FROM t_users WHERE user_id = $1", uid)
        return c or 0


async def save_history(uid, role, content):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO t_history (user_id, role, content) VALUES ($1, $2, $3)",
            uid, role, content,
        )
        # Keep last 20
        await conn.execute("""
            DELETE FROM t_history WHERE user_id = $1 AND id NOT IN (
                SELECT id FROM t_history WHERE user_id = $1 ORDER BY id DESC LIMIT 20
            )
        """, uid)


async def get_history(uid):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, content FROM t_history WHERE user_id = $1 ORDER BY id ASC",
            uid,
        )
        return [{"role": r["role"], "content": r["content"]} for r in rows]


async def clear_history(uid):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM t_history WHERE user_id = $1", uid)


# ==========================================================
# AI
# ==========================================================

SYSTEM_PROMPT = """
You are Sir English — an expert, friendly, patient English teacher for Bangla-speaking students.

Core rules:
- Reply in the user's language (Bangla → Bangla, English → English).
- Keep answers SHORT and clear unless detail is requested.
- For corrections, use:
  ❌ Wrong: ...
  ✅ Correct: ...
  📝 Why: ...
- For vocabulary: word, meaning (Bangla), pronunciation, part of speech, example.
- For grammar: rule → example → common mistake.
- For translations: natural, not literal.
- For writing help (paragraph/essay/email): well-structured, appropriate length.
- Adapt to level: beginner (simple), intermediate (deeper), advanced (nuance).
- Never invent facts. If unsure, say so.
- Be encouraging. Never mock.
- Use Markdown formatting when helpful.
- Keep responses under 3500 characters.
"""


def ask_groq(user_text, history=None, level="beginner"):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if level:
        messages.append({"role": "system", "content": f"User level: {level}"})
    if history:
        messages.extend(history[-8:])
    messages.append({"role": "user", "content": user_text})

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.4,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


# ==========================================================
# FLASK
# ==========================================================

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Sir English Bot running."


@flask_app.route("/health")
def health():
    return "OK"


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True)


# ==========================================================
# KEYBOARDS
# ==========================================================

def main_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📚 Vocabulary", callback_data="m_vocab"),
         InlineKeyboardButton("📝 Grammar", callback_data="m_grammar")],
        [InlineKeyboardButton("🎯 Quiz", callback_data="m_quiz"),
         InlineKeyboardButton("✍️ Writing", callback_data="m_writing")],
        [InlineKeyboardButton("🗣 Speaking", callback_data="m_speaking"),
         InlineKeyboardButton("💬 Translate", callback_data="m_translate")],
        [InlineKeyboardButton("👤 My Profile", callback_data="m_profile"),
         InlineKeyboardButton("🔥 Daily Lesson", callback_data="m_daily")],
        [InlineKeyboardButton("🎁 Invite & Earn", callback_data="m_invite"),
         InlineKeyboardButton("⭐ Premium", callback_data="m_premium")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="m_help")],
    ])


def back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")]
    ])


# ==========================================================
# HELPERS
# ==========================================================

async def check_streak(user_id):
    user = await get_user(user_id)
    if not user:
        return 0
    today = datetime.now().date()
    last = user.get("last_practice")
    if last is None:
        return 0
    if isinstance(last, datetime):
        last = last.date()
    diff = (today - last).days
    if diff == 0:
        return user.get("streak") or 0
    if diff == 1:
        new_streak = (user.get("streak") or 0) + 1
        await update_user(user_id, streak=new_streak, last_practice=today)
        return new_streak
    await update_user(user_id, streak=1, last_practice=today)
    return 1


async def get_leaderboard():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT name, quiz_score, words_learned, streak
            FROM t_users
            ORDER BY quiz_score DESC, words_learned DESC
            LIMIT 10
        """)
        return rows


# ==========================================================
# START
# ==========================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.is_bot:
        return
    await create_user(u.id, u.full_name or "Student")

    # Referral
    args = context.args or []
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != u.id:
                user = await get_user(u.id)
                if user and not user.get("referred_by"):
                    await update_user(u.id, referred_by=ref_id)
                    await add_coins(ref_id, REFERRAL_REWARD)
                    try:
                        await context.bot.send_message(
                            ref_id,
                            f"🎁 আপনি {REFERRAL_REWARD} কয়েন পেয়েছেন বন্ধু ইনভাইটের জন্য!"
                        )
                    except Exception:
                        pass
        except (ValueError, IndexError):
            pass

    await update.message.reply_text(
        f"👋 স্বাগতম {u.first_name}!\n\n"
        f"🎓 আমি **Sir English** — আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n"
        f"📖 যা করতে পারি:\n"
        f"• 📚 Vocabulary শেখানো\n"
        f"• 📝 Grammar ব্যাখ্যা\n"
        f"• 🎯 Quiz ও Leaderboard\n"
        f"• 💬 বাংলা ↔ ইংরেজি অনুবাদ\n"
        f"• ✍️ Writing Help\n"
        f"• 🗣 Speaking Practice\n"
        f"• 🔥 Daily Lesson + Streak\n"
        f"• 🎁 Invite & Earn Coins\n\n"
        f"👉 নিচের বাটন থেকে বেছে নিন বা সরাসরি লিখে পাঠান।",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 **সাহায্য**\n\n"
        "/start — মেইন মেনু\n"
        "/menu — মেনু\n"
        "/profile — প্রোফাইল\n"
        "/leaderboard — লিডারবোর্ড\n"
        "/daily — আজকের পাঠ\n"
        "/reset — চ্যাট ক্লিয়ার\n"
        "/adminstats — অ্যাডমিন স্ট্যাটস\n\n"
        "💡 যেকোনো ইংরেজি/বাংলা বাক্য লিখে পাঠান — আমি সাহায্য করব।",
        parse_mode="Markdown",
    )


async def menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏠 মেইন মেনু:", reply_markup=main_menu_kb()
    )


async def profile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("❌ আগে /start দিন।")
        return
    coins = user.get("coins") or 0
    streak = user.get("streak") or 0
    words = user.get("words_learned") or 0
    quizzes = user.get("quizzes_taken") or 0
    score = user.get("quiz_score") or 0
    premium = "✅ Active" if user.get("is_premium") else "❌ Inactive"
    await update.message.reply_text(
        f"👤 **আপনার প্রোফাইল**\n\n"
        f"📛 নাম: {user.get('name')}\n"
        f"🎓 লেভেল: {user.get('level')}\n"
        f"🪙 কয়েন: {coins}\n"
        f"🔥 Streak: {streak} দিন\n"
        f"📚 শেখা শব্দ: {words}\n"
        f"🎯 কুইজ দিয়েছেন: {quizzes}\n"
        f"⭐ স্কোর: {score}\n"
        f"💎 Premium: {premium}",
        parse_mode="Markdown",
    )


async def leaderboard_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = await get_leaderboard()
    if not rows:
        await update.message.reply_text("এখনো কোনো ইউজার নেই।")
        return
    text = "🏆 **টপ ১০ লিডারবোর্ড**\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        text += f"{m} {r['name']} — ⭐ {r['quiz_score']} | 📚 {r['words_learned']} | 🔥 {r['streak']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await clear_history(uid)
    await update.message.reply_text("🔄 চ্যাট ক্লিয়ার হয়েছে। /start দিন।")


async def daily_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    prompt = (
        "Give the daily English lesson. Include:\n"
        "1. One new vocabulary word with Bangla meaning, pronunciation, example\n"
        "2. One grammar tip with example\n"
        "3. One practice question\n"
        "Keep it short and clear."
    )
    await update.message.chat.send_action("typing")
    answer = await asyncio.to_thread(ask_groq, prompt)
    await update.message.reply_text(
        f"🔥 **Daily Lesson** (Streak: {streak} দিন)\n"
        f"🎁 বোনাস: +{bonus} কয়েন\n\n{answer}",
        parse_mode="Markdown",
    )


# ==========================================================
# ADMIN
# ==========================================================

async def adminstats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ অ্যাডমিন নন।")
        return
    async with db_pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM t_users")
        today = await conn.fetchval(
            "SELECT COUNT(*) FROM t_users WHERE last_active > NOW() - INTERVAL '24 hours'"
        )
        week = await conn.fetchval(
            "SELECT COUNT(*) FROM t_users WHERE last_active > NOW() - INTERVAL '7 days'"
        )
        premium = await conn.fetchval("SELECT COUNT(*) FROM t_users WHERE is_premium = TRUE")
        total_coins = await conn.fetchval("SELECT COALESCE(SUM(coins), 0) FROM t_users")
        total_msgs = await conn.fetchval("SELECT COUNT(*) FROM t_history")
    await update.message.reply_text(
        f"📊 **Admin Dashboard**\n\n"
        f"👥 মোট ইউজার: {total}\n"
        f"🟢 ২৪ ঘণ্টায় সক্রিয়: {today}\n"
        f"📅 ৭ দিনে সক্রিয়: {week}\n"
        f"💎 Premium: {premium}\n"
        f"🪙 মোট কয়েন: {total_coins}\n"
        f"💬 মোট মেসেজ: {total_msgs}",
        parse_mode="Markdown",
    )


# ==========================================================
# CALLBACKS
# ==========================================================

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 মেইন মেনু:", reply_markup=main_menu_kb())


async def cb_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = await get_user(uid)
    if not user:
        await q.edit_message_text("❌ আগে /start দিন।")
        return
    coins = user.get("coins") or 0
    streak = user.get("streak") or 0
    words = user.get("words_learned") or 0
    quizzes = user.get("quizzes_taken") or 0
    score = user.get("quiz_score") or 0
    premium = "✅ Active" if user.get("is_premium") else "❌ Inactive"
    await q.edit_message_text(
        f"👤 **আপনার প্রোফাইল**\n\n"
        f"📛 নাম: {user.get('name')}\n"
        f"🎓 লেভেল: {user.get('level')}\n"
        f"🪙 কয়েন: {coins}\n"
        f"🔥 Streak: {streak} দিন\n"
        f"📚 শেখা শব্দ: {words}\n"
        f"🎯 কুইজ: {quizzes} টি\n"
        f"⭐ স্কোর: {score}\n"
        f"💎 Premium: {premium}",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


async def cb_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    await q.edit_message_text("🔥 ডেইলি লেসন লোড হচ্ছে...")
    prompt = (
        "Give the daily English lesson: 1 vocabulary word (Bangla meaning + pronunciation + example), "
        "1 grammar tip with example, 1 practice question. Short."
    )
    answer = await asyncio.to_thread(ask_groq, prompt)
    await q.edit_message_text(
        f"🔥 **Daily Lesson** (Streak: {streak} দিন)\n"
        f"🎁 বোনাস: +{bonus} কয়েন\n\n{answer}",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


async def cb_vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    await update_user(uid, last_active=datetime.now())
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE t_users SET words_learned = words_learned + 1 WHERE user_id = $1", uid
        )
    await q.edit_message_text("📚 শব্দ তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Teach ONE useful English word: word, Bangla meaning, pronunciation, part of speech, one example. "
        "Then give ONE short practice question. Do NOT show the answer."
    )
    await q.edit_message_text(
        answer, reply_markup=back_kb(), parse_mode="Markdown"
    )


async def cb_grammar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await update_user(q.from_user.id, last_active=datetime.now())
    await q.edit_message_text("📝 গ্রামার লেসন তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Teach ONE English grammar point: rule, simple explanation, 2 examples, 1 common mistake, "
        "1 short practice question. Do not give answer."
    )
    await q.edit_message_text(
        answer, reply_markup=back_kb(), parse_mode="Markdown"
    )


async def cb_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    await update_user(uid, last_active=datetime.now())
    await q.edit_message_text("🎯 কুইজ তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Create ONE English multiple-choice quiz with 4 options. "
        "Format:\nQuestion: ...\nA) ...\nB) ...\nC) ...\nD) ...\n"
        "Answer: X) ...\nKeep it short."
    )
    await update_user(
        uid, quizzes_taken=(await get_user(uid)).get("quizzes_taken", 0) + 1
    )
    await q.edit_message_text(
        f"🎯 **Quiz**\n\n{answer}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 আরেকটি কুইজ", callback_data="m_quiz")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")],
        ]),
        parse_mode="Markdown",
    )


async def cb_writing(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "✍️ **Writing Help**\n\n"
        "লিখুন:\n"
        "• `paragraph on environment`\n"
        "• `essay on friendship`\n"
        "• `email to my friend`\n"
        "• `story about a brave boy`",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


async def cb_speaking(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🗣 Speaking প্র্যাকটিস লোড হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Start English speaking practice. Ask ONE simple real-life question and wait for the answer. "
        "Keep it short and friendly."
    )
    await q.edit_message_text(
        answer, reply_markup=back_kb(), parse_mode="Markdown"
    )


async def cb_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "💬 **Translation**\n\n"
        "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান — আমি অনুবাদ করে দেব।\n\n"
        "উদাহরণ:\n"
        "• `আমি ভাত খাই` → I eat rice.\n"
        "• `I love my family` → আমি আমার পরিবারকে ভালোবাসি।",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


async def cb_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await q.edit_message_text(
        f"🎁 **Invite & Earn**\n\n"
        f"আপনার ইনভাইট লিংক:\n`{link}`\n\n"
        f"💡 প্রতি ইনভাইটে **{REFERRAL_REWARD} কয়েন** পাবেন!",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


async def cb_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = await get_user(uid)
    if user and user.get("is_premium"):
        await q.edit_message_text(
            f"💎 আপনি ইতিমধ্যে Premium!",
            reply_markup=back_kb(),
        )
        return
    await q.edit_message_text(
        f"💎 **Premium Membership**\n\n"
        f"⭐ {PREMIUM_STARS} Telegram Stars দিয়ে {PREMIUM_DAYS} দিনের Premium\n\n"
        f"🎁 Premium সুবিধা:\n"
        f"• আনলিমিটেড AI উত্তর\n"
        f"• Detailed Grammar Lessons\n"
        f"• Personal Progress Report\n"
        f"• Priority Response\n",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ কিনুন ({PREMIUM_STARS} Stars)", callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")],
        ]),
        parse_mode="Markdown",
    )


async def cb_buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title="💎 Sir English Premium",
            description=f"{PREMIUM_DAYS} days Premium access",
            payload=f"premium_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS)],
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await q.answer("❌ Payment failed. Try again.", show_alert=True)


async def precheckout_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    until = datetime.now() + timedelta(days=PREMIUM_DAYS)
    await update_user(uid, is_premium=True, premium_until=until)
    await update.message.reply_text(
        f"🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n\n"
        f"✅ {PREMIUM_DAYS} দিনের জন্য সক্রিয়।"
    )


async def cb_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text(
        "ℹ️ **সাহায্য**\n\n"
        "🎓 বাটন থেকে বেছে নিন:\n"
        "📚 Vocabulary — নতুন শব্দ\n"
        "📝 Grammar — গ্রামার লেসন\n"
        "🎯 Quiz — কুইজ খেলুন\n"
        "✍️ Writing — রাইটিং হেল্প\n"
        "🗣 Speaking — স্পিকিং প্র্যাকটিস\n"
        "💬 Translate — অনুবাদ\n"
        "🔥 Daily Lesson — ডেইলি বোনাস\n"
        "🎁 Invite — কয়েন আর্ন করুন\n"
        "⭐ Premium — প্রিমিয়াম\n\n"
        "📝 যে কোনো বাক্য লিখে পাঠান — AI উত্তর দেবে।",
        reply_markup=back_kb(),
        parse_mode="Markdown",
    )


# ==========================================================
# MESSAGE HANDLER
# ==========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    uid = update.effective_user.id
    text = update.message.text.strip()
    if not text:
        return

    user = await get_user(uid)
    if not user:
        await create_user(uid, update.effective_user.full_name or "Student")
        user = await get_user(uid)

    await update_user(uid, last_active=datetime.now())
    await check_streak(uid)

    # Save user message
    await save_history(uid, "user", text)
    history = await get_history(uid)
    level = user.get("level", "beginner")

    try:
        await update.message.chat.send_action("typing")
        answer = await asyncio.to_thread(ask_groq, text, history, level)
        if not answer:
            answer = "⚠️ উত্তর তৈরি করা যায়নি। আবার চেষ্টা করুন।"
        if len(answer) > 4000:
            answer = answer[:4000]
        await save_history(uid, "assistant", answer)
        await update.message.reply_text(answer, parse_mode="Markdown")
    except Exception as e:
        logger.exception("AI error: %s", e)
        try:
            await update.message.reply_text(answer)
        except Exception:
            await update.message.reply_text("⚠️ কিছু ভুল হয়েছে। আবার চেষ্টা করুন।")


# ==========================================================
# BOT SETUP
# ==========================================================

async def post_init(app):
    await init_db()


async def post_shutdown(app):
    await close_db()


def run_bot():
    async def _run():
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .post_init(post_init)
            .post_shutdown(post_shutdown)
            .build()
        )

        # Commands
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("menu", menu_cmd))
        application.add_handler(CommandHandler("help", help_cmd))
        application.add_handler(CommandHandler("profile", profile_cmd))
        application.add_handler(CommandHandler("leaderboard", leaderboard_cmd))
        application.add_handler(CommandHandler("daily", daily_cmd))
        application.add_handler(CommandHandler("reset", reset_cmd))
        application.add_handler(CommandHandler("adminstats", adminstats_cmd))

        # Callbacks
        application.add_handler(CallbackQueryHandler(cb_menu, pattern="^m_menu$"))
        application.add_handler(CallbackQueryHandler(cb_profile, pattern="^m_profile$"))
        application.add_handler(CallbackQueryHandler(cb_daily, pattern="^m_daily$"))
        application.add_handler(CallbackQueryHandler(cb_vocab, pattern="^m_vocab$"))
        application.add_handler(CallbackQueryHandler(cb_grammar, pattern="^m_grammar$"))
        application.add_handler(CallbackQueryHandler(cb_quiz, pattern="^m_quiz$"))
        application.add_handler(CallbackQueryHandler(cb_writing, pattern="^m_writing$"))
        application.add_handler(CallbackQueryHandler(cb_speaking, pattern="^m_speaking$"))
        application.add_handler(CallbackQueryHandler(cb_translate, pattern="^m_translate$"))
        application.add_handler(CallbackQueryHandler(cb_invite, pattern="^m_invite$"))
        application.add_handler(CallbackQueryHandler(cb_premium, pattern="^m_premium$"))
        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_premium$"))
        application.add_handler(CallbackQueryHandler(cb_help, pattern="^m_help$"))

        # Payment
        application.add_handler(PreCheckoutQueryHandler(precheckout_cb))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_cb))

        # Messages
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )

        try:
            await application.initialize()
            await application.bot.delete_webhook(drop_pending_updates=False)
            await application.start()
            await application.updater.start_polling(drop_pending_updates=False)
            logger.info("Bot started successfully.")
            bot_info = await application.bot.get_me()
            logger.info("Bot username: @%s", bot_info.username)
            while True:
                await asyncio.sleep(3600)
        except Conflict:
            logger.error("Conflict: another instance running.")
        except TelegramError as e:
            logger.exception("Telegram error: %s", e)
        except Exception as e:
            logger.exception("Unexpected: %s", e)
        finally:
            try:
                if application.updater.running:
                    await application.updater.stop()
            except Exception:
                pass
            try:
                if application.running:
                    await application.stop()
            except Exception:
                pass
            try:
                await application.shutdown()
            except Exception:
                pass

    asyncio.run(_run())


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":
    logger.info("Starting Sir English Bot...")
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()
    logger.info("Bot + Flask threads started.")
    # Keep main thread alive
    while True:
        import time
        time.sleep(3600)
