import os
import asyncio
import logging
import threading
import random
import time
from datetime import datetime, timedelta

from flask import Flask
from groq import Groq

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice,
)
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, PreCheckoutQueryHandler,
)

try:
    import asyncpg
    HAS_ASYNCPG = True
except ImportError:
    HAS_ASYNCPG = False


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
    raise RuntimeError("BOT_TOKEN missing.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing.")


# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ==========================================================
# CONSTANTS
# ==========================================================

REFERRAL_REWARD = 10
DAILY_BONUS = 5
STREAK_BONUS = 2
CHAT_COIN = 1
PREMIUM_STARS = 50
PREMIUM_DAYS = 30

ACHIEVEMENTS = {
    "first_chat": ("🥇", "প্রথম চ্যাট"),
    "words_10": ("📚", "১০ শব্দ শিখেছেন"),
    "words_50": ("📖", "৫০ শব্দ শিখেছেন"),
    "quiz_10": ("🎯", "১০ কুইজ দিয়েছেন"),
    "streak_7": ("🔥", "৭ দিনের স্ট্রিক"),
    "streak_30": ("💪", "৩০ দিনের স্ট্রিক"),
    "premium": ("💎", "Premium সদস্য"),
    "referrer": ("🎁", "কাউকে ইনভাইট করেছেন"),
}


# ==========================================================
# GROQ + SYSTEM PROMPT
# ==========================================================

groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are EduMate AI, a smart AI Teacher and AI Assistant.

Your two main roles are:

1. AI Teacher
- Help users learn English and other languages.
- Teach vocabulary, grammar, tenses, pronunciation, sentence structure,
  speaking, writing, translation, and communication.
- Adapt teaching to the user's level and learning goal.

2. AI Assistant
- Help with everyday questions, explanations, writing, translations,
  communication, planning, general knowledge, and study.

Be friendly, patient, respectful, calm, natural, encouraging, and clear.

Avoid robotic language, unnecessary introductions, repeated questions,
excessive emojis, unnecessary explanations, fake emotions, and overly
formal textbook language.

LANGUAGE HANDLING:
- Match the user's current language when possible.
- Bangla -> normally reply in Bangla.
- English -> normally reply in English.
- Hindi -> normally reply in Hindi.
- Arabic -> normally reply in Arabic.
- Persian -> normally reply in Persian.
- Mixed language -> respond naturally.
- When teaching English, explain in the user's comfortable language when
  helpful and use English for examples and practice.

INTENT:
Understand the user's current request before answering.

Possible intents:
- Vocabulary, Translation, Grammar, Tenses, Pronunciation
- Speaking, Writing, Sentence correction, Reply/message writing
- General questions, Study help, Practice, Conversation

ADAPTIVE LEVEL:
Beginner: simple words, short explanations, clear examples
Intermediate: deeper explanations, natural usage
Advanced: nuance, register, collocations, exceptions

VOCABULARY:
- Meaning, Pronunciation, Part of speech, One simple example
- Add synonyms/antonyms only when useful

LANGUAGE ACCURACY:
- Give accurate meanings, pronunciation, grammar labels, examples
- Do not invent dictionary meanings
- For Arabic, use accurate standard Arabic
- Do not give an antonym unless genuine

TRANSLATION:
- Preserve meaning, natural over word-for-word
- Keep original tone

GRAMMAR:
Rule -> Simple explanation -> Example -> Common mistake -> Correct version

TENSES:
Usage, structure, examples, signal words, common mistakes

PRONUNCIATION:
Accurate pronunciation, IPA when useful, stress/syllables

SENTENCE CORRECTION:
Correct genuine problems, preserve meaning, if correct say so

SPEAKING:
Natural conversations, useful follow-ups, correct important mistakes only

WRITING:
Follow requested length, tone, format, audience, purpose

MESSAGE / REPLY WRITING:
Understand original message, match tone, give natural replies

GENERAL ASSISTANT:
Help with general knowledge, science, history, geography, technology,
mathematics, study planning, writing, communication, productivity

ACCURACY:
Never invent facts, dates, quotations, meanings, or grammar rules

RESPONSE LENGTH:
Concise by default. Complex -> structured. Detailed requested -> provide more.

NATURAL COMMUNICATION:
Avoid "Certainly!", "Of course!", "Here is a comprehensive answer..."
Do not pretend to have real-world experiences.

CONTEXT:
Use recent conversation context. Switch topics naturally.

CLARIFICATION:
Ask only one short clarification when genuinely necessary.

PRIVACY:
Never ask for passwords, OTPs, private keys, banking/payment credentials.

SAFETY:
Do not facilitate serious violence, illegal wrongdoing, hacking, fraud,
sexual exploitation, dangerous activities, or other harmful conduct.

TELEGRAM:
Bot code controls commands, buttons, menus, callbacks.
Do not claim a command exists unless implemented.

MAIN GOAL:
Make learning easier, communication more natural, everyday tasks simpler.

