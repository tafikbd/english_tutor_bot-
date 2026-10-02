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
from telegram.error import Conflict, TelegramError, BadRequest
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
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing.")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ==========================================================
# CONSTANTS
# ==========================================================
REFERRAL_REWARD = 10
DAILY_BONUS = 5
STREAK_BONUS = 2
PREMIUM_STARS = 50
PREMIUM_DAYS = 30

ACHIEVEMENTS = {
    "first_chat": ("🥇", {"bn": "প্রথম চ্যাট", "en": "First Chat", "hi": "पहला चैट"}),
    "words_10": ("📚", {"bn": "১০ শব্দ শিখেছেন", "en": "10 words learned", "hi": "10 शब्द सीखे"}),
    "words_50": ("📖", {"bn": "৫০ শব্দ শিখেছেন", "en": "50 words learned", "hi": "50 शब्द सीखे"}),
    "quiz_10": ("🎯", {"bn": "১০ কুইজ দিয়েছেন", "en": "10 quizzes done", "hi": "10 क्विज़ पूरी"}),
    "streak_7": ("🔥", {"bn": "৭ দিনের স্ট্রিক", "en": "7-day streak", "hi": "7 दिन की स्ट्रीक"}),
    "streak_30": ("💪", {"bn": "৩০ দিনের স্ট্রিক", "en": "30-day streak", "hi": "30 दिन की स्ट्रीक"}),
    "premium": ("💎", {"bn": "Premium সদস্য", "en": "Premium member", "hi": "Premium सदस्य"}),
    "referrer": ("🎁", {"bn": "কাউকে ইনভাইট করেছেন", "en": "Invited someone", "hi": "किसी को आमंत्रित किया"}),
}


