import os
import asyncio
import logging
import threading
import random
import time
import base64
import json
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
MAX_REVIEW_PER_DAY = 5

# Payment configuration
PREMIUM_PRICE_BDT = 200
USDT_AMOUNT = 2
BKASH_NUMBER = "01608364088"
ROCKET_NUMBER = "01608364088"
TRC20_ADDRESS = "TKeEd3wuTqHse2rdzAg3rqYeRfQD1NC7tq"
BSC20_ADDRESS = "0xb83a03d9ded3ac7a4908aa87cfdfe1df9e05f719"

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
        "desc": {"bn": "হোটেলে চেক-ইন", "en": "Hotel check-in", "hi": "होटल चेक-ইन"},
        "system": (
            "You are a hotel receptionist. The user is a guest checking in. "
            "Ask for reservation, ID, room preference. Stay in character. "
            "If they make a real error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Welcome to our hotel! Do you have a reservation with us?"
    },
}


T = {
    "welcome": {
        "bn": "👋 স্বাগতম {name}!\n\n🎓 আমি EduMate AI - আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n📖 যা করতে পারি:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 অনুবাদ\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 ছবি বিশ্লেষণ\n• 🎤 ভয়েস সাপোর্ট\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 নিচের বাটন থেকে বেছে নিন।",
        "en": "👋 Welcome {name}!\n\n🎓 I am EduMate AI - your 24/7 English teacher.\n\n📖 What I can do:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 Translation\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 Photo analysis\n• 🎤 Voice support\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 Choose from below.",
        "hi": "👋 स्वागत है {name}!\n\n🎓 मैं EduMate AI हूँ - आपका 24/7 English शिक्षक।\n\n📖 मैं क्या कर सकता हूँ:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 अनुवाद\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 फोटो विश्लेषण\n• 🎤 वॉइस सपोर्ट\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 नीचे से चुनें।",
    },
    "main_menu": {"bn": "🏠 মেইন মেনু:", "en": "🏠 Main Menu:", "hi": "🏠 मुख्य मेनू:"},
    "menu_btn": {"bn": "🏠 মেইন মেনু", "en": "🏠 Main Menu", "hi": "🏠 मुख्य मेनू"},
    "loading": {"bn": "⏳ তৈরি হচ্ছে...", "en": "⏳ Generating...", "hi": "⏳ बना रहा हूँ..."},
    "ai_error": {
        "bn": "⚠️ এখন AI-তে সমস্যা হচ্ছে। আবার চেষ্টা করুন।",
        "en": "⚠️ AI is having issues. Please try again.",
        "hi": "⚠️ AI में समस्या है। कृपया पुनः प्रयास करें।",
    },
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
    "translate_hint": {
        "bn": "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান।",
        "en": "Send any Bangla or English sentence.",
        "hi": "कोई भी Bangla या English वाक्य भेजें।",
    },
    "invite_title": {"bn": "🎁 Invite & Earn", "en": "🎁 Invite & Earn", "hi": "🎁 Invite & Earn"},
    "invite_hint": {"bn": "💡 প্রতি ইনভাইটে {n} কয়েন পাবেন!", "en": "💡 Earn {n} coins per invite!", "hi": "💡 हर invite पर {n} सिक्के!"},
    "premium_title": {"bn": "💎 Premium Membership", "en": "💎 Premium Membership", "hi": "💎 Premium Membership"},
    "premium_buy": {"bn": "⭐ কিনুন ({n} Stars)", "en": "⭐ Buy ({n} Stars)", "hi": "⭐ खरीदें ({n} Stars)"},
    "premium_already": {"bn": "💎 আপনি ইতিমধ্যে Premium!", "en": "💎 You are already Premium!", "hi": "💎 आप पहले से Premium हैं!"},
    "premium_success": {"bn": "🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n✅ {days} দিনের জন্য সক্রিয়।\n\n🎁 এখন পাবেন:\n• আনলিমিটেড ছবি\n• আনলিমিটেড ভয়েস\n• Voice reply", "en": "🎉 Congratulations! You are now Premium!\n✅ Active for {days} days.\n\n🎁 Now you get:\n• Unlimited photos\n• Unlimited voice\n• Voice replies", "hi": "🎉 बधाई! आप अब Premium हैं!\n✅ {days} दिनों के लिए सक्रिय।"},
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
    "force_sub_title": {
        "bn": "🔒 বট ব্যবহার করতে হলে আমাদের গ্রুপে জয়েন করুন",
        "en": "🔒 Please join our group to use this bot",
        "hi": "🔒 इस बॉट का उपयोग करने के लिए हमारे ग्रुप से जुड़ें",
    },
    "force_sub_desc": {
        "bn": "আমাদের Friendship Hub কমিউনিটিতে জয়েন করুন। জয়েন করার পর নিচের বাটনে ক্লিক করুন।",
        "en": "Join our Friendship Hub community. After joining, tap the button below.",
        "hi": "हमारे Friendship Hub से जुड़ें। जुड़ने के बाद नीचे के बटन पर क्लिक करें।",
    },
    "force_sub_join_btn": {"bn": "👥 গ্রুপে জয়েন করুন", "en": "👥 Join Group", "hi": "👥 ग्रुप जॉइन करें"},
    "force_sub_check_btn": {"bn": "✅ জয়েন করেছি, চেক করুন", "en": "✅ I Joined, Check", "hi": "✅ जुड़ गया, चेक करें"},
    "force_sub_not_joined": {
        "bn": "❌ আপনি এখনো গ্রুপে জয়েন করেননি। জয়েন করে আবার চেক করুন।",
        "en": "❌ You haven't joined the group yet.",
        "hi": "❌ आपने अभी तक ग्रुप जॉइन नहीं किया।",
    },
    "force_sub_thanks": {
        "bn": "✅ ধন্যবাদ! এখন আপনি বট ব্যবহার করতে পারবেন।",
        "en": "✅ Thank you! You can now use the bot.",
        "hi": "✅ धन्यवाद! अब आप बॉट का उपयोग कर सकते हैं।",
    },
    "voice_limit": {
        "bn": "🎤 ফ্রি ইউজাররা দিনে {n}টি ভয়েস পাঠাতে পারেন।\n\n⭐ Premium নিলে আনলিমিটেড + Voice Reply পাবেন।",
        "en": "🎤 Free users can send {n} voice messages per day.\n\n⭐ Get Premium for unlimited + voice replies.",
        "hi": "🎤 फ्री यूज़र्स दिन में {n} वॉइस भेज सकते हैं।\n\n⭐ Premium लें unlimited के लिए।",
    },
    "img_limit": {
        "bn": "📸 ফ্রি ইউজাররা দিনে {n}টি ছবি পাঠাতে পারেন।\n\n⭐ Premium নিলে আনলিমিটেড পাবেন।",
        "en": "📸 Free users can send {n} photos per day.\n\n⭐ Get Premium for unlimited.",
        "hi": "📸 फ्री यूज़र्स दिन में {n} फोटो भेज सकते हैं।\n\n⭐ Premium लें।",
    },
    "processing_voice": {"bn": "🎤 ভয়েস প্রসেস হচ্ছে...", "en": "🎤 Processing voice...", "hi": "🎤 वॉइस प्रोसेस हो रही है..."},
    "processing_img": {"bn": "📸 ছবি বিশ্লেষণ হচ্ছে...", "en": "📸 Analyzing image...", "hi": "📸 फोटो विश्लेषण हो रहा है..."},
    "voice_heard": {"bn": "📝 আপনি বলেছেন: {text}", "en": "📝 You said: {text}", "hi": "📝 आपने कहा: {text}"},
    "voice_fail": {"bn": "❌ ভয়েস বুঝতে পারিনি। আবার পাঠান।", "en": "❌ Could not understand voice.", "hi": "❌ वॉइस समझ नहीं आई।"},
    "img_fail": {"bn": "❌ ছবি বুঝতে পারিনি। আবার পাঠান।", "en": "❌ Could not analyze image.", "hi": "❌ फोटो समझ नहीं आई।"},
    "feedback_thanks": {"bn": "🙏 ধন্যবাদ আপনার মতামতের জন্য!", "en": "🙏 Thanks for your feedback!", "hi": "🙏 फीडबैक के लिए धन्यवाद!"},
    "practice_title": {"bn": "🎭 Role-Play Practice", "en": "🎭 Role-Play Practice", "hi": "🎭 Role-Play अभ्यास"},
    "practice_desc": {"bn": "একটা পরিস্থিতি বেছে নিন:", "en": "Choose a scenario:", "hi": "एक परिस्थिति चुनें:"},
    "rp_started": {"bn": "🎭 {title} শুরু হয়েছে!\n\nবন্ধ করতে /endroleplay দিন।", "en": "🎭 {title} started!\n\nSend /endroleplay to stop.", "hi": "🎭 {title} शुरू!\n\nरोकने के लिए /endroleplay भेजें।"},
    "rp_ended": {"bn": "🎭 Role-Play শেষ। আবার শুরু করতে /practice দিন।", "en": "🎭 Role-Play ended. Send /practice to start again.", "hi": "🎭 Role-Play खत्म। फिर से /practice भेजें।"},
    "rp_active": {"bn": "⚠️ আপনি এখনো Role-Play মোডে আছেন। /endroleplay দিয়ে বন্ধ করুন।", "en": "⚠️ You're in Role-Play mode. Send /endroleplay to stop.", "hi": "⚠️ आप Role-Play में हैं। /endroleplay भेजें।"},
    "review_title": {"bn": "🔁 Spaced Review", "en": "🔁 Spaced Review", "hi": "🔁 Spaced Review"},
    "review_none": {"bn": "✅ আজ কোনো রিভিউ নেই! আরও ভুল করতে থাকুন 😊", "en": "✅ No reviews today! Keep practicing.", "hi": "✅ आज कोई रिव्यू नहीं!"},
    "review_prompt": {"bn": "🔁 মনে আছে?\n\n❌ আগের ভুল: {wrong}\n\n✅ সঠিকটা লিখুন:", "en": "🔁 Remember?\n\n❌ Old mistake: {wrong}\n\n✅ Write the correct version:", "hi": "🔁 याद है?\n\n❌ पुरानी गलती: {wrong}\n\n✅ सही लिखें:"},
    "review_correct": {"bn": "🎉 একদম সঠিক! আজকের রিভিউ শেষ।", "en": "🎉 Perfect! Review complete for today.", "hi": "🎉 बिल्कुल सही! रिव्यू पूरा।"},
    "review_wrong": {"bn": "❌ এটা ঠিক হয়নি।\n\n✅ সঠিক: {correct}\n\nআবার চেষ্টা করুন কাল।", "en": "❌ Not quite.\n\n✅ Correct: {correct}\n\nTry again tomorrow.", "hi": "❌ सही नहीं।\n\n✅ सही: {correct}\n\nकल फिर कोशिश करें।"},
    "memory_title": {"bn": "🧠 আমি যা মনে রেখেছি", "en": "🧠 What I Remember", "hi": "🧠 मुझे याद है"},
    "review_saved": {"bn": "✅ রিভিউ লিস্টে যোগ হয়েছে!", "en": "✅ Added to review list!", "hi": "✅ रिव्यू लिस्ट में जोड़ा गया!"},
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
# GROQ
# ==========================================================
groq_client = Groq(api_key=GROQ_API_KEY)

BASE_SYSTEM_PROMPT = """
You are EduMate AI - an expert English teacher and general assistant for South Asian students.

LANGUAGE: Match the user's language (Bangla->Bangla, English->English, Hindi->Hindi).

RULES:
1. NEVER use markdown tables.
2. NEVER use asterisks (*), double asterisks (**), underscores, or backticks.
3. Use PLAIN TEXT only with emojis.
4. Use emojis as bullets: 🔷 👉 ✏️ 📝 ✅ ❌ 🎯 📚 💡 🔊 🔁 ⭐ 🔥 🎭
5. Separate each item with a BLANK LINE.
6. Be accurate. Never invent facts.
7. Be warm but not over-friendly. Never mock the user.
8. Keep responses under 3500 characters.
9. Match the user's level (beginner/intermediate/advanced).
10. Focus on what the user asks NOW.

VOCABULARY FORMAT:
🔷 word - /pronunciation/ - Part of Speech
👉 Meaning: [meaning]
✏️ Example: [English sentence]
📝 Translation: [translation]

GRAMMAR FORMAT:
📌 Rule Name
🔹 Usage: brief explanation
✅ Example: correct example
❌ Common Mistake: what learners do wrong

SENTENCE CORRECTION FORMAT (when user's sentence has errors):
❌ Wrong: [user's sentence]
✅ Correct: [corrected]
📝 Why: [brief reason in user's language]
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


def ask_groq(user_text, history=None, user=None, custom_system=None):
    try:
        system = custom_system if custom_system else BASE_SYSTEM_PROMPT
        include_name = custom_system is None
        system += build_user_context(user, include_name=include_name)
        messages = [{"role": "system", "content": system}]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": user_text})
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            temperature=0.4,
            max_tokens=1200,
        )
        text = response.choices[0].message.content.strip()
        return text if text else None
    except Exception as e:
        logger.error(f"Groq error: {e}")
        return None


async def text_to_voice(text, output_path):
    try:
        import edge_tts
        communicate = edge_tts.Communicate(text, TTS_VOICE)
        await communicate.save(output_path)
        return True
    except Exception as e:
        logger.error(f"TTS error: {e}")
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
                        {"type": "text", "text": prompt or "Describe this image briefly. Then list key points with emojis."},
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
                    last_voice_date DATE,
                    last_img_date DATE,
                    photos_sent INTEGER DEFAULT 0,
                    voices_sent INTEGER DEFAULT 0,
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
                "img_count_today": 0, "last_voice_date": None,
                "last_img_date": None, "photos_sent": 0, "voices_sent": 0,
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
                "UPDATE s_review SET reviewed_at = NOW() WHERE id = $1",
                review_id,
            )
    except Exception:
        pass


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
        [InlineKeyboardButton("📊 My Progress", callback_data="m_profile"),
         InlineKeyboardButton("🏆 Leaderboard", callback_data="m_leaderboard")],
        [InlineKeyboardButton("🎁 Invite & Earn", callback_data="m_invite"),
         InlineKeyboardButton("⭐ Premium", callback_data="m_premium")],
        [InlineKeyboardButton("📚 My Mistakes", callback_data="m_mistakes"),
         InlineKeyboardButton("🏅 Achievements", callback_data="m_achievements")],
        [InlineKeyboardButton("🧠 Memory", callback_data="m_memory"),
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
        return True
    except Exception as e:
        logger.error(f"reply fail: {e}")
        return False


async def safe_reply_feedback(message, text, msg_id):
    if not text:
        text = "⚠️"
    if len(text) > 4000:
        text = text[:4000]
    try:
        await message.reply_text(text, reply_markup=feedback_kb(msg_id))
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
    context.user_data.pop("roleplay", None)
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
    context.user_data.pop("roleplay", None)
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
    if context.user_data.get("roleplay"):
        context.user_data.pop("roleplay", None)
        lang = await get_user_lang(update.effective_user.id)
        await update.message.reply_text(t("rp_ended", lang))
    else:
        await update.message.reply_text("⚠️ আপনি Role-Play মোডে নেই।")


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
    await update.message.reply_text(
        t("review_prompt", lang, wrong=first["wrong_text"])
    )


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
            "/daily - Daily lesson\n/leaderboard - Leaderboard\n"
            "/coins - Balance\n/invite - Invite link\n"
            "/mistakes - Mistakes\n/achievements - Badges\n"
            "/level - Set level\n/reminder - Reminder\n"
            "/language - Change language\n/reset - Clear chat\n\n"
            "📸 Send photo, 🎤 voice, 👍👎 rate replies"
        )
    elif lang == "hi":
        text = (
            "📖 सहायता\n\n"
            "/start - मुख्य\n/menu - मेनू\n/profile - प्रोफ़ाइल\n"
            "/practice - 🎭 Role-Play\n/review - 🔁 रिव्यू\n"
            "/memory - 🧠 मुझे याद है\n/endroleplay - रोकें\n"
            "/daily - पाठ\n/leaderboard - लीडरबोर्ड\n"
            "/coins - सिक्के\n/invite - आमंत्रण\n"
            "/mistakes - गलतियाँ\n/achievements - बैज\n"
            "/level - स्तर\n/reminder - रिमाइंडर\n"
            "/language - भाषा\n/reset - चैट साफ़"
        )
    else:
        text = (
            "📖 সাহায্য\n\n"
            "/start - মেইন মেনু\n/menu - মেনু\n/profile - প্রোফাইল\n"
            "/practice - 🎭 Role-Play\n/review - 🔁 Spaced Review\n"
            "/memory - 🧠 আমি যা মনে রেখেছি\n/endroleplay - Role-Play বন্ধ\n"
            "/daily - Daily Lesson\n/leaderboard - লিডারবোর্ড\n"
            "/coins - কয়েন\n/invite - ইনভাইট\n"
            "/mistakes - ভুল\n/achievements - ব্যাজ\n"
            "/level - লেভেল\n/reminder - রিমাইন্ডার\n"
            "/language - ভাষা\n/reset - চ্যাট ক্লিয়ার\n\n"
            "📸 ছবি, 🎤 ভয়েস পাঠান, 👍👎 রেটিং দিন"
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
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word (with meaning + pronunciation + example), "
        "1 grammar tip with 2 examples, 1 practice question. Plain text.",
        None, user
    )
    if not answer:
        answer = "📚 Word: Persistent - Meaning: continuing firmly\nExample: Be persistent."
    await safe_reply(
        update.message,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n\n{answer}"
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
    context.user_data.pop("roleplay", None)
    context.user_data.pop("review_queue", None)
    await update.message.reply_text(t("reset_done", lang))


async def adminstats_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if db_pool is None:
        await update.message.reply_text(
            f"📊 Admin Stats\n\n👥 Users: {len(_mem_users)}\n💾 Mode: In-Memory ❌\n\nDB not connected!"
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
            total_reviews = await conn.fetchval("SELECT COUNT(*) FROM s_review")
        await safe_reply(
            update.message,
            f"📊 Admin Dashboard\n\n"
            f"👥 Total Users: {total}\n🟢 24h Active: {today}\n📅 7d Active: {week}\n"
            f"💎 Premium: {premium}\n🪙 Total Coins: {total_coins}\n💬 Messages: {total_msgs}\n"
            f"🔁 Reviews saved: {total_reviews}\n\n"
            f"💾 Mode: PostgreSQL ✅"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ DB error: {e}")


async def feedback_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if db_pool is None:
        await update.message.reply_text("❌ DB নেই।")
        return
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT rating, COUNT(*) as cnt 
                FROM s_feedback 
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY rating
            """)
        good = 0
        bad = 0
        for r in rows:
            if r["rating"] == "good":
                good = r["cnt"]
            elif r["rating"] == "bad":
                bad = r["cnt"]
        total = good + bad
        rate = (good / total * 100) if total > 0 else 0
        await update.message.reply_text(
            f"📊 Last 7 days Feedback\n\n"
            f"👍 Good: {good}\n👎 Bad: {bad}\n"
            f"📈 Satisfaction: {rate:.1f}%\n📝 Total: {total}"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


async def broadcast_command(update, context):
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


async def approve_command(update, context):
    uid = update.effective_user.id
    if uid not in ADMIN_IDS:
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /approve <user_id>")
        return
    try:
        target_uid = int(context.args[0])
        until = datetime.now() + timedelta(days=PREMIUM_DAYS)
        await update_user(target_uid, is_premium=True, premium_until=until)
        await update.message.reply_text(f"✅ User {target_uid} has been granted Premium!")
        try:
            await context.bot.send_message(target_uid, "🎉 আপনার পেমেন্ট ভেরিফাই হয়েছে! আপনি এখন Premium সদস্য।")
        except Exception:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")


# ==========================================================
# STUDENT PROMPTS
# ==========================================================
STUDENT_PROMPTS = {
    "student_learn": "Start a short English lesson. Choose one useful topic. Explain simply, give 2 examples, then ONE practice question. Plain text.",
    "student_vocab": "Teach ONE English word: meaning, pronunciation, part of speech, example. Then ONE practice question. Plain text.",
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
    await q.answer("🙏 ধন্যবাদ!")
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
    answer = await asyncio.to_thread(ask_groq, prompt, None, user)
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
    await safe_edit(q, answer, reply_markup=back_kb(lang))


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
        f"{t('rp_started', lang, title=title)}\n\n"
        f"{scenario['emoji']} {starter}"
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
    context.user_data.pop("roleplay", None)
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
    answer = await asyncio.to_thread(
        ask_groq,
        "Give today's short English lesson: 1 new word + meaning + example, 1 grammar tip, 1 practice question. Plain text.",
        None, user
    )
    if not answer:
        answer = "📚 Word: Diligent - hardworking\nExample: She is a diligent student."
    await safe_edit(
        q,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n\n{answer}",
        reply_markup=back_kb(lang),
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
    answer = await asyncio.to_thread(
        ask_groq,
        "Give ONE advanced English word of the day. Include: word, meaning, pronunciation, part of speech, 2 examples, 2 synonyms. Plain text.",
        None, user
    )
    if not answer:
        answer = "🔤 Word: Resilient\n📖 Meaning: able to recover quickly\n🔊 /riˈziliənt/"
    await safe_edit(q, f"{t('word_title', lang)}\n\n{answer}", reply_markup=back_kb(lang))


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
    answer = await asyncio.to_thread(
        ask_groq,
        "Create ONE English multiple-choice quiz with 4 options. Format:\nQuestion: ...\nA) ...\nB) ...\nC) ...\nD) ...\nAnswer: X) ...\nPlain text.",
        None, user
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
    await safe_edit(
        q,
        t("review_prompt", lang, wrong=first["wrong_text"]),
        reply_markup=back_kb(lang),
    )


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
    await safe_edit(
        q,
        f"{t('premium_title', lang)}\n\n"
        f"⭐ {PREMIUM_STARS} Telegram Stars → {PREMIUM_DAYS} {t('days', lang)}\n"
        f"💳 bKash/Rocket: {PREMIUM_PRICE_BDT} BDT → {PREMIUM_DAYS} {t('days', lang)}\n"
        f"🪙 Crypto: {USDT_AMOUNT} USDT → {PREMIUM_DAYS} {t('days', lang)}\n\n"
        f"🎁 Benefits:\n"
        f"• Unlimited AI\n"
        f"• 📸 Unlimited photos\n"
        f"• 🎤 Unlimited voices + Voice replies\n"
        f"• 🎭 Unlimited role-plays\n"
        f"• Detailed Lessons\n"
        f"• Priority Response",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(t("premium_buy", lang, n=PREMIUM_STARS), callback_data="buy_premium")],
            [InlineKeyboardButton(f"💳 bKash ({PREMIUM_PRICE_BDT}৳)", callback_data="pay_bkash")],
            [InlineKeyboardButton(f"💳 Rocket ({PREMIUM_PRICE_BDT}৳)", callback_data="pay_rocket")],
            [InlineKeyboardButton("🪙 USDT (TRC20)", callback_data="pay_trc20")],
            [InlineKeyboardButton("🪙 USDT (BSC20)", callback_data="pay_bsc20")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ]),
    )


async def cb_buy_premium(update, context):
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


# ==========================================================
# MANUAL PAYMENT CALLBACKS (with awaiting_payment flag)
# ==========================================================
async def cb_pay_bkash(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'bKash'
    text = (
        "💳 **bKash Payment**\n\n"
        f"১. আপনার bKash এপ থেকে **Send Money** করুন।\n"
        f"২. নাম্বার: `{BKASH_NUMBER}`\n"
        f"৩. এমাউন্ট: `{PREMIUM_PRICE_BDT}` টাকা\n"
        "৪. টাকা পাঠানোর পর **Transaction ID (TrxID)** এবং **স্ক্রিনশট** এই চ্যাটে পাঠান।\n\n"
        "✅ অ্যাডমিন চেক করে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।"
    )
    await safe_edit(q, text, reply_markup=back_kb("bn"))


async def cb_pay_rocket(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'Rocket'
    text = (
        "💳 **Rocket Payment**\n\n"
        f"১. আপনার Rocket এপ থেকে **Send Money** করুন।\n"
        f"২. নাম্বার: `{ROCKET_NUMBER}`\n"
        f"৩. এমাউন্ট: `{PREMIUM_PRICE_BDT}` টাকা\n"
        "৪. টাকা পাঠানোর পর **Transaction ID (TrxID)** এবং **স্ক্রিনশট** এই চ্যাটে পাঠান।\n\n"
        "✅ অ্যাডমিন চেক করে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।"
    )
    await safe_edit(q, text, reply_markup=back_kb("bn"))


async def cb_pay_trc20(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (TRC20)'
    text = (
        "🪙 **Crypto Payment (USDT TRC20)**\n\n"
        f"১. আপনার ওয়ালেট থেকে **{USDT_AMOUNT} USDT (TRC20)** পাঠান।\n"
        f"২. TRC20 অ্যাড্রেস: `{TRC20_ADDRESS}`\n"
        "৩. টাকা পাঠানোর পর **Transaction Hash (TxID)** এবং **স্ক্রিনশট** এই চ্যাটে পাঠান।\n\n"
        "✅ অ্যাডমিন চেক করে ১০ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।"
    )
    await safe_edit(q, text, reply_markup=back_kb("bn"))


async def cb_pay_bsc20(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (BSC20)'
    text = (
        "🪙 **Crypto Payment (USDT BSC20/BEP20)**\n\n"
        f"১. আপনার ওয়ালেট থেকে **{USDT_AMOUNT} USDT (BSC20)** পাঠান।\n"
        f"২. BSC20 অ্যাড্রেস: `{BSC20_ADDRESS}`\n"
        "৩. টাকা পাঠানোর পর **Transaction Hash (TxID)** এবং **স্ক্রিনশট** এই চ্যাটে পাঠান।\n\n"
        "✅ অ্যাডমিন চেক করে ১০ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেবে।"
    )
    await safe_edit(q, text, reply_markup=back_kb("bn"))


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
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n\n"
                "📸 Send photos, 🎤 voice, 👍👎 rate replies")
    elif lang == "hi":
        text = ("ℹ️ सहायता\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🔥 Daily, 📖 Word of Day, 📊 Progress, 🏆 Leaderboard\n"
                "🎁 Invite, ⭐ Premium, 📚 Mistakes, 🏅 Achievements\n"
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n\n"
                "📸 फोटो, 🎤 वॉइस, 👍👎 रेटिंग")
    else:
        text = ("ℹ️ সাহায্য\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🔥 Daily, 📖 Word of Day, 📊 Progress, 🏆 Leaderboard\n"
                "🎁 Invite, ⭐ Premium, 📚 Mistakes, 🏅 Achievements\n"
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n\n"
                "📸 ছবি, 🎤 ভয়েস, 👍👎 রেটিং")
    await safe_edit(q, text, reply_markup=back_kb(lang))


async def cb_fallback(update, context):
    q = update.callback_query
    await q.answer("Unknown option", show_alert=False)
    logger.warning(f"Unhandled callback: {q.data}")


# ==========================================================
# TEXT / PHOTO / VOICE HANDLER
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
        answer = await asyncio.to_thread(
            ask_groq, user_text, rp["history"], user, rp["system"]
        )
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
                    try:
                        os.remove(tts_path)
                    except Exception:
                        pass
            except Exception:
                pass
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
            await message.reply_text(
                t("review_wrong", lang, correct=current["corrected_text"])
            )
        if db_pool and "id" in current:
            await mark_reviewed(current["id"])
        rc = (user.get("review_count") or 0) + 1
        await update_user(uid, review_count=rc)
        await check_achievements(uid)
        idx += 1
        context.user_data["review_index"] = idx
        if idx < len(rq):
            nxt = rq[idx]
            await message.reply_text(
                t("review_prompt", lang, wrong=nxt["wrong_text"])
            )
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
            try:
                os.remove(path)
            except Exception:
                pass
            if not text:
                await msg.edit_text(t("voice_fail", lang))
                return
            await msg.edit_text(t("voice_heard", lang, text=text) + "\n\n⏳")
            history = await get_history(uid)
            answer = await asyncio.to_thread(ask_groq, text, history, user)
            if not answer:
                answer = t("ai_error", lang)
            await save_history(uid, "user", text)
            await save_history(uid, "assistant", answer)
            await update_user(uid,
                              last_active=datetime.now(),
                              voices_sent=(user.get("voices_sent") or 0) + 1)
            await safe_reply_feedback(message, answer, message.message_id)
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
                        try:
                            os.remove(tts_path)
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(f"Voice reply: {e}")
            try:
                await msg.delete()
            except Exception:
                pass
            await check_achievements(uid)
        except Exception as e:
            logger.error(f"Voice handler: {e}")
            await msg.edit_text("❌ Error processing voice.")
        return

    # ================= PHOTO =================
    if message.photo:
        # ============ PAYMENT PROOF HANDLING (NEW) ============
        if context.user_data.get('awaiting_payment'):
            method = context.user_data.get('payment_method', 'Unknown')
            # Forward to all admins
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.forward_message(
                        chat_id=admin_id,
                        from_chat_id=message.chat_id,
                        message_id=message.message_id
                    )
                    await context.bot.send_message(
                        admin_id,
                        f"💰 {method} পেমেন্ট প্রুফ পাওয়া গেছে!\n\n"
                        f"👤 ইউজারের নাম: {message.from_user.full_name}\n"
                        f"🆔 ইউজার আইডি: `{uid}`\n\n"
                        f"ভেরিফাই করে অ্যাপ্রুভ করতে এই কমান্ডটি কপি করুন:\n"
                        f"`/approve {uid}`"
                    )
                except Exception as e:
                    logger.error(f"Failed to forward payment proof to admin {admin_id}: {e}")

            await message.reply_text(
                "✅ আপনার পেমেন্ট প্রুফ অ্যাডমিনের কাছে পাঠানো হয়েছে।\n"
                "ভেরিফিকেশন শেষ হলে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেওয়া হবে।"
            )
            context.user_data.pop('awaiting_payment', None)
            context.user_data.pop('payment_method', None)
            return

        # ============ NORMAL IMAGE ANALYSIS ============
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
            try:
                os.remove(path)
            except Exception:
                pass
            if not answer:
                await msg.edit_text(t("img_fail", lang))
                return
            await save_history(uid, "user", f"[Photo] {caption}")
            await save_history(uid, "assistant", answer)
            await update_user(uid,
                              last_active=datetime.now(),
                              photos_sent=(user.get("photos_sent") or 0) + 1)
            await safe_reply_feedback(message, answer, message.message_id)
            try:
                await msg.delete()
            except Exception:
                pass
            await check_achievements(uid)
        except Exception as e:
            logger.error(f"Photo handler: {e}")
            await msg.edit_text("❌ Error processing photo.")
        return

    # ================= TEXT =================
    if not message.text:
        return

    # If user is in payment mode and sends text (TrxID), forward to admin too
    if context.user_data.get('awaiting_payment') and message.text and not message.text.startswith("/"):
        method = context.user_data.get('payment_method', 'Unknown')
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.forward_message(
                    chat_id=admin_id,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
                await context.bot.send_message(
                    admin_id,
                    f"💰 {method} পেমেন্ট ইনফো (টেক্সট)!\n\n"
                    f"👤 ইউজারের নাম: {message.from_user.full_name}\n"
                    f"🆔 ইউজার আইডি: `{uid}`\n\n"
                    f"অ্যাপ্রুভ করতে: `/approve {uid}`"
                )
            except Exception as e:
                logger.error(f"Failed to forward text to admin: {e}")
        await message.reply_text(
            "✅ আপনার পেমেন্ট ইনফো অ্যাডমিনের কাছে পাঠানো হয়েছে।\n"
            "ভেরিফিকেশন শেষ হলে ৫ মিনিটের মধ্যে আপনার প্রিমিয়াম চালু করে দেওয়া হবে।"
        )
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

    answer = await asyncio.to_thread(ask_groq, user_text, history, user)
    if not answer:
        answer = t("ai_error", lang)

    await save_history(uid, "assistant", answer)
    await safe_reply_feedback(message, answer, message.message_id)

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
                try:
                    os.remove(tts_path)
                except Exception:
                    pass
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
                WHERE reviewed_at IS NULL AND review_at <= NOW()
                LIMIT 200
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
            ("practice", practice_command),
            ("endroleplay", end_roleplay_command),
            ("review", review_command),
            ("memory", memory_command),
        ]:
            application.add_handler(CommandHandler(cmd, fn))

        application.add_handler(CallbackQueryHandler(cb_forcesub_check, pattern="^forcesub_check$"))
        application.add_handler(CallbackQueryHandler(cb_feedback, pattern="^fb_"))
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

        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_premium$"))
        application.add_handler(CallbackQueryHandler(cb_pay_bkash, pattern="^pay_bkash$"))
        application.add_handler(CallbackQueryHandler(cb_pay_rocket, pattern="^pay_rocket$"))
        application.add_handler(CallbackQueryHandler(cb_pay_trc20, pattern="^pay_trc20$"))
        application.add_handler(CallbackQueryHandler(cb_pay_bsc20, pattern="^pay_bsc20$"))
        application.add_handler(CallbackQueryHandler(cb_reminder_set, pattern="^rem_"))
        application.add_handler(CallbackQueryHandler(cb_set_level, pattern="^setlvl_"))

        application.add_handler(PreCheckoutQueryHandler(precheckout_cb))
        application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_cb))

        application.add_handler(CallbackQueryHandler(cb_fallback))

        application.add_handler(
            MessageHandler(
                (filters.TEXT | filters.PHOTO | filters.VOICE | filters.AUDIO) & ~filters.COMMAND,
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