Be smart. Be natural. Be accurate. Be concise. Be patient. Be useful.
Focus on what the user is asking NOW.
"""


# ==========================================================
# AI FUNCTION
# ==========================================================

def ask_groq(user_text, history=None):
    try:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-6:])
        messages.append({"role": "user", "content": user_text})

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=900,
        )
        text = response.choices[0].message.content.strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return None


# ==========================================================
# DATABASE (PostgreSQL + in-memory fallback)
# ==========================================================

db_pool = None
_mem_users = {}
_mem_history = {}


async def init_db():
    global db_pool
    if not DATABASE_URL or not HAS_ASYNCPG:
        logger.warning("DB disabled — using in-memory only.")
        db_pool = None
        return

    try:
        url = DATABASE_URL
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        db_pool = await asyncpg.create_pool(url, min_size=1, max_size=5)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_users (
                    user_id BIGINT PRIMARY KEY,
                    name VARCHAR(120),
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
                    achievements TEXT DEFAULT '',
                    remind_at VARCHAR(5),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS s_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role VARCHAR(20),
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_sh_user ON s_history(user_id);
                CREATE TABLE IF NOT EXISTS s_mistakes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    wrong_text TEXT,
                    corrected_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS s_broadcast (
                    id SERIAL PRIMARY KEY,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("✅ Database initialized.")
    except Exception as e:
        logger.error(f"DB init failed: {e}. In-memory mode.")
        db_pool = None


async def close_db():
    if db_pool:
        try:
            await db_pool.close()
        except Exception:
            pass


async def get_user(uid):
    if db_pool is None:
        return _mem_users.get(uid)
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM s_users WHERE user_id = $1", uid)
            return dict(row) if row else None
    except Exception:
        return _mem_users.get(uid)


async def create_user(uid, name):
    if db_pool is None:
        if uid not in _mem_users:
            _mem_users[uid] = {
                "user_id": uid, "name": name, "language": "bn",
                "level": "beginner", "coins": 0, "streak": 0,
                "last_practice": None, "words_learned": 0,
                "quizzes_taken": 0, "quiz_score": 0,
                "is_premium": False, "premium_until": None,
                "referred_by": None, "achievements": "",
                "remind_at": None,
            }
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_users (user_id, name) VALUES ($1, $2) "
                "ON CONFLICT (user_id) DO NOTHING", uid, name,
            )
    except Exception as e:
        logger.error(f"create_user: {e}")


async def update_user(uid, **kwargs):
    if db_pool is None:
        if uid in _mem_users:
            _mem_users[uid].update(kwargs)
        return
    if not kwargs:
        return
    try:
        cols = list(kwargs.keys())
        vals = list(kwargs.values())
        sets = ", ".join([f"{c} = ${i+2}" for i, c in enumerate(cols)])
        async with db_pool.acquire() as conn:
            await conn.execute(
                f"UPDATE s_users SET {sets} WHERE user_id = $1", uid, *vals,
            )
    except Exception as e:
        logger.error(f"update_user: {e}")


async def add_coins(uid, amount):
    if db_pool is None:
        if uid in _mem_users:
            _mem_users[uid]["coins"] = _mem_users[uid].get("coins", 0) + amount
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE s_users SET coins = coins + $1 WHERE user_id = $2",
                amount, uid,
            )
    except Exception:
        pass


async def save_history(uid, role, content):
    if db_pool is None:
        h = _mem_history.setdefault(uid, [])
        h.append({"role": role, "content": content})
        _mem_history[uid] = h[-20:]
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_history (user_id, role, content) VALUES ($1,$2,$3)",
                uid, role, content,
            )
    except Exception:
        pass


async def get_history(uid):
    if db_pool is None:
        return _mem_history.get(uid, [])
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content FROM s_history WHERE user_id=$1 "
                "ORDER BY id DESC LIMIT 12", uid,
            )
            return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    except Exception:
        return []


async def clear_history(uid):
    if db_pool is None:
        _mem_history[uid] = []
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM s_history WHERE user_id=$1", uid)
    except Exception:
        pass


async def save_mistake(uid, wrong, corrected):
    if db_pool is None:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_mistakes (user_id, wrong_text, corrected_text) VALUES ($1,$2,$3)",
                uid, wrong, corrected,
            )
    except Exception:
        pass


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
        [InlineKeyboardButton("🎓 Learn", callback_data="student_learn"),
         InlineKeyboardButton("📚 Vocabulary", callback_data="student_vocab")],
        [InlineKeyboardButton("📝 Grammar", callback_data="student_grammar"),
         InlineKeyboardButton("⏱ Tenses", callback_data="student_tenses")],
        [InlineKeyboardButton("🗣 Speaking", callback_data="student_speaking"),
         InlineKeyboardButton("✍️ Writing", callback_data="student_writing")],
        [InlineKeyboardButton("🎯 Quiz", callback_data="m_quiz"),
         InlineKeyboardButton("💬 Translate", callback_data="m_translate")],
        [InlineKeyboardButton("🔥 Daily Lesson", callback_data="m_daily"),
         InlineKeyboardButton("📖 Word of Day", callback_data="m_word")],
        [InlineKeyboardButton("📊 My Progress", callback_data="m_profile"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="m_leaderboard")],
        [InlineKeyboardButton("🎁 Invite & Earn", callback_data="m_invite"),
         InlineKeyboardButton("⭐ Premium", callback_data="m_premium")],
        [InlineKeyboardButton("📚 My Mistakes", callback_data="m_mistakes"),
         InlineKeyboardButton("🏅 Achievements", callback_data="m_achievements")],
        [InlineKeyboardButton("🔔 Reminder", callback_data="m_reminder"),
         InlineKeyboardButton("ℹ️ Help", callback_data="m_help")],
    ])


def back_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")]
    ])


# ==========================================================
# STREAK
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
        await check_achievements(user_id)
        return new_streak
    await update_user(user_id, streak=1, last_practice=today)
    return 1


# ==========================================================
# ACHIEVEMENTS
# ==========================================================

async def check_achievements(uid):
    user = await get_user(uid)
    if not user:
        return None
    earned = set(filter(None, (user.get("achievements") or "").split(",")))
    new_ones = []

    checks = {
        "first_chat": lambda u: True,
        "words_10": lambda u: (u.get("words_learned") or 0) >= 10,
        "words_50": lambda u: (u.get("words_learned") or 0) >= 50,
        "quiz_10": lambda u: (u.get("quizzes_taken") or 0) >= 10,
        "streak_7": lambda u: (u.get("streak") or 0) >= 7,
        "streak_30": lambda u: (u.get("streak") or 0) >= 30,
        "premium": lambda u: u.get("is_premium"),
        "referrer": lambda u: u.get("referred_by") is not None,
    }
    for key, fn in checks.items():
        if key not in earned:
            try:
                if fn(user):
                    earned.add(key)
                    new_ones.append(key)
            except Exception:
                pass

    if new_ones:
        await update_user(uid, achievements=",".join(earned))
    return new_ones


def achievements_text(user):
    earned = set(filter(None, (user.get("achievements") or "").split(",")))
    lines = []
    for k, (emoji, title) in ACHIEVEMENTS.items():
        mark = "✅" if k in earned else "🔒"
        lines.append(f"{mark} {emoji} {title}")
    return "\n".join(lines)


# ==========================================================
# SAFE REPLY
# ==========================================================

async def safe_reply(message, text):
    if not text:
        text = "⚠️ উত্তর তৈরি করা যায়নি। আবার চেষ্টা করুন।"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await message.reply_text(text, parse_mode="Markdown")
    except Exception:
        try:
            await message.reply_text(text)
        except Exception as e:
            logger.error(f"reply failed: {e}")


async def safe_edit(query, text, reply_markup=None):
    if not text:
        text = "⚠️ কিছু পাওয়া যায়নি।"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception:
        try:
            await query.edit_message_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"edit failed: {e}")


# ==========================================================
# /start
# ==========================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.is_bot:
        return
    await create_user(u.id, u.full_name or "Student")

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

    await safe_reply(
        update.message,
        f"👋 স্বাগতম {u.first_name}!\n\n"
        f"🎓 আমি EduMate AI — আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n"
        f"📖 যা করতে পারি:\n"
        f"• 📚 Vocabulary শেখানো\n"
        f"• 📝 Grammar ব্যাখ্যা\n"
        f"• 🎯 Quiz ও Leaderboard\n"
        f"• 💬 বাংলা ↔ ইংরেজি অনুবাদ\n"
        f"• ✍️ Writing Help\n"
        f"• 🗣 Speaking Practice\n"
        f"• 🔥 Daily Lesson + Streak\n"
        f"• 🎁 Invite & Earn Coins\n"
        f"• 🏅 Achievements\n\n"
        f"👉 নিচের বাটন থেকে বেছে নিন।"
    )
    await update.message.reply_text("🏠 মেইন মেনু:", reply_markup=main_menu_kb())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🏠 মেইন মেনু:", reply_markup=main_menu_kb())


# ==========================================================
# OTHER COMMANDS
# ==========================================================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update.message,
        "📖 সাহায্য\n\n"
        "/start — মেইন মেনু\n"
        "/menu — মেনু\n"
        "/profile — প্রোফাইল\n"
        "/daily — আজকের পাঠ\n"
        "/leaderboard — লিডারবোর্ড\n"
        "/coins — কয়েন ব্যালেন্স\n"
        "/invite — ইনভাইট লিংক\n"
        "/mistakes — আপনার ভুল\n"
        "/achievements — অ্যাচিভমেন্ট\n"
        "/level — লেভেল সেট\n"
        "/reminder — রিমাইন্ডার সেট\n"
        "/reset — চ্যাট ক্লিয়ার\n"
        "/adminstats — অ্যাডমিন"
    )


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("❌ আগে /start দিন।")
        return
    await safe_reply(
        update.message,
        f"👤 আপনার প্রোফাইল\n\n"
        f"📛 নাম: {user.get('name')}\n"
        f"🎓 লেভেল: {user.get('level')}\n"
        f"🪙 কয়েন: {user.get('coins') or 0}\n"
        f"🔥 Streak: {user.get('streak') or 0} দিন\n"
        f"📚 শেখা শব্দ: {user.get('words_learned') or 0}\n"
        f"🎯 কুইজ: {user.get('quizzes_taken') or 0} টি\n"
        f"⭐ স্কোর: {user.get('quiz_score') or 0}\n"
        f"💎 Premium: {'✅ Active' if user.get('is_premium') else '❌ Inactive'}\n"
        f"🎁 ইনভাইট: {'হ্যাঁ' if user.get('referred_by') else 'না'}"
    )


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    await update.message.chat.send_action("typing")
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word (Bangla meaning + pronunciation + example), "
        "1 grammar tip with 2 examples, 1 practice question. Short and clear."
    )
    if not answer:
        answer = ("📚 আজকের পাঠ\n\n"
                  "🔤 শব্দ: Persistent\n📖 অর্থ: অধ্যবসায়ী\n"
                  "✏️ উদাহরণ: Be persistent in your efforts.\n\n"
                  "📝 Grammar: Present Continuous — 'I am reading' (এখন চলছে)\n\n"
                  "❓ প্র্যাকটিস: 'She ___ (study) now.' সঠিক রূপ লিখুন।")
    await safe_reply(
        update.message,
        f"🔥 Daily Lesson (Streak: {streak} দিন)\n🎁 +{bonus} কয়েন\n\n{answer}"
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if db_pool is None:
        rows = sorted(_mem_users.values(),
                     key=lambda x: (x.get("quiz_score", 0), x.get("words_learned", 0)),
                     reverse=True)[:10]
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT name, quiz_score, words_learned, streak FROM s_users "
                    "ORDER BY quiz_score DESC, words_learned DESC LIMIT 10"
                )
        except Exception:
            rows = []
    if not rows:
        await update.message.reply_text("এখনো কোনো ইউজার নেই।")
        return
    text = "🏆 টপ ১০ লিডারবোর্ড\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        name = r["name"] if isinstance(r, dict) else r.get("name", "?")
        score = r["quiz_score"] if isinstance(r, dict) else r.get("quiz_score", 0)
        words = r["words_learned"] if isinstance(r, dict) else r.get("words_learned", 0)
        text += f"{m} {name} — ⭐ {score} | 📚 {words}\n"
    await safe_reply(update.message, text)


async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await get_user(update.effective_user.id)
    if not user:
        await update.message.reply_text("❌ আগে /start দিন।")
        return
    await safe_reply(
        update.message,
        f"🪙 আপনার কয়েন: {user.get('coins') or 0}\n"
        f"💎 Premium: {'✅' if user.get('is_premium') else '❌'}\n\n"
        f"🎁 ইনভাইট করে কয়েন আর্ন করুন: /invite"
    )


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_reply(
        update.message,
        f"🎁 ইনভাইট লিংক:\n\n{link}\n\n"
        f"💡 প্রতি ইনভাইটে {REFERRAL_REWARD} কয়েন পাবেন!"
    )


async def mistakes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if db_pool is None:
        await update.message.reply_text("💾 ডেটাবেজ নেই, ভুল সেভ হয় না।")
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT wrong_text, corrected_text FROM s_mistakes "
                "WHERE user_id=$1 ORDER BY id DESC LIMIT 10", uid
            )
    except Exception:
        rows = []
    if not rows:
        await update.message.reply_text("✅ আপনার কোনো ভুল নেই!")
        return
    text = "📚 আপনার সাম্প্রতিক ভুল\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. ❌ {r['wrong_text'][:80]}\n   ✅ {r['corrected_text'][:80]}\n\n"
    await safe_reply(update.message, text[:4000])


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text("❌ আগে /start দিন।")
        return
    await safe_reply(
        update.message,
        f"🏅 Achievements\n\n{achievements_text(user)}"
    )


async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎓 আপনার লেভেল সেট করুন:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Beginner", callback_data="setlvl_beginner")],
            [InlineKeyboardButton("🟡 Intermediate", callback_data="setlvl_intermediate")],
            [InlineKeyboardButton("🔴 Advanced", callback_data="setlvl_advanced")],
        ]),
    )


async def reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔔 কখন রিমাইন্ডার পেতে চান?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 সকাল ৮টা", callback_data="rem_08:00")],
            [InlineKeyboardButton("☀️ দুপুর ১২টা", callback_data="rem_12:00")],
            [InlineKeyboardButton("🌆 সন্ধ্যা ৬টা", callback_data="rem_18:00")],
            [InlineKeyboardButton("🌙 রাত ৯টা", callback_data="rem_21:00")],
            [InlineKeyboardButton("❌ বন্ধ করুন", callback_data="rem_off")],
        ]),
    )


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await clear_history(update.effective_user.id)
    await update.message.reply_text("🔄 চ্যাট ক্লিয়ার। /start দিন।")


async def adminstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ অ্যাডমিন নন।")
        return
    if db_pool is None:
        await update.message.reply_text(
            f"📊 Admin Stats\n\n👥 ইউজার: {len(_mem_users)}\n💾 Mode: In-Memory"
        )
        return
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM s_users")
            today = await conn.fetchval(
                "SELECT COUNT(*) FROM s_users WHERE last_active > NOW() - INTERVAL '24 hours'"
            )
            week = await conn.fetchval(
                "SELECT COUNT(*) FROM s_users WHERE last_active > NOW() - INTERVAL '7 days'"
            )
            premium = await conn.fetchval(
                "SELECT COUNT(*) FROM s_users WHERE is_premium = TRUE"
            )
            total_coins = await conn.fetchval("SELECT COALESCE(SUM(coins),0) FROM s_users")
            total_msgs = await conn.fetchval("SELECT COUNT(*) FROM s_history")
        await safe_reply(
            update.message,
            f"📊 Admin Dashboard\n\n"
            f"👥 মোট ইউজার: {total}\n"
            f"🟢 ২৪ ঘণ্টায় সক্রিয়: {today}\n"
            f"📅 ৭ দিনে: {week}\n"
            f"💎 Premium: {premium}\n"
            f"🪙 মোট কয়েন: {total_coins}\n"
            f"💬 মোট মেসেজ: {total_msgs}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ DB error: {e}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ অ্যাডমিন নন।")
        return
    if not context.args:
        await update.message.reply_text("ব্যবহার: /broadcast আপনার মেসেজ")
        return
    msg = " ".join(context.args)
    if db_pool is None:
        uids = list(_mem_users.keys())
    else:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT user_id FROM s_users")
            uids = [r["user_id"] for r in rows]
    sent, failed = 0, 0
    for u_id in uids:
        try:
            await context.bot.send_message(u_id, f"📢 {msg}")
            sent += 1
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ পাঠানো: {sent}, ❌ ব্যর্থ: {failed}")


# ==========================================================
# STUDENT PROMPTS (original)
# ==========================================================

STUDENT_PROMPTS = {
    "student_learn": (
        "Start a short English lesson for a beginner or intermediate "
        "student. Choose one useful topic. Explain it simply, give "
        "one or two examples, then give ONE short practice question. "
        "Do not give the answer immediately. Plain text, no Markdown."
    ),
    "student_vocab": (
        "Teach ONE useful English word. Give its meaning, pronunciation, "
        "part of speech, and one simple example. Then give ONE short "
        "practice question. Do NOT show the answer. Plain text."
    ),
    "student_grammar": (
        "Teach ONE useful English grammar point. Explain its use and "
        "structure simply, give examples, mention one common mistake, "
        "then give ONE short practice question. Do NOT show the answer. Plain text."
    ),
    "student_tenses": (
        "Start a short English tense lesson. Choose ONE useful tense. "
        "Explain its use and structure simply, give examples, mention "
        "one common mistake if useful, then give ONE short practice "
        "question. Plain text."
    ),
    "student_writing": (
        "Start English writing practice. Give the student ONE short "
        "writing task suitable for their level and wait for their answer. "
        "After they answer, correct important mistakes briefly. Plain text."
    ),
}


SPEAKING_QUESTIONS = [
    "What did you have for breakfast today?",
    "What do you usually do in your free time?",
    "What is your favorite food, and why?",
    "What did you do yesterday?",
    "What kind of music do you enjoy?",
    "What is one place you would love to visit?",
    "What do you usually do on weekends?",
    "Who is someone you really respect, and why?",
    "What is something new you learned recently?",
    "What makes you happy on a normal day?",
    "What is your favorite movie or TV show?",
    "What would you like to improve about your English?",
]


# ==========================================================
# CALLBACK: STUDENT MENU (original)
# ==========================================================

async def student_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()

    uid = q.from_user.id
    await update_user(uid, last_active=datetime.now())

    data = q.data

    if data == "student_speaking":
        last_q = context.user_data.get("last_speaking_question")
        avail = [x for x in SPEAKING_QUESTIONS if x != last_q]
        question = random.choice(avail)
        context.user_data["last_speaking_question"] = question
        prompt = (
            "Start English speaking practice.\n\n"
            f"Ask the student this exact question:\n\n{question}\n\n"
            "Wait for the student's answer. Keep it natural."
        )
    else:
        prompt = STUDENT_PROMPTS.get(data)

    if not prompt:
        return

    await safe_edit(q, "⏳ তৈরি হচ্ছে...")

    answer = await asyncio.to_thread(ask_groq, prompt)

    if not answer:
        answer = "⚠️ AI সমস্যা। আবার চেষ্টা করুন।"

    if data == "student_vocab":
        user = await get_user(uid)
        words = (user.get("words_learned") or 0) + 1 if user else 1
        await update_user(uid, words_learned=words)
        new = await check_achievements(uid)
        if new:
            await q.message.reply_text(
                "🎉 নতুন অ্যাচিভমেন্ট!\n" +
                "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1]}" for k in new)
            )

    await safe_edit(q, answer, reply_markup=back_kb())


# ==========================================================
# CALLBACKS — Main Menu Items
# ==========================================================

async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("🏠 মেইন মেনু:", reply_markup=main_menu_kb())


async def cb_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    if not user:
        await safe_edit(q, "❌ আগে /start দিন।")
        return
    await safe_edit(
        q,
        f"👤 আপনার প্রোফাইল\n\n"
        f"📛 নাম: {user.get('name')}\n"
        f"🎓 লেভেল: {user.get('level')}\n"
        f"🪙 কয়েন: {user.get('coins') or 0}\n"
        f"🔥 Streak: {user.get('streak') or 0} দিন\n"
        f"📚 শেখা শব্দ: {user.get('words_learned') or 0}\n"
        f"🎯 কুইজ: {user.get('quizzes_taken') or 0} টি\n"
        f"⭐ স্কোর: {user.get('quiz_score') or 0}\n"
        f"💎 Premium: {'✅' if user.get('is_premium') else '❌'}",
        reply_markup=back_kb(),
    )


async def cb_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    await q.edit_message_text("🔥 Daily Lesson তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word (Bangla meaning + pronunciation + example), "
        "1 grammar tip with 2 examples, 1 practice question. Plain text."
    )
    if not answer:
        answer = ("📚 আজকের পাঠ:\n\n"
                  "🔤 শব্দ: Diligent\n📖 অর্থ: পরিশ্রমী\n"
                  "✏️ উদাহরণ: She is a diligent student.\n\n"
                  "📝 Grammar: Present Continuous — 'I am reading'\n\n"
                  "❓ প্র্যাকটিস: 'She ___ (study) now.' সঠিক রূপ লিখুন।")
    await safe_edit(
        q,
        f"🔥 Daily Lesson (Streak: {streak} দিন)\n🎁 +{bonus} কয়েন\n\n{answer}",
        reply_markup=back_kb(),
    )


async def cb_word_of_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.edit_message_text("📖 শব্দ তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Give ONE advanced English word of the day. Include: word, Bangla meaning, "
        "pronunciation, part of speech, 2 example sentences, 2 synonyms. Plain text."
    )
    if not answer:
        answer = ("📖 Word of the Day\n\n"
                  "🔤 Word: Resilient\n📖 অর্থ: স্থিতিস্থাপক\n"
                  "🔊 /rɪˈzɪliənt/\n✏️ Example: Children are resilient.\n"
                  "🔁 Synonyms: Strong, Tough")
    await safe_edit(q, f"📖 Word of the Day\n\n{answer}", reply_markup=back_kb())


async def cb_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = await get_user(uid)
    quizzes = (user.get("quizzes_taken") or 0) + 1 if user else 1
    await update_user(uid, quizzes_taken=quizzes)
    await q.edit_message_text("🎯 কুইজ তৈরি হচ্ছে...")
    answer = await asyncio.to_thread(
        ask_groq,
        "Create ONE English multiple-choice quiz with 4 options. "
        "Format exactly:\nQuestion: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: X) ...\n"
        "Keep it short. Plain text."
    )
    if not answer:
        answer = ("🎯 Quiz\n\nQuestion: Past tense of 'go'?\n"
                  "A) goed\nB) went\nC) gone\nD) going\nAnswer: B) went")
    await safe_edit(
        q,
        f"🎯 Quiz\n\n{answer}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎯 আরেকটি কুইজ", callback_data="m_quiz")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")],
        ]),
    )


async def cb_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await safe_edit(
        q,
        "💬 Translation\n\n"
        "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান — আমি অনুবাদ করে দেব।\n\n"
        "উদাহরণ:\n"
        "• আমি ভাত খাই → I eat rice.\n"
        "• I love my family → আমি আমার পরিবারকে ভালোবাসি।",
        reply_markup=back_kb(),
    )


async def cb_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_edit(
        q,
        f"🎁 Invite & Earn\n\nআপনার ইনভাইট লিংক:\n{link}\n\n"
        f"💡 প্রতি ইনভাইটে {REFERRAL_REWARD} কয়েন পাবেন!",
        reply_markup=back_kb(),
    )


async def cb_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    if user and user.get("is_premium"):
        await safe_edit(q, "💎 আপনি ইতিমধ্যে Premium!", reply_markup=back_kb())
        return
    await safe_edit(
        q,
        f"💎 Premium Membership\n\n"
        f"⭐ {PREMIUM_STARS} Stars দিয়ে {PREMIUM_DAYS} দিনের Premium\n\n"
        f"🎁 সুবিধা:\n• আনলিমিটেড AI উত্তর\n• Detailed Lessons\n• Priority Response",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ কিনুন ({PREMIUM_STARS} Stars)",
                                  callback_data="buy_premium")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="m_menu")],
        ]),
    )


async def cb_buy_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title="💎 EduMate Premium",
            description=f"{PREMIUM_DAYS} days Premium access",
            payload=f"premium_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS)],
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await q.answer("❌ Payment failed.", show_alert=True)


async def precheckout_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    until = datetime.now() + timedelta(days=PREMIUM_DAYS)
    await update_user(uid, is_premium=True, premium_until=until)
    await update.message.reply_text(
        f"🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n✅ {PREMIUM_DAYS} দিনের জন্য সক্রিয়।"
    )
    new = await check_achievements(uid)
    if new:
        await update.message.reply_text(
            "🎉 নতুন অ্যাচিভমেন্ট!\n" +
            "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1]}" for k in new)
        )


async def cb_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if db_pool is None:
        rows = sorted(_mem_users.values(),
                     key=lambda x: (x.get("quiz_score", 0), x.get("words_learned", 0)),
                     reverse=True)[:10]
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT name, quiz_score, words_learned, streak FROM s_users "
                    "ORDER BY quiz_score DESC, words_learned DESC LIMIT 10"
                )
        except Exception:
            rows = []
    if not rows:
        await safe_edit(q, "এখনো কোনো ইউজার নেই।", reply_markup=back_kb())
        return
    text = "🏆 টপ ১০ লিডারবোর্ড\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        name = r["name"] if isinstance(r, dict) else r.get("name", "?")
        score = r["quiz_score"] if isinstance(r, dict) else r.get("quiz_score", 0)
        text += f"{m} {name} — ⭐ {score}\n"
    await safe_edit(q, text, reply_markup=back_kb())


async def cb_mistakes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if db_pool is None:
        await safe_edit(q, "💾 ডেটাবেজ নেই।", reply_markup=back_kb())
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT wrong_text, corrected_text FROM s_mistakes "
                "WHERE user_id=$1 ORDER BY id DESC LIMIT 8", uid
            )
    except Exception:
        rows = []
    if not rows:
        await safe_edit(q, "✅ কোনো ভুল নেই!", reply_markup=back_kb())
        return
    text = "📚 সাম্প্রতিক ভুল\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. ❌ {r['wrong_text'][:80]}\n   ✅ {r['corrected_text'][:80]}\n\n"
    await safe_edit(q, text[:4000], reply_markup=back_kb())


async def cb_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user = await get_user(q.from_user.id)
    if not user:
        await safe_edit(q, "❌ আগে /start দিন।", reply_markup=back_kb())
        return
    await safe_edit(q, f"🏅 Achievements\n\n{achievements_text(user)}", reply_markup=back_kb())


async def cb_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await safe_edit(
        q,
        "🔔 কখন রিমাইন্ডার পেতে চান?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 সকাল ৮টা", callback_data="rem_08:00")],
            [InlineKeyboardButton("☀️ দুপুর ১২টা", callback_data="rem_12:00")],
            [InlineKeyboardButton("🌆 সন্ধ্যা ৬টা", callback_data="rem_18:00")],
            [InlineKeyboardButton("🌙 রাত ৯টা", callback_data="rem_21:00")],
            [InlineKeyboardButton("❌ বন্ধ করুন", callback_data="rem_off")],
        ]),
    )


async def cb_reminder_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    val = q.data.replace("rem_", "")
    if val == "off":
        await update_user(uid, remind_at=None)
        await safe_edit(q, "🔕 রিমাইন্ডার বন্ধ।", reply_markup=back_kb())
    else:
        await update_user(uid, remind_at=val)
        await safe_edit(q, f"🔔 রিমাইন্ডার সেট: {val}", reply_markup=back_kb())


async def cb_set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lvl = q.data.replace("setlvl_", "")
    await update_user(uid, level=lvl)
    await safe_edit(q, f"✅ লেভেল সেট: {lvl}", reply_markup=back_kb())


async def cb_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await safe_edit(
        q,
        "ℹ️ সাহায্য\n\n"
        "🎓 বাটন:\n"
        "🎓 Learn — লেসন\n"
        "📚 Vocabulary — শব্দ\n"
        "📝 Grammar — গ্রামার\n"
        "⏱ Tenses — টেন্স\n"
        "🗣 Speaking — স্পিকিং\n"
        "✍️ Writing — রাইটিং\n"
        "🎯 Quiz — কুইজ\n"
        "💬 Translate — অনুবাদ\n"
        "🔥 Daily Lesson — ডেইলি বোনাস\n"
        "📖 Word of Day — শব্দ\n"
        "📊 My Progress — প্রোগ্রেস\n"
        "🏆 Leaderboard — লিডারবোর্ড\n"
        "🎁 Invite — কয়েন\n"
        "⭐ Premium — প্রিমিয়াম\n"
        "🏅 Achievements — ব্যাজ\n"
        "🔔 Reminder — রিমাইন্ডার\n\n"
        "📝 যেকোনো বাক্য লিখে পাঠান — AI উত্তর দেবে।",
        reply_markup=back_kb(),
    )


# ==========================================================
# TEXT MESSAGE HANDLER (original + mistake log + streak)
# ==========================================================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return
    chat = update.effective_chat
    if not chat:
        return

    uid = update.effective_user.id
    await create_user(uid, update.effective_user.full_name or "Student")

    if chat.type == "private":
        user_text = message.text.strip()
        if not user_text:
            return
    else:
        bot_username = context.bot.username
        if not bot_username:
            return
        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id == context.bot.id
        )
        mention = f"@{bot_username.lower()}"
        if mention not in message.text.lower() and not is_reply_to_bot:
            return
        user_text = message.text.replace(f"@{bot_username}", "").strip()
        if not user_text:
            user_text = "Please help me with English."

    await update_user(uid, last_active=datetime.now())
    await check_streak(uid)
    await save_history(uid, "user", user_text)
    history = await get_history(uid)

    try:
        await message.chat.send_action("typing")
    except Exception:
        pass

    answer = await asyncio.to_thread(ask_groq, user_text, history)

    if not answer:
        answer = "⚠️ এখন AI-তে সমস্যা হচ্ছে। আবার চেষ্টা করুন।"

    await save_history(uid, "assistant", answer)
    await safe_reply(message, answer)

    # Achievement check
    new = await check_achievements(uid)
    if new:
        await message.reply_text(
            "🎉 নতুন অ্যাচিভমেন্ট!\n" +
            "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1]}" for k in new)
        )


# ==========================================================
# DAILY AUTO LESSON (job)
# ==========================================================

async def daily_auto_lesson(context: ContextTypes.DEFAULT_TYPE):
    """প্রতিদিন সব ইউজারকে অটো লেসন পাঠাবে।"""
    logger.info("📅 Sending daily auto lesson...")
    if db_pool is None:
        uids = list(_mem_users.keys())
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM s_users")
                uids = [r["user_id"] for r in rows]
        except Exception:
            uids = []

    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's daily English lesson: 1 new word with Bangla meaning and example, "
        "1 grammar tip, 1 practice question. Plain text, short."
    )
    if not answer:
        answer = ("📚 আজকের পাঠ:\n\n"
                  "🔤 Word: Consistent\n📖 অর্থ: ধারাবাহিক\n"
                  "✏️ Example: She is a consistent learner.\n\n"
                  "❓ What is the past tense of 'eat'?")

    text = f"🌅 শুভ সকাল!\n\n🔥 আজকের Daily Lesson:\n\n{answer}"
    for u_id in uids[:500]:
        try:
            await context.bot.send_message(u_id, text)
            await asyncio.sleep(0.05)
        except Exception:
            pass
    logger.info(f"✅ Daily lesson sent to {len(uids)} users.")


async def daily_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """যে ইউজার reminder সেট করেছে, তাদের পাঠাবে।"""
    now_hm = datetime.now().strftime("%H:%M")
    if db_pool is None:
        users = [u for u in _mem_users.values() if u.get("remind_at") == now_hm]
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT user_id FROM s_users WHERE remind_at = $1", now_hm
                )
                users = [{"user_id": r["user_id"]} for r in rows]
        except Exception:
            users = []

    for u in users:
        try:
            await context.bot.send_message(
                u["user_id"],
                "🔔 সময় হয়েছে! আজকের পড়াশোনা শুরু করুন। /daily দিয়ে লেসন নিন।",
            )
        except Exception:
            pass


# ==========================================================
# BOT SETUP
# ==========================================================

async def post_init(app):
    await init_db()
    # Schedule daily lesson at 08:00 server time
    app.job_queue.run_daily(daily_auto_lesson, time=datetime.strptime("08:00", "%H:%M").time())
    # Check reminders every minute
    app.job_queue.run_repeating(daily_reminder_job, interval=60, first=10)
    logger.info("⏰ Job queue scheduled.")


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
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("menu", menu_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("profile", profile_command))
        application.add_handler(CommandHandler("daily", daily_command))
        application.add_handler(CommandHandler("leaderboard", leaderboard_command))
        application.add_handler(CommandHandler("coins", coins_command))
        application.add_handler(CommandHandler("invite", invite_command))
        application.add_handler(CommandHandler("mistakes", mistakes_command))
        application.add_handler(CommandHandler("achievements", achievements_command))
        application.add_handler(CommandHandler("level", level_command))
        application.add_handler(CommandHandler("reminder", reminder_command))
        application.add_handler(CommandHandler("reset", reset_command))
        application.add_handler(CommandHandler("adminstats", adminstats_command))
        application.add_handler(CommandHandler("broadcast", broadcast_command))
        application.add_handler(CommandHandler("vocab", lambda u, c: student_menu_callback(
            type("X", (), {"callback_query": type("Y", (), {
                "data": "student_vocab", "answer": lambda: None,
                "from_user": u.effective_user, "edit_message_text": u.message.reply_text,
                "message": u.message,
            })()})(), c)))

        # All callback handlers (specific first, then catch-all)
        application.add_handler(CallbackQueryHandler(cb_menu, pattern="^m_menu$"))
        application.add_handler(CallbackQueryHandler(cb_profile, pattern="^m_profile$"))
        application.add_handler(CallbackQueryHandler(cb_daily, pattern="^m_daily$"))
        application.add_handler(CallbackQueryHandler(cb_word_of_day, pattern="^m_word$"))
        application.add_handler(CallbackQueryHandler(cb_quiz, pattern="^m_quiz$"))
        application.add_handler(CallbackQueryHandler(cb_translate, pattern="^m_translate$"))
        application.add_handler(CallbackQueryHandler(cb_invite, pattern="^m_invite$"))
        application.add_handler(CallbackQueryHandler(cb_premium, pattern="^m_premium$"))
        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_premium$"))
        application.add_handler(CallbackQueryHandler(cb_leaderboard, pattern="^m_leaderboard$"))
        application.add_handler(CallbackQueryHandler(cb_mistakes, pattern="^m_mistakes$"))
        application.add_handler(CallbackQueryHandler(cb_achievements, pattern="^m_achievements$"))
        application.add_handler(CallbackQueryHandler(cb_reminder, pattern="^m_reminder$"))
        application.add_handler(CallbackQueryHandler(cb_reminder_set, pattern="^rem_"))
        application.add_handler(CallbackQueryHandler(cb_set_level, pattern="^setlvl_"))
        application.add_handler(CallbackQueryHandler(cb_help, pattern="^m_help$"))

        # Original student menu
        application.add_handler(CallbackQueryHandler(
            student_menu_callback,
            pattern="^student_"
        ))

        # Payment
        application.add_handler(PreCheckoutQueryHandler(precheckout_cb))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_cb))

        # Text messages
        application.add_handler(MessageHandler(
            filters.TEXT & ~filters.COMMAND, handle_message
        ))

        try:
            await application.initialize()
            await application.bot.delete_webhook(drop_pending_updates=False)
            await application.start()
            await application.updater.start_polling(drop_pending_updates=False)
            logger.info("✅ Bot started successfully.")
            bot_info = await application.bot.get_me()
            logger.info(f"Bot: @{bot_info.username} | Model: {GROQ_MODEL}")
            while True:
                await asyncio.sleep(3600)
        except Conflict:
            logger.error("409 Conflict: another instance running.")
        except TelegramError as e:
            logger.exception(f"Telegram error: {e}")
        except Exception as e:
            logger.exception(f"Unexpected: {e}")
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
    logger.info("Starting EduMate AI...")
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=run_bot, daemon=True).start()
    logger.info("Bot + Flask threads started.")
    while True:
        time.sleep(3600)