# ==========================================================
# TRANSLATIONS
# ==========================================================
T = {
    "welcome": {
        "bn": "👋 স্বাগতম {name}!\n\n🎓 আমি EduMate AI — আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n📖 যা করতে পারি:\n• 📚 Vocabulary শেখানো\n• 📝 Grammar ব্যাখ্যা\n• 🎯 Quiz ও Leaderboard\n• 💬 বাংলা ↔ ইংরেজি অনুবাদ\n• ✍️ Writing Help\n• 🗣 Speaking Practice\n• 🔥 Daily Lesson + Streak\n• 🎁 Invite & Earn Coins\n\n👉 নিচের বাটন থেকে বেছে নিন।",
        "en": "👋 Welcome {name}!\n\n🎓 I am EduMate AI — your 24/7 English teacher.\n\n📖 What I can do:\n• 📚 Teach Vocabulary\n• 📝 Explain Grammar\n• 🎯 Quiz & Leaderboard\n• 💬 Bangla ↔ English Translation\n• ✍️ Writing Help\n• 🗣 Speaking Practice\n• 🔥 Daily Lesson + Streak\n• 🎁 Invite & Earn Coins\n\n👉 Choose from the buttons below.",
        "hi": "👋 स्वागत है {name}!\n\n🎓 मैं EduMate AI हूँ — आपका 24/7 English शिक्षक।\n\n📖 मैं क्या कर सकता हूँ:\n• 📚 Vocabulary सिखाना\n• 📝 Grammar समझाना\n• 🎯 Quiz और Leaderboard\n• 💬 Bangla ↔ English अनुवाद\n• ✍️ Writing Help\n• 🗣 Speaking Practice\n• 🔥 Daily Lesson + Streak\n• 🎁 Invite & Earn Coins\n\n👉 नीचे से चुनें।",
    },
    "main_menu": {
        "bn": "🏠 মেইন মেনু:",
        "en": "🏠 Main Menu:",
        "hi": "🏠 मुख्य मेनू:",
    },
    "menu_btn": {
        "bn": "🏠 মেইন মেনু", "en": "🏠 Main Menu", "hi": "🏠 मुख्य मेनू",
    },
    "loading": {
        "bn": "⏳ তৈরি হচ্ছে...", "en": "⏳ Generating...", "hi": "⏳ बना रहा हूँ...",
    },
    "ai_error": {
        "bn": "⚠️ এখন AI-তে সমস্যা হচ্ছে। আবার চেষ্টা করুন।",
        "en": "⚠️ AI is having issues. Please try again.",
        "hi": "⚠️ AI में समस्या है। कृपया पुनः प्रयास करें।",
    },
    "profile_title": {
        "bn": "👤 আপনার প্রোফাইল", "en": "👤 Your Profile", "hi": "👤 आपकी प्रोफ़ाइल",
    },
    "name": {"bn": "📛 নাম", "en": "📛 Name", "hi": "📛 नाम"},
    "level": {"bn": "🎓 লেভেল", "en": "🎓 Level", "hi": "🎓 स्तर"},
    "coins": {"bn": "🪙 কয়েন", "en": "🪙 Coins", "hi": "🪙 सिक्के"},
    "streak": {"bn": "🔥 Streak", "en": "🔥 Streak", "hi": "🔥 स्ट्रीक"},
    "words_learned": {"bn": "📚 শেখা শব্দ", "en": "📚 Words learned", "hi": "📚 सीखे शब्द"},
    "quizzes": {"bn": "🎯 কুইজ", "en": "🎯 Quizzes", "hi": "🎯 क्विज़"},
    "score": {"bn": "⭐ স্কোর", "en": "⭐ Score", "hi": "⭐ स्कोर"},
    "premium_status": {"bn": "💎 Premium", "en": "💎 Premium", "hi": "💎 Premium"},
    "active": {"bn": "✅ সক্রিয়", "en": "✅ Active", "hi": "✅ सक्रिय"},
    "inactive": {"bn": "❌ নিষ্ক্রিয়", "en": "❌ Inactive", "hi": "❌ निष्क्रिय"},
    "help_title": {"bn": "📖 সাহায্য", "en": "📖 Help", "hi": "📖 सहायता"},
    "language_set": {
        "bn": "✅ ভাষা সেট হয়েছে: বাংলা",
        "en": "✅ Language set: English",
        "hi": "✅ भाषा सेट: हिन्दी",
    },
    "choose_lang": {
        "bn": "🌍 ভাষা নির্বাচন করুন:\n\nChoose your language:\n\nअपनी भाषा चुनें:",
        "en": "🌍 Choose your language:\n\nআপনার ভাষা নির্বাচন করুন:\n\nअपनी भाषा चुनें:",
        "hi": "🌍 अपनी भाषा चुनें:\n\nChoose your language:\n\nআপনার ভাষা নির্বাচন করুন:",
    },
    "reset_done": {
        "bn": "🔄 চ্যাট ক্লিয়ার হয়েছে। /start দিন।",
        "en": "🔄 Chat cleared. Send /start.",
        "hi": "🔄 चैट साफ। /start भेजें।",
    },
    "start_first": {
        "bn": "❌ আগে /start দিন।", "en": "❌ Please /start first.", "hi": "❌ पहले /start करें।",
    },
    "daily_title": {"bn": "🔥 Daily Lesson", "en": "🔥 Daily Lesson", "hi": "🔥 Daily Lesson"},
    "bonus_coins": {"bn": "🎁 বোনাস", "en": "🎁 Bonus", "hi": "🎁 बोनस"},
    "days": {"bn": "দিন", "en": "days", "hi": "दिन"},
    "leaderboard_title": {"bn": "🏆 টপ ১০ লিডারবোর্ড", "en": "🏆 Top 10 Leaderboard", "hi": "🏆 टॉप 10 लीडरबोर्ड"},
    "no_users": {"bn": "এখনো কোনো ইউজার নেই।", "en": "No users yet.", "hi": "अभी कोई उपयोगकर्ता नहीं।"},
    "word_title": {"bn": "📖 Word of the Day", "en": "📖 Word of the Day", "hi": "📖 आज का शब्द"},
    "quiz_title": {"bn": "🎯 Quiz", "en": "🎯 Quiz", "hi": "🎯 Quiz"},
    "quiz_more": {"bn": "🎯 আরেকটি কুইজ", "en": "🎯 Another Quiz", "hi": "🎯 एक और Quiz"},
    "translate_title": {"bn": "💬 Translation", "en": "💬 Translation", "hi": "💬 अनुवाद"},
    "translate_hint": {
        "bn": "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান।\n\nউদাহরণ:\n• আমি ভাত খাই → I eat rice.\n• I love my family → আমি আমার পরিবারকে ভালোবাসি।",
        "en": "Send any Bangla or English sentence.\n\nExamples:\n• আমি ভাত খাই → I eat rice.\n• I love my family → আমি আমার পরিবারকে ভালোবাসি।",
        "hi": "कोई भी Bangla या English वाक्य भेजें।\n\nउदाहरण:\n• আমি ভাত খাই → I eat rice.\n• I love my family → আমি আমার পরিবারকে ভালোবাসি।",
    },
    "invite_title": {"bn": "🎁 Invite & Earn", "en": "🎁 Invite & Earn", "hi": "🎁 Invite & Earn"},
    "invite_hint": {"bn": "💡 প্রতি ইনভাইটে {n} কয়েন পাবেন!", "en": "💡 Earn {n} coins per invite!", "hi": "💡 हर invite पर {n} सिक्के!"},
    "premium_title": {"bn": "💎 Premium Membership", "en": "💎 Premium Membership", "hi": "💎 Premium Membership"},
    "premium_buy": {"bn": "⭐ কিনুন ({n} Stars)", "en": "⭐ Buy ({n} Stars)", "hi": "⭐ खरीदें ({n} Stars)"},
    "premium_already": {"bn": "💎 আপনি ইতিমধ্যে Premium!", "en": "💎 You are already Premium!", "hi": "💎 आप पहले से Premium हैं!"},
    "premium_success": {"bn": "🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n✅ {days} দিনের জন্য সক্রিয়।", "en": "🎉 Congratulations! You are now Premium!\n✅ Active for {days} days.", "hi": "🎉 बधाई! आप अब Premium हैं!\n✅ {days} दिनों के लिए सक्रिय।"},
    "achievements_title": {"bn": "🏅 Achievements", "en": "🏅 Achievements", "hi": "🏅 Achievements"},
    "mistakes_title": {"bn": "📚 সাম্প্রতিক ভুল", "en": "📚 Recent Mistakes", "hi": "📚 हाल की गलतियाँ"},
    "mistakes_none": {"bn": "✅ কোনো ভুল নেই!", "en": "✅ No mistakes!", "hi": "✅ कोई गलती नहीं!"},
    "reminder_title": {"bn": "🔔 কখন রিমাইন্ডার পেতে চান?", "en": "🔔 When do you want a reminder?", "hi": "🔔 कब reminder चाहिए?"},
    "reminder_off": {"bn": "🔕 রিমাইন্ডার বন্ধ।", "en": "🔕 Reminder off.", "hi": "🔕 Reminder बंद।"},
    "reminder_set": {"bn": "🔔 রিমাইন্ডার সেট: {t}", "en": "🔔 Reminder set: {t}", "hi": "🔔 Reminder सेट: {t}"},
    "level_set": {"bn": "✅ লেভেল সেট: {lvl}", "en": "✅ Level set: {lvl}", "hi": "✅ स्तर सेट: {lvl}"},
    "choose_level": {"bn": "🎓 আপনার লেভেল সেট করুন:", "en": "🎓 Set your level:", "hi": "🎓 अपना स्तर चुनें:"},
    "new_achievement": {"bn": "🎉 নতুন অ্যাচিভমেন্ট!", "en": "🎉 New Achievement!", "hi": "🎉 नई उपलब्धि!"},
    "referral_bonus": {"bn": "🎁 আপনি {n} কয়েন পেয়েছেন বন্ধু ইনভাইটের জন্য!", "en": "🎁 You earned {n} coins for referring a friend!", "hi": "🎁 दोस्त को invite करने पर {n} सिक्के मिले!"},
}


