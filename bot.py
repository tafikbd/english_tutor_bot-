import os
import re
import asyncio
import logging
import threading
import random
import time
import base64
import json
import difflib
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

try:
    import edge_tts
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

try:
    from pypdf import PdfReader
    HAS_PDF = True
except ImportError:
    HAS_PDF = False


# ==========================================================
# CONFIG
# ==========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
VISION_MODEL = os.getenv("VISION_MODEL", "llama-3.2-90b-vision-preview")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
PORT = int(os.getenv("PORT", "10000"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip().isdigit()]
FORCE_SUB_GROUP_ID = os.getenv("FORCE_SUB_GROUP_ID", "")
FORCE_SUB_GROUP_LINK = os.getenv("FORCE_SUB_GROUP_LINK", "")

PDF_URL = "https://drive.google.com/uc?export=download&id=10RoxnUbUOuCwcotzg6-d-j1LXNMyUWqa"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN missing.")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY missing.")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

REFERRAL_REWARD = 10
DAILY_BONUS = 5
STREAK_BONUS = 2
PREMIUM_STARS = 100
PREMIUM_DAYS = 30
FREE_IMG_PER_DAY = 5
FREE_VOICE_PER_DAY = 10
FREE_PDF_PER_DAY = 5
MAX_REVIEW_PER_DAY = 5
MAX_PDF_SIZE_MB = 10
MAX_PDF_PAGES = 20

PREMIUM_PRICE_BDT = 200
USDT_AMOUNT = 2
BKASH_NUMBER = "01608364088"
ROCKET_NUMBER = "01608364088"
TRC20_ADDRESS = "TKeEd3wuTqHse2rdzAg3rqYeRfQD1NC7tq"
BSC20_ADDRESS = "0xb83a03d9ded3ac7a4908aa87cfdfe1df9e05f719"
SUPPORT_CONTACT = "@asikul_echo"

ACHIEVEMENTS = {
    "first_chat": ("🥇", {"bn": "প্রথম চ্যাট", "en": "First Chat", "hi": "पहला चैट"}),
    "words_10": ("📚", {"bn": "১০ শব্দ শিখেছেন", "en": "10 words learned", "hi": "10 शब्द सीखे"}),
    "words_50": ("📖", {"bn": "৫০ শব্দ শিখেছেন", "en": "50 words learned", "hi": "50 शब्द सीखे"}),
    "quiz_10": ("🎯", {"bn": "১০ কুইজ দিয়েছেন", "en": "10 quizzes done", "hi": "10 क्विज़ पूरी"}),
    "streak_7": ("🔥", {"bn": "৭ দিনের স্ট্রিক", "en": "7-day streak", "hi": "7 दिन की स्ट्रीक"}),
    "streak_30": ("💪", {"bn": "৩০ দিনের স্ট্রিক", "en": "30-day streak", "hi": "30 दिन की स्ट्रीक"}),
    "premium": ("💎", {"bn": "Premium সদস্য", "en": "Premium member", "hi": "Premium सदस्य"}),
    "referrer": ("🎁", {"bn": "কাউকে ইনভাইট করেছেন", "en": "Invited someone", "hi": "किसी को आमंत्रित किया"}),
    "photo_5": ("📸", {"bn": "৫টি ছবি পাঠিয়েছেন", "en": "5 photos sent", "hi": "5 फोटो भेजे"}),
    "voice_10": ("🎤", {"bn": "১০টি ভয়েস পাঠিয়েছেন", "en": "10 voices sent", "hi": "10 वॉइस भेजे"}),
    "roleplay_5": ("🎭", {"bn": "৫টি Role-Play করেছেন", "en": "5 role-plays done", "hi": "5 रोल-प्ले किए"}),
    "review_10": ("🔁", {"bn": "১০টি রিভিউ করেছেন", "en": "10 reviews done", "hi": "10 रिव्यू किए"}),
    "pronounce_10": ("🎤", {"bn": "১০টি উচ্চারণ প্র্যাকটিস", "en": "10 pronunciation practices", "hi": "10 उच्चारण अभ्यास"}),
    "ielts_done": ("🎯", {"bn": "IELTS টেস্ট সম্পন্ন", "en": "IELTS test completed", "hi": "IELTS टेस्ट पूरा"}),
    "pdf_quiz_5": ("🧠", {"bn": "৫টি PDF কুইজ", "en": "5 PDF quizzes", "hi": "5 PDF क्विज़"}),
}