def t(key, lang="bn", **kwargs):
    entry = T.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get("en") or entry.get("bn") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


# ==========================================================
# GROQ + SYSTEM PROMPT
# ==========================================================
groq_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """
You are EduMate AI, a smart AI Teacher and AI Assistant.

Roles:
1. AI Teacher — Vocabulary, Grammar, Tenses, Pronunciation, Speaking,
   Writing, Sentence Correction, Translation, Communication.
2. AI Assistant — Everyday questions, explanations, planning, general knowledge.

Be friendly, patient, respectful, calm, natural, encouraging, clear.
Avoid robotic phrases, excessive emojis, fake emotions.

LANGUAGE: Match user's language (Bangla→Bangla, English→English, Hindi→Hindi).
When teaching English, explain in user's language with English examples.

STYLE: Concise by default. Complex → structured. No invented facts.
Use plain text. Avoid complex Markdown that might break Telegram.

For corrections:
❌ Wrong: ...
✅ Correct: ...
📝 Why: ...

For vocabulary: word, Bangla meaning, pronunciation, part of speech, example.
For grammar: rule → example → common mistake.

Keep responses under 3500 characters. Focus on what the user asks NOW.
"""


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
# DATABASE
# ==========================================================
db_pool = None
_mem_users = {}
_mem_history = {}


async def init_db():
    global db_pool
    if not DATABASE_URL or not HAS_ASYNCPG:
        logger.warning("DB disabled — in-memory mode.")
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
            await conn.execute(f"UPDATE s_users SET {sets} WHERE user_id = $1", uid, *vals)
    except Exception as e:
        logger.error(f"update_user: {e}")


async def add_coins(uid, amount):
    if db_pool is None:
        if uid in _mem_users:
            _mem_users[uid]["coins"] = _mem_users[uid].get("coins", 0) + amount
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE s_users SET coins = coins + $1 WHERE user_id = $2", amount, uid)
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
                "SELECT role, content FROM s_history WHERE user_id=$1 ORDER BY id DESC LIMIT 12", uid,
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


async def get_user_lang(uid):
    u = await get_user(uid)
    return (u or {}).get("language") or "bn"


# ==========================================================
# FLASK
# ==========================================================
flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "EduMate Bot running."


@flask_app.route("/health")
def health():
    return "OK"


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, threaded=True)


# ==========================================================
# KEYBOARDS (regenerated per language)
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
         InlineKeyboardButton("🌍 Language", callback_data="m_lang")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="m_help")],
    ])


def back_kb(lang="bn"):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])


def lang_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="setlang_bn"),
         InlineKeyboardButton("🇬🇧 English", callback_data="setlang_en")],
        [InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="setlang_hi")],
    ])


# ==========================================================
# SAFE EDIT / REPLY
# ==========================================================
async def safe_reply(message, text):
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await message.reply_text(text)
    except Exception as e:
        logger.error(f"reply fail: {e}")


async def safe_edit(query, text, reply_markup=None):
    """Try edit; if fails, delete old message & send new."""
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
        return True
    except BadRequest as e:
        msg = str(e).lower()
        if "message is not modified" in msg:
            # Same content — just return
            return True
        # Fall through to send new
    except Exception as e:
        logger.error(f"edit fail: {e}")

    # Fallback: send new message
    try:
        if query.message:
            await query.message.reply_text(text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"send fallback fail: {e}")
        return False


# ==========================================================
# STREAK + ACHIEVEMENTS
# ==========================================================
async def check_streak(uid):
    user = await get_user(uid)
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
        await update_user(uid, streak=new_streak, last_practice=today)
        await check_achievements(uid)
        return new_streak
    await update_user(uid, streak=1, last_practice=today)
    return 1


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


def achievements_text(user, lang="bn"):
    earned = set(filter(None, (user.get("achievements") or "").split(",")))
    lines = []
    for k, (emoji, titles) in ACHIEVEMENTS.items():
        mark = "✅" if k in earned else "🔒"
        title = titles.get(lang) or titles.get("en") or k
        lines.append(f"{mark} {emoji} {title}")
    return "\n".join(lines)


# ==========================================================
# COMMANDS
# ==========================================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or u.is_bot:
        return

    existing = await get_user(u.id)
    if not existing:
        await create_user(u.id, u.full_name or "Student")
        await update.message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())
        # Save referral pending
        args = context.args or []
        if args and args[0].startswith("ref_"):
            try:
                context.user_data["pending_ref"] = int(args[0][4:])
            except Exception:
                pass
        return

    # Existing user — handle referral
    args = context.args or []
    if args and args[0].startswith("ref_"):
        try:
            ref_id = int(args[0][4:])
            if ref_id != u.id and not existing.get("referred_by"):
                await update_user(u.id, referred_by=ref_id)
                await add_coins(ref_id, REFERRAL_REWARD)
                try:
                    ref_lang = await get_user_lang(ref_id)
                    await context.bot.send_message(
                        ref_id, t("referral_bonus", ref_lang, n=REFERRAL_REWARD)
                    )
                except Exception:
                    pass
        except Exception:
            pass

    lang = existing.get("language") or "bn"
    await safe_reply(
        update.message,
        t("welcome", lang, name=u.first_name or "Student"),
    )
    await update.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    if lang == "en":
        text = ("📖 Help\n\n"
                "/start — Main menu\n/menu — Menu\n/profile — Profile\n"
                "/daily — Today's lesson\n/leaderboard — Leaderboard\n"
                "/coins — Balance\n/invite — Invite link\n"
                "/mistakes — Your mistakes\n/achievements — Badges\n"
                "/level — Set level\n/reminder — Set reminder\n"
                "/language — Change language\n/reset — Clear chat")
    elif lang == "hi":
        text = ("📖 सहायता\n\n"
                "/start — मुख्य मेनू\n/menu — मेनू\n/profile — प्रोफ़ाइल\n"
                "/daily — आज का पाठ\n/leaderboard — लीडरबोर्ड\n"
                "/coins — सिक्के\n/invite — आमंत्रण लिंक\n"
                "/mistakes — आपकी गलतियाँ\n/achievements — बैज\n"
                "/level — स्तर\n/reminder — रिमाइंडर\n"
                "/language — भाषा\n/reset — चैट साफ़ करें")
    else:
        text = ("📖 সাহায্য\n\n"
                "/start — মেইন মেনু\n/menu — মেনু\n/profile — প্রোফাইল\n"
                "/daily — আজকের পাঠ\n/leaderboard — লিডারবোর্ড\n"
                "/coins — কয়েন\n/invite — ইনভাইট লিংক\n"
                "/mistakes — আপনার ভুল\n/achievements — ব্যাজ\n"
                "/level — লেভেল\n/reminder — রিমাইন্ডার\n"
                "/language — ভাষা পরিবর্তন\n/reset — চ্যাট ক্লিয়ার")
    await update.message.reply_text(text)


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", "bn"))
        return
    lang = user.get("language") or "bn"
    status = t("active", lang) if user.get("is_premium") else t("inactive", lang)
    await update.message.reply_text(
        f"{t('profile_title', lang)}\n\n"
        f"{t('name', lang)}: {user.get('name')}\n"
        f"{t('level', lang)}: {user.get('level')}\n"
        f"{t('coins', lang)}: {user.get('coins') or 0}\n"
        f"{t('streak', lang)}: {user.get('streak') or 0} {t('days', lang)}\n"
        f"{t('words_learned', lang)}: {user.get('words_learned') or 0}\n"
        f"{t('quizzes', lang)}: {user.get('quizzes_taken') or 0}\n"
        f"{t('score', lang)}: {user.get('quiz_score') or 0}\n"
        f"{t('premium_status', lang)}: {status}"
    )


async def daily_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    await update.message.chat.send_action("typing")
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word (with Bangla meaning + pronunciation + example), "
        "1 grammar tip with 2 examples, 1 practice question. Plain text, no complex Markdown."
    )
    if not answer:
        answer = "📚 Word: Persistent — অর্থ: অধ্যবসায়ী\nExample: Be persistent.\n\n❓ What is past tense of 'eat'?"
    await safe_reply(
        update.message,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus} {t('coins', lang)}\n\n{answer}"
    )


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    rows = await fetch_leaderboard()
    if not rows:
        await update.message.reply_text(t("no_users", lang))
        return
    text = f"{t('leaderboard_title', lang)}\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        name = r.get("name", "?")
        score = r.get("quiz_score", 0)
        text += f"{m} {name} — ⭐ {score}\n"
    await safe_reply(update.message, text)