# ==========================================================
# ROLE-PLAY SCENARIOS
# ==========================================================
ROLEPLAY_SCENARIOS = {
    "restaurant": {
        "emoji": "🍽️",
        "title": {"bn": "রেস্টুরেন্ট", "en": "Restaurant", "hi": "रेस्टोरेंट"},
        "desc": {"bn": "খাবার অর্ডার করা শিখুন", "en": "Learn to order food", "hi": "खाना ऑर्डर करना सीखें"},
        "system": (
            "You are a friendly waiter at a restaurant. The user is a customer. "
            "Start by greeting them and offering the menu. Stay in character at all times. "
            "After EVERY user reply, if they made a real grammar/vocabulary error, "
            "add a line at the end: [Correction: wrong -> correct]. "
            "Keep each reply to 2-3 short lines. Use plain text with 1 emoji."
        ),
        "starter": "Good evening! Welcome to our restaurant. Here's the menu. What would you like to order?"
    },
    "airport": {
        "emoji": "✈️",
        "title": {"bn": "এয়ারপোর্ট", "en": "Airport Check-in", "hi": "एयरपोर्ट"},
        "desc": {"bn": "চেক-ইন শেখা", "en": "Learn check-in English", "hi": "चेक-इन सीखें"},
        "system": (
            "You are an airport check-in agent. The user is a passenger. "
            "Ask for passport, ticket, luggage details one by one. Stay in character. "
            "If the user makes a major English error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Good morning! May I see your passport and ticket, please?"
    },
    "interview": {
        "emoji": "💼",
        "title": {"bn": "চাকরির ইন্টারভিউ", "en": "Job Interview", "hi": "जॉब इंटरव्यू"},
        "desc": {"bn": "ইন্টারভিউ প্র্যাকটিস", "en": "Practice job interviews", "hi": "इंटरव्यू अभ्यास"},
        "system": (
            "You are a hiring manager conducting a job interview. The user is a candidate. "
            "Ask one interview question at a time. Give 1-line feedback after each answer. "
            "If they make a major error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Hello, thanks for coming in today. Please have a seat. Tell me a little about yourself."
    },
    "shopping": {
        "emoji": "🛒",
        "title": {"bn": "শপিং", "en": "Shopping", "hi": "शॉपिंग"},
        "desc": {"bn": "দোকানে কেনাকাটা", "en": "Shopping at a store", "hi": "दुकान में खरीदारी"},
        "system": (
            "You are a friendly shop assistant. The user is a customer. "
            "Help them find items, discuss prices, sizes. Stay in character. "
            "If they make a real error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Hi there! Welcome to our store. Are you looking for something specific today?"
    },
    "doctor": {
        "emoji": "🏥",
        "title": {"bn": "ডাক্তার", "en": "Doctor Visit", "hi": "डॉक्टर"},
        "desc": {"bn": "ডাক্তারের সাথে কথা", "en": "Talk to a doctor", "hi": "डॉक्टर से बात"},
        "system": (
            "You are a friendly doctor. The user is a patient describing symptoms. "
            "Ask about their health, symptoms, duration. Stay in character. "
            "If they make a real error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Good morning. Please sit down. What brings you in today? How are you feeling?"
    },
    "hotel": {
        "emoji": "🏨",
        "title": {"bn": "হোটেল", "en": "Hotel Check-in", "hi": "होटल"},
        "desc": {"bn": "হোটেলে চেক-ইন", "en": "Hotel check-in", "hi": "होटल चेक-इन"},
        "system": (
            "You are a hotel receptionist. The user is a guest checking in. "
            "Ask for reservation, ID, room preference. Stay in character. "
            "If they make a real error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Welcome to our hotel! Do you have a reservation with us?"
    },
}


# ==========================================================
# NEW: PRONUNCIATION COACH DATA
# ==========================================================
PRONUNCIATION_SENTENCES = [
    "The weather is beautiful today.",
    "I would like to order a cup of coffee.",
    "Can you please repeat that slowly?",
    "I am learning English every single day.",
    "Practice makes a person perfect.",
    "Reading books improves your vocabulary.",
    "Never give up on your dreams.",
    "Where there is a will there is a way.",
    "Actions speak louder than words.",
    "She sells seashells by the seashore.",
    "The quick brown fox jumps over the lazy dog.",
    "Learning a new language takes time and patience.",
    "Every morning I try to read English aloud.",
    "Please speak slowly so I can understand you.",
    "Honesty is the best policy in life.",
    "A journey of a thousand miles begins with one step.",
]


# ==========================================================
# NEW: IELTS SPEAKING SIMULATOR DATA
# ==========================================================
IELTS_PART1_QUESTIONS = [
    "What is your full name?",
    "Where are you from?",
    "Are you working or studying at the moment?",
    "What do you like most about your hometown?",
    "Do you enjoy reading books? Why or why not?",
]

IELTS_PART2_CUE = (
    "Describe a book you recently read.\n\n"
    "You should say:\n"
    "• What the book is about\n"
    "• Why you decided to read it\n"
    "• What you learned from it\n"
    "• And explain whether you would recommend it to others."
)

IELTS_PART3_QUESTIONS = [
    "Why do you think reading is important for young people?",
    "How has the reading habit changed over the years in your country?",
    "Should governments invest more in public libraries? Why?",
    "Do you think physical books will disappear in the future?",
]


# ==========================================================
# FLASHCARDS VOCABULARY (Difficulty Based)
# ==========================================================
FLASHCARDS = {
    "easy": [
        {"word": "Apple", "pron": "/ˈæp.əl/", "meaning": "আপেল", "ex": "I eat an apple every day."},
        {"word": "Book", "pron": "/bʊk/", "meaning": "বই", "ex": "This book is very interesting."},
        {"word": "Happy", "pron": "/ˈhæp.i/", "meaning": "খুশি", "ex": "She is very happy today."},
        {"word": "Water", "pron": "/ˈwɔː.tər/", "meaning": "পানি", "ex": "Please give me a glass of water."},
        {"word": "Friend", "pron": "/frend/", "meaning": "বন্ধু", "ex": "He is my best friend."},
        {"word": "Family", "pron": "/ˈfæm.əl.i/", "meaning": "পরিবার", "ex": "I love my family."},
        {"word": "School", "pron": "/skuːl/", "meaning": "স্কুল", "ex": "I go to school every day."},
        {"word": "Teacher", "pron": "/ˈtiː.tʃər/", "meaning": "শিক্ষক", "ex": "My teacher is very kind."},
    ],
    "medium": [
        {"word": "Beautiful", "pron": "/ˈbjuː.tɪ.fəl/", "meaning": "সুন্দর", "ex": "The garden looks beautiful."},
        {"word": "Knowledge", "pron": "/ˈnɒl.ɪdʒ/", "meaning": "জ্ঞান", "ex": "Knowledge is power."},
        {"word": "Practice", "pron": "/ˈpræk.tɪs/", "meaning": "অনুশীলন", "ex": "Practice makes a man perfect."},
        {"word": "Computer", "pron": "/kəmˈpjuː.tər/", "meaning": "কম্পিউটার", "ex": "I use a computer for work."},
        {"word": "Journey", "pron": "/ˈdʒɜː.ni/", "meaning": "যাত্রা", "ex": "The journey was very long."},
        {"word": "Hospital", "pron": "/ˈhɒs.pɪ.təl/", "meaning": "হাসপাতাল", "ex": "He is admitted to the hospital."},
        {"word": "Culture", "pron": "/ˈkʌl.tʃər/", "meaning": "সংস্কৃতি", "ex": "Bangladesh has a rich culture."},
        {"word": "Nature", "pron": "/ˈneɪ.tʃər/", "meaning": "প্রকৃতি", "ex": "We should protect nature."},
    ],
    "hard": [
        {"word": "Confident", "pron": "/ˈkɒn.fɪ.dənt/", "meaning": "আত্মবিশ্বাসী", "ex": "She is confident about her success."},
        {"word": "Vocabulary", "pron": "/vəˈkæb.jə.lər.i/", "meaning": "শব্দভাণ্ডার", "ex": "Reading books improves your vocabulary."},
        {"word": "Pronunciation", "pron": "/prəˌnʌn.siˈeɪ.ʃən/", "meaning": "উচ্চারণ", "ex": "Your pronunciation is very good."},
        {"word": "Opportunity", "pron": "/ˌɒp.əˈtʃuː.nə.ti/", "meaning": "সুযোগ", "ex": "Don't miss this golden opportunity."},
        {"word": "Environment", "pron": "/ɪnˈvaɪ.rən.mənt/", "meaning": "পরিবেশ", "ex": "We must keep our environment clean."},
        {"word": "Achievement", "pron": "/əˈtʃiːv.mənt/", "meaning": "অর্জন", "ex": "This is a great achievement for us."},
        {"word": "Responsibility", "pron": "/rɪˌspɒn.sɪˈbɪl.ə.ti/", "meaning": "দায়িত্ব", "ex": "It is your responsibility to help the poor."},
        {"word": "Experience", "pron": "/ɪkˈspɪə.ri.əns/", "meaning": "অভিজ্ঞতা", "ex": "He has 5 years of work experience."},
    ]
}

WORD_GAME_LIST = [
    "apple", "banana", "orange", "school", "teacher", "student", "water", "happy",
    "family", "friend", "garden", "money", "river", "mountain", "flower", "animal",
    "doctor", "police", "market", "holiday", "science", "history", "music", "picture",
    "library", "letter", "summer", "winter", "breakfast", "dinner", "country", "language",
    "computer", "mobile", "internet", "office", "hospital", "journey", "culture", "nature",
    "amazing", "beautiful", "confident", "knowledge", "practice", "sentence", "vocabulary", "grammar"
]


T = {
    "welcome": {
        "bn": "👋 স্বাগতম {name}!\n\n🎓 আমি EduMate AI - আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n📖 যা করতে পারি:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 অনুবাদ\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 ছবি বিশ্লেষণ\n• 📄 PDF বিশ্লেষণ\n• 🎤 ভয়েস সাপোর্ট\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 নিচের বাটন থেকে বেছে নিন।",
        "en": "👋 Welcome {name}!\n\n🎓 I am EduMate AI - your 24/7 English teacher.\n\n📖 What I can do:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 Translation\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 Photo analysis\n• 📄 PDF analysis\n• 🎤 Voice support\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 Choose from below.",
        "hi": "👋 स्वागत है {name}!\n\n🎓 मैं EduMate AI हूँ - आपका 24/7 English शिक्षक।\n\n📖 मैं क्या कर सकता हूँ:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 अनुवाद\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 फोटो विश्लेषण\n• 📄 PDF विश्लेषण\n• 🎤 वॉइस सपोर्ट\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 नीचे से चुनें।",
    },
    "main_menu": {"bn": "🏠 মেইন মেনু:", "en": "🏠 Main Menu:", "hi": "🏠 मुख्य मेनू:"},
    "menu_btn": {"bn": "🏠 মেইন মেনু", "en": "🏠 Main Menu", "hi": "🏠 मुख्य मेनू"},
    "loading": {"bn": "⏳ তৈরি হচ্ছে...", "en": "⏳ Generating...", "hi": "⏳ बना रहा हूँ..."},
    "ai_error": {"bn": "⚠️ এখন AI-তে সমস্যা হচ্ছে। আবার চেষ্টা করুন।", "en": "⚠️ AI is having issues. Please try again.", "hi": "⚠️ AI में समस्या है। कृपया पुनः प्रयास करें।"},
    "profile_title": {"bn": "👤 আপনার প্রোফাইল", "en": "👤 Your Profile", "hi": "👤 आपकी प्रोफ़ाइल"},
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
    "language_set": {"bn": "✅ ভাষা সেট হয়েছে: বাংলা", "en": "✅ Language set: English", "hi": "✅ भाषा सेट: हिन्दी"},
    "choose_lang": {
        "bn": "🌍 ভাষা নির্বাচন করুন:\n\nChoose your language:\n\nअपनी भाषा चुनें:",
        "en": "🌍 Choose your language:\n\nআপনার ভাষা নির্বাচন করুন:\n\nअपनी भाषा चुनें:",
        "hi": "🌍 अपनी भाषा चुनें:\n\nChoose your language:\n\nআপনার ভাষা নির্বাচন করুন:",
    },
    "reset_done": {"bn": "🔄 চ্যাট ক্লিয়ার হয়েছে। /start দিন।", "en": "🔄 Chat cleared. Send /start.", "hi": "🔄 चैट साफ। /start भेजें।"},
    "start_first": {"bn": "❌ আগে /start দিন।", "en": "❌ Please /start first.", "hi": "❌ पहले /start करें।"},
    "daily_title": {"bn": "🔥 Daily Lesson", "en": "🔥 Daily Lesson", "hi": "🔥 Daily Lesson"},
    "bonus_coins": {"bn": "🎁 বোনাস", "en": "🎁 Bonus", "hi": "🎁 बोनस"},
    "days": {"bn": "দিন", "en": "days", "hi": "दिन"},
    "leaderboard_title": {"bn": "🏆 টপ ১০ লিডারবোর্ড", "en": "🏆 Top 10 Leaderboard", "hi": "🏆 टॉप 10 लीडरबोर्ड"},
    "no_users": {"bn": "এখনো কোনো ইউজার নেই।", "en": "No users yet.", "hi": "अभी कोई उपयोगकर्ता नहीं।"},
    "word_title": {"bn": "📖 Word of the Day", "en": "📖 Word of the Day", "hi": "📖 आज का शब्द"},
    "quiz_title": {"bn": "🎯 Quiz", "en": "🎯 Quiz", "hi": "🎯 Quiz"},
    "quiz_more": {"bn": "🎯 আরেকটি কুইজ", "en": "🎯 Another Quiz", "hi": "🎯 एक और Quiz"},
    "translate_hint": {"bn": "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান।", "en": "Send any Bangla or English sentence.", "hi": "कोई भी Bangla या English वाक्य भेजें।"},
    "invite_title": {"bn": "🎁 Invite & Earn", "en": "🎁 Invite & Earn", "hi": "🎁 Invite & Earn"},
    "invite_hint": {"bn": "💡 প্রতি ইনভাইটে {n} কয়েন পাবেন!", "en": "💡 Earn {n} coins per invite!", "hi": "💡 हर invite पर {n} सिक्के!"},
    "premium_title": {"bn": "💎 Premium Membership", "en": "💎 Premium Membership", "hi": "💎 Premium Membership"},
    "premium_buy": {"bn": "⭐ কিনুন ({n} Stars)", "en": "⭐ Buy ({n} Stars)", "hi": "⭐ खरीदें ({n} Stars)"},
    "premium_already": {"bn": "💎 আপনি ইতিমধ্যে Premium!", "en": "💎 You are already Premium!", "hi": "💎 आप पहले से Premium हैं!"},
    "premium_success": {"bn": "🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n✅ {days} দিনের জন্য সক্রিয়।\n\n🎁 এখন পাবেন:\n• আনলিমিটেড ছবি\n• আনলিমিটেড ভয়েস\n• Voice reply\n• আনলিমিটেড PDF\n• 🎤 Pronunciation Coach\n• 🎯 IELTS Speaking Simulator\n• 🧠 Quiz from PDF", "en": "🎉 Congratulations! You are now Premium!\n✅ Active for {days} days.\n\n🎁 Now you get:\n• Unlimited photos\n• Unlimited voice\n• Voice replies\n• Unlimited PDFs\n• 🎤 Pronunciation Coach\n• 🎯 IELTS Speaking Simulator\n• 🧠 Quiz from PDF", "hi": "🎉 बधाई! आप अब Premium हैं!\n✅ {days} दिनों के लिए सक्रिय।"},
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
    "force_sub_title": {"bn": "🔒 বট ব্যবহার করতে হলে আমাদের গ্রুপে জয়েন করুন", "en": "🔒 Please join our group to use this bot", "hi": "🔒 इस बॉट का उपयोग करने के लिए हमारे ग्रुप से जुड़ें"},
    "force_sub_desc": {"bn": "আমাদের Friendship Hub কমিউনিটিতে জয়েন করুন। জয়েন করার পর নিচের বাটনে ক্লিক করুন।", "en": "Join our Friendship Hub community. After joining, tap the button below.", "hi": "हमारे Friendship Hub से जुड़ें। जुड़ने के बाद नीचे के बटन पर क्लिक करें।"},
    "force_sub_join_btn": {"bn": "👥 গ্রুপে জয়েন করুন", "en": "👥 Join Group", "hi": "👥 ग्रुप जॉइन करें"},
    "force_sub_check_btn": {"bn": "✅ জয়েন করেছি, চেক করুন", "en": "✅ I Joined, Check", "hi": "✅ जुड़ गया, चेक करें"},
    "force_sub_not_joined": {"bn": "❌ আপনি এখনো গ্রুপে জয়েন করেননি। জয়েন করে আবার চেক করুন।", "en": "❌ You haven't joined the group yet.", "hi": "❌ आपने अभी तक ग्रुप जॉइन नहीं किया।"},
    "force_sub_thanks": {"bn": "✅ ধন্যবাদ! এখন আপনি বট ব্যবহার করতে পারবেন।", "en": "✅ Thank you! You can now use the bot.", "hi": "✅ धन्यवाद! अब आप बॉट का उपयोग कर सकते हैं।"},
    "voice_limit": {"bn": "🎤 ফ্রি ইউজাররা দিনে {n}টি ভয়েস পাঠাতে পারেন।\n\n⭐ Premium নিলে আনলিমিটেড + Voice Reply পাবেন।", "en": "🎤 Free users can send {n} voice messages per day.\n\n⭐ Get Premium for unlimited + voice replies.", "hi": "🎤 फ्री यूज़र्स दिन में {n} वॉइस भेज सकते हैं।\n\n⭐ Premium लें unlimited के लिए।"},
    "img_limit": {"bn": "📸 ফ্রি ইউজাররা দিনে {n}টি ছবি পাঠাতে পারেন।\n\n⭐ Premium নিলে আনলিমিটেড পাবেন।", "en": "📸 Free users can send {n} photos per day.\n\n⭐ Get Premium for unlimited.", "hi": "📸 फ्री यूज़र्स दिन में {n} फोटो भेज सकते हैं।\n\n⭐ Premium लें।"},
    "pdf_limit": {"bn": "📄 ফ্রি ইউজাররা দিনে {n}টি PDF পাঠাতে পারেন।\n\n⭐ Premium নিলে আনলিমিটেড পাবেন।", "en": "📄 Free users can send {n} PDFs per day.\n\n⭐ Get Premium for unlimited.", "hi": "📄 फ्री यूज़र्स दिन में {n} PDF भेज सकते हैं।\n\n⭐ Premium लें।"},
    "processing_voice": {"bn": "🎤 ভয়েস প্রসেস হচ্ছে...", "en": "🎤 Processing voice...", "hi": "🎤 वॉइस प्रोसेस हो रही है..."},
    "processing_img": {"bn": "📸 ছবি বিশ্লেষণ হচ্ছে...", "en": "📸 Analyzing image...", "hi": "📸 फोटो विश्लेषण हो रहा है..."},
    "processing_pdf": {"bn": "📄 PDF পড়া হচ্ছে...", "en": "📄 Reading PDF...", "hi": "📄 PDF पढ़ रहा हूँ..."},
    "pdf_analyzing": {"bn": "🤖 PDF বিশ্লেষণ করা হচ্ছে...", "en": "🤖 Analyzing PDF...", "hi": "🤖 PDF विश्लेषण हो रहा है..."},
    "pdf_fail": {"bn": "❌ PDF পড়তে পারিনি। টেক্সট-ভিত্তিক PDF পাঠান (স্ক্যান করা নয়)।", "en": "❌ Could not read PDF. Please send a text-based PDF (not scanned).", "hi": "❌ PDF नहीं पढ़ सका। टेक्स्ट-बेस्ड PDF भेजें।"},
    "pdf_too_big": {"bn": "📄 PDF বড়, প্রথম {n} পৃষ্ঠা পড়া হয়েছে।", "en": "📄 PDF is large. First {n} pages were read.", "hi": "📄 PDF बड़ा है। पहले {n} पेज पढ़े गए।"},
    "pdf_too_large": {"bn": "❌ ফাইলটি খুব বড়। সর্বোচ্চ {n} MB পাঠাতে পারবেন।", "en": "❌ File is too large. Max {n} MB allowed.", "hi": "❌ फाइल बहुत बड़ी है। अधिकतम {n} MB।"},
    "voice_heard": {"bn": "📝 আপনি বলেছেন: {text}", "en": "📝 You said: {text}", "hi": "📝 आपने कहा: {text}"},
    "voice_fail": {"bn": "❌ ভয়েস বুঝতে পারিনি। আবার পাঠান।", "en": "❌ Could not understand voice.", "hi": "❌ वॉइस समझ नहीं आई।"},
    "img_fail": {"bn": "❌ ছবি বুঝতে পারিনি। আবার পাঠান।", "en": "❌ Could not analyze image.", "hi": "❌ फोटो समझ नहीं आई।"},
    "feedback_thanks": {"bn": "🙏 ধন্যবাদ আপনার মতামতের জন্য!", "en": "🙏 Thanks for your feedback!", "hi": "🙏 फीडबैक के लिए धन्यवाद!"},
    "practice_title": {"bn": "🎭 Role-Play Practice", "en": "🎭 Role-Play Practice", "hi": "🎭 Role-Play अभ्यास"},
    "practice_desc": {"bn": "একটা পরিস্থিতি বেছে নিন:", "en": "Choose a scenario:", "hi": "एक परिस्थिति चुनें:"},
    "rp_started": {"bn": "🎭 {title} শুরু হয়েছে!\n\nবন্ধ করতে /endroleplay দিন।", "en": "🎭 {title} started!\n\nSend /endroleplay to stop.", "hi": "🎭 {title} शुरू!\n\nरोकने के लिए /endroleplay भेजें।"},
    "rp_ended": {"bn": "🎭 Role-Play শেষ। আবার শুরু করতে /practice দিন।", "en": "🎭 Role-Play ended. Send /practice to start again.", "hi": "🎭 Role-Play खत्म। फिर से /practice भेजें।"},
    "rp_active": {"bn": "⚠️ আপনি এখনো Role-Play মোডে আছেন। /endroleplay দিয়ে বন্ধ করুন।", "en": "⚠️ You're in Role-Play mode. Send /endroleplay to stop.", "hi": "⚠️ आप Role-Play में हैं। /endroleplay भेजें।"},
    "rp_not_in": {"bn": "⚠️ আপনি Role-Play মোডে নেই।", "en": "⚠️ You are not in Role-Play mode.", "hi": "⚠️ आप Role-Play मोड में नहीं हैं।"},
    "review_title": {"bn": "🔁 Spaced Review", "en": "🔁 Spaced Review", "hi": "🔁 Spaced Review"},
    "review_none": {"bn": "✅ আজ কোনো রিভিউ নেই! আরও ভুল করতে থাকুন 😊", "en": "✅ No reviews today! Keep practicing.", "hi": "✅ आज कोई रिव्यू नहीं!"},
    "review_prompt": {"bn": "🔁 মনে আছে?\n\n❌ আগের ভুল: {wrong}\n\n✅ সঠিকটা লিখুন:", "en": "🔁 Remember?\n\n❌ Old mistake: {wrong}\n\n✅ Write the correct version:", "hi": "🔁 याद है?\n\n❌ पुरानी गलती: {wrong}\n\n✅ सही लिखें:"},
    "review_correct": {"bn": "🎉 একদম সঠিক! আজকের রিভিউ শেষ।", "en": "🎉 Perfect! Review complete for today.", "hi": "🎉 बिल्कुल सही! रिव्यू पूरा।"},
    "review_wrong": {"bn": "❌ এটা ঠিক হয়নি।\n\n✅ সঠিক: {correct}\n\nআবার চেষ্টা করুন কাল।", "en": "❌ Not quite.\n\n✅ Correct: {correct}\n\nTry again tomorrow.", "hi": "❌ सही नहीं।\n\n✅ सही: {correct}\n\nकल फिर कोशिश करें।"},
    "memory_title": {"bn": "🧠 আমি যা মনে রেখেছি", "en": "🧠 What I Remember", "hi": "🧠 मुझे याद है"},
    "review_saved": {"bn": "✅ রিভিউ লিস্টে যোগ হয়েছে!", "en": "✅ Added to review list!", "hi": "✅ रिव्यू लिस्ट में जोड़ा गया!"},
    "cancel_payment_btn": {"bn": "❌ পেমেন্ট বাতিল করুন", "en": "❌ Cancel Payment", "hi": "❌ भुगतान रद्द करें"},
    "copy_btn": {"bn": "📋 কপি করুন", "en": "📋 Copy", "hi": "📋 कॉपी करें"},
    "copy_hint": {"bn": "👇 ট্যাপ করে কপি করুন।", "en": "👇 Tap to copy.", "hi": "👇 टैप करके कॉपी करें।"},
    "pay_bkash_title": {"bn": "💳 bKash পেমেন্ট", "en": "💳 bKash Payment", "hi": "💳 bKash भुगतान"},
    "pay_bkash_desc": {
        "bn": "১. আপনার bKash এপ থেকে Send Money করুন।\n২. নাম্বার: `{number}`\n৩. এমাউন্ট: `{amount}` টাকা\n৪. টাকা পাঠানোর পর Transaction ID (TrxID) এবং স্ক্রিনশট এই চ্যাটে পাঠান।\n\n✅ অ্যাডমিন চেক করে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।",
        "en": "1. Send Money from your bKash app.\n2. Number: `{number}`\n3. Amount: `{amount}` BDT\n4. After sending, send the Transaction ID (TrxID) and screenshot to this chat.\n\n✅ Admin will verify and activate your premium within 5 minutes.",
        "hi": "1. अपने bKash ऐप से Send Money करें।\n2. नंबर: `{number}`\n3. राशि: `{amount}` BDT\n4. भेजने के बाद Transaction ID (TrxID) और स्क्रीनशॉट इस चैट में भेजें।\n\n✅ एडमिन 5 मिनट के भीतर आपका प्रीमियम एक्टिवेट कर देगा।"
    },
    "pay_rocket_title": {"bn": "💳 Rocket পেমেন্ট", "en": "💳 Rocket Payment", "hi": "💳 Rocket भुगतान"},
    "pay_rocket_desc": {
        "bn": "১. আপনার Rocket এপ থেকে Send Money করুন।\n২. নাম্বার: `{number}`\n৩. এমাউন্ট: `{amount}` টাকা\n৪. টাকা পাঠানোর পর Transaction ID (TrxID) এবং স্ক্রিনশট এই চ্যাটে পাঠান।\n\n✅ অ্যাডমিন চেক করে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।",
        "en": "1. Send Money from your Rocket app.\n2. Number: `{number}`\n3. Amount: `{amount}` BDT\n4. After sending, send the Transaction ID (TrxID) and screenshot to this chat.\n\n✅ Admin will verify and activate your premium within 5 minutes.",
        "hi": "1. अपने Rocket ऐप से Send Money करें।\n2. नंबर: `{number}`\n3. राशि: `{amount}` BDT\n4. भेजने के बाद Transaction ID (TrxID) और स्क्रीनशॉट इस चैट में भेजें।\n\n✅ एडमिन 5 मिनट के भीतर आपका प्रीमियम एक्टिवेट कर देगा।"
    },
    "pay_trc20_title": {"bn": "🪙 ক্রিপ্টো পেমেন্ট (USDT TRC20)", "en": "🪙 Crypto Payment (USDT TRC20)", "hi": "🪙 क्रिप्टो भुगतान (USDT TRC20)"},
    "pay_trc20_desc": {
        "bn": "১. আপনার ওয়ালেট থেকে `{amount}` USDT (TRC20) পাঠান।\n২. TRC20 অ্যাড্রেস: `{address}`\n৩. টাকা পাঠানোর পর Transaction Hash (TxID) এবং স্ক্রিনশট এই চ্যাটে পাঠান।\n\n✅ অ্যাডমিন চেক করে ১০ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।",
        "en": "1. Send `{amount}` USDT (TRC20) from your wallet.\n2. TRC20 Address: `{address}`\n3. After sending, send the Transaction Hash (TxID) and screenshot to this chat.\n\n✅ Admin will verify and activate your premium within 10 minutes.",
        "hi": "1. अपने वॉलेट से `{amount}` USDT (TRC20) भेजें।\n2. TRC20 एड्रेस: `{address}`\n3. भेजने के बाद Transaction Hash (TxID) और स्क्रीनशॉट इस चैट में भेजें।\n\n✅ एडमिन 10 मिनट के भीतर आपका प्रीमियम एक्टिवेट कर देगा।"
    },
    "pay_bsc20_title": {"bn": "🪙 ক্রিপ্টো পেমেন্ট (USDT BSC20)", "en": "🪙 Crypto Payment (USDT BSC20)", "hi": "🪙 क्रिप्टो भुगतान (USDT BSC20)"},
    "pay_bsc20_desc": {
        "bn": "১. আপনার ওয়ালেট থেকে `{amount}` USDT (BSC20) পাঠান।\n২. BSC20 অ্যাড্রেস: `{address}`\n৩. টাকা পাঠানোর পর Transaction Hash (TxID) এবং স্ক্রিনশট এই চ্যাটে পাঠান।\n\n✅ অ্যাডমিন চেক করে ১০ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।",
        "en": "1. Send `{amount}` USDT (BSC20) from your wallet.\n2. BSC20 Address: `{address}`\n3. After sending, send the Transaction Hash (TxID) and screenshot to this chat.\n\n✅ Admin will verify and activate your premium within 10 minutes.",
        "hi": "1. अपने वॉलेट से `{amount}` USDT (BSC20) भेजें।\n2. BSC20 एड्रेस: `{address}`\n3. भेजने के बाद Transaction Hash (TxID) और स्क्रीनशॉट इस चैट में भेजें।\n\n✅ एडमिन 10 मिनट के भीतर आपका प्रीमियम एक्टिवेट कर देगा।"
    },
    "support_title": {"bn": "🆘 সাপোর্ট", "en": "🆘 Support", "hi": "🆘 सहायता"},
    "support_desc": {
        "bn": "আপনার কোনো সমস্যা, প্রশ্ন বা সাজেশন থাকলে নিচে লিখে পাঠান।\n\n📩 আপনার মেসেজটি সরাসরি অ্যাডমিনের কাছে পাঠানো হবে এবং শীঘ্রই উত্তর দেওয়া হবে।\n\n📞 বিকল্প যোগাযোগ: @asikul_echo",
        "en": "If you have any problem, question, or suggestion, write it below.\n\n📩 Your message will be sent directly to the admin and you will get a reply soon.\n\n📞 Alternative contact: @asikul_echo",
        "hi": "यदि आपको कोई समस्या, प्रश्न या सुझाव है तो नीचे लिखें।\n\n📩 आपका संदेश सीधे एडमिन को भेजा जाएगा और जल्द ही उत्तर दिया जाएगा।\n\n📞 वैकल्पिक संपर्क: @asikul_echo"
    },
    "support_sent": {"bn": "✅ আপনার মেসেজ অ্যাডমিনের কাছে পাঠানো হয়েছে। শীঘ্রই উত্তর পাবেন।", "en": "✅ Your message has been sent to the admin. You will get a reply soon.", "hi": "✅ आपका संदेश एडमिन को भेज दिया गया है। जल्द ही उत्तर मिलेगा।"},
    "support_btn": {"bn": "🆘 সাপোর্ট", "en": "🆘 Support", "hi": "🆘 सहायता"},
    "support_cancel": {"bn": "❌ বাতিল করুন", "en": "❌ Cancel", "hi": "❌ रद्द करें"},
    "support_cancelled": {"bn": "✅ সাপোর্ট মোড বাতিল করা হয়েছে।", "en": "✅ Support mode cancelled.", "hi": "✅ सहायता मोड रद्द कर दिया गया।"},
    "payment_proof_sent": {"bn": "✅ আপনার পেমেন্ট প্রুফ অ্যাডমিনের কাছে পাঠানো হয়েছে।\nভেরিফিকেশন শেষ হলে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেওয়া হবে।", "en": "✅ Your payment proof has been sent to the admin.\nPremium will be activated within 5 minutes after verification.", "hi": "✅ आपका भुगतान प्रमाण एडमिन को भेज दिया गया है।"},
    "payment_info_sent": {"bn": "✅ আপনার পেমেন্ট ইনফো অ্যাডমিনের কাছে পাঠানো হয়েছে।\nভেরিফিকেশন শেষ হলে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেওয়া হবে।", "en": "✅ Your payment info has been sent to the admin.\nPremium will be activated within 5 minutes after verification.", "hi": "✅ आपकी भुगतान जानकारी एडमिन को भेज दी गई है।"},
    "suggestion_expired": {"bn": "⚠️ এক্সপায়ার হয়ে গেছে। আবার চেষ্টা করুন।", "en": "⚠️ This option has expired. Please try again.", "hi": "⚠️ यह विकल्प समाप्त हो गया है। फिर प्रयास करें।"},
    "game_title": {"bn": "🎮 Word Scramble Game", "en": "🎮 Word Scramble Game", "hi": "🎮 Word Scramble Game"},
    "game_scrambled": {"bn": "🔤 এলোমেলো শব্দ: `{word}`", "en": "🔤 Scrambled word: `{word}`", "hi": "🔤 अव्यवस्थित शब्द: `{word}`"},
    "game_prompt": {"bn": "👉 সঠিক ইংরেজি শব্দটি চ্যাটে লিখে পাঠান।", "en": "👉 Type the correct English word in chat.", "hi": "👉 सही अंग्रेजी शब्द चैट में लिखें।"},
    "game_score": {"bn": "🏆 আপনার স্কোর: {score}", "en": "🏆 Your score: {score}", "hi": "🏆 आपका स्कोर: {score}"},
    "game_stop_hint": {"bn": "❌ খেলা বন্ধ করতে: /endgame", "en": "❌ To stop: /endgame", "hi": "❌ रोकने के लिए: /endgame"},
    "game_skip_btn": {"bn": "⏭️ Skip / Next Word", "en": "⏭️ Skip / Next Word", "hi": "⏭️ Skip / अगला शब्द"},
    "game_correct": {"bn": "🎉 একদম সঠিক! আপনি ৫ কয়েন পেয়েছেন।", "en": "🎉 Correct! You earned 5 coins.", "hi": "🎉 बिल्कुल सही! आपने 5 सिक्के कमाए।"},
    "game_next_word": {"bn": "🔤 পরের শব্দ: `{word}`", "en": "🔤 Next word: `{word}`", "hi": "🔤 अगला शब्द: `{word}`"},
    "game_wrong": {"bn": "❌ ভুল হয়েছে!", "en": "❌ Wrong!", "hi": "❌ गलत!"},
    "game_hint": {"bn": "💡 হিন্ট: প্রথম অক্ষর `{first}`, শব্দটির {length}টি অক্ষর।", "en": "💡 Hint: first letter `{first}`, {length} letters.", "hi": "💡 संकेत: पहला अक्षर `{first}`, {length} अक्षर।"},
    "game_try_again": {"bn": "👉 আবার চেষ্টা করুন।", "en": "👉 Try again.", "hi": "👉 फिर कोशिश करें।"},
    "game_over_title": {"bn": "🎮 গেম শেষ!", "en": "🎮 Game Over!", "hi": "🎮 गेम खत्म!"},
    "game_total_score": {"bn": "🏆 আপনার মোট স্কোর: {score}", "en": "🏆 Your total score: {score}", "hi": "🏆 आपका कुल स्कोर: {score}"},
    "game_play_again": {"bn": "আবার খেলতে মেইন মেনু থেকে 🎮 Word Game এ ক্লিক করুন।", "en": "To play again, tap 🎮 Word Game from main menu.", "hi": "फिर से खेलने के लिए मुख्य मेनू से 🎮 Word Game पर टैप करें।"},
    "game_not_in": {"bn": "⚠️ আপনি এখন কোনো গেমে নেই।", "en": "⚠️ You're not in a game.", "hi": "⚠️ आप किसी गेम में नहीं हैं।"},
    "game_new_word": {"bn": "নতুন শব্দ আসছে...", "en": "Loading new word...", "hi": "नया शब्द आ रहा है..."},
    "fc_title": {"bn": "📇 ডেইলি Vocabulary Flashcards", "en": "📇 Daily Vocabulary Flashcards", "hi": "📇 डेली Vocabulary Flashcards"},
    "fc_choose_level": {"bn": "আপনি কোন লেভেলের শব্দ শিখতে চান?\nনিচের বাটন থেকে বেছে নিন:", "en": "Which level of words do you want to learn?\nChoose from below:", "hi": "आप किस स्तर के शब्द सीखना चाहते हैं?\nनीचे से चुनें:"},
    "fc_easy": {"bn": "🟢 Easy - সহজ শব্দ", "en": "🟢 Easy words", "hi": "🟢 Easy - आसान शब्द"},
    "fc_medium": {"bn": "🟡 Medium - মাঝারি শব্দ", "en": "🟡 Medium words", "hi": "🟡 Medium - मध्यम शब्द"},
    "fc_hard": {"bn": "🔴 Hard - কঠিন শব্দ", "en": "🔴 Hard words", "hi": "🔴 Hard - कठिन शब्द"},
    "fc_word": {"bn": "📇 শব্দ: {word}", "en": "📇 Word: {word}", "hi": "📇 शब्द: {word}"},
    "fc_pron": {"bn": "🔊 উচ্চারণ: {pron}", "en": "🔊 Pronunciation: {pron}", "hi": "🔊 उच्चारण: {pron}"},
    "fc_ask": {"bn": "👉 আপনি কি শব্দটির অর্থ জানেন?\nনিচের বাটনে ক্লিক করে উত্তর দেখুন।", "en": "👉 Do you know the meaning of this word?\nTap below to see the answer.", "hi": "👉 क्या आपको इस शब्द का अर्थ पता है?\nनीचे टैप करके उत्तर देखें।"},
    "fc_show_btn": {"bn": "✅ উত্তর দেখুন", "en": "✅ Show Answer", "hi": "✅ उत्तर देखें"},
    "fc_next_btn": {"bn": "⏭️ পরের শব্দ", "en": "⏭️ Next Word", "hi": "⏭️ अगला शब्द"},
    "fc_meaning": {"bn": "📝 অর্থ: {meaning}", "en": "📝 Meaning: {meaning}", "hi": "📝 अर्थ: {meaning}"},
    "fc_example": {"bn": "✏️ উদাহরণ: {ex}", "en": "✏️ Example: {ex}", "hi": "✏️ उदाहरण: {ex}"},
    "fc_remember_hint": {"bn": "🎯 এই শব্দটি মনে রাখার চেষ্টা করুন।", "en": "🎯 Try to remember this word.", "hi": "🎯 इस शब्द को याद रखने की कोशिश करें।"},
    "fc_change_level": {"bn": "🔙 লেভেল পরিবর্তন", "en": "🔙 Change Level", "hi": "🔙 स्तर बदलें"},
    "premium_body": {
        "bn": (
            "💎 Premium Membership\n\n"
            "⭐ {stars} Telegram Stars → {days} দিন\n"
            "💳 bKash/Rocket: {bdt} BDT → {days} দিন\n"
            "🪙 Crypto: {usdt} USDT → {days} দিন\n\n"
            "🎁 Benefits:\n"
            "• Unlimited AI\n"
            "• 📸 Unlimited photos\n"
            "• 🎤 Unlimited voices + Voice replies\n"
            "• 📄 Unlimited PDFs\n"
            "• 🎭 Unlimited role-plays\n"
            "• 🎤 Pronunciation Coach (স্কোর সহ)\n"
            "• 🎯 IELTS Speaking Simulator\n"
            "• 🧠 Quiz from PDF\n"
            "• Detailed Lessons\n"
            "• Priority Response"
        ),
        "en": (
            "💎 Premium Membership\n\n"
            "⭐ {stars} Telegram Stars → {days} days\n"
            "💳 bKash/Rocket: {bdt} BDT → {days} days\n"
            "🪙 Crypto: {usdt} USDT → {days} days\n\n"
            "🎁 Benefits:\n"
            "• Unlimited AI\n"
            "• 📸 Unlimited photos\n"
            "• 🎤 Unlimited voices + Voice replies\n"
            "• 📄 Unlimited PDFs\n"
            "• 🎭 Unlimited role-plays\n"
            "• 🎤 Pronunciation Coach (with score)\n"
            "• 🎯 IELTS Speaking Simulator\n"
            "• 🧠 Quiz from PDF\n"
            "• Detailed Lessons\n"
            "• Priority Response"
        ),
        "hi": (
            "💎 Premium Membership\n\n"
            "⭐ {stars} Telegram Stars → {days} दिन\n"
            "💳 bKash/Rocket: {bdt} BDT → {days} दिन\n"
            "🪙 Crypto: {usdt} USDT → {days} दिन\n\n"
            "🎁 Benefits:\n"
            "• Unlimited AI\n"
            "• 📸 Unlimited photos\n"
            "• 🎤 Unlimited voices + Voice replies\n"
            "• 📄 Unlimited PDFs\n"
            "• 🎭 Unlimited role-plays\n"
            "• 🎤 Pronunciation Coach\n"
            "• 🎯 IELTS Speaking Simulator\n"
            "• 🧠 Quiz from PDF\n"
            "• Detailed Lessons\n"
            "• Priority Response"
        ),
    },
    "premium_bkash_btn": {"bn": "💳 bKash ({n}৳)", "en": "💳 bKash ({n}৳)", "hi": "💳 bKash ({n}৳)"},
    "premium_rocket_btn": {"bn": "💳 Rocket ({n}৳)", "en": "💳 Rocket ({n}৳)", "hi": "💳 Rocket ({n}৳)"},
    "premium_trc20_btn": {"bn": "🪙 USDT (TRC20)", "en": "🪙 USDT (TRC20)", "hi": "🪙 USDT (TRC20)"},
    "premium_bsc20_btn": {"bn": "🪙 USDT (BSC20)", "en": "🪙 USDT (BSC20)", "hi": "🪙 USDT (BSC20)"},
    "payment_cancelled": {"bn": "✅ পেমেন্ট বাতিল করা হয়েছে।", "en": "✅ Payment cancelled.", "hi": "✅ भुगतान रद्द कर दिया गया।"},
    "payment_fail": {"bn": "❌ পেমেন্ট ব্যর্থ হয়েছে", "en": "❌ Payment failed", "hi": "❌ भुगतान विफल"},
    "vocab_book_title": {"bn": "📘 Sir English Vocabulary Book", "en": "📘 Sir English Vocabulary Book", "hi": "📘 Sir English Vocabulary Book"},
    "vocab_book_desc": {
        "bn": "✨ ৫০০+ শব্দ, ২০টি সেকশন\n📖 অর্থ, উচ্চারণ ও উদাহরণসহ\n\n👇 নিচে থেকে ডাউনলোড করুন:",
        "en": "✨ 500+ words, 20 sections\n📖 With meaning, pronunciation & examples\n\n👇 Download below:",
        "hi": "✨ 500+ शब्द, 20 सेक्शन\n📖 अर्थ, उच्चारण और उदाहरण के साथ\n\n👇 नीचे से डाउनलोड करें:"
    },
    "files_menu_title": {"bn": "📂 ফাইল ও রিসোর্স", "en": "📂 Files & Resources", "hi": "📂 फाइल्स और रिसोर्स"},
    "files_menu_desc": {"bn": "নিচের ফাইলগুলো থেকে বেছে নিন:", "en": "Choose from the files below:", "hi": "नीचे दी गई फाइल्स से चुनें:"},
    "files_none": {"bn": "📂 এখনো কোনো ফাইল আপলোড করা হয়নি।", "en": "📂 No files uploaded yet.", "hi": "📂 अभी तक कोई फाइल अपलोड नहीं की गई।"},
    "file_sending": {"bn": "📤 পাঠানো হচ্ছে...", "en": "📤 Sending...", "hi": "📤 भेजा जा रहा है..."},
    "file_not_found": {"bn": "❌ ফাইল পাওয়া যায়নি।", "en": "❌ File not found.", "hi": "❌ फाइल नहीं मिली।"},
    "file_send_fail": {"bn": "❌ ফাইল পাঠাতে সমস্যা হচ্ছে। পরে আবার চেষ্টা করুন।", "en": "❌ Failed to send file. Please try again later.", "hi": "❌ फाइल भेजने में समस्या।"},
    "admin_only": {"bn": "⛔ শুধু অ্যাডমিন।", "en": "⛔ Admin only.", "hi": "⛔ केवल एडमिन।"},
    "addfile_mode": {"bn": "📎 File Upload Mode চালু হয়েছে!\n\nএখন যেকোনো PDF, DOC বা ফাইল এই চ্যাটে পাঠান।\n\nবাতিল করতে: /cancel", "en": "📎 File Upload Mode ON!\n\nSend any PDF, DOC or file to this chat.\n\nTo cancel: /cancel", "hi": "📎 File Upload Mode चालू!\n\nअब कोई PDF, DOC या फाइल इस चैट में भेजें।\n\nरद्द करने के लिए: /cancel"},
    "addfile_received": {"bn": "📎 File received: {name}\n\nএখন একটি caption লিখুন (বা caption ছাড়াই সেভ করতে /skip পাঠান)।", "en": "📎 File received: {name}\n\nNow type a caption (or send /skip to save without caption).", "hi": "📎 फाइल मिली: {name}\n\nअब कैप्शन लिखें (या /skip भेजें)।"},
    "addfile_saved": {"bn": "✅ File সেভ হয়েছে!\n📎 {name}\n📝 Caption: {caption}\n\nইউজাররা এখন 📂 Files মেনু থেকে এটি পাবে।", "en": "✅ File saved!\n📎 {name}\n📝 Caption: {caption}\n\nUsers can now get it from 📂 Files menu.", "hi": "✅ फाइल सेव हो गई!\n📎 {name}\n📝 कैप्शन: {caption}"},
    "addfile_saved_no_caption": {"bn": "✅ Caption ছাড়াই সেভ হয়েছে!\n📎 {name}", "en": "✅ Saved without caption!\n📎 {name}", "hi": "✅ कैप्शन के बिना सेव!\n📎 {name}"},
    "addfile_save_fail": {"bn": "❌ সেভ করতে ব্যর্থ হয়েছে।", "en": "❌ Save failed.", "hi": "❌ सेव विफल।"},
    "addfile_cancel": {"bn": "✅ File upload বাতিল করা হয়েছে।", "en": "✅ File upload cancelled.", "hi": "✅ फाइल अपलोड रद्द।"},
    "addfile_nothing": {"bn": "⚠️ কোনো pending ফাইল নেই।", "en": "⚠️ No pending file.", "hi": "⚠️ कोई पेंडिंग फाइल नहीं।"},
    "listfiles_empty": {"bn": "📂 এখনো কোনো ফাইল নেই। /addfile দিয়ে যোগ করুন।", "en": "📂 No files yet. Add with /addfile.", "hi": "📂 कोई फाइल नहीं। /addfile से जोड़ें।"},
    "listfiles_header": {"bn": "📂 Saved Files:", "en": "📂 Saved Files:", "hi": "📂 सेव की गई फाइल्स:"},
    "listfiles_footer": {"bn": "মুছতে: /delfile <id>", "en": "To delete: /delfile <id>", "hi": "डिलीट करने के लिए: /delfile <id>"},
    "delfile_usage": {"bn": "Usage: /delfile <id>\n\nআইডি দেখতে: /listfiles", "en": "Usage: /delfile <id>\n\nSee IDs: /listfiles", "hi": "Usage: /delfile <id>"},
    "delfile_done": {"bn": "✅ File {id} মুছে ফেলা হয়েছে।", "en": "✅ File {id} deleted.", "hi": "✅ फाइल {id} डिलीट हो गई।"},
    "delfile_fail": {"bn": "❌ Delete failed.", "en": "❌ Delete failed.", "hi": "❌ डिलीट विफल।"},
    
    # ===== NEW: PRONUNCIATION =====
    "pron_premium": {
        "bn": "🎤 Pronunciation Coach\n\n✨ এটি একটি Premium ফিচার!\n\n🎯 আপনার উচ্চারণ AI দিয়ে বিশ্লেষণ করুন এবং স্কোর পান।\n📊 ভুল শব্দগুলো দেখুন\n🔊 সঠিক উচ্চারণ শুনুন\n\n⭐ Premium কিনে আনলক করুন!",
        "en": "🎤 Pronunciation Coach\n\n✨ This is a Premium feature!\n\n🎯 Practice your English pronunciation and get instant scores.\n📊 See which words to improve\n🔊 Listen to the correct pronunciation\n\n⭐ Buy Premium to unlock!",
        "hi": "🎤 Pronunciation Coach\n\n✨ यह एक Premium फीचर है!\n\n🎯 अपना उच्चारण सुधारें और स्कोर पाएं।\n📊 गलत शब्द देखें\n🔊 सही उच्चारण सुनें\n\n⭐ Premium खरीदें!"
    },
    "pron_title": {"bn": "🎤 Pronunciation Coach", "en": "🎤 Pronunciation Coach", "hi": "🎤 Pronunciation Coach"},
    "pron_read": {"bn": "📝 এই বাক্যটি জোরে পড়ুন:", "en": "📝 Read this sentence aloud:", "hi": "📝 यह वाक्य जोर से पढ़ें:"},
    "pron_send_voice": {"bn": "🎙️ এখন একটি VOICE message পাঠান বাক্যটি পড়ে।", "en": "🎙️ Now send a VOICE message reading it.", "hi": "🎙️ अब VOICE message भेजें।"},
    "pron_cancel_hint": {"bn": "❌ বাতিল করতে: /cancelpronounce", "en": "❌ To cancel: /cancelpronounce", "hi": "❌ रद्द करने के लिए: /cancelpronounce"},
    "pron_new_sentence": {"bn": "🔄 নতুন বাক্য", "en": "🔄 New Sentence", "hi": "🔄 नया वाक्य"},
    "pron_processing": {"bn": "🎤 আপনার উচ্চারণ প্রসেস হচ্ছে...", "en": "🎤 Processing your pronunciation...", "hi": "🎤 आपका उच्चारण प्रोसेस हो रहा है..."},
    "pron_result": {"bn": "🎤 উচ্চারণের স্কোর", "en": "🎤 Pronunciation Score", "hi": "🎤 उच्चारण स्कोर"},
    "pron_target": {"bn": "📝 মূল বাক্য", "en": "📝 Target", "hi": "📝 लक्ष्य"},
    "pron_said": {"bn": "🗣️ আপনি বলেছেন", "en": "🗣️ You said", "hi": "🗣️ आपने कहा"},
    "pron_improve": {"bn": "⚠️ উন্নতির জন্য শব্দ", "en": "⚠️ Words to improve", "hi": "⚠️ सुधार के लिए शब्द"},
    "pron_listen_again": {"bn": "🔊 শুনুন এবং আবার বলুন।", "en": "🔊 Listen and repeat.", "hi": "🔊 सुनें और दोहराएं।"},
    "pron_excellent": {"bn": "🏆 অসাধারণ!", "en": "🏆 Excellent!", "hi": "🏆 शानदार!"},
    "pron_very_good": {"bn": "🎉 খুব ভালো!", "en": "🎉 Very Good!", "hi": "🎉 बहुत अच्छा!"},
    "pron_good": {"bn": "👍 ভালো", "en": "👍 Good", "hi": "👍 अच्छा"},
    "pron_keep_practicing": {"bn": "📚 প্র্যাকটিস চালিয়ে যান", "en": "📚 Keep Practicing", "hi": "📚 अभ्यास जारी रखें"},
    "pron_try_again": {"bn": "🔁 আবার চেষ্টা করুন", "en": "🔁 Try Again", "hi": "🔁 फिर कोशिश करें"},
    "pron_cancelled": {"bn": "✅ Pronunciation mode বাতিল।", "en": "✅ Pronunciation mode cancelled.", "hi": "✅ उच्चारण मोड रद्द।"},
    "pron_not_in": {"bn": "⚠️ আপনি Pronunciation mode-এ নেই।", "en": "⚠️ Not in pronunciation mode.", "hi": "⚠️ Pronunciation मोड में नहीं।"},
    
    # ===== NEW: IELTS SPEAKING =====
    "ielts_premium": {
        "bn": "🎯 IELTS Speaking Simulator\n\n✨ এটি একটি Premium ফিচার!\n\n🎯 পূর্ণ IELTS Speaking Test (Part 1+2+3)\n📊 AI Band Score + Detailed Feedback\n🎤 ভয়েস বা টেক্সট — যেভাবে সুবিধা\n\n⭐ Premium কিনে আনলক করুন!",
        "en": "🎯 IELTS Speaking Simulator\n\n✨ This is a Premium feature!\n\n🎯 Full IELTS Speaking Test (Part 1+2+3)\n📊 AI Band Score + Detailed Feedback\n🎤 Voice or Text — your choice\n\n⭐ Buy Premium to unlock!",
        "hi": "🎯 IELTS Speaking Simulator\n\n✨ यह एक Premium फीचर है!\n\n🎯 पूरा IELTS Speaking Test\n📊 AI Band Score + Feedback\n\n⭐ Premium खरीदें!"
    },
    "ielts_title": {"bn": "🎯 IELTS Speaking Simulator", "en": "🎯 IELTS Speaking Simulator", "hi": "🎯 IELTS Speaking Simulator"},
    "ielts_welcome": {
        "bn": "🎯 IELTS Speaking Simulator\n\nস্বাগতম! এই টেস্টে ৩টি অংশ থাকবে:\n• Part 1: পরিচিতি (৫টি প্রশ্ন)\n• Part 2: Cue Card (১টি টপিক, ২ মিনিট)\n• Part 3: আলোচনা (৪টি প্রশ্ন)\n\n⏱️ মোট সময়: ১০-১৫ মিনিট\n\nশেষে আপনি পাবেন:\n📊 Band Score (০-৯)\n📈 Fluency, Vocabulary, Grammar, Pronunciation — আলাদা স্কোর\n💡 উন্নতির পরামর্শ\n\n👉 আপনি Text বা Voice — যেভাবেই উত্তর দিতে পারবেন।\n\nচলুন শুরু করি!",
        "en": "🎯 IELTS Speaking Simulator\n\nWelcome! The test has 3 parts:\n• Part 1: Interview (5 questions)\n• Part 2: Cue Card (1 topic, 2 minutes)\n• Part 3: Discussion (4 questions)\n\n⏱️ Total time: 10-15 minutes\n\nAt the end you will get:\n📊 Band Score (0-9)\n📈 Fluency, Vocabulary, Grammar, Pronunciation — separate scores\n💡 Personalized feedback\n\n👉 You can answer by Text or Voice.\n\nLet's begin!",
        "hi": "🎯 IELTS Speaking Simulator\n\nस्वागत! 3 भाग होंगे:\n• Part 1: Interview (5 प्रश्न)\n• Part 2: Cue Card\n• Part 3: Discussion (4 प्रश्न)\n\nशुरू करें!"
    },
    "ielts_part1_start": {"bn": "📍 Part 1 — Interview\n\nপ্রশ্ন {n}/৫:", "en": "📍 Part 1 — Interview\n\nQuestion {n}/5:", "hi": "📍 Part 1 — Interview\n\nप्रश्न {n}/5:"},
    "ielts_part2_start": {
        "bn": "📍 Part 2 — Cue Card\n\n⏱️ আপনার ১ মিনিট প্রস্তুতির সময় আছে।\n🎙️ তারপর ২ মিনিট বলুন।\n\n📋 আপনার টপিক:\n\n{cue}\n\nপ্রস্তুতি নিয়ে শুরু করুন।",
        "en": "📍 Part 2 — Cue Card\n\n⏱️ You have 1 minute to prepare.\n🎙️ Then speak for 2 minutes.\n\n📋 Your topic:\n\n{cue}\n\nTake your time and begin.",
        "hi": "📍 Part 2 — Cue Card\n\n⏱️ 1 मिनट तैयारी करें।\n🎙️ फिर 2 मिनट बोलें।\n\n📋 आपका टॉपिक:\n\n{cue}"
    },
    "ielts_part3_start": {"bn": "📍 Part 3 — Discussion\n\nপ্রশ্ন {n}/৪:", "en": "📍 Part 3 — Discussion\n\nQuestion {n}/4:", "hi": "📍 Part 3 — Discussion\n\nप्रश्न {n}/4:"},
    "ielts_analyzing": {"bn": "📊 আপনার স্পিকিং বিশ্লেষণ করা হচ্ছে...", "en": "📊 Analyzing your speaking...", "hi": "📊 आपकी स्पीकिंग का विश्लेषण हो रहा है..."},
    "ielts_done": {"bn": "✅ IELTS Speaking Test সম্পন্ন!", "en": "✅ IELTS Speaking Test Complete!", "hi": "✅ IELTS Speaking Test पूरा!"},
    "ielts_cancel": {"bn": "❌ টেস্ট বাতিল করতে: /cancelielts", "en": "❌ To cancel: /cancelielts", "hi": "❌ रद्द करने के लिए: /cancelielts"},
    "ielts_cancelled": {"bn": "✅ IELTS Test বাতিল করা হয়েছে।", "en": "✅ IELTS test cancelled.", "hi": "✅ IELTS टेस्ट रद्द।"},
    "ielts_not_in": {"bn": "⚠️ আপনি IELTS test-এ নেই।", "en": "⚠️ Not in IELTS test.", "hi": "⚠️ IELTS टेस्ट में नहीं।"},
    "ielts_answer_too_short": {"bn": "⚠️ একটু বড় উত্তর দিন (অন্তত ২-৩ লাইন)।", "en": "⚠️ Please give a longer answer (2-3 sentences).", "hi": "⚠️ लंबा उत्तर दें।"},
    "ielts_end_btn": {"bn": "🛑 Test শেষ করুন", "en": "🛑 End Test", "hi": "🛑 टेस्ट खत्म करें"},
    
    # ===== NEW: PDF QUIZ =====
    "pdfquiz_premium": {
        "bn": "🧠 Quiz from Your PDF\n\n✨ এটি একটি Premium ফিচার!\n\n🎯 যেকোনো PDF পাঠান\n🤖 AI ১০টি MCQ বানাবে\n📊 আপনি উত্তর দিয়ে স্কোর পাবেন\n💡 প্রতিটি উত্তরের ব্যাখ্যা\n\n⭐ Premium কিনে আনলক করুন!",
        "en": "🧠 Quiz from Your PDF\n\n✨ This is a Premium feature!\n\n🎯 Send any PDF\n🤖 AI creates 10 MCQs from it\n📊 Answer and get your score\n💡 Explanation for each answer\n\n⭐ Buy Premium to unlock!",
        "hi": "🧠 Quiz from Your PDF\n\n✨ यह एक Premium फीचर है!\n\n🎯 कोई PDF भेजें\n🤖 AI 10 MCQ बनाएगा\n\n⭐ Premium खरीदें!"
    },
    "pdfquiz_title": {"bn": "🧠 Quiz from PDF", "en": "🧠 Quiz from PDF", "hi": "🧠 Quiz from PDF"},
    "pdfquiz_prompt": {
        "bn": "🧠 Quiz from PDF\n\n📄 এখন আপনার PDF পাঠান।\n🤖 AI সেটা পড়ে ১০টি MCQ বানাবে।\n\n❌ বাতিল করতে: /cancelpdfquiz",
        "en": "🧠 Quiz from PDF\n\n📄 Now send your PDF.\n🤖 AI will create 10 MCQs from it.\n\n❌ To cancel: /cancelpdfquiz",
        "hi": "🧠 Quiz from PDF\n\n📄 अब PDF भेजें।\n🤖 AI 10 MCQ बनाएगा।\n\n❌ रद्द करें: /cancelpdfquiz"
    },
    "pdfquiz_processing": {"bn": "📄 PDF পড়া হচ্ছে...", "en": "📄 Reading PDF...", "hi": "📄 PDF पढ़ रहा हूँ..."},
    "pdfquiz_generating": {"bn": "🤖 AI কুইজ তৈরি করছে...", "en": "🤖 AI is generating quiz...", "hi": "🤖 AI क्विज़ बना रहा है..."},
    "pdfquiz_fail": {"bn": "❌ কুইজ তৈরি করতে পারিনি। অন্য PDF চেষ্টা করুন।", "en": "❌ Could not generate quiz. Try another PDF.", "hi": "❌ क्विज़ नहीं बना।"},
    "pdfquiz_q": {"bn": "❓ প্রশ্ন {n}/10", "en": "❓ Question {n}/10", "hi": "❓ प्रश्न {n}/10"},
    "pdfquiz_score": {"bn": "📊 আপনার স্কোর", "en": "📊 Your Score", "hi": "📊 आपका स्कोर"},
    "pdfquiz_correct": {"bn": "✅ সঠিক!", "en": "✅ Correct!", "hi": "✅ सही!"},
    "pdfquiz_wrong": {"bn": "❌ ভুল!", "en": "❌ Wrong!", "hi": "❌ गलत!"},
    "pdfquiz_answer": {"bn": "✅ সঠিক উত্তর", "en": "✅ Correct answer", "hi": "✅ सही उत्तर"},
    "pdfquiz_cancelled": {"bn": "✅ PDF Quiz বাতিল করা হয়েছে।", "en": "✅ PDF Quiz cancelled.", "hi": "✅ PDF Quiz रद्द।"},
    "pdfquiz_not_in": {"bn": "⚠️ আপনি PDF Quiz mode-এ নেই।", "en": "⚠️ Not in PDF Quiz mode.", "hi": "⚠️ PDF Quiz में नहीं।"},
    "pdfquiz_done": {"bn": "🎉 কুইজ শেষ!", "en": "🎉 Quiz Complete!", "hi": "🎉 क्विज़ पूरा!"},
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
# GROQ PROMPTS
# ==========================================================
groq_client = Groq(api_key=GROQ_API_KEY)

PROMPT_BEGINNER = """
You are EduMate AI, a patient English teacher for beginners.
1. Language Rule: Reply in the SAME language the user wrote in. If English -> very simple English. If Bangla -> simple Bangla. DO NOT just translate the user's message.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use asterisks (*), bold (**), or markdown.
3. Tone: Be highly encouraging. Keep responses short (under 1500 characters).
4. Chat naturally. DO NOT turn the conversation into a dictionary.

⚠️ CRITICAL INSTRUCTION: You MUST ALWAYS end your response with exactly 3 follow-up questions.
Format them EXACTLY like this at the very end: [SUGGESTIONS] Question 1 | Question 2 | Question 3
"""

PROMPT_INTERMEDIATE = """
You are EduMate AI, an English tutor for intermediate learners.
1. Language Rule: Reply in the user's language. If English -> 90% English. If Bangla -> 50% Bangla, 50% English. Chat naturally, DO NOT just translate.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use asterisks (*), bold (**), or markdown.
3. Style: Moderate length (under 2500 characters), engaging, correct mistakes gently.

⚠️ CRITICAL INSTRUCTION: You MUST ALWAYS end your response with exactly 3 follow-up questions.
Format them EXACTLY like this at the very end: [SUGGESTIONS] Question 1 | Question 2 | Question 3
"""

PROMPT_ADVANCED = """
You are EduMate AI, a strict IELTS examiner.
1. Language Rule: Reply ONLY in English, regardless of the user's language. If the user writes in Bangla, politely ask them to try English.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use asterisks (*), bold (**), or markdown.
3. Style: Advanced vocabulary (under 3500 characters), strict error correction.

⚠️ CRITICAL INSTRUCTION: You MUST ALWAYS end your response with exactly 3 follow-up questions.
Format them EXACTLY like this at the very end: [SUGGESTIONS] Question 1 | Question 2 | Question 3
"""


def build_user_context(user, include_name=True):
    if not user:
        return ""
    parts = []
    if include_name and user.get("name"):
        parts.append(f"User's name: {user['name']}")
    if user.get("level"):
        parts.append(f"Level: {user['level']}")
    if user.get("streak"):
        parts.append(f"Streak: {user['streak']} days")
    if user.get("words_learned"):
        parts.append(f"Words learned: {user['words_learned']}")
    if not parts:
        return ""
    return "\nUSER CONTEXT: " + " | ".join(parts) + "\nUse this info naturally if relevant."


def ask_groq(user_text, history=None, user=None, custom_system=None, json_mode=False):
    try:
        if custom_system:
            system = custom_system
        else:
            user_level = (user or {}).get("level", "beginner").lower()
            if user_level == "advanced":
                system = PROMPT_ADVANCED
            elif user_level == "intermediate":
                system = PROMPT_INTERMEDIATE
            else:
                system = PROMPT_BEGINNER
        
        if not json_mode:
            system += build_user_context(user, include_name=True)
        
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": user_text})
        
        kwargs = {
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.4,
            "max_tokens": 1200,
        }
        response = groq_client.chat.completions.create(**kwargs)
        raw_text = response.choices[0].message.content.strip()
        if not raw_text:
            return "", []
        
        suggestions = []
        if "[SUGGESTIONS]" in raw_text:
            parts = raw_text.split("[SUGGESTIONS]")
            answer = parts[0].strip()
            sug_raw = parts[1].strip()
            
            sug_clean = re.sub(r'[\|\n,]', '|||', sug_raw)
            sug_list = [s.strip() for s in sug_clean.split("|||") if s.strip()]
            
            for s in sug_list[:3]:
                s = re.sub(r'^[\d\-\*\.\)\s]+', '', s).strip()
                if s:
                    suggestions.append(s)
                    
            return answer, suggestions
        return raw_text, []
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return None, []


async def text_to_voice(text, output_path):
    try:
        import edge_tts
        clean_text = text.replace("*", "").replace("_", "").replace("`", "").strip()
        if not clean_text:
            return False
        communicate = edge_tts.Communicate(clean_text, TTS_VOICE)
        await communicate.save(output_path)
        return True
    except Exception as e:
        logger.error(f"TTS generation failed: {e}")
        return False


def extract_correction(answer):
    try:
        if "❌ Wrong:" in answer and "✅ Correct:" in answer:
            wrong = answer.split("❌ Wrong:")[1].split("✅")[0].strip().split("\n")[0].strip()
            correct = answer.split("✅ Correct:")[1].split("📝")[0].split("\n")[0].strip()
            if wrong and correct and len(wrong) < 250 and len(correct) < 250:
                return wrong, correct
    except Exception:
        pass
    return None


def transcribe_sync(voice_path):
    try:
        with open(voice_path, "rb") as f:
            response = groq_client.audio.transcriptions.create(
                file=("voice.ogg", f.read()),
                model=WHISPER_MODEL,
            )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Whisper error: {e}")
        return None


def analyze_image_sync(image_path, prompt):
    try:
        with open(image_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        system_rules = (
            "You analyze images for English learners. "
            "CRITICAL FORMATTING RULES: "
            "1. NEVER use markdown (no *, **, __, ```, ###, ---). "
            "2. Use PLAIN TEXT only with emojis. "
            "3. Use emojis as bullets: 🔷 👉 ✏️ 📝 ✅ ❌ 🎯 📚 💡 🔊 🔁 ⭐ 🔥. "
            "4. Separate each item with a BLANK LINE. "
            "5. Keep responses under 1500 characters. "
            "6. Reply in the user's language (Bangla for Bangla users). "
            "7. Start with a 1-line summary, then bullet points."
        )
        response = groq_client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {"role": "system", "content": system_rules},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Describe this image briefly."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_data}"}}
                    ]
                }
            ],
            temperature=0.4,
            max_tokens=800,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Vision error: {e}")
        return None


def extract_pdf_text_sync(pdf_path, max_chars=6000):
    try:
        if not HAS_PDF:
            return None
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        text_parts = []
        pages_to_read = min(total_pages, MAX_PDF_PAGES)
        for i in range(pages_to_read):
            try:
                page = reader.pages[i]
                txt = page.extract_text() or ""
                if txt.strip():
                    text_parts.append(f"[Page {i+1}]\n{txt}")
            except Exception:
                continue
            if sum(len(x) for x in text_parts) > max_chars:
                break
        full_text = "\n\n".join(text_parts).strip()
        if not full_text:
            return None
        if len(full_text) > max_chars:
            full_text = full_text[:max_chars] + "\n\n[... truncated ...]"
        return full_text, total_pages
    except Exception as e:
        logger.error(f"PDF extract error: {e}")
        return None


def calculate_pronunciation_score(target, said):
    """Returns (score, wrong_words_list)"""
    def clean(s):
        return re.sub(r'[^\w\s]', ' ', s.lower()).split()
    
    target_words = clean(target)
    said_words = clean(said)
    
    if not target_words:
        return 0, []
    
    # Overall similarity
    matcher = difflib.SequenceMatcher(None, target_words, said_words)
    score = int(matcher.ratio() * 100)
    
    # Find wrong words
    wrong = []
    sm = difflib.SequenceMatcher(None, target_words, said_words)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != 'equal':
            wrong_segment = " ".join(target_words[i1:i2]).strip()
            if wrong_segment:
                wrong.append(wrong_segment)
    
    return score, wrong[:8]


def parse_quiz_json(text):
    """Extract JSON array from AI response"""
    if not text:
        return None
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, list) or len(data) == 0:
            return None
        # Validate structure
        for item in data:
            if not all(k in item for k in ("q", "options", "answer")):
                return None
            if not isinstance(item["options"], list) or len(item["options"]) < 2:
                return None
            if not isinstance(item["answer"], int):
                return None
        return data[:10]  # Max 10 questions
    except Exception as e:
        logger.error(f"Quiz JSON parse error: {e}")
        return None


# ==========================================================
# DATABASE
# ==========================================================
db_pool = None
_mem_users = {}
_mem_history = {}
_mem_review = []


async def init_db():
    global db_pool
    logger.info("========== DB INIT START ==========")
    logger.info(f"DATABASE_URL present? {bool(DATABASE_URL)}")
    logger.info(f"HAS_ASYNCPG? {HAS_ASYNCPG}")

    if not DATABASE_URL:
        logger.warning("DB DISABLED: DATABASE_URL is empty")
        db_pool = None
        return

    if not HAS_ASYNCPG:
        logger.warning("DB DISABLED: asyncpg not installed")
        db_pool = None
        return

    url = DATABASE_URL.strip().replace("\n", "").replace("\r", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    logger.info(f"Attempting DB connect...")

    try:
        db_pool = await asyncio.wait_for(
            asyncpg.create_pool(url, min_size=1, max_size=5),
            timeout=60.0
        )
        logger.info("*** DB POOL CREATED ***")
    except asyncio.TimeoutError:
        logger.error("*** DB TIMEOUT ***")
        db_pool = None
        return
    except Exception as e:
        logger.error(f"*** DB CONNECT FAILED: {type(e).__name__}: {e} ***")
        db_pool = None
        return

    try:
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
                    voice_count_today INTEGER DEFAULT 0,
                    img_count_today INTEGER DEFAULT 0,
                    pdf_count_today INTEGER DEFAULT 0,
                    last_voice_date DATE,
                    last_img_date DATE,
                    last_pdf_date DATE,
                    photos_sent INTEGER DEFAULT 0,
                    voices_sent INTEGER DEFAULT 0,
                    pdfs_sent INTEGER DEFAULT 0,
                    roleplay_count INTEGER DEFAULT 0,
                    review_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    role VARCHAR(20),
                    content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sh_user ON s_history(user_id)")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_mistakes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    wrong_text TEXT,
                    corrected_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_feedback (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    message_id BIGINT,
                    rating VARCHAR(10),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_review (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    wrong_text TEXT,
                    corrected_text TEXT,
                    review_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    reviewed_at TIMESTAMP
                )
            """)
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_sr_user ON s_review(user_id)")
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS s_files (
                    id SERIAL PRIMARY KEY,
                    file_id TEXT UNIQUE,
                    file_name TEXT,
                    caption TEXT,
                    uploaded_by BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            for col_name, col_def in [
                ("pdf_count_today", "INTEGER DEFAULT 0"),
                ("last_pdf_date", "DATE"),
                ("pdfs_sent", "INTEGER DEFAULT 0"),
            ]:
                try:
                    await conn.execute(
                        f"ALTER TABLE s_users ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
                    )
                except Exception:
                    pass
        logger.info("*** ALL TABLES CREATED ***")
    except Exception as e:
        logger.error(f"*** TABLE CREATE FAILED: {e} ***")

    logger.info(f"========== DB INIT END (db_pool={'OK' if db_pool else 'NONE'}) ==========")


async def keep_alive_db():
    while True:
        try:
            if db_pool:
                async with db_pool.acquire() as conn:
                    await conn.execute("SELECT 1")
                logger.info("DB Keep-Alive: Success")
            await asyncio.sleep(180)
        except Exception as e:
            logger.error(f"DB Keep-Alive error: {e}")
            await asyncio.sleep(60)


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
                "remind_at": None, "voice_count_today": 0,
                "img_count_today": 0, "pdf_count_today": 0,
                "last_voice_date": None, "last_img_date": None,
                "last_pdf_date": None,
                "photos_sent": 0, "voices_sent": 0, "pdfs_sent": 0,
                "roleplay_count": 0, "review_count": 0,
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


async def save_review(uid, wrong, correct):
    next_review = datetime.now() + timedelta(days=1)
    if db_pool is None:
        _mem_review.append({
            "user_id": uid, "wrong": wrong, "correct": correct,
            "review_at": next_review, "reviewed": False
        })
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_review (user_id, wrong_text, corrected_text, review_at) "
                "VALUES ($1, $2, $3, $4)",
                uid, wrong, correct, next_review,
            )
    except Exception as e:
        logger.error(f"save_review: {e}")


async def get_due_reviews(uid, limit=3):
    if db_pool is None:
        now = datetime.now()
        due = [r for r in _mem_review
               if r["user_id"] == uid and not r["reviewed"] and r["review_at"] <= now]
        return due[:limit]
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, wrong_text, corrected_text FROM s_review "
                "WHERE user_id = $1 AND reviewed_at IS NULL AND review_at <= NOW() "
                "ORDER BY review_at ASC LIMIT $2",
                uid, limit
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def mark_reviewed(review_id):
    if db_pool is None:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE s_review SET reviewed_at = NOW() WHERE id = $1", review_id,
            )
    except Exception:
        pass


async def save_file(file_id, file_name, caption, uploaded_by):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_files (file_id, file_name, caption, uploaded_by) "
                "VALUES ($1, $2, $3, $4) ON CONFLICT (file_id) DO NOTHING",
                file_id, file_name, caption, uploaded_by
            )
        return True
    except Exception as e:
        logger.error(f"save_file: {e}")
        return False


async def get_all_files():
    if db_pool is None:
        return []
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, file_name, caption FROM s_files ORDER BY id DESC"
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def get_file_by_db_id(fid):
    if db_pool is None:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT file_id, file_name, caption FROM s_files WHERE id = $1", fid
            )
            return dict(row) if row else None
    except Exception:
        return None


async def delete_file(fid):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("DELETE FROM s_files WHERE id = $1", fid)
        return True
    except Exception:
        return False


# ==========================================================
# FORCE SUBSCRIBE
# ==========================================================
async def is_user_joined(bot, user_id):
    if not FORCE_SUB_GROUP_ID:
        return True
    try:
        try:
            chat_id = int(FORCE_SUB_GROUP_ID)
        except ValueError:
            chat_id = FORCE_SUB_GROUP_ID
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator", "member", "restricted")
    except Exception as e:
        logger.error(f"ForceSub check error: {e}")
        return True


def force_sub_kb(lang="bn"):
    join_url = FORCE_SUB_GROUP_LINK or "https://t.me/friendships_hub"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(t("force_sub_join_btn", lang), url=join_url)],
        [InlineKeyboardButton(t("force_sub_check_btn", lang), callback_data="forcesub_check")],
    ])


async def send_force_sub_message(message, lang="bn"):
    await message.reply_text(
        f"{t('force_sub_title', lang)}\n\n{t('force_sub_desc', lang)}",
        reply_markup=force_sub_kb(lang),
    )


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
        [InlineKeyboardButton("🎭 Role-Play", callback_data="rp_menu"),
         InlineKeyboardButton("🔁 Review", callback_data="m_review")],
        [InlineKeyboardButton("🎯 Quiz", callback_data="m_quiz"),
         InlineKeyboardButton("💬 Translate", callback_data="m_translate")],
        [InlineKeyboardButton("🔥 Daily Lesson", callback_data="m_daily"),
         InlineKeyboardButton("📖 Word of Day", callback_data="m_word")],
        [InlineKeyboardButton("📇 Flashcards", callback_data="m_flashcard"),
         InlineKeyboardButton("🎮 Word Game", callback_data="m_game")],
        [InlineKeyboardButton("🎤 Pronunciation", callback_data="m_pronounce"),
         InlineKeyboardButton("🎯 IELTS Speaking", callback_data="m_ielts")],
        [InlineKeyboardButton("🧠 Quiz from PDF", callback_data="m_pdfquiz")],
        [InlineKeyboardButton("📘 Vocabulary Book", callback_data="m_vocab_book"),
         InlineKeyboardButton("📂 Files / Resources", callback_data="m_files")],
        [InlineKeyboardButton("📊 My Progress", callback_data="m_profile"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="m_leaderboard")],
        [InlineKeyboardButton("🎁 Invite & Earn", callback_data="m_invite"),
         InlineKeyboardButton("⭐ Premium", callback_data="m_premium")],
        [InlineKeyboardButton("📚 My Mistakes", callback_data="m_mistakes"),
         InlineKeyboardButton("🏅 Achievements", callback_data="m_achievements")],
        [InlineKeyboardButton("🧠 Memory", callback_data="m_memory"),
         InlineKeyboardButton("🌍 Language", callback_data="m_lang")],
        [InlineKeyboardButton("🆘 Support", callback_data="m_support"),
         InlineKeyboardButton("ℹ️ Help", callback_data="m_help")],
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


def feedback_kb(message_id):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👍", callback_data=f"fb_good_{message_id}"),
         InlineKeyboardButton("👎", callback_data=f"fb_bad_{message_id}")]
    ])


def practice_menu_kb(lang="bn"):
    rows = []
    for key, sc in ROLEPLAY_SCENARIOS.items():
        title = sc["title"].get(lang) or sc["title"].get("en")
        rows.append([InlineKeyboardButton(f"{sc['emoji']} {title}", callback_data=f"rp_{key}")])
    rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])
    return InlineKeyboardMarkup(rows)


def merge_keyboards(kb1, kb2):
    if not kb1: return kb2
    if not kb2: return kb1
    return InlineKeyboardMarkup(kb1.inline_keyboard + kb2.inline_keyboard)


def suggestions_kb(suggestions, context):
    if not suggestions:
        return None
    context.user_data['cached_suggestions'] = suggestions
    rows = []
    for i, s in enumerate(suggestions[:3]):
        display_text = s if len(s) < 35 else s[:32] + "..."
        rows.append([InlineKeyboardButton(f"👉 {display_text}", callback_data=f"sg_{i}")])
    return InlineKeyboardMarkup(rows)


# ==========================================================
# SAFE EDIT / REPLY
# ==========================================================
async def safe_reply(message, text, reply_markup=None):
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await message.reply_text(text, reply_markup=reply_markup)
        return True
    except Exception as e:
        logger.error(f"reply fail: {e}")
        return False


async def safe_reply_feedback(message, text, msg_id, extra_kb=None):
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        fb_markup = feedback_kb(msg_id)
        final_markup = merge_keyboards(extra_kb, fb_markup) if extra_kb else fb_markup
        await message.reply_text(text, reply_markup=final_markup)
        return True
    except Exception:
        return await safe_reply(message, text)


async def safe_edit(query, text, reply_markup=None):
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await query.edit_message_text(text, reply_markup=reply_markup)
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return True
    except Exception as e:
        logger.error(f"edit fail: {e}")
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
        "photo_5": lambda u: (u.get("photos_sent") or 0) >= 5,
        "voice_10": lambda u: (u.get("voices_sent") or 0) >= 10,
        "roleplay_5": lambda u: (u.get("roleplay_count") or 0) >= 5,
        "review_10": lambda u: (u.get("review_count") or 0) >= 10,
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
    for key in ["roleplay", "awaiting_payment", "payment_method", "awaiting_support",
                "game_active", "awaiting_file", "awaiting_file_caption",
                "pending_file_id", "pending_file_name", "pronunciation_mode",
                "ielts_speaking", "pdf_quiz", "pdf_quiz_mode"]:
        context.user_data.pop(key, None)
    if not await is_user_joined(context.bot, u.id):
        existing = await get_user(u.id)
        lang = (existing or {}).get("language") or "bn"
        await send_force_sub_message(update.message, lang)
        return
    existing = await get_user(u.id)
    if not existing:
        await create_user(u.id, u.full_name or "Student")
        await update.message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())
        args = context.args or []
        if args and args[0].startswith("ref_"):
            try:
                context.user_data["pending_ref"] = int(args[0][4:])
            except Exception:
                pass
        return
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
    await safe_reply(update.message, t("welcome", lang, name=u.first_name or "Student"))
    await update.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


async def menu_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    for key in ["roleplay", "awaiting_payment", "payment_method", "awaiting_support",
                "game_active", "pronunciation_mode", "ielts_speaking", "pdf_quiz", "pdf_quiz_mode"]:
        context.user_data.pop(key, None)
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


async def practice_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        f"{t('practice_title', lang)}\n\n{t('practice_desc', lang)}",
        reply_markup=practice_menu_kb(lang),
    )


async def end_roleplay_command(update, context):
    lang = await get_user_lang(update.effective_user.id)
    if context.user_data.get("roleplay"):
        context.user_data.pop("roleplay", None)
        await update.message.reply_text(t("rp_ended", lang))
    else:
        await update.message.reply_text(t("rp_not_in", lang))


async def review_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    due = await get_due_reviews(uid, limit=3)
    if not due:
        await update.message.reply_text(t("review_none", lang))
        return
    context.user_data["review_queue"] = due
    context.user_data["review_index"] = 0
    first = due[0]
    await update.message.reply_text(t("review_prompt", lang, wrong=first["wrong_text"]))


async def endgame_command(update, context):
    lang = await get_user_lang(update.effective_user.id)
    if context.user_data.get('game_active'):
        context.user_data['game_active'] = False
        score = context.user_data.get('game_score', 0)
        context.user_data['game_score'] = 0
        await update.message.reply_text(
            f"{t('game_over_title', lang)}\n\n"
            f"{t('game_total_score', lang, score=score)}\n\n"
            f"{t('game_play_again', lang)}"
        )
    else:
        await update.message.reply_text(t("game_not_in", lang))


async def memory_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", lang))
        return
    text = (
        f"{t('memory_title', lang)}\n\n"
        f"📛 {t('name', lang)}: {user.get('name')}\n"
        f"🎓 {t('level', lang)}: {user.get('level')}\n"
        f"🪙 {t('coins', lang)}: {user.get('coins') or 0}\n"
        f"🔥 {t('streak', lang)}: {user.get('streak') or 0} {t('days', lang)}\n"
        f"📚 {t('words_learned', lang)}: {user.get('words_learned') or 0}\n"
        f"🎯 {t('quizzes', lang)}: {user.get('quizzes_taken') or 0}\n"
        f"📸 Photos sent: {user.get('photos_sent') or 0}\n"
        f"🎤 Voices sent: {user.get('voices_sent') or 0}\n"
        f"📄 PDFs sent: {user.get('pdfs_sent') or 0}\n"
        f"🎭 Role-plays: {user.get('roleplay_count') or 0}\n"
        f"🔁 Reviews: {user.get('review_count') or 0}\n"
        f"🌍 Language: {user.get('language') or 'bn'}"
    )
    await update.message.reply_text(text)


async def help_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    lang = await get_user_lang(update.effective_user.id)
    if lang == "en":
        text = (
            "📖 Help\n\n"
            "/start - Main menu\n/menu - Menu\n/profile - Profile\n"
            "/practice - 🎭 Role-Play\n/review - 🔁 Spaced review\n"
            "/memory - 🧠 What I remember\n/endroleplay - End role-play\n"
            "/endgame - Stop Word Game\n"
            "/daily - Daily lesson\n/leaderboard - Leaderboard\n"
            "/coins - Balance\n/invite - Invite link\n"
            "/mistakes - Mistakes\n/achievements - Badges\n"
            "/level - Set level\n/reminder - Reminder\n"
            "/language - Change language\n/reset - Clear chat\n"
            "/pronounce - 🎤 Pronunciation Coach (Premium)\n"
            "/ielts - 🎯 IELTS Speaking Simulator (Premium)\n"
            "/pdfquiz - 🧠 Quiz from PDF (Premium)\n\n"
            "📸 Send photo, 🎤 voice, 📄 PDF, 👍👎 rate replies\n"
            "🆘 Need help? Use the Support button or contact @asikul_echo"
        )
    elif lang == "hi":
        text = (
            "📖 सहायता\n\n"
            "/start - मुख्य\n/menu - मेनू\n/profile - प्रोफ़ाइल\n"
            "/practice - 🎭 Role-Play\n/review - 🔁 रिव्यू\n"
            "/pronounce - 🎤 Pronunciation Coach\n"
            "/ielts - 🎯 IELTS Speaking Simulator\n"
            "/pdfquiz - 🧠 Quiz from PDF\n"
            "🆘 सहायता: @asikul_echo"
        )
    else:
        text = (
            "📖 সাহায্য\n\n"
            "/start - মেইন মেনু\n/menu - মেনু\n/profile - প্রোফাইল\n"
            "/practice - 🎭 Role-Play\n/review - 🔁 Spaced Review\n"
            "/memory - 🧠 আমি যা মনে রেখেছি\n/endroleplay - Role-Play বন্ধ\n"
            "/endgame - Word Game বন্ধ\n"
            "/daily - Daily Lesson\n/leaderboard - লিডারবোর্ড\n"
            "/coins - কয়েন\n/invite - ইনভাইট\n"
            "/mistakes - ভুল\n/achievements - ব্যাজ\n"
            "/level - লেভেল\n/reminder - রিমাইন্ডার\n"
            "/language - ভাষা\n/reset - চ্যাট ক্লিয়ার\n\n"
            "🎤 /pronounce - Pronunciation Coach (Premium)\n"
            "🎯 /ielts - IELTS Speaking Simulator (Premium)\n"
            "🧠 /pdfquiz - Quiz from PDF (Premium)\n\n"
            "📸 ছবি, 🎤 ভয়েস, 📄 PDF পাঠান, 👍👎 রেটিং দিন\n"
            "🆘 সাপোর্ট: @asikul_echo"
        )
    await update.message.reply_text(text)


async def profile_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
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
        f"📸 Photos: {user.get('photos_sent') or 0}\n"
        f"🎤 Voices: {user.get('voices_sent') or 0}\n"
        f"📄 PDFs: {user.get('pdfs_sent') or 0}\n"
        f"🎭 Role-plays: {user.get('roleplay_count') or 0}\n"
        f"🔁 Reviews: {user.get('review_count') or 0}\n"
        f"{t('premium_status', lang)}: {status}"
    )


async def daily_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    user = await get_user(uid)
    await update.message.chat.send_action("typing")
    answer, suggestions = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word (with meaning + pronunciation + example), "
        "1 grammar tip with 2 examples, 1 practice question. Plain text.",
        None, user
    )
    if not answer:
        answer = "📚 Word: Persistent - Meaning: continuing firmly\nExample: Be persistent."
    kb = suggestions_kb(suggestions, context)
    await safe_reply(
        update.message,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n\n{answer}",
        reply_markup=kb
    )


async def fetch_leaderboard():
    if db_pool is None:
        return sorted(_mem_users.values(),
                     key=lambda x: (x.get("quiz_score", 0), x.get("words_learned", 0)),
                     reverse=True)[:10]
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, quiz_score, words_learned, streak FROM s_users "
                "ORDER BY quiz_score DESC, words_learned DESC LIMIT 10"
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def leaderboard_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    lang = await get_user_lang(update.effective_user.id)
    rows = await fetch_leaderboard()
    if not rows:
        await update.message.reply_text(t("no_users", lang))
        return
    text = f"{t('leaderboard_title', lang)}\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        text += f"{m} {r.get('name', '?')} - ⭐ {r.get('quiz_score', 0)}\n"
    await safe_reply(update.message, text)


async def coins_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", lang))
        return
    status = t("active", lang) if user.get("is_premium") else t("inactive", lang)
    await safe_reply(
        update.message,
        f"{t('coins', lang)}: {user.get('coins') or 0}\n{t('premium_status', lang)}: {status}"
    )


async def invite_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_reply(
        update.message,
        f"{t('invite_title', lang)}\n\n{link}\n\n{t('invite_hint', lang, n=REFERRAL_REWARD)}"
    )


async def mistakes_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    if db_pool is None:
        await update.message.reply_text(t("mistakes_none", lang))
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT wrong_text, corrected_text FROM s_review "
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


async def achievements_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user:
        await update.message.reply_text(t("start_first", lang))
        return
    await safe_reply(update.message, f"{t('achievements_title', lang)}\n\n{achievements_text(user, lang)}")


async def level_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    lang = await get_user_lang(update.effective_user.id)
    await update.message.reply_text(
        t("choose_level", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Beginner", callback_data="setlvl_beginner")],
            [InlineKeyboardButton("🟡 Intermediate", callback_data="setlvl_intermediate")],
            [InlineKeyboardButton("🔴 Advanced", callback_data="setlvl_advanced")],
        ]),
    )


async def reminder_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
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


async def language_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    await update.message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())


async def reset_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    await clear_history(uid)
    for key in ["roleplay", "review_queue", "review_index", "awaiting_payment",
                "payment_method", "awaiting_support", "game_active",
                "pronunciation_mode", "ielts_speaking", "pdf_quiz", "pdf_quiz_mode"]:
        context.user_data.pop(key, None)
    await update.message.reply_text(t("reset_done", lang))


async def adminstats_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    if db_pool is None:
        await update.message.reply_text(
            f"📊 Admin Stats\n\n👥 Users: {len(_mem_users)}\n💾 Mode: In-Memory ❌"
        )
        return
    try:
        async with db_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM s_users")
            today = await conn.fetchval("SELECT COUNT(*) FROM s_users WHERE last_active > NOW() - INTERVAL '24 hours'")
            week = await conn.fetchval("SELECT COUNT(*) FROM s_users WHERE last_active > NOW() - INTERVAL '7 days'")
            premium = await conn.fetchval("SELECT COUNT(*) FROM s_users WHERE is_premium = TRUE")
            total_coins = await conn.fetchval("SELECT COALESCE(SUM(coins),0) FROM s_users")
            total_msgs = await conn.fetchval("SELECT COUNT(*) FROM s_history")
            total_reviews = await conn.fetchval("SELECT COUNT(*) FROM s_review")
            total_files = await conn.fetchval("SELECT COUNT(*) FROM s_files")
        await safe_reply(
            update.message,
            f"📊 Admin Dashboard\n\n"
            f"👥 Total Users: {total}\n🟢 24h Active: {today}\n📅 7d Active: {week}\n"
            f"💎 Premium: {premium}\n🪙 Total Coins: {total_coins}\n💬 Messages: {total_msgs}\n"
            f"🔁 Reviews saved: {total_reviews}\n📂 Files saved: {total_files}\n\n"
            f"💾 Mode: PostgreSQL ✅"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ DB error: {e}")


async def feedback_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    if db_pool is None:
        await update.message.reply_text("❌ DB নেই।")
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT rating, COUNT(*) as cnt FROM s_feedback 
                WHERE created_at > NOW() - INTERVAL '7 days' GROUP BY rating
            """)
        good = 0; bad = 0
        for r in rows:
            if r["rating"] == "good": good = r["cnt"]
            elif r["rating"] == "bad": bad = r["cnt"]
        total = good + bad
        rate = (good / total * 100) if total > 0 else 0
        await update.message.reply_text(
            f"📊 Last 7 days Feedback\n\n👍 Good: {good}\n👎 Bad: {bad}\n"
            f"📈 Satisfaction: {rate:.1f}%\n📝 Total: {total}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def broadcast_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if update.message.reply_to_message:
        msg_text = update.message.reply_to_message.text or update.message.reply_to_message.caption or ""
    elif context.args:
        msg_text = " ".join(context.args)
    else:
        await update.message.reply_text(
            "Usage:\n1. /broadcast your message (single line)\n"
            "2. Reply to any message with /broadcast (multi-line)"
        )
        return
    if not msg_text:
        await update.message.reply_text("❌ Empty message.")
        return
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
            await context.bot.send_message(u_id, f"📢 {msg_text}")
            sent += 1
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
    await update.message.reply_text(f"✅ Sent: {sent} | ❌ Failed: {failed}")


async def approve_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <user_id>")
        return
    try:
        target_uid = int(context.args[0])
        until = datetime.now() + timedelta(days=PREMIUM_DAYS)
        await update_user(target_uid, is_premium=True, premium_until=until)
        await update.message.reply_text(f"✅ User {target_uid} granted Premium!")
        try:
            target_lang = await get_user_lang(target_uid)
            await context.bot.send_message(target_uid, t("premium_success", target_lang, days=PREMIUM_DAYS))
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def reply_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Usage: /reply <user_id> <your_message>")
        return
    try:
        target_uid = int(context.args[0])
        reply_text = " ".join(context.args[1:])
        await context.bot.send_message(target_uid, f"📩 Admin Reply:\n\n{reply_text}")
        await update.message.reply_text(f"✅ Reply sent to {target_uid}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def addfile_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    context.user_data['awaiting_file'] = True
    context.user_data.pop('awaiting_file_caption', None)
    context.user_data.pop('pending_file_id', None)
    context.user_data.pop('pending_file_name', None)
    await update.message.reply_text(t("addfile_mode", "en"))


async def listfiles_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    files = await get_all_files()
    if not files:
        await update.message.reply_text(t("listfiles_empty", "en"))
        return
    text = t("listfiles_header", "en") + "\n\n"
    for f in files:
        text += f"🆔 {f['id']} — {f['file_name']}\n"
    text += "\n" + t("listfiles_footer", "en")
    await update.message.reply_text(text)


async def delfile_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text(t("admin_only", "en"))
        return
    if not context.args:
        await update.message.reply_text(t("delfile_usage", "en"))
        return
    try:
        fid = int(context.args[0])
        ok = await delete_file(fid)
        if ok:
            await update.message.reply_text(t("delfile_done", "en", id=fid))
        else:
            await update.message.reply_text(t("delfile_fail", "en"))
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def cancel_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return
    cleared = False
    for k in ['awaiting_file', 'awaiting_file_caption', 'pending_file_id', 'pending_file_name']:
        if context.user_data.pop(k, None) is not None:
            cleared = True
    if cleared:
        await update.message.reply_text(t("addfile_cancel", "en"))
    else:
        await update.message.reply_text(t("addfile_nothing", "en"))


async def skip_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        return
    if not context.user_data.get('awaiting_file_caption'):
        await update.message.reply_text(t("addfile_nothing", "en"))
        return
    file_id = context.user_data.pop('pending_file_id', None)
    file_name = context.user_data.pop('pending_file_name', 'file')
    context.user_data.pop('awaiting_file_caption', None)
    if file_id:
        ok = await save_file(file_id, file_name, "", uid)
        if ok:
            await update.message.reply_text(t("addfile_saved_no_caption", "en", name=file_name))
        else:
            await update.message.reply_text(t("addfile_save_fail", "en"))


# ==========================================================
# NEW: Pronunciation Commands
# ==========================================================
async def pronounce_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await update.message.reply_text(
            t("pron_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    # Cancel other modes
    for k in ['ielts_speaking', 'pdf_quiz', 'pdf_quiz_mode', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    sentence = random.choice(PRONUNCIATION_SENTENCES)
    context.user_data['pronunciation_mode'] = {'target': sentence}
    await update.message.reply_text(
        f"{t('pron_title', lang)}\n\n"
        f"{t('pron_read', lang)}\n\n❝ {sentence} ❞\n\n"
        f"{t('pron_send_voice', lang)}\n\n{t('pron_cancel_hint', lang)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("pron_new_sentence", lang), callback_data="pron_new")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def cancel_pronounce_command(update, context):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    if context.user_data.pop('pronunciation_mode', None):
        await update.message.reply_text(t("pron_cancelled", lang))
    else:
        await update.message.reply_text(t("pron_not_in", lang))


async def cb_pronunciation(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await safe_edit(
            q, t("pron_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    for k in ['ielts_speaking', 'pdf_quiz', 'pdf_quiz_mode', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    sentence = random.choice(PRONUNCIATION_SENTENCES)
    context.user_data['pronunciation_mode'] = {'target': sentence}
    await safe_edit(
        q,
        f"{t('pron_title', lang)}\n\n"
        f"{t('pron_read', lang)}\n\n❝ {sentence} ❞\n\n"
        f"{t('pron_send_voice', lang)}\n\n{t('pron_cancel_hint', lang)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("pron_new_sentence", lang), callback_data="pron_new")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def cb_pron_new(update, context):
    q = update.callback_query
    await q.answer()
    await cb_pronunciation(update, context)


async def cb_cancel_pronounce(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data.pop('pronunciation_mode', None)
    lang = await get_user_lang(q.from_user.id)
    await safe_edit(q, t("main_menu", lang), reply_markup=main_menu_kb())


# ==========================================================
# NEW: IELTS Speaking Commands
# ==========================================================
async def ielts_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await update.message.reply_text(
            t("ielts_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    for k in ['pronunciation_mode', 'pdf_quiz', 'pdf_quiz_mode', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    context.user_data['ielts_speaking'] = {
        'stage': 1,
        'q_index': 0,
        'history': [],
        'current_q': IELTS_PART1_QUESTIONS[0],
    }
    await update.message.reply_text(
        f"{t('ielts_welcome', lang)}\n\n"
        f"{t('ielts_part1_start', lang, n=1)}\n\n"
        f"❓ {IELTS_PART1_QUESTIONS[0]}\n\n{t('ielts_cancel', lang)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def cancel_ielts_command(update, context):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    if context.user_data.pop('ielts_speaking', None):
        await update.message.reply_text(t("ielts_cancelled", lang))
    else:
        await update.message.reply_text(t("ielts_not_in", lang))


async def cb_ielts_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await safe_edit(
            q, t("ielts_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    for k in ['pronunciation_mode', 'pdf_quiz', 'pdf_quiz_mode', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    context.user_data['ielts_speaking'] = {
        'stage': 1,
        'q_index': 0,
        'history': [],
        'current_q': IELTS_PART1_QUESTIONS[0],
    }
    await safe_edit(
        q,
        f"{t('ielts_welcome', lang)}\n\n"
        f"{t('ielts_part1_start', lang, n=1)}\n\n"
        f"❓ {IELTS_PART1_QUESTIONS[0]}\n\n{t('ielts_cancel', lang)}",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def cb_ielts_end(update, context):
    q = update.callback_query
    await q.answer("Ending test...")
    lang = await get_user_lang(q.from_user.id)
    ielts = context.user_data.get('ielts_speaking')
    if not ielts:
        await safe_edit(q, t("ielts_not_in", lang), reply_markup=back_kb(lang))
        return
    # If they gave at least 1 answer, we can score
    if ielts['history']:
        await generate_ielts_feedback(q.message, context, q.from_user.id, ielts, await get_user(q.from_user.id))
    else:
        await safe_edit(q, "❌ No answers given. Test cancelled.", reply_markup=back_kb(lang))
    context.user_data.pop('ielts_speaking', None)


async def generate_ielts_feedback(message_obj, context, uid, ielts, user):
    """Called when IELTS test finishes. Sends band score + feedback."""
    lang = await get_user_lang(uid)
    analyzing_msg = await message_obj.reply_text(t("ielts_analyzing", lang))
    
    # Build transcript
    transcript_lines = []
    for item in ielts['history']:
        transcript_lines.append(f"Q: {item['q']}\nA: {item['a']}")
    transcript = "\n\n".join(transcript_lines)
    
    system_prompt = (
        "You are a strict IELTS Speaking examiner. "
        "Evaluate the candidate's responses and give:\n"
        "1) Overall Band Score (0-9, in 0.5 steps)\n"
        "2) Four criteria scores (0-9): Fluency & Coherence, Lexical Resource, "
        "Grammatical Range & Accuracy, Pronunciation\n"
        "3) 2-3 specific strengths\n"
        "4) 2-3 specific weaknesses\n"
        "5) Concrete advice for improvement\n\n"
        "Format with emojis and plain text. No markdown (no *, **). "
        "Use blank lines to separate sections. Keep under 2500 characters."
    )
    
    prompt = (
        f"Candidate's IELTS Speaking Test transcript:\n\n{transcript}\n\n"
        f"Evaluate and give the band score and detailed feedback."
    )
    
    try:
        # Direct Groq call (no suggestion parsing)
        response = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1500,
        )
        result = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"IELTS eval error: {e}")
        result = "❌ Evaluation failed. Please try again."
    
    try:
        await analyzing_msg.delete()
    except Exception:
        pass
    
    final_text = (
        f"{t('ielts_done', lang)}\n\n"
        f"{result}\n\n"
        f"👉 /ielts — Try again\n"
        f"👉 /menu — Main menu"
    )
    await safe_reply(message_obj, final_text)
    
    # Update user stats
    if user:
        await update_user(uid, last_active=datetime.now())
        # Award achievement
        earned = set(filter(None, (user.get("achievements") or "").split(",")))
        if "ielts_done" not in earned:
            earned.add("ielts_done")
            await update_user(uid, achievements=",".join(earned))


async def process_ielts_answer(message, context, user, text):
    """Process user answer for IELTS speaking test."""
    ielts = context.user_data.get('ielts_speaking')
    if not ielts:
        return
    
    lang = user.get("language") or "bn"
    user_answer = text.strip()
    
    if len(user_answer) < 15:
        await message.reply_text(t("ielts_answer_too_short", lang))
        return
    
    # Save answer
    ielts['history'].append({
        'q': ielts.get('current_q', ''),
        'a': user_answer
    })
    ielts['q_index'] += 1
    qi = ielts['q_index']
    stage = ielts['stage']
    
    if stage == 1:
        if qi < len(IELTS_PART1_QUESTIONS):
            next_q = IELTS_PART1_QUESTIONS[qi]
            ielts['current_q'] = next_q
            await message.reply_text(
                f"{t('ielts_part1_start', lang, n=qi+1)}\n\n"
                f"❓ {next_q}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
                ])
            )
        else:
            # Move to Part 2
            ielts['stage'] = 2
            ielts['q_index'] = 0
            ielts['current_q'] = IELTS_PART2_CUE
            await message.reply_text(
                f"{t('ielts_part2_start', lang, cue=IELTS_PART2_CUE)}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
                ])
            )
    elif stage == 2:
        # Move to Part 3
        ielts['stage'] = 3
        ielts['q_index'] = 0
        next_q = IELTS_PART3_QUESTIONS[0]
        ielts['current_q'] = next_q
        await message.reply_text(
            f"{t('ielts_part3_start', lang, n=1)}\n\n❓ {next_q}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
            ])
        )
    elif stage == 3:
        if qi < len(IELTS_PART3_QUESTIONS):
            next_q = IELTS_PART3_QUESTIONS[qi]
            ielts['current_q'] = next_q
            await message.reply_text(
                f"{t('ielts_part3_start', lang, n=qi+1)}\n\n❓ {next_q}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
                ])
            )
        else:
            # Done
            await generate_ielts_feedback(message, context, user['user_id'], ielts, user)
            context.user_data.pop('ielts_speaking', None)


# ==========================================================
# NEW: PDF Quiz Commands
# ==========================================================
async def pdfquiz_command(update, context):
    if not await is_user_joined(context.bot, update.effective_user.id):
        await send_force_sub_message(update.message, "bn")
        return
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await update.message.reply_text(
            t("pdfquiz_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    for k in ['pronunciation_mode', 'ielts_speaking', 'pdf_quiz', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    context.user_data['pdf_quiz_mode'] = True
    await update.message.reply_text(
        t("pdfquiz_prompt", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def cancel_pdfquiz_command(update, context):
    uid = update.effective_user.id
    lang = await get_user_lang(uid)
    cleared = False
    for k in ['pdf_quiz_mode', 'pdf_quiz']:
        if context.user_data.pop(k, None) is not None:
            cleared = True
    if cleared:
        await update.message.reply_text(t("pdfquiz_cancelled", lang))
    else:
        await update.message.reply_text(t("pdfquiz_not_in", lang))


async def cb_pdfquiz_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if not user or not user.get("is_premium"):
        await safe_edit(
            q, t("pdfquiz_premium", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⭐ Go Premium", callback_data="m_premium")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        )
        return
    for k in ['pronunciation_mode', 'ielts_speaking', 'pdf_quiz', 'roleplay', 'game_active']:
        context.user_data.pop(k, None)
    context.user_data['pdf_quiz_mode'] = True
    await safe_edit(
        q, t("pdfquiz_prompt", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
    )


async def generate_pdf_quiz(message, context, uid, pdf_text, file_name, user):
    """Generate MCQ quiz from PDF and send first question."""
    lang = user.get("language") or "bn"
    gen_msg = await message.reply_text(t("pdfquiz_generating", lang))
    
    system_prompt = (
        "You are an expert quiz maker. Create 10 multiple-choice questions from the given content. "
        "Return ONLY a JSON array. No explanation, no markdown fences.\n\n"
        "Format exactly:\n"
        '[{"q": "Question text?", "options": ["Option A", "Option B", "Option C", "Option D"], "answer": 0}, ...]\n\n'
        "Rules:\n"
        "- Exactly 10 questions\n"
        "- Each question 4 options\n"
        "- 'answer' is the index (0-3) of the correct option\n"
        "- Questions should be based on the content\n"
        "- Simple, clear English"
    )
    
    prompt = f"Content:\n\n{pdf_text}\n\nCreate 10 MCQs based on this content."
    
    try:
        response = await asyncio.to_thread(
            groq_client.chat.completions.create,
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=2500,
        )
        raw = response.choices[0].message.content.strip()
        quiz = parse_quiz_json(raw)
    except Exception as e:
        logger.error(f"Quiz gen error: {e}")
        quiz = None
    
    try:
        await gen_msg.delete()
    except Exception:
        pass
    
    if not quiz:
        await message.reply_text(t("pdfquiz_fail", lang))
        context.user_data.pop('pdf_quiz_mode', None)
        return
    
    # Save quiz state
    context.user_data['pdf_quiz'] = {
        'questions': quiz,
        'current': 0,
        'score': 0,
        'answers': [],
    }
    context.user_data.pop('pdf_quiz_mode', None)
    
    # Send Q1
    await send_quiz_question(message, context, uid, user)


async def send_quiz_question(message, context, uid, user):
    """Send the current quiz question with inline option buttons."""
    lang = user.get("language") or "bn"
    state = context.user_data.get('pdf_quiz')
    if not state:
        return
    idx = state['current']
    questions = state['questions']
    if idx >= len(questions):
        await finish_quiz(message, context, uid, user)
        return
    q = questions[idx]
    
    text = (
        f"{t('pdfquiz_title', lang)}\n\n"
        f"{t('pdfquiz_q', lang, n=idx+1)}\n\n"
        f"❓ {q['q']}"
    )
    rows = []
    letters = ["A", "B", "C", "D", "E", "F"]
    for i, opt in enumerate(q['options'][:4]):
        rows.append([InlineKeyboardButton(
            f"{letters[i]}) {opt[:50]}", callback_data=f"pq_{i}"
        )])
    rows.append([InlineKeyboardButton("🛑 Stop Quiz", callback_data="pq_stop")])
    
    try:
        await message.reply_text(text, reply_markup=InlineKeyboardMarkup(rows))
    except Exception as e:
        logger.error(f"Send quiz Q error: {e}")


async def finish_quiz(message, context, uid, user):
    """Send final score summary."""
    lang = user.get("language") or "bn"
    state = context.user_data.pop('pdf_quiz', None)
    if not state:
        return
    total = len(state['questions'])
    score = state['score']
    pct = int(score / total * 100) if total > 0 else 0
    
    if pct >= 80:
        emoji = "🏆"
        label = "Outstanding!"
    elif pct >= 60:
        emoji = "🎉"
        label = "Very Good!"
    elif pct >= 40:
        emoji = "👍"
        label = "Good"
    else:
        emoji = "📚"
        label = "Keep Learning"
    
    text = (
        f"{t('pdfquiz_done', lang)}\n\n"
        f"{t('pdfquiz_score', lang)}\n"
        f"{emoji} {score}/{total} ({pct}%) — {label}\n\n"
        f"👉 /pdfquiz — Try another PDF\n"
        f"👉 /menu — Main menu"
    )
    await safe_reply(message, text)


async def process_quiz_answer(update, context, option_idx):
    """Process a quiz answer click."""
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    user = await get_user(uid)
    state = context.user_data.get('pdf_quiz')
    if not state:
        await q.answer("Quiz expired", show_alert=True)
        return
    
    idx = state['current']
    questions = state['questions']
    if idx >= len(questions):
        await q.answer("Done", show_alert=False)
        return
    
    question = questions[idx]
    correct_idx = question['answer']
    letters = ["A", "B", "C", "D", "E", "F"]
    correct_text = question['options'][correct_idx] if correct_idx < len(question['options']) else "?"
    
    if option_idx == correct_idx:
        state['score'] += 1
        result_text = f"{t('pdfquiz_correct', lang)} ✅"
    else:
        result_text = (
            f"{t('pdfquiz_wrong', lang)}\n"
            f"{t('pdfquiz_answer', lang)}: {letters[correct_idx]}) {correct_text}"
        )
    
    await q.answer("✅" if option_idx == correct_idx else "❌", show_alert=False)
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    
    await q.message.reply_text(result_text)
    
    state['current'] += 1
    if state['current'] >= len(questions):
        await finish_quiz(q.message, context, uid, user)
    else:
        await send_quiz_question(q.message, context, uid, user)


async def cb_quiz_answer(update, context):
    q = update.callback_query
    try:
        idx = int(q.data.split("_")[1])
    except Exception:
        await q.answer()
        return
    await process_quiz_answer(update, context, idx)


async def cb_quiz_stop(update, context):
    q = update.callback_query
    await q.answer("Stopped")
    context.user_data.pop('pdf_quiz', None)
    lang = await get_user_lang(q.from_user.id)
    await q.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


# ==========================================================
# STUDENT PROMPTS
# ==========================================================
TENSES_LIST = [
    "Simple Present", "Present Continuous", "Present Perfect", "Present Perfect Continuous",
    "Simple Past", "Past Continuous", "Past Perfect", "Past Perfect Continuous",
    "Simple Future", "Future Continuous", "Future Perfect", "Future Perfect Continuous"
]

STUDENT_PROMPTS = {
    "student_learn": "Start a short English lesson. Choose one useful topic. Explain simply, give 2 examples, then ONE practice question. Plain text.",
    "student_vocab": "Teach ONE English word: meaning, pronunciation, part of speech, example. Then ONE practice question. Plain text.",
    "student_grammar": "Teach ONE English grammar point: rule, explanation, 2 examples, common mistake, 1 practice question. Plain text.",
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
]


# ==========================================================
# CALLBACKS
# ==========================================================
async def cb_forcesub_check(update, context):
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    joined = await is_user_joined(context.bot, uid)
    if not joined:
        await q.answer(t("force_sub_not_joined", lang), show_alert=True)
        return
    await q.answer(t("force_sub_thanks", lang), show_alert=False)
    try:
        await q.edit_message_text(
            t("force_sub_thanks", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
            ]),
        )
    except Exception:
        pass
    existing = await get_user(uid)
    if not existing:
        await create_user(uid, q.from_user.full_name or "Student")
        await q.message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())
    else:
        await q.message.reply_text(t("welcome", lang, name=q.from_user.first_name or "Student"))
        await q.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())


async def cb_feedback(update, context):
    q = update.callback_query
    await q.answer("🙏")
    data = q.data
    parts = data.split("_")
    rating = parts[1]
    msg_id = parts[2] if len(parts) > 2 else "0"
    uid = q.from_user.id
    if db_pool:
        try:
            async with db_pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO s_feedback (user_id, message_id, rating) VALUES ($1, $2, $3)",
                    uid, int(msg_id), rating
                )
        except Exception as e:
            logger.error(f"Feedback save: {e}")
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    lang = await get_user_lang(uid)
    emoji = "👍" if rating == "good" else "👎"
    await q.message.reply_text(f"{emoji} {t('feedback_thanks', lang)}")


async def cb_suggestion_click(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    idx = int(q.data.split("_")[1])
    suggestions = context.user_data.get('cached_suggestions', [])
    lang = await get_user_lang(uid)
    if idx >= len(suggestions):
        await q.message.reply_text(t("suggestion_expired", lang))
        return
    user_text = suggestions[idx]
    try:
        await q.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    user = await get_user(uid)
    try:
        await q.message.chat.send_action("typing")
    except Exception:
        pass
    history = await get_history(uid)
    answer, suggestions = await asyncio.to_thread(ask_groq, user_text, history, user)
    if not answer:
        answer = t("ai_error", lang)
    await save_history(uid, "user", user_text)
    await save_history(uid, "assistant", answer)
    kb = suggestions_kb(suggestions, context)
    await safe_reply_feedback(q.message, answer, q.message.message_id, kb)


async def cb_set_language(update, context):
    q = update.callback_query
    await q.answer()
    lang = q.data.replace("setlang_", "")
    uid = q.from_user.id
    await create_user(uid, q.from_user.full_name or "Student")
    await update_user(uid, language=lang)
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
    try:
        await q.message.reply_text(t("welcome", lang, name=q.from_user.first_name or "Student"))
        await q.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())
    except Exception as e:
        logger.error(f"lang reply fail: {e}")


async def student_menu_callback(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        await q.edit_message_text(
            f"{t('force_sub_title', lang)}\n\n{t('force_sub_desc', lang)}",
            reply_markup=force_sub_kb(lang),
        )
        return
    await update_user(uid, last_active=datetime.now())
    data = q.data
    if data == "student_speaking":
        last_q = context.user_data.get("last_speaking_question")
        avail = [x for x in SPEAKING_QUESTIONS if x != last_q]
        question = random.choice(avail)
        context.user_data["last_speaking_question"] = question
        prompt = f"Start English speaking practice. Ask this exact question:\n\n{question}\n\nWait for the answer. Plain text."
    elif data == "student_tenses":
        tense = random.choice(TENSES_LIST)
        prompt = f"Teach ONE English tense: {tense}. Explain usage, structure, 2 examples, common mistake, 1 practice question. Plain text."
    else:
        prompt = STUDENT_PROMPTS.get(data)
    if not prompt:
        await q.answer("Unknown option", show_alert=False)
        return
    user = await get_user(uid)
    try:
        await q.edit_message_text(t("loading", lang))
    except Exception:
        pass
    answer, suggestions = await asyncio.to_thread(ask_groq, prompt, None, user)
    if not answer:
        answer = t("ai_error", lang)
    if data == "student_vocab":
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
    kb = suggestions_kb(suggestions, context)
    await safe_edit(q, answer, reply_markup=merge_keyboards(kb, back_kb(lang)))


async def cb_practice_menu(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    await safe_edit(
        q,
        f"{t('practice_title', lang)}\n\n{t('practice_desc', lang)}",
        reply_markup=practice_menu_kb(lang),
    )


async def cb_rp_start(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    key = q.data.replace("rp_", "")
    scenario = ROLEPLAY_SCENARIOS.get(key)
    if not scenario:
        await q.answer("Unknown scenario", show_alert=True)
        return
    context.user_data["roleplay"] = {
        "key": key,
        "system": scenario["system"],
        "history": [],
    }
    title = scenario["title"].get(lang) or scenario["title"].get("en")
    starter = scenario["starter"]
    user = await get_user(uid)
    count = (user.get("roleplay_count") or 0) + 1 if user else 1
    await update_user(uid, roleplay_count=count)
    await safe_edit(
        q,
        f"{t('rp_started', lang, title=title)}\n\n{scenario['emoji']} {starter}"
    )
    await save_history(uid, "assistant", f"[RP:{key}] {starter}")


async def cb_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        await q.edit_message_text(
            f"{t('force_sub_title', lang)}\n\n{t('force_sub_desc', lang)}",
            reply_markup=force_sub_kb(lang),
        )
        return
    for k in ["roleplay", "awaiting_payment", "payment_method", "awaiting_support",
              "game_active", "pronunciation_mode", "ielts_speaking", "pdf_quiz", "pdf_quiz_mode"]:
        context.user_data.pop(k, None)
    await safe_edit(q, t("main_menu", lang), reply_markup=main_menu_kb())


async def cb_profile(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
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
        f"📸 Photos: {user.get('photos_sent') or 0}\n"
        f"🎤 Voices: {user.get('voices_sent') or 0}\n"
        f"📄 PDFs: {user.get('pdfs_sent') or 0}\n"
        f"🎭 Role-plays: {user.get('roleplay_count') or 0}\n"
        f"🔁 Reviews: {user.get('review_count') or 0}\n"
        f"{t('premium_status', lang)}: {status}"
    )
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_daily(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        await q.edit_message_text(
            f"{t('force_sub_title', lang)}\n\n{t('force_sub_desc', lang)}",
            reply_markup=force_sub_kb(lang),
        )
        return
    streak = await check_streak(uid)
    bonus = DAILY_BONUS + (streak * STREAK_BONUS)
    await add_coins(uid, bonus)
    user = await get_user(uid)
    await q.edit_message_text(t("loading", lang))
    answer, suggestions = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word + meaning + example, 1 grammar tip, 1 practice question. Plain text.",
        None, user
    )
    if not answer:
        answer = "📚 Word: Diligent - hardworking\nExample: She is a diligent student."
    kb = suggestions_kb(suggestions, context)
    await safe_edit(
        q,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n\n{answer}",
        reply_markup=merge_keyboards(kb, back_kb(lang)),
    )


async def cb_word_of_day(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    await q.edit_message_text(t("loading", lang))
    answer, suggestions = await asyncio.to_thread(
        ask_groq,
        "Give ONE advanced English word of the day. Include: word, meaning, pronunciation, part of speech, 2 examples, 2 synonyms. Plain text.",
        None, user
    )
    if not answer:
        answer = "🔤 Word: Resilient\n📖 Meaning: able to recover quickly\n🔊 /riˈziliənt/"
    kb = suggestions_kb(suggestions, context)
    await safe_edit(q, f"{t('word_title', lang)}\n\n{answer}", reply_markup=merge_keyboards(kb, back_kb(lang)))


async def cb_quiz(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        await q.edit_message_text(
            f"{t('force_sub_title', lang)}\n\n{t('force_sub_desc', lang)}",
            reply_markup=force_sub_kb(lang),
        )
        return
    user = await get_user(uid)
    quizzes = (user.get("quizzes_taken") or 0) + 1 if user else 1
    await update_user(uid, quizzes_taken=quizzes)
    await q.edit_message_text(t("loading", lang))
    answer, suggestions = await asyncio.to_thread(
        ask_groq,
        "Create ONE English multiple-choice quiz with 4 options. Format:\nQuestion: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: X) ...\nPlain text.",
        None, user
    )
    if not answer:
        answer = "Question: Past tense of 'go'?\nA) goed\nB) went\nC) gone\nD) going\nAnswer: B) went"
    kb = suggestions_kb(suggestions, context)
    base_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("quiz_more", lang), callback_data="m_quiz")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
    ])
    await safe_edit(q, f"{t('quiz_title', lang)}\n\n{answer}", reply_markup=merge_keyboards(kb, base_markup))


async def cb_review(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    due = await get_due_reviews(uid, limit=3)
    if not due:
        await safe_edit(q, t("review_none", lang), reply_markup=back_kb(lang))
        return
    context.user_data["review_queue"] = due
    context.user_data["review_index"] = 0
    first = due[0]
    await safe_edit(q, t("review_prompt", lang, wrong=first["wrong_text"]), reply_markup=back_kb(lang))


async def cb_translate(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    await safe_edit(q, t("translate_hint", lang), reply_markup=back_kb(lang))


async def cb_invite(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    bot = await context.bot.get_me()
    link = f"https://t.me/{bot.username}?start=ref_{uid}"
    await safe_edit(
        q,
        f"{t('invite_title', lang)}\n\n{link}\n\n{t('invite_hint', lang, n=REFERRAL_REWARD)}",
        reply_markup=back_kb(lang),
    )


async def cb_premium(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if user and user.get("is_premium"):
        await safe_edit(q, t("premium_already", lang), reply_markup=back_kb(lang))
        return
    context.user_data.pop("awaiting_payment", None)
    context.user_data.pop("payment_method", None)
    context.user_data.pop("awaiting_support", None)
    await safe_edit(
        q,
        t("premium_body", lang, stars=PREMIUM_STARS, days=PREMIUM_DAYS,
          bdt=PREMIUM_PRICE_BDT, usdt=USDT_AMOUNT),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("premium_buy", lang, n=PREMIUM_STARS), callback_data="buy_premium")],
            [InlineKeyboardButton(t("premium_bkash_btn", lang, n=PREMIUM_PRICE_BDT), callback_data="pay_bkash")],
            [InlineKeyboardButton(t("premium_rocket_btn", lang, n=PREMIUM_PRICE_BDT), callback_data="pay_rocket")],
            [InlineKeyboardButton(t("premium_trc20_btn", lang), callback_data="pay_trc20")],
            [InlineKeyboardButton(t("premium_bsc20_btn", lang), callback_data="pay_bsc20")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ]),
    )


async def cb_buy_premium(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
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
        await q.answer(t("payment_fail", lang), show_alert=True)


async def cb_vocab_book(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    caption_text = f"{t('vocab_book_title', lang)}\n\n{t('vocab_book_desc', lang)}"
    try:
        await context.bot.send_document(
            chat_id=uid, document=PDF_URL,
            filename="Sir_English_Vocabulary_Book.pdf",
            caption=caption_text
        )
        await q.message.reply_text(t("main_menu", lang), reply_markup=main_menu_kb())
    except Exception as e:
        logger.error(f"PDF send error: {e}")
        await q.message.reply_text(f"📘 Sir English Vocabulary Book\n\n👇 Link:\n{PDF_URL}")


async def cb_files_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    files = await get_all_files()
    if not files:
        await safe_edit(q, t("files_none", lang), reply_markup=back_kb(lang))
        return
    rows = []
    for f in files:
        name = f['file_name'] or "file"
        display = name if len(name) < 30 else name[:27] + "..."
        rows.append([InlineKeyboardButton(f"📎 {display}", callback_data=f"fget_{f['id']}")])
    rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])
    await safe_edit(
        q,
        f"{t('files_menu_title', lang)}\n\n{t('files_menu_desc', lang)}",
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def cb_file_send(update, context):
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    await q.answer(t("file_sending", lang))
    try:
        fid = int(q.data.split("_")[1])
    except Exception:
        return
    file = await get_file_by_db_id(fid)
    if not file:
        await q.message.reply_text(t("file_not_found", lang))
        return
    try:
        await context.bot.send_document(
            chat_id=uid, document=file['file_id'], caption=file.get('caption') or ""
        )
    except Exception as e:
        logger.error(f"Send file error: {e}")
        await q.message.reply_text(t("file_send_fail", lang))


async def cb_word_game(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    word = random.choice(WORD_GAME_LIST).lower()
    scrambled = list(word)
    random.shuffle(scrambled)
    scrambled_word = "".join(scrambled).upper()
    context.user_data['game_active'] = True
    context.user_data['game_word'] = word
    context.user_data['game_score'] = context.user_data.get('game_score', 0)
    text = (
        f"{t('game_title', lang)}\n\n"
        f"{t('game_scrambled', lang, word=scrambled_word)}\n\n"
        f"{t('game_prompt', lang)}\n"
        f"{t('game_score', lang, score=context.user_data['game_score'])}\n\n"
        f"{t('game_stop_hint', lang)}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("game_skip_btn", lang), callback_data="game_skip")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_game_skip(update, context):
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    await q.answer(t("game_new_word", lang))
    word = random.choice(WORD_GAME_LIST).lower()
    scrambled = list(word)
    random.shuffle(scrambled)
    scrambled_word = "".join(scrambled).upper()
    context.user_data['game_active'] = True
    context.user_data['game_word'] = word
    text = (
        f"{t('game_title', lang)}\n\n"
        f"{t('game_scrambled', lang, word=scrambled_word)}\n\n"
        f"{t('game_prompt', lang)}\n"
        f"{t('game_score', lang, score=context.user_data.get('game_score', 0))}\n\n"
        f"{t('game_stop_hint', lang)}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("game_skip_btn", lang), callback_data="game_skip")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_flashcard_menu(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    text = (
        f"{t('fc_title', lang)}\n\n{t('fc_choose_level', lang)}\n\n"
        f"{t('fc_easy', lang)}\n{t('fc_medium', lang)}\n{t('fc_hard', lang)}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("fc_easy", lang), callback_data="fc_easy"),
         InlineKeyboardButton(t("fc_medium", lang), callback_data="fc_medium")],
        [InlineKeyboardButton(t("fc_hard", lang), callback_data="fc_hard")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_flashcard_start(update, context):
    q = update.callback_query
    await q.answer()
    level = q.data.replace("fc_", "")
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if level not in FLASHCARDS:
        level = "easy"
    card = random.choice(FLASHCARDS[level])
    context.user_data['current_card'] = card
    context.user_data['fc_level'] = level
    text = (
        f"{t('fc_word', lang, word=card['word'])}\n"
        f"{t('fc_pron', lang, pron=card['pron'])}\n\n"
        f"{t('fc_ask', lang)}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("fc_show_btn", lang), callback_data="fc_show")],
        [InlineKeyboardButton(t("fc_next_btn", lang), callback_data=f"fc_{level}")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_flashcard_show(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    card = context.user_data.get('current_card')
    level = context.user_data.get('fc_level', 'easy')
    if not card:
        await cb_flashcard_menu(update, context)
        return
    text = (
        f"{t('fc_word', lang, word=card['word'])}\n"
        f"{t('fc_pron', lang, pron=card['pron'])}\n"
        f"{t('fc_meaning', lang, meaning=card['meaning'])}\n\n"
        f"{t('fc_example', lang, ex=card['ex'])}\n\n"
        f"{t('fc_remember_hint', lang)}"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("fc_next_btn", lang), callback_data=f"fc_{level}")],
        [InlineKeyboardButton(t("fc_change_level", lang), callback_data="m_flashcard")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_bkash(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'bKash'
    text = f"{t('pay_bkash_title', lang)}\n\n{t('pay_bkash_desc', lang, number=BKASH_NUMBER, amount=PREMIUM_PRICE_BDT)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_bkash")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_rocket(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'Rocket'
    text = f"{t('pay_rocket_title', lang)}\n\n{t('pay_rocket_desc', lang, number=ROCKET_NUMBER, amount=PREMIUM_PRICE_BDT)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_rocket")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_trc20(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (TRC20)'
    text = f"{t('pay_trc20_title', lang)}\n\n{t('pay_trc20_desc', lang, amount=USDT_AMOUNT, address=TRC20_ADDRESS)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_trc20")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_bsc20(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (BSC20)'
    text = f"{t('pay_bsc20_title', lang)}\n\n{t('pay_bsc20_desc', lang, amount=USDT_AMOUNT, address=BSC20_ADDRESS)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_bsc20")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_copy_bkash(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await q.message.reply_text(f"`{BKASH_NUMBER}`\n\n{t('copy_hint', lang)}")

async def cb_copy_rocket(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await q.message.reply_text(f"`{ROCKET_NUMBER}`\n\n{t('copy_hint', lang)}")

async def cb_copy_trc20(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await q.message.reply_text(f"`{TRC20_ADDRESS}`\n\n{t('copy_hint', lang)}")

async def cb_copy_bsc20(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    await q.message.reply_text(f"`{BSC20_ADDRESS}`\n\n{t('copy_hint', lang)}")


async def cb_cancel_payment(update, context):
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    await q.answer(t("payment_cancelled", lang))
    context.user_data.pop("awaiting_payment", None)
    context.user_data.pop("payment_method", None)
    await safe_edit(q, t("main_menu", lang), reply_markup=main_menu_kb())


async def cb_support(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    context.user_data['awaiting_support'] = True
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("support_cancel", lang), callback_data="cancel_support")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
    ])
    await safe_edit(q, f"{t('support_title', lang)}\n\n{t('support_desc', lang)}", reply_markup=markup)


async def cb_cancel_support(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    context.user_data.pop("awaiting_support", None)
    await safe_edit(q, t("support_cancelled", lang), reply_markup=back_kb(lang))


async def precheckout_cb(update, context):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_cb(update, context):
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


async def cb_leaderboard(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    rows = await fetch_leaderboard()
    if not rows:
        await safe_edit(q, t("no_users", lang), reply_markup=back_kb(lang))
        return
    text = f"{t('leaderboard_title', lang)}\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, r in enumerate(rows):
        m = medals[i] if i < 3 else f"{i+1}."
        text += f"{m} {r.get('name', '?')} - ⭐ {r.get('quiz_score', 0)}\n"
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_mistakes(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    if db_pool is None:
        await safe_edit(q, t("mistakes_none", lang), reply_markup=back_kb(lang))
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT wrong_text, corrected_text FROM s_review "
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


async def cb_achievements(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if not user:
        await safe_edit(q, t("start_first", lang), reply_markup=back_kb(lang))
        return
    await safe_edit(q, f"{t('achievements_title', lang)}\n\n{achievements_text(user, lang)}",
                    reply_markup=back_kb(lang))


async def cb_memory(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return
    user = await get_user(uid)
    if not user:
        await safe_edit(q, t("start_first", lang), reply_markup=back_kb(lang))
        return
    text = (
        f"{t('memory_title', lang)}\n\n"
        f"📛 {t('name', lang)}: {user.get('name')}\n"
        f"🎓 {t('level', lang)}: {user.get('level')}\n"
        f"🪙 {t('coins', lang)}: {user.get('coins') or 0}\n"
        f"🔥 {t('streak', lang)}: {user.get('streak') or 0} {t('days', lang)}\n"
        f"📚 {t('words_learned', lang)}: {user.get('words_learned') or 0}\n"
        f"🎯 {t('quizzes', lang)}: {user.get('quizzes_taken') or 0}\n"
        f"📄 PDFs: {user.get('pdfs_sent') or 0}\n"
        f"🎭 Role-plays: {user.get('roleplay_count') or 0}\n"
        f"🔁 Reviews: {user.get('review_count') or 0}\n"
        f"🌍 Language: {user.get('language') or 'bn'}"
    )
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_reminder(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    await safe_edit(
        q, t("reminder_title", lang),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌅 08:00", callback_data="rem_08:00"),
             InlineKeyboardButton("☀️ 12:00", callback_data="rem_12:00")],
            [InlineKeyboardButton("🌆 18:00", callback_data="rem_18:00"),
             InlineKeyboardButton("🌙 21:00", callback_data="rem_21:00")],
            [InlineKeyboardButton("❌ Off", callback_data="rem_off")],
        ]),
    )


async def cb_reminder_set(update, context):
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


async def cb_set_level(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    lvl = q.data.replace("setlvl_", "")
    await update_user(uid, level=lvl)
    await safe_edit(q, t("level_set", lang, lvl=lvl), reply_markup=back_kb(lang))


async def cb_lang_menu(update, context):
    q = update.callback_query
    await q.answer()
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    await safe_edit(q, t("choose_lang", "bn"), reply_markup=lang_kb())


async def cb_help(update, context):
    q = update.callback_query
    await q.answer()
    lang = await get_user_lang(q.from_user.id)
    if not await is_user_joined(context.bot, q.from_user.id):
        return
    if lang == "en":
        text = ("ℹ️ Help\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🔥 Daily, 📖 Word of Day, 📊 Progress, 🏆 Leaderboard\n"
                "🎁 Invite, ⭐ Premium, 📚 Mistakes, 🏅 Achievements\n"
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n"
                "🎤 Pronunciation, 🎯 IELTS Speaking, 🧠 Quiz from PDF\n\n"
                "📸 Send photos, 🎤 voice, 📄 PDFs, 👍👎 rate replies\n"
                "🆘 Need help? Use the Support button or contact @asikul_echo")
    elif lang == "hi":
        text = ("ℹ️ सहायता\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🎤 Pronunciation, 🎯 IELTS Speaking, 🧠 Quiz from PDF\n\n"
                "📸 फोटो, 🎤 वॉइस, 📄 PDF, 👍👎 रेटिंग\n"
                "🆘 सहायता: @asikul_echo")
    else:
        text = ("ℹ️ সাহায্য\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🔥 Daily, 📖 Word of Day, 📊 Progress, 🏆 Leaderboard\n"
                "🎁 Invite, ⭐ Premium, 📚 Mistakes, 🏅 Achievements\n"
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n"
                "🎤 Pronunciation, 🎯 IELTS Speaking, 🧠 Quiz from PDF\n\n"
                "📸 ছবি, 🎤 ভয়েস, 📄 PDF পাঠান, 👍👎 রেটিং\n"
                "🆘 সাপোর্ট: @asikul_echo")
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_fallback(update, context):
    q = update.callback_query
    await q.answer("Unknown option", show_alert=False)
    logger.warning(f"Unhandled callback: {q.data}")


# ==========================================================
# MAIN MESSAGE HANDLER
# ==========================================================
async def handle_message(update, context):
    message = update.effective_message
    if not message:
        return
    chat = update.effective_chat
    if not chat:
        return

    uid = update.effective_user.id

    if not await is_user_joined(context.bot, uid):
        existing = await get_user(uid)
        lang = (existing or {}).get("language") or "bn"
        await send_force_sub_message(message, lang)
        return

    user = await get_user(uid)
    if not user:
        await create_user(uid, update.effective_user.full_name or "Student")
        user = await get_user(uid)
        await message.reply_text(t("choose_lang", "bn"), reply_markup=lang_kb())
        return

    lang = user.get("language") or "bn"
    today = datetime.now().date()

    # ================= ADMIN FILE UPLOAD (CAPTION MODE) =================
    if context.user_data.get('awaiting_file_caption') and uid in ADMIN_IDS and message.text:
        caption = message.text.strip()
        file_id = context.user_data.pop('pending_file_id', None)
        file_name = context.user_data.pop('pending_file_name', 'file')
        context.user_data.pop('awaiting_file_caption', None)
        if file_id:
            ok = await save_file(file_id, file_name, caption, uid)
            if ok:
                await message.reply_text(t("addfile_saved", "en", name=file_name, caption=caption))
            else:
                await message.reply_text(t("addfile_save_fail", "en"))
        return

    # ================= IELTS SPEAKING MODE =================
    ielts = context.user_data.get('ielts_speaking')
    if ielts:
        # Accept text OR voice
        if message.text and not message.text.startswith("/"):
            await process_ielts_answer(message, context, user, message.text.strip())
            return
        if message.voice or message.audio:
            voice = message.voice or message.audio
            msg = await message.reply_text("🎤 Transcribing...")
            path = f"/tmp/ielts_{uid}.ogg"
            try:
                f = await context.bot.get_file(voice.file_id)
                await f.download_to_drive(path)
                text = await asyncio.to_thread(transcribe_sync, path)
                try: os.remove(path)
                except: pass
                if not text:
                    await msg.edit_text(t("voice_fail", lang))
                    return
                await msg.edit_text(f"📝 You said: {text}")
                await process_ielts_answer(message, context, user, text)
            except Exception as e:
                logger.error(f"IELTS voice error: {e}")
                await msg.edit_text("❌ Error processing voice.")
            return

    # ================= PRONUNCIATION COACH MODE =================
    if context.user_data.get('pronunciation_mode'):
        if message.voice or message.audio:
            target = context.user_data['pronunciation_mode']['target']
            msg = await message.reply_text(t("pron_processing", lang))
            path = f"/tmp/pron_{uid}.ogg"
            try:
                voice = message.voice or message.audio
                f = await context.bot.get_file(voice.file_id)
                await f.download_to_drive(path)
                user_said = await asyncio.to_thread(transcribe_sync, path)
                try: os.remove(path)
                except: pass
                if not user_said:
                    await msg.edit_text(t("voice_fail", lang))
                    return
                score, wrong_words = calculate_pronunciation_score(target, user_said)
                
                if score >= 90:
                    emoji, label = "🏆", t("pron_excellent", lang)
                elif score >= 75:
                    emoji, label = "🎉", t("pron_very_good", lang)
                elif score >= 60:
                    emoji, label = "👍", t("pron_good", lang)
                elif score >= 40:
                    emoji, label = "📚", t("pron_keep_practicing", lang)
                else:
                    emoji, label = "🔁", t("pron_try_again", lang)
                
                feedback = (
                    f"{t('pron_result', lang)}\n\n"
                    f"{emoji} {score}/100 — {label}\n\n"
                    f"{t('pron_target', lang)}: {target}\n"
                    f"{t('pron_said', lang)}: {user_said}\n"
                )
                if wrong_words:
                    feedback += f"\n{t('pron_improve', lang)}:\n"
                    for w in wrong_words:
                        if w.strip():
                            feedback += f"• {w}\n"
                
                await msg.edit_text(feedback)
                
                # Send correct pronunciation as voice
                if HAS_TTS:
                    try:
                        tts_path = f"/tmp/correct_{uid}.mp3"
                        ok = await text_to_voice(target, tts_path)
                        if ok:
                            with open(tts_path, "rb") as vf:
                                await message.reply_voice(
                                    voice=vf,
                                    caption=t("pron_listen_again", lang)
                                )
                            try: os.remove(tts_path)
                            except: pass
                    except Exception:
                        pass
                
                await message.reply_text(
                    f"👉 Send another voice to try again.\n"
                    f"🔄 /pronounce for new sentence\n"
                    f"❌ /cancelpronounce to exit"
                )
                
                # Update user stats
                await update_user(uid, last_active=datetime.now(),
                                  voices_sent=(user.get("voices_sent") or 0) + 1)
            except Exception as e:
                logger.error(f"Pronunciation error: {e}")
                try:
                    await msg.edit_text("❌ Error processing voice.")
                except Exception:
                    pass
            return
        else:
            # Non-voice message in pronunciation mode
            if message.text and not message.text.startswith("/"):
                await message.reply_text(
                    "🎤 Please send a VOICE message. Text won't work here.\n"
                    "❌ /cancelpronounce to exit."
                )
                return

    # ================= PDF QUIZ MODE (waiting for PDF) =================
    if context.user_data.get('pdf_quiz_mode') and message.document:
        doc = message.document
        file_size = doc.file_size or 0
        file_name = doc.file_name or "document.pdf"
        mime = (doc.mime_type or "").lower()

        if file_size > MAX_PDF_SIZE_MB * 1024 * 1024:
            await message.reply_text(t("pdf_too_large", lang, n=MAX_PDF_SIZE_MB))
            return
        if "pdf" not in mime and not file_name.lower().endswith(".pdf"):
            await message.reply_text("❌ Please send a PDF file.")
            return
        if not HAS_PDF:
            await message.reply_text("❌ PDF support is not enabled.")
            return

        msg = await message.reply_text(t("pdfquiz_processing", lang))
        pdf_path = f"/tmp/quiz_{uid}.pdf"
        try:
            f = await context.bot.get_file(doc.file_id)
            await f.download_to_drive(pdf_path)
            result = await asyncio.to_thread(extract_pdf_text_sync, pdf_path)
            try: os.remove(pdf_path)
            except: pass
            if not result:
                await msg.edit_text(t("pdf_fail", lang))
                return
            pdf_text, _ = result
            try: await msg.delete()
            except: pass
            await generate_pdf_quiz(message, context, uid, pdf_text, file_name, user)
            await update_user(uid, last_active=datetime.now(),
                              pdfs_sent=(user.get("pdfs_sent") or 0) + 1)
        except Exception as e:
            logger.error(f"PDF Quiz error: {e}")
            try: await msg.edit_text("❌ Error processing PDF.")
            except: pass
        return

    # ================= PDF QUIZ (answer mode) =================
    pdf_quiz = context.user_data.get('pdf_quiz')
    if pdf_quiz and message.text and not message.text.startswith("/"):
        # If user types text instead of clicking, gently remind
        await message.reply_text(
            "👆 Please click one of the option buttons above.\n"
            "🛑 To stop the quiz, click the Stop button."
        )
        return

    # ================= ROLE-PLAY MODE =================
    rp = context.user_data.get("roleplay")
    if rp and message.text and not message.text.startswith("/"):
        user_text = message.text.strip()
        rp["history"].append({"role": "user", "content": user_text})
        await save_history(uid, "user", f"[RP] {user_text}")
        try:
            await message.chat.send_action("typing")
        except Exception:
            pass
        answer, _ = await asyncio.to_thread(ask_groq, user_text, rp["history"], user, rp["system"])
        if not answer:
            answer = t("ai_error", lang)
        rp["history"].append({"role": "assistant", "content": answer})
        await save_history(uid, "assistant", answer)
        corr = extract_correction(answer)
        if corr:
            await save_review(uid, corr[0], corr[1])
        await safe_reply_feedback(message, answer, message.message_id)
        if user.get("is_premium") and HAS_TTS and len(answer) < 400:
            try:
                tts_path = f"/tmp/tts_{uid}.mp3"
                ok = await text_to_voice(answer[:400], tts_path)
                if ok:
                    with open(tts_path, "rb") as vf:
                        await message.reply_voice(voice=vf)
                    try: os.remove(tts_path)
                    except Exception: pass
            except Exception:
                pass
        return

    # ================= WORD GAME MODE =================
    if context.user_data.get('game_active') and message.text and not message.text.startswith("/"):
        user_answer = message.text.strip().lower()
        correct_word = context.user_data.get('game_word', '').lower()
        if user_answer == correct_word:
            score = context.user_data.get('game_score', 0) + 5
            context.user_data['game_score'] = score
            await add_coins(uid, 5)
            word = random.choice(WORD_GAME_LIST).lower()
            scrambled = list(word)
            random.shuffle(scrambled)
            scrambled_word = "".join(scrambled).upper()
            context.user_data['game_word'] = word
            text = (
                f"{t('game_correct', lang)}\n\n"
                f"{t('game_next_word', lang, word=scrambled_word)}\n\n"
                f"{t('game_score', lang, score=score)}\n\n"
                f"{t('game_stop_hint', lang)}"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(t("game_skip_btn", lang), callback_data="game_skip")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")]
            ])
            await message.reply_text(text, reply_markup=markup)
        else:
            await message.reply_text(
                f"{t('game_wrong', lang)}\n\n"
                f"{t('game_hint', lang, first=correct_word[0].upper(), length=len(correct_word))}\n"
                f"{t('game_try_again', lang)}"
            )
        return

    # ================= REVIEW MODE =================
    rq = context.user_data.get("review_queue")
    if rq and message.text and not message.text.startswith("/"):
        idx = context.user_data.get("review_index", 0)
        if idx >= len(rq):
            context.user_data.pop("review_queue", None)
            context.user_data.pop("review_index", None)
            await message.reply_text(t("review_none", lang))
            return
        current = rq[idx]
        user_ans = message.text.strip().lower()
        correct = current["corrected_text"].lower()
        correct_words = set(w for w in correct.split() if len(w) > 3)
        user_words = set(w for w in user_ans.split() if len(w) > 3)
        match = len(correct_words & user_words) / max(len(correct_words), 1) if correct_words else 0
        if match >= 0.6:
            await message.reply_text(t("review_correct", lang))
            await add_coins(uid, 3)
        else:
            await message.reply_text(t("review_wrong", lang, correct=current["corrected_text"]))
        if db_pool and "id" in current:
            await mark_reviewed(current["id"])
        rc = (user.get("review_count") or 0) + 1
        await update_user(uid, review_count=rc)
        await check_achievements(uid)
        idx += 1
        context.user_data["review_index"] = idx
        if idx < len(rq):
            nxt = rq[idx]
            await message.reply_text(t("review_prompt", lang, wrong=nxt["wrong_text"]))
        else:
            context.user_data.pop("review_queue", None)
            context.user_data.pop("review_index", None)
            await message.reply_text(t("review_none", lang))
        return

    # ================= VOICE =================
    if message.voice or message.audio:
        if not user.get("is_premium"):
            last_date = user.get("last_voice_date")
            count = user.get("voice_count_today") or 0
            if last_date != today:
                count = 0
                await update_user(uid, voice_count_today=0, last_voice_date=today)
            if count >= FREE_VOICE_PER_DAY:
                await message.reply_text(t("voice_limit", lang, n=FREE_VOICE_PER_DAY))
                return
            await update_user(uid, voice_count_today=count + 1)
        msg = await message.reply_text(t("processing_voice", lang))
        path = f"/tmp/voice_{uid}.ogg"
        try:
            voice = message.voice or message.audio
            f = await context.bot.get_file(voice.file_id)
            await f.download_to_drive(path)
            text = await asyncio.to_thread(transcribe_sync, path)
            try: os.remove(path)
            except Exception: pass
            if not text:
                await msg.edit_text(t("voice_fail", lang))
                return
            await msg.edit_text(t("voice_heard", lang, text=text) + "\n\n⏳")
            history = await get_history(uid)
            answer, suggestions = await asyncio.to_thread(ask_groq, text, history, user)
            if not answer:
                answer = t("ai_error", lang)
            await save_history(uid, "user", text)
            await save_history(uid, "assistant", answer)
            await update_user(uid, last_active=datetime.now(),
                              voices_sent=(user.get("voices_sent") or 0) + 1)
            kb = suggestions_kb(suggestions, context)
            await safe_reply_feedback(message, answer, message.message_id, kb)
            corr = extract_correction(answer)
            if corr:
                await save_review(uid, corr[0], corr[1])
            if user.get("is_premium") and HAS_TTS:
                try:
                    tts_path = f"/tmp/tts_{uid}.mp3"
                    ok = await text_to_voice(answer[:500], tts_path)
                    if ok:
                        with open(tts_path, "rb") as vf:
                            await message.reply_voice(voice=vf)
                        try: os.remove(tts_path)
                        except Exception: pass
                except Exception as e:
                    logger.error(f"Voice reply: {e}")
            try: await msg.delete()
            except Exception: pass
            await check_achievements(uid)
        except Exception as e:
            logger.error(f"Voice handler: {e}")
            await msg.edit_text("❌ Error processing voice.")
        return

    # ================= DOCUMENT (PDF ANALYSIS or ADMIN UPLOAD) =================
    if message.document:
        doc = message.document
        file_size = doc.file_size or 0
        file_name = doc.file_name or "document.pdf"
        mime = (doc.mime_type or "").lower()

        # ---- Admin file upload mode ----
        if uid in ADMIN_IDS and context.user_data.get('awaiting_file'):
            context.user_data['pending_file_id'] = doc.file_id
            context.user_data['pending_file_name'] = file_name
            context.user_data['awaiting_file'] = False
            context.user_data['awaiting_file_caption'] = True
            await message.reply_text(t("addfile_received", "en", name=file_name))
            return

        # ---- Normal user PDF analysis ----
        if file_size > MAX_PDF_SIZE_MB * 1024 * 1024:
            await message.reply_text(t("pdf_too_large", lang, n=MAX_PDF_SIZE_MB))
            return
        if "pdf" not in mime and not file_name.lower().endswith(".pdf"):
            await message.reply_text("❌ Only PDF files are supported for analysis.")
            return
        if not HAS_PDF:
            await message.reply_text("❌ PDF support is not enabled.")
            return
        if not user.get("is_premium"):
            last_date = user.get("last_pdf_date")
            count = user.get("pdf_count_today") or 0
            if last_date != today:
                count = 0
                await update_user(uid, pdf_count_today=0, last_pdf_date=today)
            if count >= FREE_PDF_PER_DAY:
                await message.reply_text(t("pdf_limit", lang, n=FREE_PDF_PER_DAY))
                return
            await update_user(uid, pdf_count_today=count + 1)

        msg = await message.reply_text(t("processing_pdf", lang))
        pdf_path = f"/tmp/doc_{uid}.pdf"
        try:
            f = await context.bot.get_file(doc.file_id)
            await f.download_to_drive(pdf_path)
            result = await asyncio.to_thread(extract_pdf_text_sync, pdf_path)
            try: os.remove(pdf_path)
            except Exception: pass
            if not result:
                await msg.edit_text(t("pdf_fail", lang))
                return
            pdf_text, total_pages = result
            if total_pages > MAX_PDF_PAGES:
                await msg.edit_text(t("pdf_too_big", lang, n=MAX_PDF_PAGES))
            else:
                await msg.edit_text(t("pdf_analyzing", lang))
            user_caption = (message.caption or "").strip()
            if user_caption:
                prompt = (
                    f"The user sent a PDF file named '{file_name}' with this request: {user_caption}\n\n"
                    f"PDF Content:\n{pdf_text}\n\n"
                    f"Analyze the PDF and answer the user's request. If no specific request, summarize the PDF "
                    f"and explain its key points in simple English (with Bangla explanation if the user's language is Bangla). "
                    f"Use plain text and emojis only. No markdown."
                )
            else:
                prompt = (
                    f"The user sent a PDF file named '{file_name}'.\n\n"
                    f"PDF Content:\n{pdf_text}\n\n"
                    f"Please: 1) Give a short summary, 2) List 5-7 key points, "
                    f"3) Suggest what the user can learn from it. Use plain text and emojis only."
                )
            answer, suggestions = await asyncio.to_thread(ask_groq, prompt, None, user)
            if not answer:
                answer = t("ai_error", lang)
            await save_history(uid, "user", f"[PDF] {file_name} - {user_caption[:100]}")
            await save_history(uid, "assistant", answer)
            await update_user(uid, last_active=datetime.now(),
                              pdfs_sent=(user.get("pdfs_sent") or 0) + 1)
            kb = suggestions_kb(suggestions, context)
            await safe_reply_feedback(message, answer, message.message_id, kb)
            try: await msg.delete()
            except Exception: pass
            await check_achievements(uid)
        except Exception as e:
            logger.error(f"PDF handler: {e}")
            try:
                await msg.edit_text("❌ PDF প্রসেস করতে সমস্যা হয়েছে।")
            except Exception:
                pass
        return

    # ================= PHOTO =================
    if message.photo:
        if context.user_data.get('awaiting_payment'):
            method = context.user_data.get('payment_method', 'Unknown')
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.forward_message(
                        chat_id=admin_id, from_chat_id=message.chat_id,
                        message_id=message.message_id
                    )
                    await context.bot.send_message(
                        admin_id,
                        f"💰 {method} payment proof received!\n\n"
                        f"👤 User: {message.from_user.full_name}\n"
                        f"🆔 User ID: `{uid}`\n\n"
                        f"Approve with:\n`/approve {uid}`"
                    )
                except Exception as e:
                    logger.error(f"Fwd proof fail: {e}")
            await message.reply_text(t("payment_proof_sent", lang))
            context.user_data.pop('awaiting_payment', None)
            context.user_data.pop('payment_method', None)
            return

        if not user.get("is_premium"):
            last_date = user.get("last_img_date")
            count = user.get("img_count_today") or 0
            if last_date != today:
                count = 0
                await update_user(uid, img_count_today=0, last_img_date=today)
            if count >= FREE_IMG_PER_DAY:
                await message.reply_text(t("img_limit", lang, n=FREE_IMG_PER_DAY))
                return
            await update_user(uid, img_count_today=count + 1)

        msg = await message.reply_text(t("processing_img", lang))
        path = f"/tmp/img_{uid}.jpg"
        try:
            photo = message.photo[-1]
            f = await context.bot.get_file(photo.file_id)
            await f.download_to_drive(path)
            caption = message.caption or "Describe this image in English. Then give a Bangla translation. Use plain text with emojis only."
            answer = await asyncio.to_thread(analyze_image_sync, path, caption)
            try: os.remove(path)
            except Exception: pass
            if not answer:
                await msg.edit_text(t("img_fail", lang))
                return
            await save_history(uid, "user", f"[Photo] {caption}")
            await save_history(uid, "assistant", answer)
            await update_user(uid, last_active=datetime.now(),
                              photos_sent=(user.get("photos_sent") or 0) + 1)
            await safe_reply_feedback(message, answer, message.message_id)
            try: await msg.delete()
            except Exception: pass
            await check_achievements(uid)
        except Exception as e:
            logger.error(f"Photo handler: {e}")
            await msg.edit_text("❌ Error processing photo.")
        return

    # ================= TEXT =================
    if not message.text:
        return

    if context.user_data.get('awaiting_support') and message.text and not message.text.startswith("/"):
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.forward_message(
                    chat_id=admin_id, from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                await context.bot.send_message(
                    admin_id,
                    f"📩 Support message!\n\n"
                    f"👤 User: {message.from_user.full_name}\n"
                    f"🆔 User ID: `{uid}`\n\n"
                    f"Reply with:\n`/reply {uid} your_reply`"
                )
            except Exception as e:
                logger.error(f"Support fwd fail: {e}")
        await message.reply_text(t("support_sent", lang))
        context.user_data.pop('awaiting_support', None)
        return

    if context.user_data.get('awaiting_payment') and message.text and not message.text.startswith("/"):
        method = context.user_data.get('payment_method', 'Unknown')
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.forward_message(
                    chat_id=admin_id, from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                await context.bot.send_message(
                    admin_id,
                    f"💰 {method} payment info (text)!\n\n"
                    f"👤 User: {message.from_user.full_name}\n"
                    f"🆔 User ID: `{uid}`\n\n"
                    f"Approve with: `/approve {uid}`"
                )
            except Exception as e:
                logger.error(f"Text fwd fail: {e}")
        await message.reply_text(t("payment_info_sent", lang))
        context.user_data.pop('awaiting_payment', None)
        context.user_data.pop('payment_method', None)
        return

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
    answer, suggestions = await asyncio.to_thread(ask_groq, user_text, history, user)
    if not answer:
        answer = t("ai_error", lang)
    await save_history(uid, "assistant", answer)
    kb = suggestions_kb(suggestions, context)
    await safe_reply_feedback(message, answer, message.message_id, kb)
    corr = extract_correction(answer)
    if corr:
        await save_review(uid, corr[0], corr[1])
    if user.get("is_premium") and HAS_TTS and len(answer) < 400:
        try:
            tts_path = f"/tmp/tts_{uid}.mp3"
            ok = await text_to_voice(answer[:400], tts_path)
            if ok:
                with open(tts_path, "rb") as vf:
                    await message.reply_voice(voice=vf)
                try: os.remove(tts_path)
                except Exception: pass
        except Exception as e:
            logger.error(f"TTS send: {e}")
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
# DAILY REVIEW JOB
# ==========================================================
async def daily_review_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        if db_pool is None:
            return
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT user_id FROM s_review
                WHERE reviewed_at IS NULL AND review_at <= NOW() LIMIT 200
            """)
        for r in rows:
            uid = r["user_id"]
            try:
                due = await get_due_reviews(uid, limit=3)
                if not due:
                    continue
                lang = await get_user_lang(uid)
                first = due[0]
                await context.bot.send_message(
                    uid,
                    f"🔔 {t('review_title', lang)}\n\n{t('review_prompt', lang, wrong=first['wrong_text'])}"
                )
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Review notify {uid}: {e}")
        logger.info(f"Daily review sent to {len(rows)} users.")
    except Exception as e:
        logger.error(f"daily_review_job: {e}")


# ==========================================================
# BOT SETUP
# ==========================================================
async def post_init(app):
    try:
        await init_db()
        asyncio.create_task(keep_alive_db())
    except Exception as e:
        logger.error(f"post_init exception: {e}")
    try:
        app.job_queue.run_daily(
            daily_review_job,
            time=datetime.strptime("14:00", "%H:%M").time(),
        )
        logger.info("Daily review job scheduled at 14:00 UTC.")
    except Exception as e:
        logger.error(f"Job schedule error: {e}")
    logger.info("Init done.")


async def post_shutdown(app):
    await close_db()


def run_bot():
    async def _run():
        await init_db()
        try:
            application = (
                Application.builder()
                .token(BOT_TOKEN)
                .post_init(post_init)
                .post_shutdown(post_shutdown)
                .build()
            )
        except Exception as e:
            logger.exception(f"Application build failed: {e}")
            return

        for cmd, fn in [
            ("start", start_command), ("menu", menu_command),
            ("help", help_command), ("profile", profile_command),
            ("daily", daily_command), ("leaderboard", leaderboard_command),
            ("coins", coins_command), ("invite", invite_command),
            ("mistakes", mistakes_command), ("achievements", achievements_command),
            ("level", level_command), ("reminder", reminder_command),
            ("language", language_command), ("reset", reset_command),
            ("adminstats", adminstats_command), ("feedback", feedback_command),
            ("broadcast", broadcast_command), ("approve", approve_command),
            ("reply", reply_command),
            ("practice", practice_command),
            ("endroleplay", end_roleplay_command),
            ("endgame", endgame_command),
            ("review", review_command),
            ("memory", memory_command),
            ("addfile", addfile_command),
            ("listfiles", listfiles_command),
            ("delfile", delfile_command),
            ("cancel", cancel_command),
            ("skip", skip_command),
            # NEW
            ("pronounce", pronounce_command),
            ("cancelpronounce", cancel_pronounce_command),
            ("ielts", ielts_command),
            ("cancelielts", cancel_ielts_command),
            ("pdfquiz", pdfquiz_command),
            ("cancelpdfquiz", cancel_pdfquiz_command),
        ]:
            application.add_handler(CommandHandler(cmd, fn))

        application.add_handler(CallbackQueryHandler(cb_forcesub_check, pattern="^forcesub_check$"))
        application.add_handler(CallbackQueryHandler(cb_feedback, pattern="^fb_"))
        application.add_handler(CallbackQueryHandler(cb_suggestion_click, pattern="^sg_"))
        application.add_handler(CallbackQueryHandler(cb_set_language, pattern="^setlang_"))
        application.add_handler(CallbackQueryHandler(cb_lang_menu, pattern="^m_lang$"))
        application.add_handler(CallbackQueryHandler(student_menu_callback, pattern="^student_"))

        application.add_handler(CallbackQueryHandler(cb_practice_menu, pattern="^rp_menu$"))
        application.add_handler(CallbackQueryHandler(cb_rp_start, pattern="^rp_(?!menu$)[a-z]+$"))

        application.add_handler(CallbackQueryHandler(cb_menu, pattern="^m_menu$"))
        application.add_handler(CallbackQueryHandler(cb_profile, pattern="^m_profile$"))
        application.add_handler(CallbackQueryHandler(cb_daily, pattern="^m_daily$"))
        application.add_handler(CallbackQueryHandler(cb_word_of_day, pattern="^m_word$"))
        application.add_handler(CallbackQueryHandler(cb_quiz, pattern="^m_quiz$"))
        application.add_handler(CallbackQueryHandler(cb_review, pattern="^m_review$"))
        application.add_handler(CallbackQueryHandler(cb_memory, pattern="^m_memory$"))
        application.add_handler(CallbackQueryHandler(cb_translate, pattern="^m_translate$"))
        application.add_handler(CallbackQueryHandler(cb_invite, pattern="^m_invite$"))
        application.add_handler(CallbackQueryHandler(cb_premium, pattern="^m_premium$"))
        application.add_handler(CallbackQueryHandler(cb_leaderboard, pattern="^m_leaderboard$"))
        application.add_handler(CallbackQueryHandler(cb_mistakes, pattern="^m_mistakes$"))
        application.add_handler(CallbackQueryHandler(cb_achievements, pattern="^m_achievements$"))
        application.add_handler(CallbackQueryHandler(cb_reminder, pattern="^m_reminder$"))
        application.add_handler(CallbackQueryHandler(cb_help, pattern="^m_help$"))

        # NEW callbacks
        application.add_handler(CallbackQueryHandler(cb_pronunciation, pattern="^m_pronounce$"))
        application.add_handler(CallbackQueryHandler(cb_pron_new, pattern="^pron_new$"))
        application.add_handler(CallbackQueryHandler(cb_cancel_pronounce, pattern="^cancel_pronounce$"))
        application.add_handler(CallbackQueryHandler(cb_ielts_menu, pattern="^m_ielts$"))
        application.add_handler(CallbackQueryHandler(cb_ielts_end, pattern="^ielts_end$"))
        application.add_handler(CallbackQueryHandler(cb_pdfquiz_menu, pattern="^m_pdfquiz$"))
        application.add_handler(CallbackQueryHandler(cb_quiz_answer, pattern="^pq_\\d+$"))
        application.add_handler(CallbackQueryHandler(cb_quiz_stop, pattern="^pq_stop$"))

        application.add_handler(CallbackQueryHandler(cb_vocab_book, pattern="^m_vocab_book$"))
        application.add_handler(CallbackQueryHandler(cb_files_menu, pattern="^m_files$"))
        application.add_handler(CallbackQueryHandler(cb_file_send, pattern="^fget_"))

        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_premium$"))
        application.add_handler(CallbackQueryHandler(cb_pay_bkash, pattern="^pay_bkash$"))
        application.add_handler(CallbackQueryHandler(cb_pay_rocket, pattern="^pay_rocket$"))
        application.add_handler(CallbackQueryHandler(cb_pay_trc20, pattern="^pay_trc20$"))
        application.add_handler(CallbackQueryHandler(cb_pay_bsc20, pattern="^pay_bsc20$"))
        application.add_handler(CallbackQueryHandler(cb_cancel_payment, pattern="^cancel_payment$"))

        application.add_handler(CallbackQueryHandler(cb_copy_bkash, pattern="^copy_bkash$"))
        application.add_handler(CallbackQueryHandler(cb_copy_rocket, pattern="^copy_rocket$"))
        application.add_handler(CallbackQueryHandler(cb_copy_trc20, pattern="^copy_trc20$"))
        application.add_handler(CallbackQueryHandler(cb_copy_bsc20, pattern="^copy_bsc20$"))

        application.add_handler(CallbackQueryHandler(cb_support, pattern="^m_support$"))
        application.add_handler(CallbackQueryHandler(cb_cancel_support, pattern="^cancel_support$"))

        application.add_handler(CallbackQueryHandler(cb_word_game, pattern="^m_game$"))
        application.add_handler(CallbackQueryHandler(cb_game_skip, pattern="^game_skip$"))
        application.add_handler(CallbackQueryHandler(cb_flashcard_menu, pattern="^m_flashcard$"))
        application.add_handler(CallbackQueryHandler(cb_flashcard_start, pattern="^fc_(easy|medium|hard)$"))
        application.add_handler(CallbackQueryHandler(cb_flashcard_show, pattern="^fc_show$"))

        application.add_handler(CallbackQueryHandler(cb_reminder_set, pattern="^rem_"))
        application.add_handler(CallbackQueryHandler(cb_set_level, pattern="^setlvl_"))

        application.add_handler(PreCheckoutQueryHandler(precheckout_cb))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_cb))

        application.add_handler(CallbackQueryHandler(cb_fallback))

        application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO
                 | filters.Document.ALL) & ~filters.COMMAND,
                handle_message
            )
        )

        try:
            await application.initialize()
            await application.bot.delete_webhook(drop_pending_updates=True)
            await asyncio.sleep(5)
            await application.start()
            await application.updater.start_polling(drop_pending_updates=True)
            logger.info("Bot started.")
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