async def fetch_leaderboard():
    if db_pool is None:
        return sorted(
            _mem_users.values(),
            key=lambda x: (x.get("quiz_score", 0), x.get("words_learned", 0)),
            reverse=True,
        )[:10]
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, quiz_score, words_learned, streak FROM s_users "
                "ORDER BY quiz_score DESC, words_learned DESC LIMIT 10"
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def coins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", lang))
        return
    status = t("active", lang) if user.get("is_premium") else t("inactive", lang)
    await safe_reply(
        update.message,
        f"{t('coins', lang)}: {user.get('coins') or 0}\n"
        f"{t('premium_status', lang)}: {status}"
    )


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_reply(
        update.message,
        f"{t('invite_title', lang)}\n\n{link}\n\n{t('invite_hint', lang, n=REFERRAL_REWARD)}"
    )


async def mistakes_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    if db_pool is None:
        await update.message.reply_text(t("mistakes_none", lang))
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
        await update.message.reply_text(t("mistakes_none", lang))
        return
    text = f"{t('mistakes_title', lang)}\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. ❌ {r['wrong_text'][:80]}\n   ✅ {r['corrected_text'][:80]}\n\n"
    await safe_reply(update.message, text[:4000])


async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", lang))
        return
    await safe_reply(update.message, f"{t('achievements_title', lang)}\n\n{achievements_text(user, lang)}")


async def level_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        t("choose_level", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Beginner", callback_data="setlvl_beginner")],
            [InlineKeyboardButton("🟡 Intermediate", callback_data="setlvl_intermediate")],
            [InlineKeyboardButton("🔴 Advanced", callback_data="setlvl_advanced")],
        ]),
    )


async def reminder_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        t("reminder_title", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 08:00", callback_data="rem_08:00"),
             InlineKeyboardButton("☀️ 12:00", callback_data="rem_12:00")],
            [InlineKeyboardButton("🌆 18:00", callback_data="rem_18:00"),
             InlineKeyboardButton("🌙 21:00", callback_data="rem_21:00")],
            [InlineKeyboardButton("❌ Off", callback_data="rem_off")],
        ]),
    )


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())


async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    await clear_history(uid)
    await update.message.reply_text(t("reset_done", lang))


async def adminstats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if db_pool is None:
        await update.message.reply_text(
            f"📊 Admin Stats\n\n👥 Users: {len(_mem_users)}\n💾 Mode: In-Memory"
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
            premium = await conn.fetchval("SELECT COUNT(*) FROM s_users WHERE is_premium = TRUE")
            total_coins = await conn.fetchval("SELECT COALESCE(SUM(coins),0) FROM s_users")
            total_msgs = await conn.fetchval("SELECT COUNT(*) FROM s_history")
        await safe_reply(
            update.message,
            f"📊 Admin Dashboard\n\n"
            f"👥 Total Users: {total}\n🟢 24h Active: {today}\n📅 7d Active: {week}\n"
            f"💎 Premium: {premium}\n🪙 Total Coins: {total_coins}\n💬 Messages: {total_msgs}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ DB error: {e}")


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast your message")
        return
    msg = " ".join(context.args)
    if db_pool is None:
        uids = list(_mem_users.keys())
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM s_users")
                uids = [r["user_id"] for r in rows]
        except Exception:
            uids = []
    sent, failed = 0, 0
    for u_id in uids:
        try:
            await context.bot.send_message(u_id, f"📢 {msg}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Sent: {sent} | ❌ Failed: {failed}")


# ==========================================================
# STUDENT PROMPTS
# ==========================================================
STUDENT_PROMPTS = {
    "student_learn": "Start a short English lesson. Choose one useful topic. Explain simply, give 2 examples, then ONE practice question. Plain text.",
    "student_vocab": "Teach ONE English word: meaning (Bangla), pronunciation, part of speech, example. Then ONE practice question. Plain text.",
    "student_grammar": "Teach ONE English grammar point: rule, explanation, 2 examples, common mistake, 1 practice question. Plain text.",
    "student_tenses": "Teach ONE English tense: usage, structure, 2 examples, common mistake, 1 practice question. Plain text.",
    "student_writing": "Give ONE short English writing task. Wait for the student's answer. Plain text.",
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
# LANGUAGE CALLBACK
# ==========================================================
async def cb_set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = q.data.replace("setlang_", "")  # bn/en/hi
    uid = q.from_user.id
    await create_user(uid, q.from_user.full_name or "Student")
    await update_user(uid, language=lang)

    # Handle pending referral
    ref_id = context.user_data.pop("pending_ref", None)
    if ref_id and ref_id != uid:
        user = await get_user(uid)
        if user and not user.get("referred_by"):
            await update_user(uid, referred_by=ref_id)
            await add_coins(ref_id, REFERRAL_REWARD)
            try:
                ref_lang = await get_user_lang(ref_id)
                await context.bot.send_message(
                    ref_id, t("referral_bonus", ref_lang, n=REFERRAL_REWARD)
                )
            except Exception:
                pass

    await safe_edit(q, t("language_set", lang))
    await q.message.reply_text(
        t("welcome", lang, name=q.from_user.first_name or "Student"),
    )
    await q.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


# ==========================================================
# STUDENT MENU CALLBACK
# ==========================================================
async def student_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    await update_user(uid, last_active=datetime.now())

    data = q.data
    if data == "student_speaking":
        last_q = context.user_data.get("last_speaking_question")
        avail = [x for x in SPEAKING_QUESTIONS if x != last_q]
        question = random.choice(avail)
        context.user_data["last_speaking_question"] = question
        prompt = f"Start English speaking practice. Ask this exact question:\n\n{question}\n\nWait for the answer. Plain text."
    else:
        prompt = STUDENT_PROMPTS.get(data)

    if not prompt:
        await q.answer("Unknown option", show_alert=False)
        return

    # Show loading
    try:
        await q.edit_message_text(t("loading", lang))
    except Exception:
        pass

    answer = await asyncio.to_thread(ask_groq, prompt)
    if not answer:
        answer = t("ai_error", lang)

    if data == "student_vocab":
        user = await get_user(uid)
        words = (user.get("words_learned") or 0) + 1 if user else 1
        await update_user(uid, words_learned=words)
        new = await check_achievements(uid)
        if new:
            try:
                await q.message.reply_text(
                    t("new_achievement", lang) + "\n" +
                    "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1].get(lang, k)}" for k in new)
                )
            except Exception:
                pass

    await safe_edit(q, answer, reply_markup=back_kb(lang))


# ==========================================================
# OTHER CALLBACKS
# ==========================================================
async def cb_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await safe_edit(q, t("main_menu", lang), reply_markup=main_menu_kb())


async def cb_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await safe_edit(q, t("start_first", lang), reply_markup=back_kb(lang))
        return
    status = t("active", lang) if user.get("is_premium") else t("inactive", lang)
    text = (
        f"{t('profile_title', lang)}\n\n"
        f"{t('name', lang)}: {user.get('name')}\n"
        f"{t('level', lang)}: {user.get('level')}\n"
        f"{t('coins', lang)}: {user.get('coins') or 0}\n"
        f"{t('streak', lang)}: {user.get('streak') or 0} {t('days', lang)}\n"
        f"{t('words_learned', lang)}: {user.get('words_learned') or 0}\n"
        f"{t('quizzes', lang)}: {user.get('quizzes_taken') or 0}\n"
        f"{t('score', lang)}: {user.get('quiz_score') or 0}\n"
        f"{t('premium_status', lang)}: {status}"
    )
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    await q.edit_message_text(t("loading", lang))
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word + Bangla meaning + example, 1 grammar tip, 1 practice question. Plain text."
    )
    if not answer:
        answer = "📚 Word: Diligent — অর্থ: পরিশ্রমী\nExample: She is a diligent student.\n\n❓ What is past tense of 'go'?"
    await safe_edit(
        q,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n\n{answer}",
        reply_markup=back_kb(lang),
    )


async def cb_word_of_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await q.edit_message_text(t("loading", lang))
    answer = await asyncio.to_thread(
        ask_groq,
        "Give ONE advanced English word of the day. Include: word, Bangla meaning, pronunciation, part of speech, 2 examples, 2 synonyms. Plain text."
    )
    if not answer:
        answer = "🔤 Word: Resilient\n📖 অর্থ: স্থিতিস্থাপক\n🔊 /rɪˈzɪliənt/\n✏️ Children are resilient.\n🔁 Synonyms: Strong, Tough"
    await safe_edit(q, f"{t('word_title', lang)}\n\n{answer}", reply_markup=back_kb(lang))


async def cb_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    quizzes = (user.get("quizzes_taken") or 0) + 1 if user else 1
    await update_user(uid, quizzes_taken=quizzes)
    await q.edit_message_text(t("loading", lang))
    answer = await asyncio.to_thread(
        ask_groq,
        "Create ONE English multiple-choice quiz with 4 options. Format:\nQuestion: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: X) ...\nPlain text."
    )
    if not answer:
        answer = "Question: Past tense of 'go'?\nA) goed\nB) went\nC) gone\nD) going\nAnswer: B) went"
    await safe_edit(
        q,
        f"{t('quiz_title', lang)}\n\n{answer}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("quiz_more", lang), callback_data="m_quiz")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ]),
    )


async def cb_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await safe_edit(q, t("translate_hint", lang), reply_markup=back_kb(lang))


async def cb_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_edit(
        q,
        f"{t('invite_title', lang)}\n\n{link}\n\n{t('invite_hint', lang, n=REFERRAL_REWARD)}",
        reply_markup=back_kb(lang),
    )


async def cb_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if user and user.get("is_premium"):
        await safe_edit(q, t("premium_already", lang), reply_markup=back_kb(lang))
        return
    await safe_edit(
        q,
        f"{t('premium_title', lang)}\n\n"
        f"⭐ {PREMIUM_STARS} Telegram Stars → {PREMIUM_DAYS} {t('days', lang)}\n\n"
        f"🎁 Benefits:\n• Unlimited AI\n• Detailed Lessons\n• Priority Response",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("premium_buy", lang, n=PREMIUM_STARS), callback_data="buy_premium")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
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
            description=f"{PREMIUM_DAYS} days Premium",
            payload=f"premium_{uid}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=PREMIUM_STARS)],
        )
    except Exception as e:
        logger.error(f"Invoice error: {e}")
        await q.answer("❌ Payment failed", show_alert=True)


async def precheckout_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    until = datetime.now() + timedelta(days=PREMIUM_DAYS)
    await update_user(uid, is_premium=True, premium_until=until)
    await update.message.reply_text(t("premium_success", lang, days=PREMIUM_DAYS))
    new = await check_achievements(uid)
    if new:
        await update.message.reply_text(
            t("new_achievement", lang) + "\n" +
            "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1].get(lang, k)}" for k in new)
        )


async def cb_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    rows = await fetch_leaderboard()
    if not rows:
        await safe_edit(q, t("no_users", lang), reply_markup=back_kb(lang))
        return
    text = f"{t('leaderboard_title', lang)}\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        name = r.get("name", "?")
        score = r.get("quiz_score", 0)
        text += f"{m} {name} — ⭐ {score}\n"
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_mistakes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if db_pool is None:
        await safe_edit(q, t("mistakes_none", lang), reply_markup=back_kb(lang))
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
        await safe_edit(q, t("mistakes_none", lang), reply_markup=back_kb(lang))
        return
    text = f"{t('mistakes_title', lang)}\n\n"
    for i, r in enumerate(rows, 1):
        text += f"{i}. ❌ {r['wrong_text'][:80]}\n   ✅ {r['corrected_text'][:80]}\n\n"
    await safe_edit(q, text[:4000], reply_markup=back_kb(lang))


async def cb_achievements(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await safe_edit(q, t("start_first", lang), reply_markup=back_kb(lang))
        return
    await safe_edit(q, f"{t('achievements_title', lang)}\n\n{achievements_text(user, lang)}",
                    reply_markup=back_kb(lang))


async def cb_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await safe_edit(
        q,
        t("reminder_title", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 08:00", callback_data="rem_08:00"),
             InlineKeyboardButton("☀️ 12:00", callback_data="rem_12:00")],
            [InlineKeyboardButton("🌆 18:00", callback_data="rem_18:00"),
             InlineKeyboardButton("🌙 21:00", callback_data="rem_21:00")],
            [InlineKeyboardButton("❌ Off", callback_data="rem_off")],
        ]),
    )


async def cb_reminder_set(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    val = q.data.replace("rem_", "")
    if val == "off":
        await update_user(uid, remind_at=None)
        await safe_edit(q, t("reminder_off", lang), reply_markup=back_kb(lang))
    else:
        await update_user(uid, remind_at=val)
        await safe_edit(q, t("reminder_set", lang, t=val), reply_markup=back_kb(lang))


async def cb_set_level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    lvl = q.data.replace("setlvl_", "")
    await update_user(uid, level=lvl)
    await safe_edit(q, t("level_set", lang, lvl=lvl), reply_markup=back_kb(lang))


async def cb_lang_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await safe_edit(q, t("choose_lang", "bn"), reply_markup=lang_kb())


async def cb_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if lang == "en":
        text = ("ℹ️ Help\n\nAll buttons work:\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎯 Quiz, 💬 Translate, 🔥 Daily, 📖 Word of Day\n"
                "📊 Progress, 🏆 Leaderboard, 🎁 Invite, ⭐ Premium\n"
                "📚 Mistakes, 🏅 Achievements, 🔔 Reminder, 🌍 Language")
    elif lang == "hi":
        text = ("ℹ️ सहायता\n\nसभी बटन काम करते हैं:\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎯 Quiz, 💬 Translate, 🔥 Daily, 📖 Word of Day\n"
                "📊 Progress, 🏆 Leaderboard, 🎁 Invite, ⭐ Premium\n"
                "📚 Mistakes, 🏅 Achievements, 🔔 Reminder, 🌍 Language")
    else:
        text = ("ℹ️ সাহায্য\n\nসব বাটন কাজ করে:\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎯 Quiz, 💬 Translate, 🔥 Daily, 📖 Word of Day\n"
                "📊 Progress, 🏆 Leaderboard, 🎁 Invite, ⭐ Premium\n"
                "📚 Mistakes, 🏅 Achievements, 🔔 Reminder, 🌍 Language")
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Catch-all — unknown callbacks er jonno."""
    q = update.callback_query
    await q.answer("Unknown option", show_alert=False)
    logger.warning(f"Unhandled callback: {q.data}")


# ==========================================================
# TEXT HANDLER
# ==========================================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return
    chat = update.effective_chat
    if not chat:
        return

    uid = update.effective_user.id
    user = await get_user(uid)
    if not user:
        await create_user(uid, update.effective_user.full_name or "Student")
        await message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())
        return

    lang = user.get("language") or "bn"

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
        answer = t("ai_error", lang)

    await save_history(uid, "assistant", answer)
    await safe_reply(message, answer)

    new = await check_achievements(uid)
    if new:
        try:
            await message.reply_text(
                t("new_achievement", lang) + "\n" +
                "\n".join(f"{ACHIEVEMENTS[k][0]} {ACHIEVEMENTS[k][1].get(lang, k)}" for k in new)
            )
        except Exception:
            pass


# ==========================================================
# JOBS
# ==========================================================
async def daily_auto_lesson(context: ContextTypes.DEFAULT_TYPE):
    logger.info("📅 Daily auto lesson...")
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
        "Give today's daily English lesson: 1 new word + Bangla meaning + example, 1 grammar tip, 1 practice question. Plain text."
    )
    if not answer:
        answer = "📚 Word: Consistent\n📖 অর্থ: ধারাবাহিক\n✏️ She is consistent.\n\n❓ Past tense of 'eat'?"

    for u_id in uids[:500]:
        try:
            lang = await get_user_lang(u_id)
            await context.bot.send_message(u_id, f"🌅 {t('daily_title', lang)}\n\n{answer}")
            await asyncio.sleep(0.05)
        except Exception:
            pass
    logger.info(f"Sent daily lesson to {len(uids)} users.")


async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    now_hm = datetime.now().strftime("%H:%M")
    if db_pool is None:
        users = [{"user_id": u["user_id"]} for u in _mem_users.values() if u.get("remind_at") == now_hm]
    else:
        try:
            async with db_pool.acquire() as conn:
                rows = await conn.fetch("SELECT user_id FROM s_users WHERE remind_at = $1", now_hm)
                users = [{"user_id": r["user_id"]} for r in rows]
        except Exception:
            users = []
    for u in users:
        try:
            await context.bot.send_message(
                u["user_id"],
                "🔔 Time to study! /daily",
            )
        except Exception:
            pass


# ==========================================================
# BOT SETUP
# ==========================================================
async def post_init(app):
    await init_db()
    try:
        app.job_queue.run_daily(
            daily_auto_lesson,
            time=datetime.strptime("08:00", "%H:%M").time(),
        )
        app.job_queue.run_repeating(reminder_job, interval=60, first=10)
        logger.info("⏰ Jobs scheduled.")
    except Exception as e:
        logger.error(f"Job schedule error: {e}")


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
        for cmd, fn in [
            ("start", start_command), ("menu", menu_command),
            ("help", help_command), ("profile", profile_command),
            ("daily", daily_command), ("leaderboard", leaderboard_command),
            ("coins", coins_command), ("invite", invite_command),
            ("mistakes", mistakes_command), ("achievements", achievements_command),
            ("level", level_command), ("reminder", reminder_command),
            ("language", language_command), ("reset", reset_command),
            ("adminstats", adminstats_command), ("broadcast", broadcast_command),
        ]:
            application.add_handler(CommandHandler(cmd, fn))

        # Callbacks — ORDER MATTERS! Specific patterns first
        # Language
        application.add_handler(CallbackQueryHandler(cb_set_language, pattern="^setlang_"))
        application.add_handler(CallbackQueryHandler(cb_lang_menu, pattern="^m_lang$"))

        # Student menu (specific prefix)
        application.add_handler(CallbackQueryHandler(student_menu_callback, pattern="^student_"))

        # Main menu items
        application.add_handler(CallbackQueryHandler(cb_menu, pattern="^m_menu$"))
        application.add_handler(CallbackQueryHandler(cb_profile, pattern="^m_profile$"))
        application.add_handler(CallbackQueryHandler(cb_daily, pattern="^m_daily$"))
        application.add_handler(CallbackQueryHandler(cb_word_of_day, pattern="^m_word$"))
        application.add_handler(CallbackQueryHandler(cb_quiz, pattern="^m_quiz$"))
        application.add_handler(CallbackQueryHandler(cb_translate, pattern="^m_translate$"))
        application.add_handler(CallbackQueryHandler(cb_invite, pattern="^m_invite$"))
        application.add_handler(CallbackQueryHandler(cb_premium, pattern="^m_premium$"))
        application.add_handler(CallbackQueryHandler(cb_leaderboard, pattern="^m_leaderboard$"))
        application.add_handler(CallbackQueryHandler(cb_mistakes, pattern="^m_mistakes$"))
        application.add_handler(CallbackQueryHandler(cb_achievements, pattern="^m_achievements$"))
        application.add_handler(CallbackQueryHandler(cb_reminder, pattern="^m_reminder$"))
        application.add_handler(CallbackQueryHandler(cb_help, pattern="^m_help$"))

        # Sub-actions
        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_premium$"))
        application.add_handler(CallbackQueryHandler(cb_reminder_set, pattern="^rem_"))
        application.add_handler(CallbackQueryHandler(cb_set_level, pattern="^setlvl_"))

        # Payment
        application.add_handler(PreCheckoutQueryHandler(precheckout_cb))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_cb))

        # Catch-all callback (must be last among callbacks)
        application.add_handler(CallbackQueryHandler(cb_fallback))

        # Text messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

        try:
            await application.initialize()
            await application.bot.delete_webhook(drop_pending_updates=False)
            await application.start()
            await application.updater.start_polling(drop_pending_updates=False)
            logger.info("✅ Bot started.")
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
            for fn in (application.updater.stop, application.stop, application.shutdown):
                try:
                    if getattr(application.updater, "running", False) or getattr(application, "running", False):
                        await fn()
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
