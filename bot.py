try:
    from course_content_bn import get_static_lesson_bn, BEGINNER_BN
    HAS_STATIC_BN = True
except ImportError:
    HAS_STATIC_BN = False
    BEGINNER_BN = {}
    def get_static_lesson_bn(k, d): return None
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

try:
    from courses import (
        COURSE_DATA, COURSE_TOTAL_DAYS,
        get_course_name, get_course_desc, get_day_info,
        get_topic_display, build_lesson_prompt, build_quiz_prompt,
    )
    HAS_COURSES = True
except ImportError:
    HAS_COURSES = False
    COURSE_DATA = {}
    COURSE_TOTAL_DAYS = 30
    def get_course_name(k, l): return "Course"
    def get_course_desc(k, l): return ""
    def get_day_info(k, d): return None
    def get_topic_display(k, d, l): return "—"
    def build_lesson_prompt(k, d, l): return None
    def build_quiz_prompt(k, d, l): return None


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
FREE_IMG_PER_DAY = 5
FREE_VOICE_PER_DAY = 10
FREE_PDF_PER_DAY = 5
MAX_REVIEW_PER_DAY = 5
MAX_PDF_SIZE_MB = 10
MAX_PDF_PAGES = 20

PREMIUM_PLANS = {
    "1m": {
        "days": 30, "bdt": 200, "stars": 100, "usdt": 2,
        "label_bn": "১ মাস", "label_en": "1 Month",
        "label_hi": "1 महीना", "label_ru": "1 месяц",
    },
    "3m": {
        "days": 90, "bdt": 500, "stars": 250, "usdt": 5,
        "label_bn": "৩ মাস", "label_en": "3 Months",
        "label_hi": "3 महीने", "label_ru": "3 месяца",
    },
    "6m": {
        "days": 180, "bdt": 900, "stars": 450, "usdt": 9,
        "label_bn": "৬ মাস", "label_en": "6 Months",
        "label_hi": "6 महीने", "label_ru": "6 месяцев",
    },
}

PREMIUM_STARS = 100
PREMIUM_DAYS = 30
PREMIUM_PRICE_BDT = 200
USDT_AMOUNT = 2
BKASH_NUMBER = "01608364088"
ROCKET_NUMBER = "01608364088"
TRC20_ADDRESS = "TKeEd3wuTqHse2rdzAg3rqYeRfQD1NC7tq"
BSC20_ADDRESS = "0xb83a03d9ded3ac7a4908aa87cfdfe1df9e05f719"
SUPPORT_CONTACT = "@asikul_echo"

ACHIEVEMENTS = {
    "first_chat": ("🥇", {"bn": "প্রথম চ্যাট", "en": "First Chat", "hi": "पहला चैट", "ru": "Первый чат"}),
    "words_10": ("📚", {"bn": "১০ শব্দ শিখেছেন", "en": "10 words learned", "hi": "10 शब्द सीखे", "ru": "10 слов изучено"}),
    "words_50": ("📖", {"bn": "৫০ শব্দ শিখেছেন", "en": "50 words learned", "hi": "50 शब्द सीखे", "ru": "50 слов изучено"}),
    "quiz_10": ("🎯", {"bn": "১০ কুইজ দিয়েছেন", "en": "10 quizzes done", "hi": "10 क्विज़ पूरी", "ru": "10 викторин"}),
    "streak_7": ("🔥", {"bn": "৭ দিনের স্ট্রিক", "en": "7-day streak", "hi": "7 दिन की स्ट्रीक", "ru": "7-дневная серия"}),
    "streak_30": ("💪", {"bn": "৩০ দিনের স্ট্রিক", "en": "30-day streak", "hi": "30 दिन की स्ट्रीक", "ru": "30-дневная серия"}),
    "premium": ("💎", {"bn": "Premium সদস্য", "en": "Premium member", "hi": "Premium सदस्य", "ru": "Premium-участник"}),
    "referrer": ("🎁", {"bn": "কাউকে ইনভাইট করেছেন", "en": "Invited someone", "hi": "किसी को आमंत्रित किया", "ru": "Пригласил друга"}),
    "photo_5": ("📸", {"bn": "৫টি ছবি পাঠিয়েছেন", "en": "5 photos sent", "hi": "5 फोटो भेजे", "ru": "5 фото отправлено"}),
    "voice_10": ("🎤", {"bn": "১০টি ভয়েস পাঠিয়েছেন", "en": "10 voices sent", "hi": "10 वॉइस भेजे", "ru": "10 голосовых"}),
    "roleplay_5": ("🎭", {"bn": "৫টি Role-Play করেছেন", "en": "5 role-plays done", "hi": "5 रोल-प्ले किए", "ru": "5 ролевых игр"}),
    "review_10": ("🔁", {"bn": "১০টি রিভিউ করেছেন", "en": "10 reviews done", "hi": "10 रिव्यू किए", "ru": "10 повторений"}),
    "pronounce_10": ("🎤", {"bn": "১০টি উচ্চারণ প্র্যাকটিস", "en": "10 pronunciation practices", "hi": "10 उच्चारण अभ्यास", "ru": "10 упражнений"}),
    "ielts_done": ("🎯", {"bn": "IELTS টেস্ট সম্পন্ন", "en": "IELTS test completed", "hi": "IELTS टेस्ट पूरा", "ru": "IELTS тест завершён"}),
    "pdf_quiz_5": ("🧠", {"bn": "৫টি PDF কুইজ", "en": "5 PDF quizzes", "hi": "5 PDF क्विज़", "ru": "5 викторин"}),
}


ROLEPLAY_SCENARIOS = {
    "restaurant": {
        "emoji": "🍽️",
        "title": {"bn": "রেস্টুরেন্ট", "en": "Restaurant", "hi": "रेस्टोरेंट", "ru": "Ресторан"},
        "desc": {"bn": "খাবার অর্ডার করা শিখুন", "en": "Learn to order food", "hi": "खाना ऑर्डर करना सीखें", "ru": "Заказ еды"},
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
        "title": {"bn": "এয়ারপোর্ট", "en": "Airport Check-in", "hi": "एयरपोर्ट", "ru": "Аэропорт"},
        "desc": {"bn": "চেক-ইন শেখা", "en": "Learn check-in English", "hi": "चेक-इन सीखें", "ru": "Регистрация"},
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
        "title": {"bn": "চাকরির ইন্টারভিউ", "en": "Job Interview", "hi": "जॉब इंटरव्यू", "ru": "Собеседование"},
        "desc": {"bn": "ইন্টারভিউ প্র্যাকটিস", "en": "Practice job interviews", "hi": "इंटरव्यू अभ्यास", "ru": "Практика"},
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
        "title": {"bn": "শপিং", "en": "Shopping", "hi": "शॉपिंग", "ru": "Шопинг"},
        "desc": {"bn": "দোকানে কেনাকাটা", "en": "Shopping at a store", "hi": "दुकान में खरीदारी", "ru": "Покупки"},
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
        "title": {"bn": "ডাক্তার", "en": "Doctor Visit", "hi": "डॉक्टर", "ru": "У врача"},
        "desc": {"bn": "ডাক্তারের সাথে কথা", "en": "Talk to a doctor", "hi": "डॉक्टर से बात", "ru": "Разговор с врачом"},
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
        "title": {"bn": "হোটেল", "en": "Hotel Check-in", "hi": "होटल", "ru": "Отель"},
        "desc": {"bn": "হোটেলে চেক-ইন", "en": "Hotel check-in", "hi": "होटल चेक-इन", "ru": "Заселение"},
        "system": (
            "You are a hotel receptionist. The user is a guest checking in. "
            "Ask for reservation, ID, room preference. Stay in character. "
            "If they make a real error, add [Correction: wrong -> correct] at the end. "
            "Keep replies to 2-3 short lines. Plain text with 1 emoji."
        ),
        "starter": "Welcome to our hotel! Do you have a reservation with us?"
    },
}


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


LEARN_TOPICS = [
    "Greetings and introductions", "Ordering food at a restaurant",
    "Asking for directions", "Talking about hobbies", "Making small talk",
    "Shopping vocabulary", "Describing people", "Weather and seasons",
    "Daily routine", "At the doctor's office", "Job interview basics",
    "Travel and airport", "Making phone calls", "At the bank",
    "Emergency situations", "Making appointments", "Describing your hometown",
    "Sports and games", "Music and entertainment", "Technology and gadgets",
    "Family and relationships", "Food and cooking", "Health and fitness",
    "Education and school", "Money and banking", "Emotions and feelings",
    "Transportation", "Housing and apartments", "Festivals and celebrations",
    "Nature and environment", "Body and health", "Colors and shapes",
    "Numbers and counting", "Time and dates", "Holidays and traditions",
    "Work and office", "Public transportation", "Restaurant conversation",
    "Hotel booking", "Customer service", "At the supermarket",
    "Post office vocabulary", "Airport immigration", "Using public transport",
    "Meeting new people", "Compliments and responses", "Apologies and forgiveness",
    "Expressing opinions", "Giving advice", "Making suggestions",
]

VOCAB_WORDS = [
    "abundant", "beneficial", "coherent", "diligent", "eloquent", "fascinating",
    "grateful", "humble", "innovative", "jubilant", "keen", "lucid",
    "magnificent", "notable", "optimistic", "persistent", "quaint", "resilient",
    "sincere", "tenacious", "unique", "vibrant", "witty", "yearn", "zealous",
    "articulate", "benevolent", "candid", "dynamic", "empathy", "fluent",
    "genuine", "harmony", "insight", "kindle", "legacy", "meticulous",
    "nostalgic", "obstinate", "pragmatic", "quell", "robust", "serene",
    "tranquil", "ubiquitous", "versatile", "wary", "yield", "zeal",
    "affable", "brisk", "concur", "dwindle", "exemplary", "fervent",
    "gregarious", "hinder", "immaculate", "juxtapose", "lament",
    "mirth", "nurture", "obscure", "placid", "quintessential",
    "relish", "succinct", "tangible", "unravel", "vivid", "yearning",
]

GRAMMAR_TOPICS = [
    "Present Simple vs Present Continuous",
    "Past Simple vs Past Continuous",
    "Present Perfect vs Past Simple",
    "Future forms (will / going to)",
    "Articles (a, an, the)",
    "Prepositions of time (in, on, at)",
    "Prepositions of place",
    "Modal verbs (can, could, should, must)",
    "Conditionals (zero, first, second, third)",
    "Passive voice",
    "Reported speech",
    "Gerunds vs infinitives",
    "Comparatives and superlatives",
    "Countable vs uncountable nouns",
    "Some vs any",
    "Much vs many",
    "Relative clauses (who, which, that)",
    "Phrasal verbs basics",
    "Question tags",
    "Used to vs would",
    "Verb patterns",
    "Adverbs of frequency",
    "Conjunctions (and, but, or, because)",
    "Reflexive pronouns",
    "Possessives (my, mine, yours)",
    "Question words (WH- questions)",
    "Negative sentences",
    "There is / There are",
    "This / That / These / Those",
    "Subject-verb agreement",
    "Adjective order",
    "Direct vs indirect objects",
    "Articles with geographic names",
    "Time clauses (when, while, before, after)",
    "Purpose clauses (to, in order to)",
]

WRITING_TASKS = [
    "Write a 5-sentence paragraph about your favorite place.",
    "Write an email to a friend inviting them to a party.",
    "Write a short diary entry about your day.",
    "Write a 5-sentence description of your best friend.",
    "Write an apology message to your teacher.",
    "Write about your future goals in 5 sentences.",
    "Write a thank-you note to someone who helped you.",
    "Write a short review of a movie you watched.",
    "Write about your daily routine in 8-10 sentences.",
    "Write a message asking for directions to a place.",
    "Write a short paragraph about your hometown.",
    "Write about what you did last weekend.",
    "Write a complaint letter about a bad product.",
    "Write a 5-sentence story with a surprise ending.",
    "Write about a memorable trip you took.",
    "Write about a person you admire.",
    "Write a letter to your younger self.",
    "Write about your dream job.",
    "Write about a hobby you enjoy.",
    "Write about the best day of your life.",
    "Write about a mistake you learned from.",
    "Write about your favorite food and how to make it.",
    "Write about a skill you want to learn.",
    "Write about your favorite season.",
    "Write a short story about a lost key.",
    "Write about a festival you celebrate.",
    "Write about a book that changed your mind.",
    "Write an email applying for a job.",
    "Write about your role model.",
    "Write a letter to your future self.",
    "Write about a challenge you overcame.",
    "Write about your favorite teacher.",
    "Write about a place you want to visit.",
    "Write about your ideal weekend.",
    "Write about a funny incident.",
]

DAILY_TOPICS = [
    "Business English phrases", "Travel English", "Cooking vocabulary",
    "Sports idioms", "Weather expressions", "At the airport",
    "Doctor's visit", "Shopping phrases", "Phone conversations",
    "Email writing", "Job interview", "Daily routine",
    "Emotions & feelings", "Health & fitness", "Technology",
    "Social media", "Education", "Money & banking",
    "Restaurant ordering", "Directions", "Family & relationships",
    "Weather & seasons", "Sports & hobbies", "Music & movies",
    "Holidays & celebrations", "Transportation", "Nature & environment",
    "Books & reading", "Art & culture", "Science & innovation",
    "Time management", "Problem solving", "Making decisions",
    "Customer service", "Public speaking",
    "At the pharmacy", "Banking terms", "Real estate",
    "Online shopping", "Emergency vocabulary",
]

WORD_OF_DAY_POOL = [
    "serendipity", "ephemeral", "resilience", "ubiquitous", "paradigm",
    "eloquent", "ambiguous", "benevolent", "candid", "diligent",
    "empathy", "fluent", "grateful", "harmony", "innovative",
    "jubilant", "kindle", "lucid", "magnificent", "nostalgia",
    "optimistic", "pragmatic", "quaint", "robust", "serene",
    "tenacious", "unique", "versatile", "witty", "zealous",
    "articulate", "brisk", "coherent", "dynamic", "exemplary",
    "fascinating", "genuine", "humble", "insight", "journey",
    "keen", "legacy", "meticulous", "notable", "obstinate",
    "persistent", "quell", "resilient", "sincere", "tranquil",
    "affable", "concise", "deliberate", "elaborate", "formidable",
    "gregarious", "hinder", "immaculate", "jovial", "lament",
    "mirth", "nurture", "obscure", "placid", "quintessential",
    "relish", "succinct", "tangible", "unravel", "vivid",
    "yearning", "zeal", "abundant", "coherent", "deliberate",
]


def get_next_item(uid, pool_name, pool, context):
    used_key = f"used_{pool_name}"
    used = list(context.user_data.get(used_key, []))
    available = [x for x in pool if x not in used]
    if not available:
        used = []
        available = list(pool)
    choice = random.choice(available)
    used.append(choice)
    context.user_data[used_key] = used[-len(pool):]
    return choice

T = {
    "welcome": {
        "bn": "👋 স্বাগতম {name}!\n\n🎓 আমি EduMate AI - আপনার ২৪/৭ ইংরেজি শিক্ষক।\n\n📖 যা করতে পারি:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 অনুবাদ\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 ছবি বিশ্লেষণ\n• 📄 PDF বিশ্লেষণ\n• 🎤 ভয়েস সাপোর্ট\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 নিচের বাটন থেকে বেছে নিন।",
        "en": "👋 Welcome {name}!\n\n🎓 I am EduMate AI - your 24/7 English teacher.\n\n📖 What I can do:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 Translation\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 Photo analysis\n• 📄 PDF analysis\n• 🎤 Voice support\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 Choose from below.",
        "hi": "👋 स्वागत है {name}!\n\n🎓 मैं EduMate AI हूँ - आपका 24/7 English शिक्षक।\n\n📖 मैं क्या कर सकता हूँ:\n• 📚 Vocabulary\n• 📝 Grammar\n• 🎯 Quiz\n• 💬 अनुवाद\n• ✍️ Writing\n• 🎭 Role-Play\n• 📸 फोटो विश्लेषण\n• 📄 PDF विश्लेषण\n• 🎤 वॉइस सपोर्ट\n• 🔁 Spaced Review\n• 🔥 Daily Lesson\n• 🎁 Invite & Earn\n\n👉 नीचे से चुनें।",
        "ru": "👋 Добро пожаловать, {name}!\n\n🎓 Я EduMate AI — твой учитель английского 24/7.\n\n📖 Что я умею:\n• 📚 Словарь\n• 📝 Грамматика\n• 🎯 Викторина\n• 💬 Перевод\n• ✍️ Письмо\n• 🎭 Ролевая игра\n• 📸 Анализ фото\n• 📄 Анализ PDF\n• 🎤 Голос\n• 🔁 Повторение\n• 🔥 Урок дня\n• 🎁 Пригласи друга\n\n👉 Выберите кнопку ниже.",
    },
    "main_menu": {"bn": "🏠 মেইন মেনু:", "en": "🏠 Main Menu:", "hi": "🏠 मुख्य मेनू:", "ru": "🏠 Главное меню:"},
    "menu_btn": {"bn": "🏠 মেইন মেনু", "en": "🏠 Main Menu", "hi": "🏠 मुख्य मेनू", "ru": "🏠 Главное меню"},
    "loading": {"bn": "⏳ তৈরি হচ্ছে...", "en": "⏳ Generating...", "hi": "⏳ बना रहा हूँ...", "ru": "⏳ Генерирую..."},
    "ai_error": {"bn": "⚠️ এখন AI-তে সমস্যা হচ্ছে। আবার চেষ্টা করুন।", "en": "⚠️ AI is having issues. Please try again.", "hi": "⚠️ AI में समस्या है।", "ru": "⚠️ Проблема с AI."},
    "profile_title": {"bn": "👤 আপনার প্রোফাইল", "en": "👤 Your Profile", "hi": "👤 आपकी प्रोफ़ाइल", "ru": "👤 Ваш профиль"},
    "name": {"bn": "📛 নাম", "en": "📛 Name", "hi": "📛 नाम", "ru": "📛 Имя"},
    "level": {"bn": "🎓 লেভেল", "en": "🎓 Level", "hi": "🎓 स्तर", "ru": "🎓 Уровень"},
    "coins": {"bn": "🪙 কয়েন", "en": "🪙 Coins", "hi": "🪙 सिक्के", "ru": "🪙 Монеты"},
    "streak": {"bn": "🔥 Streak", "en": "🔥 Streak", "hi": "🔥 स्ट्रीक", "ru": "🔥 Серия"},
    "words_learned": {"bn": "📚 শেখা শব্দ", "en": "📚 Words learned", "hi": "📚 सीखे शब्द", "ru": "📚 Слов изучено"},
    "quizzes": {"bn": "🎯 কুইজ", "en": "🎯 Quizzes", "hi": "🎯 क्विज़", "ru": "🎯 Викторины"},
    "score": {"bn": "⭐ স্কোর", "en": "⭐ Score", "hi": "⭐ स्कोर", "ru": "⭐ Очки"},
    "premium_status": {"bn": "💎 Premium", "en": "💎 Premium", "hi": "💎 Premium", "ru": "💎 Premium"},
    "active": {"bn": "✅ সক্রিয়", "en": "✅ Active", "hi": "✅ सक्रिय", "ru": "✅ Активен"},
    "inactive": {"bn": "❌ নিষ্ক্রিয়", "en": "❌ Inactive", "hi": "❌ निष्क्रिय", "ru": "❌ Неактивен"},
    "language_set": {"bn": "✅ ভাষা সেট: বাংলা", "en": "✅ Language set: English", "hi": "✅ भाषा: हिन्दी", "ru": "✅ Язык: Русский"},
    "choose_lang": {
        "bn": "🌍 ভাষা নির্বাচন করুন:\n\nChoose your language:\n\nअपनी भाषा चुनें:\n\nВыберите язык:",
        "en": "🌍 Choose your language:\n\nআপনার ভাষা নির্বাচন করুন:\n\nअपनी भाषा चुनें:\n\nВыберите язык:",
        "hi": "🌍 अपनी भाषा चुनें:\n\nChoose your language:\n\nআপনার ভাষা নির্বাচন করুন:\n\nВыберите язык:",
        "ru": "🌍 Выберите язык:\n\nChoose your language:\n\nআপনার ভাষা নির্বাচন করুন:\n\nअपनी भाषा चुनें:",
    },
    "reset_done": {"bn": "🔄 চ্যাট ক্লিয়ার হয়েছে। /start দিন।", "en": "🔄 Chat cleared. Send /start.", "hi": "🔄 चैट साफ। /start भेजें।", "ru": "🔄 Чат очищен. Отправьте /start."},
    "start_first": {"bn": "❌ আগে /start দিন।", "en": "❌ Please /start first.", "hi": "❌ पहले /start करें।", "ru": "❌ Сначала /start."},
    "daily_title": {"bn": "🔥 Daily Lesson", "en": "🔥 Daily Lesson", "hi": "🔥 Daily Lesson", "ru": "🔥 Урок дня"},
    "bonus_coins": {"bn": "🎁 বোনাস", "en": "🎁 Bonus", "hi": "🎁 बोनस", "ru": "🎁 Бонус"},
    "days": {"bn": "দিন", "en": "days", "hi": "दिन", "ru": "дней"},
    "leaderboard_title": {"bn": "🏆 টপ ১০ লিডারবোর্ড", "en": "🏆 Top 10 Leaderboard", "hi": "🏆 टॉप 10", "ru": "🏆 Топ-10"},
    "no_users": {"bn": "এখনো কোনো ইউজার নেই।", "en": "No users yet.", "hi": "अभी कोई उपयोगकर्ता नहीं।", "ru": "Пока нет пользователей."},
    "word_title": {"bn": "📖 Word of the Day", "en": "📖 Word of the Day", "hi": "📖 आज का शब्द", "ru": "📖 Слово дня"},
    "quiz_title": {"bn": "🎯 Quiz", "en": "🎯 Quiz", "hi": "🎯 Quiz", "ru": "🎯 Викторина"},
    "quiz_more": {"bn": "🎯 আরেকটি কুইজ", "en": "🎯 Another Quiz", "hi": "🎯 एक और Quiz", "ru": "🎯 Ещё викторина"},
    "translate_hint": {"bn": "যেকোনো বাংলা বা ইংরেজি বাক্য লিখে পাঠান।", "en": "Send any Bangla or English sentence.", "hi": "कोई भी Bangla या English वाक्य भेजें।", "ru": "Отправьте предложение."},
    "invite_title": {"bn": "🎁 Invite & Earn", "en": "🎁 Invite & Earn", "hi": "🎁 Invite & Earn", "ru": "🎁 Пригласи друга"},
    "invite_hint": {"bn": "💡 প্রতি ইনভাইটে {n} কয়েন পাবেন!", "en": "💡 Earn {n} coins per invite!", "hi": "💡 हर invite पर {n} सिक्के!", "ru": "💡 {n} монет за приглашение!"},
    "premium_title": {"bn": "💎 Premium Membership", "en": "💎 Premium Membership", "hi": "💎 Premium Membership", "ru": "💎 Premium"},
    "premium_buy": {"bn": "⭐ কিনুন ({n} Stars)", "en": "⭐ Buy ({n} Stars)", "hi": "⭐ खरीदें ({n} Stars)", "ru": "⭐ Купить ({n} Stars)"},
    "premium_already": {"bn": "💎 আপনি ইতিমধ্যে Premium!", "en": "💎 You are already Premium!", "hi": "💎 आप पहले से Premium हैं!", "ru": "💎 У вас уже есть Premium!"},
    "premium_success": {
        "bn": "🎉 অভিনন্দন! আপনি Premium হয়েছেন!\n✅ {days} দিনের জন্য সক্রিয়।\n\n🎁 এখন পাবেন:\n• আনলিমিটেড ছবি\n• আনলিমিটেড ভয়েস\n• Voice reply\n• আনলিমিটেড PDF\n• 🎤 Pronunciation Coach\n• 🎯 IELTS Speaking Simulator\n• 🧠 Quiz from PDF\n• 📂 সব Premium PDF ফাইল",
        "en": "🎉 Congratulations! You are now Premium!\n✅ Active for {days} days.\n\n🎁 Now you get:\n• Unlimited photos\n• Unlimited voice\n• Voice replies\n• Unlimited PDFs\n• 🎤 Pronunciation Coach\n• 🎯 IELTS Speaking Simulator\n• 🧠 Quiz from PDF\n• 📂 ALL Premium PDF Files",
        "hi": "🎉 बधाई! आप अब Premium हैं!\n✅ {days} दिनों के लिए सक्रिय।",
        "ru": "🎉 Поздравляем! Вы Premium!\n✅ Активно {days} дней.",
    },
    "achievements_title": {"bn": "🏅 Achievements", "en": "🏅 Achievements", "hi": "🏅 Achievements", "ru": "🏅 Достижения"},
    "mistakes_title": {"bn": "📚 সাম্প্রতিক ভুল", "en": "📚 Recent Mistakes", "hi": "📚 हाल की गलतियाँ", "ru": "📚 Недавние ошибки"},
    "mistakes_none": {"bn": "✅ কোনো ভুল নেই!", "en": "✅ No mistakes!", "hi": "✅ कोई गलती नहीं!", "ru": "✅ Ошибок нет!"},
    "reminder_title": {"bn": "🔔 কখন রিমাইন্ডার পেতে চান?", "en": "🔔 When do you want a reminder?", "hi": "🔔 कब reminder?", "ru": "🔔 Когда напомнить?"},
    "reminder_off": {"bn": "🔕 রিমাইন্ডার বন্ধ।", "en": "🔕 Reminder off.", "hi": "🔕 Reminder बंद।", "ru": "🔕 Отключено."},
    "reminder_set": {"bn": "🔔 রিমাইন্ডার সেট: {t}", "en": "🔔 Reminder set: {t}", "hi": "🔔 Set: {t}", "ru": "🔔 Напоминание: {t}"},
    "level_set": {"bn": "✅ লেভেল সেট: {lvl}", "en": "✅ Level set: {lvl}", "hi": "✅ स्तर: {lvl}", "ru": "✅ Уровень: {lvl}"},
    "choose_level": {"bn": "🎓 আপনার লেভেল সেট করুন:", "en": "🎓 Set your level:", "hi": "🎓 अपना स्तर चुनें:", "ru": "🎓 Выберите уровень:"},
    "new_achievement": {"bn": "🎉 নতুন অ্যাচিভমেন্ট!", "en": "🎉 New Achievement!", "hi": "🎉 नई उपलब्धि!", "ru": "🎉 Новое достижение!"},
    "referral_bonus": {"bn": "🎁 আপনি {n} কয়েন পেয়েছেন!", "en": "🎁 You earned {n} coins!", "hi": "🎁 {n} सिक्के मिले!", "ru": "🎁 Вы получили {n} монет!"},
    "voice_limit": {"bn": "🎤 ফ্রি ইউজাররা দিনে {n}টি ভয়েস পাঠাতে পারেন।\n\n⭐ Premium = আনলিমিটেড", "en": "🎤 Free: {n} voices per day.\n\n⭐ Premium = unlimited", "hi": "🎤 फ्री: {n} वॉइस/दिन", "ru": "🎤 Бесплатно: {n} голосовых"},
    "img_limit": {"bn": "📸 ফ্রি ইউজাররা দিনে {n}টি ছবি পাঠাতে পারেন।", "en": "📸 Free: {n} photos per day.", "hi": "📸 फ्री: {n} फोटो", "ru": "📸 Бесплатно: {n} фото"},
    "pdf_limit": {"bn": "📄 ফ্রি ইউজাররা দিনে {n}টি PDF পাঠাতে পারেন।", "en": "📄 Free: {n} PDFs per day.", "hi": "📄 फ्री: {n} PDF", "ru": "📄 Бесплатно: {n} PDF"},
    "processing_voice": {"bn": "🎤 ভয়েস প্রসেস হচ্ছে...", "en": "🎤 Processing voice...", "hi": "🎤 वॉइस...", "ru": "🎤 Обработка..."},
    "processing_img": {"bn": "📸 ছবি বিশ্লেষণ হচ্ছে...", "en": "📸 Analyzing image...", "hi": "📸 फोटो...", "ru": "📸 Анализ фото..."},
    "processing_pdf": {"bn": "📄 PDF পড়া হচ্ছে...", "en": "📄 Reading PDF...", "hi": "📄 PDF...", "ru": "📄 Читаю PDF..."},
    "pdf_analyzing": {"bn": "🤖 PDF বিশ্লেষণ...", "en": "🤖 Analyzing PDF...", "hi": "🤖 PDF...", "ru": "🤖 Анализ PDF..."},
    "pdf_fail": {"bn": "❌ PDF পড়তে পারিনি।", "en": "❌ Could not read PDF.", "hi": "❌ PDF नहीं पढ़ा।", "ru": "❌ Не удалось прочитать PDF."},
    "pdf_too_big": {"bn": "📄 PDF বড়, প্রথম {n} পৃষ্ঠা।", "en": "📄 First {n} pages read.", "hi": "📄 पहले {n} पेज।", "ru": "📄 Первые {n} страниц."},
    "pdf_too_large": {"bn": "❌ ফাইল বড়। সর্বোচ্চ {n} MB।", "en": "❌ File too large. Max {n} MB.", "hi": "❌ फाइल बहुत बड़ी।", "ru": "❌ Файл слишком большой."},
    "voice_heard": {"bn": "📝 আপনি বলেছেন: {text}", "en": "📝 You said: {text}", "hi": "📝 आपने कहा: {text}", "ru": "📝 Вы сказали: {text}"},
    "voice_fail": {"bn": "❌ ভয়েস বুঝতে পারিনি।", "en": "❌ Could not understand voice.", "hi": "❌ वॉइस समझ नहीं आई।", "ru": "❌ Не удалось распознать голос."},
    "img_fail": {"bn": "❌ ছবি বুঝতে পারিনি।", "en": "❌ Could not analyze image.", "hi": "❌ फोटो समझ नहीं आई।", "ru": "❌ Не удалось проанализировать фото."},
    "feedback_thanks": {"bn": "🙏 ধন্যবাদ!", "en": "🙏 Thanks for your feedback!", "hi": "🙏 धन्यवाद!", "ru": "🙏 Спасибо!"},
    "practice_title": {"bn": "🎭 Role-Play Practice", "en": "🎭 Role-Play Practice", "hi": "🎭 Role-Play", "ru": "🎭 Ролевая игра"},
    "practice_desc": {"bn": "একটা পরিস্থিতি বেছে নিন:", "en": "Choose a scenario:", "hi": "परिस्थिति चुनें:", "ru": "Выберите сценарий:"},
    "rp_started": {"bn": "🎭 {title} শুরু!\n\nবন্ধ: /endroleplay", "en": "🎭 {title} started!\n\nStop: /endroleplay", "hi": "🎭 {title} शुरू!", "ru": "🎭 {title} начато!"},
    "rp_ended": {"bn": "🎭 Role-Play শেষ।", "en": "🎭 Role-Play ended.", "hi": "🎭 खत्म।", "ru": "🎭 Завершено."},
    "rp_active": {"bn": "⚠️ আপনি Role-Play মোডে আছেন।", "en": "⚠️ You're in Role-Play mode.", "hi": "⚠️ Role-Play में हैं।", "ru": "⚠️ Вы в ролевой игре."},
    "rp_not_in": {"bn": "⚠️ আপনি Role-Play মোডে নেই।", "en": "⚠️ Not in Role-Play mode.", "hi": "⚠️ नहीं हैं।", "ru": "⚠️ Не в режиме."},
    "review_title": {"bn": "🔁 Spaced Review", "en": "🔁 Spaced Review", "hi": "🔁 Review", "ru": "🔁 Повторение"},
    "review_none": {"bn": "✅ আজ কোনো রিভিউ নেই!", "en": "✅ No reviews today!", "hi": "✅ आज कोई रिव्यू नहीं!", "ru": "✅ Сегодня нет повторений!"},
    "review_prompt": {"bn": "🔁 মনে আছে?\n\n❌ {wrong}\n\n✅ সঠিকটা লিখুন:", "en": "🔁 Remember?\n\n❌ {wrong}\n\n✅ Write correct:", "hi": "🔁 याद है?\n\n❌ {wrong}\n\n✅ सही लिखें:", "ru": "🔁 Помните?\n\n❌ {wrong}\n\n✅ Напишите:"},
    "review_correct": {"bn": "🎉 সঠিক!", "en": "🎉 Perfect!", "hi": "🎉 सही!", "ru": "🎉 Идеально!"},
    "review_wrong": {"bn": "❌ ঠিক হয়নি।\n\n✅ {correct}", "en": "❌ Not quite.\n\n✅ {correct}", "hi": "❌ सही नहीं।\n\n✅ {correct}", "ru": "❌ Не совсем.\n\n✅ {correct}"},
    "memory_title": {"bn": "🧠 আমি যা মনে রেখেছি", "en": "🧠 What I Remember", "hi": "🧠 मुझे याद है", "ru": "🧠 Что я помню"},
    "review_saved": {"bn": "✅ রিভিউ লিস্টে যোগ!", "en": "✅ Added to review!", "hi": "✅ रिव्यू लिस्ट में!", "ru": "✅ Добавлено!"},
    "cancel_payment_btn": {"bn": "❌ পেমেন্ট বাতিল", "en": "❌ Cancel Payment", "hi": "❌ भुगतान रद्द", "ru": "❌ Отменить"},
    "copy_btn": {"bn": "📋 কপি", "en": "📋 Copy", "hi": "📋 कॉपी", "ru": "📋 Копировать"},
    "copy_hint": {"bn": "👇 ট্যাপ করে কপি করুন।", "en": "👇 Tap to copy.", "hi": "👇 टैप करें।", "ru": "👇 Нажмите."},
    "pay_bkash_title": {"bn": "💳 bKash পেমেন্ট", "en": "💳 bKash Payment", "hi": "💳 bKash", "ru": "💳 bKash"},
    "pay_bkash_desc": {"bn": "১. Send Money করুন।\n২. নাম্বার: `{number}`\n৩. এমাউন্ট: `{amount}` টাকা\n৪. TrxID + স্ক্রিনশট পাঠান।", "en": "1. Send Money.\n2. Number: `{number}`\n3. Amount: `{amount}` BDT\n4. Send TrxID + screenshot.", "hi": "1. Send Money.\n2. नंबर: `{number}`\n3. राशि: `{amount}` BDT", "ru": "1. Send Money.\n2. Номер: `{number}`\n3. Сумма: `{amount}` BDT"},
    "pay_rocket_title": {"bn": "💳 Rocket পেমেন্ট", "en": "💳 Rocket Payment", "hi": "💳 Rocket", "ru": "💳 Rocket"},
    "pay_rocket_desc": {"bn": "১. Send Money করুন।\n২. নাম্বার: `{number}`\n৩. এমাউন্ট: `{amount}` টাকা\n৪. TrxID + স্ক্রিনশট পাঠান।", "en": "1. Send Money.\n2. Number: `{number}`\n3. Amount: `{amount}` BDT", "hi": "1. Send Money.\n2. नंबर: `{number}`", "ru": "1. Send Money.\n2. Номер: `{number}`"},
    "pay_trc20_title": {"bn": "🪙 USDT (TRC20)", "en": "🪙 USDT (TRC20)", "hi": "🪙 USDT", "ru": "🪙 USDT"},
    "pay_trc20_desc": {"bn": "১. `{amount}` USDT পাঠান।\n২. অ্যাড্রেস: `{address}`", "en": "1. Send `{amount}` USDT.\n2. Address: `{address}`", "hi": "1. `{amount}` USDT.\n2. एड्रेस: `{address}`", "ru": "1. Отправьте `{amount}` USDT.\n2. Адрес: `{address}`"},
    "pay_bsc20_title": {"bn": "🪙 USDT (BSC20)", "en": "🪙 USDT (BSC20)", "hi": "🪙 USDT", "ru": "🪙 USDT"},
    "pay_bsc20_desc": {"bn": "১. `{amount}` USDT পাঠান।\n২. অ্যাড্রেস: `{address}`", "en": "1. Send `{amount}` USDT.\n2. Address: `{address}`", "hi": "1. `{amount}` USDT.\n2. एड्रेस: `{address}`", "ru": "1. Отправьте `{amount}` USDT.\n2. Адрес: `{address}`"},
    "support_title": {"bn": "🆘 সাপোর্ট", "en": "🆘 Support", "hi": "🆘 सहायता", "ru": "🆘 Поддержка"},
    "support_desc": {"bn": "সমস্যা, প্রশ্ন বা সাজেশন নিচে লিখুন।\n\n📩 সরাসরি অ্যাডমিনের কাছে যাবে।\n\n📞 @asikul_echo", "en": "Write below.\n\n📩 Sent to admin.\n\n📞 @asikul_echo", "hi": "नीचे लिखें।", "ru": "Напишите ниже."},
    "support_sent": {"bn": "✅ মেসেজ অ্যাডমিনের কাছে পাঠানো হয়েছে।", "en": "✅ Sent to admin.", "hi": "✅ भेज दिया।", "ru": "✅ Отправлено."},
    "support_btn": {"bn": "🆘 সাপোর্ট", "en": "🆘 Support", "hi": "🆘 सहायता", "ru": "🆘 Поддержка"},
    "support_cancel": {"bn": "❌ বাতিল", "en": "❌ Cancel", "hi": "❌ रद्द", "ru": "❌ Отмена"},
    "support_cancelled": {"bn": "✅ সাপোর্ট মোড বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "payment_proof_sent": {"bn": "✅ পেমেন্ট প্রুফ অ্যাডমিনের কাছে।\nভেরিফিকেশন শেষে ৫ মিনিটে চালু হবে।", "en": "✅ Payment proof sent.\nActivated within 5 min.", "hi": "✅ भुगतान प्रमाण भेजा।", "ru": "✅ Доказательство отправлено."},
    "payment_info_sent": {"bn": "✅ পেমেন্ট ইনফো পাঠানো হয়েছে।", "en": "✅ Payment info sent.", "hi": "✅ भेज दिया।", "ru": "✅ Отправлено."},
    "suggestion_expired": {"bn": "⚠️ এক্সপায়ার হয়েছে।", "en": "⚠️ Expired.", "hi": "⚠️ समाप्त।", "ru": "⚠️ Устарело."},
    "game_title": {"bn": "🎮 Word Scramble", "en": "🎮 Word Scramble", "hi": "🎮 Word Scramble", "ru": "🎮 Word Scramble"},
    "game_scrambled": {"bn": "🔤 এলোমেলো: `{word}`", "en": "🔤 Scrambled: `{word}`", "hi": "🔤 `{word}`", "ru": "🔤 `{word}`"},
    "game_prompt": {"bn": "👉 সঠিক ইংরেজি শব্দটি লিখুন।", "en": "👉 Type correct word.", "hi": "👉 सही शब्द लिखें।", "ru": "👉 Напишите слово."},
    "game_score": {"bn": "🏆 স্কোর: {score}", "en": "🏆 Score: {score}", "hi": "🏆 स्कोर: {score}", "ru": "🏆 Очки: {score}"},
    "game_stop_hint": {"bn": "❌ বন্ধ: /endgame", "en": "❌ Stop: /endgame", "hi": "❌ /endgame", "ru": "❌ /endgame"},
    "game_skip_btn": {"bn": "⏭️ Skip", "en": "⏭️ Skip", "hi": "⏭️ Skip", "ru": "⏭️ Пропустить"},
    "game_correct": {"bn": "🎉 সঠিক! +৫ কয়েন", "en": "🎉 Correct! +5 coins", "hi": "🎉 सही! +5", "ru": "🎉 Верно! +5"},
    "game_next_word": {"bn": "🔤 পরের শব্দ: `{word}`", "en": "🔤 Next: `{word}`", "hi": "🔤 अगला: `{word}`", "ru": "🔤 Далее: `{word}`"},
    "game_wrong": {"bn": "❌ ভুল!", "en": "❌ Wrong!", "hi": "❌ गलत!", "ru": "❌ Неверно!"},
    "game_hint": {"bn": "💡 হিন্ট: প্রথম অক্ষর `{first}`, {length}টি অক্ষর।", "en": "💡 Hint: `{first}`, {length} letters.", "hi": "💡 `{first}`, {length} अक्षर।", "ru": "💡 `{first}`, {length} букв."},
    "game_try_again": {"bn": "👉 আবার চেষ্টা করুন।", "en": "👉 Try again.", "hi": "👉 फिर कोशिश करें।", "ru": "👉 Попробуйте снова."},
    "game_over_title": {"bn": "🎮 গেম শেষ!", "en": "🎮 Game Over!", "hi": "🎮 गेम खत्म!", "ru": "🎮 Игра окончена!"},
    "game_total_score": {"bn": "🏆 মোট স্কোর: {score}", "en": "🏆 Total: {score}", "hi": "🏆 कुल: {score}", "ru": "🏆 Итог: {score}"},
    "game_play_again": {"bn": "আবার খেলতে 🎮 Word Game এ ক্লিক করুন।", "en": "Tap 🎮 Word Game again.", "hi": "फिर 🎮 Word Game।", "ru": "Нажмите 🎮 Word Game."},
    "game_not_in": {"bn": "⚠️ আপনি গেমে নেই।", "en": "⚠️ Not in a game.", "hi": "⚠️ गेम में नहीं।", "ru": "⚠️ Не в игре."},
    "game_new_word": {"bn": "নতুন শব্দ আসছে...", "en": "Loading new word...", "hi": "नया शब्द...", "ru": "Загружаю..."},
    "fc_title": {"bn": "📇 Flashcards", "en": "📇 Flashcards", "hi": "📇 Flashcards", "ru": "📇 Карточки"},
    "fc_choose_level": {"bn": "কোন লেভেল?", "en": "Which level?", "hi": "कौन सा स्तर?", "ru": "Какой уровень?"},
    "fc_easy": {"bn": "🟢 Easy", "en": "🟢 Easy", "hi": "🟢 Easy", "ru": "🟢 Лёгкий"},
    "fc_medium": {"bn": "🟡 Medium", "en": "🟡 Medium", "hi": "🟡 Medium", "ru": "🟡 Средний"},
    "fc_hard": {"bn": "🔴 Hard", "en": "🔴 Hard", "hi": "🔴 Hard", "ru": "🔴 Сложный"},
    "fc_word": {"bn": "📇 শব্দ: {word}", "en": "📇 Word: {word}", "hi": "📇 शब्द: {word}", "ru": "📇 Слово: {word}"},
    "fc_pron": {"bn": "🔊 উচ্চারণ: {pron}", "en": "🔊 Pronunciation: {pron}", "hi": "🔊 उच्चारण: {pron}", "ru": "🔊 Произношение: {pron}"},
    "fc_ask": {"bn": "👉 অর্থ জানেন? উত্তর দেখুন।", "en": "👉 Show answer?", "hi": "👉 उत्तर देखें?", "ru": "👉 Показать ответ?"},
    "fc_show_btn": {"bn": "✅ উত্তর", "en": "✅ Show Answer", "hi": "✅ उत्तर", "ru": "✅ Ответ"},
    "fc_next_btn": {"bn": "⏭️ পরের শব্দ", "en": "⏭️ Next Word", "hi": "⏭️ अगला शब्द", "ru": "⏭️ Следующее"},
    "fc_meaning": {"bn": "📝 অর্থ: {meaning}", "en": "📝 Meaning: {meaning}", "hi": "📝 अर्थ: {meaning}", "ru": "📝 Значение: {meaning}"},
    "fc_example": {"bn": "✏️ উদাহরণ: {ex}", "en": "✏️ Example: {ex}", "hi": "✏️ उदाहरण: {ex}", "ru": "✏️ Пример: {ex}"},
    "fc_remember_hint": {"bn": "🎯 মনে রাখুন।", "en": "🎯 Remember it.", "hi": "🎯 याद रखें।", "ru": "🎯 Запомните."},
    "fc_change_level": {"bn": "🔙 লেভেল", "en": "🔙 Change Level", "hi": "🔙 स्तर", "ru": "🔙 Уровень"},
    "premium_bkash_btn": {"bn": "💳 bKash ({n}৳)", "en": "💳 bKash ({n}৳)", "hi": "💳 bKash ({n}৳)", "ru": "💳 bKash ({n}৳)"},
    "premium_rocket_btn": {"bn": "💳 Rocket ({n}৳)", "en": "💳 Rocket ({n}৳)", "hi": "💳 Rocket ({n}৳)", "ru": "💳 Rocket ({n}৳)"},
    "premium_trc20_btn": {"bn": "🪙 USDT (TRC20)", "en": "🪙 USDT (TRC20)", "hi": "🪙 USDT (TRC20)", "ru": "🪙 USDT (TRC20)"},
    "premium_bsc20_btn": {"bn": "🪙 USDT (BSC20)", "en": "🪙 USDT (BSC20)", "hi": "🪙 USDT (BSC20)", "ru": "🪙 USDT (BSC20)"},
    "payment_cancelled": {"bn": "✅ বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "payment_fail": {"bn": "❌ পেমেন্ট ব্যর্থ।", "en": "❌ Payment failed", "hi": "❌ विफल", "ru": "❌ Ошибка"},
    "vocab_book_title": {"bn": "📘 Sir English Vocabulary Book", "en": "📘 Sir English Vocabulary Book", "hi": "📘 Vocabulary Book", "ru": "📘 Vocabulary Book"},
    "vocab_book_desc": {"bn": "✨ ৫০০+ শব্দ, ২০টি সেকশন\n\n👇 ডাউনলোড:", "en": "✨ 500+ words, 20 sections\n\n👇 Download:", "hi": "✨ 500+ शब्द\n\n👇 डाउनलोड:", "ru": "✨ 500+ слов\n\n👇 Скачать:"},
    "files_menu_title": {"bn": "📂 ফাইল ও রিসোর্স", "en": "📂 Files & Resources", "hi": "📂 फाइल्स", "ru": "📂 Файлы"},
    "files_menu_desc": {"bn": "নিচের ফাইল থেকে বেছে নিন:", "en": "Choose from files:", "hi": "चुनें:", "ru": "Выберите:"},
    "files_none": {"bn": "📂 এখনো কোনো ফাইল নেই।", "en": "📂 No files yet.", "hi": "📂 कोई फाइल नहीं।", "ru": "📂 Файлов нет."},
    "file_sending": {"bn": "📤 পাঠানো হচ্ছে...", "en": "📤 Sending...", "hi": "📤 भेजा जा रहा...", "ru": "📤 Отправляю..."},
    "file_not_found": {"bn": "❌ ফাইল পাওয়া যায়নি।", "en": "❌ File not found.", "hi": "❌ फाइल नहीं मिली।", "ru": "❌ Файл не найден."},
    "file_send_fail": {"bn": "❌ ফাইল পাঠাতে সমস্যা।", "en": "❌ Failed to send.", "hi": "❌ भेजने में समस्या।", "ru": "❌ Не удалось отправить."},
    "admin_only": {"bn": "⛔ শুধু অ্যাডমিন।", "en": "⛔ Admin only.", "hi": "⛔ केवल एडमिन।", "ru": "⛔ Только админ."},
    "addfile_mode": {"bn": "📎 File Upload Mode চালু!\n\nPDF/DOC পাঠান।\n\nবাতিল: /cancel", "en": "📎 Upload Mode ON!\n\nSend PDF/DOC.\n\nCancel: /cancel", "hi": "📎 Upload Mode ON!", "ru": "📎 Режим загрузки!"},
    "addfile_received": {"bn": "📎 ফাইল পেয়েছি: {name}\n\nCaption লিখুন।", "en": "📎 File: {name}\n\nType caption.", "hi": "📎 {name}", "ru": "📎 {name}"},
    "addfile_saved": {"bn": "✅ সেভ!\n📎 {name}\n📝 {caption}", "en": "✅ Saved!\n📎 {name}\n📝 {caption}", "hi": "✅ सेव!", "ru": "✅ Сохранено!"},
    "addfile_saved_no_caption": {"bn": "✅ সেভ!\n📎 {name}", "en": "✅ Saved!\n📎 {name}", "hi": "✅ सेव!", "ru": "✅ Сохранено!"},
    "addfile_save_fail": {"bn": "❌ সেভ ব্যর্থ।", "en": "❌ Save failed.", "hi": "❌ सेव विफल।", "ru": "❌ Ошибка."},
    "addfile_cancel": {"bn": "✅ বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "addfile_nothing": {"bn": "⚠️ কোনো pending ফাইল নেই।", "en": "⚠️ No pending file.", "hi": "⚠️ कोई फाइल नहीं।", "ru": "⚠️ Нет файла."},
    "listfiles_empty": {"bn": "📂 কোনো ফাইল নেই।", "en": "📂 No files yet.", "hi": "📂 कोई फाइल नहीं।", "ru": "📂 Файлов нет."},
    "listfiles_header": {"bn": "📂 Saved Files:", "en": "📂 Saved Files:", "hi": "📂 फाइल्स:", "ru": "📂 Файлы:"},
    "listfiles_footer": {"bn": "মুছতে: /delfile <id>", "en": "Delete: /delfile <id>", "hi": "डिलीट: /delfile <id>", "ru": "Удалить: /delfile <id>"},
    "delfile_usage": {"bn": "Usage: /delfile <id>", "en": "Usage: /delfile <id>", "hi": "Usage: /delfile <id>", "ru": "Использование: /delfile <id>"},
    "delfile_done": {"bn": "✅ File {id} মুছে ফেলা হয়েছে।", "en": "✅ File {id} deleted.", "hi": "✅ फाइल {id} डिलीट।", "ru": "✅ Файл {id} удалён."},
    "delfile_fail": {"bn": "❌ Delete failed.", "en": "❌ Delete failed.", "hi": "❌ डिलीट विफल।", "ru": "❌ Ошибка удаления."},
    "files_free_title": {"bn": "🆓 ফ্রি ফাইল", "en": "🆓 Free Files", "hi": "🆓 मुफ्त फाइलें", "ru": "🆓 Бесплатные"},
    "files_premium_title": {"bn": "🔐 প্রিমিয়াম ফাইল", "en": "🔐 Premium Files", "hi": "🔐 प्रीमियम", "ru": "🔐 Premium"},
    "premium_file_locked": {"bn": "🔐 প্রিমিয়াম ফাইল!\n\n📂 {name}\n\n💎 প্রিমিয়াম নিন সব ফাইল আনলক করতে।", "en": "🔐 Premium File!\n\n📂 {name}\n\n💎 Get Premium to unlock.", "hi": "🔐 प्रीमियम!", "ru": "🔐 Premium файл!"},
    "premium_files_sent": {"bn": "🎉 প্রিমিয়াম চালু! ফাইল পাঠানো হচ্ছে...", "en": "🎉 Premium activated! Sending files...", "hi": "🎉 Premium एक्टिव!", "ru": "🎉 Premium активирован!"},
    "premium_no_files": {"bn": "⚠️ এখনো প্রিমিয়াম ফাইল আপলোড হয়নি।", "en": "⚠️ No premium files yet.", "hi": "⚠️ अभी कोई प्रीमियम फाइल नहीं।", "ru": "⚠️ Premium файлов нет."},
    "addfile_ask_type": {"bn": "📎 ফাইল: {name}\n\n❓ Free না Premium?", "en": "📎 File: {name}\n\n❓ Free or Premium?", "hi": "📎 {name}\n\n❓ Free/Premium?", "ru": "📎 {name}\n\n❓ Free/Premium?"},
    "addfile_free_btn": {"bn": "🆓 Free ফাইল", "en": "🆓 Free File", "hi": "🆓 Free", "ru": "🆓 Бесплатно"},
    "addfile_premium_btn": {"bn": "🔐 Premium ফাইল", "en": "🔐 Premium File", "hi": "🔐 Premium", "ru": "🔐 Premium"},
    "addfile_type_saved": {"bn": "✅ সেভ!\n📎 {name}\n🏷️ {type}\n📝 {caption}", "en": "✅ Saved!\n📎 {name}\n🏷️ {type}\n📝 {caption}", "hi": "✅ सेव!", "ru": "✅ Сохранено!"},
    "premium_choose": {"bn": "💎 আপনার প্ল্যান বেছে নিন:", "en": "💎 Choose your plan:", "hi": "💎 प्लान चुनें:", "ru": "💎 Выберите план:"},
    "premium_plan_body": {"bn": "💎 Premium — {label}\n\n💰 bKash/Rocket: ৳{bdt}\n⭐ Stars: {stars}\n🪙 USDT: {usdt}\n⏳ {days} days\n\n👇 পেমেন্ট:", "en": "💎 Premium — {label}\n\n💰 ৳{bdt}\n⭐ {stars}\n🪙 {usdt}\n⏳ {days} days\n\n👇 Pay:", "hi": "💎 {label}\n\n৳{bdt}", "ru": "💎 {label}\n\n৳{bdt}"},
    "premium_plan_btn": {"bn": "{label} — ৳{bdt} / {stars}⭐", "en": "{label} — ৳{bdt} / {stars}⭐", "hi": "{label} — ৳{bdt}", "ru": "{label} — ৳{bdt}"},
    "pron_premium": {"bn": "🎤 Pronunciation Coach\n\n✨ Premium ফিচার!", "en": "🎤 Pronunciation Coach\n\n✨ Premium feature!", "hi": "🎤 Premium!", "ru": "🎤 Premium!"},
    "pron_title": {"bn": "🎤 Pronunciation Coach", "en": "🎤 Pronunciation Coach", "hi": "🎤 Pronunciation", "ru": "🎤 Произношение"},
    "pron_read": {"bn": "📝 জোরে পড়ুন:", "en": "📝 Read aloud:", "hi": "📝 जोर से पढ़ें:", "ru": "📝 Прочитайте:"},
    "pron_send_voice": {"bn": "🎙️ VOICE message পাঠান।", "en": "🎙️ Send VOICE message.", "hi": "🎙️ VOICE भेजें।", "ru": "🎙️ Отправьте голос."},
    "pron_cancel_hint": {"bn": "❌ বাতিল: /cancelpronounce", "en": "❌ Cancel: /cancelpronounce", "hi": "❌ /cancelpronounce", "ru": "❌ /cancelpronounce"},
    "pron_new_sentence": {"bn": "🔄 নতুন বাক্য", "en": "🔄 New Sentence", "hi": "🔄 नया वाक्य", "ru": "🔄 Новое предложение"},
    "pron_processing": {"bn": "🎤 প্রসেস হচ্ছে...", "en": "🎤 Processing...", "hi": "🎤 प्रोसेस...", "ru": "🎤 Обработка..."},
    "pron_result": {"bn": "🎤 স্কোর", "en": "🎤 Score", "hi": "🎤 स्कोर", "ru": "🎤 Оценка"},
    "pron_target": {"bn": "📝 মূল বাক্য", "en": "📝 Target", "hi": "📝 लक्ष्य", "ru": "📝 Оригинал"},
    "pron_said": {"bn": "🗣️ আপনি বলেছেন", "en": "🗣️ You said", "hi": "🗣️ आपने कहा", "ru": "🗣️ Вы сказали"},
    "pron_improve": {"bn": "⚠️ উন্নতির শব্দ", "en": "⚠️ Words to improve", "hi": "⚠️ सुधार:", "ru": "⚠️ Улучшить:"},
    "pron_listen_again": {"bn": "🔊 শুনুন ও বলুন।", "en": "🔊 Listen and repeat.", "hi": "🔊 सुनें और दोहराएं।", "ru": "🔊 Слушайте и повторяйте."},
    "pron_excellent": {"bn": "🏆 অসাধারণ!", "en": "🏆 Excellent!", "hi": "🏆 शानदार!", "ru": "🏆 Отлично!"},
    "pron_very_good": {"bn": "🎉 খুব ভালো!", "en": "🎉 Very Good!", "hi": "🎉 बहुत अच्छा!", "ru": "🎉 Очень хорошо!"},
    "pron_good": {"bn": "👍 ভালো", "en": "👍 Good", "hi": "👍 अच्छा", "ru": "👍 Хорошо"},
    "pron_keep_practicing": {"bn": "📚 চালিয়ে যান", "en": "📚 Keep Practicing", "hi": "📚 अभ्यास जारी", "ru": "📚 Продолжайте"},
    "pron_try_again": {"bn": "🔁 আবার চেষ্টা", "en": "🔁 Try Again", "hi": "🔁 फिर कोशिश", "ru": "🔁 Попробуйте снова"},
    "pron_cancelled": {"bn": "✅ বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "pron_not_in": {"bn": "⚠️ মোডে নেই।", "en": "⚠️ Not in mode.", "hi": "⚠️ मोड में नहीं।", "ru": "⚠️ Не в режиме."},
    "ielts_premium": {"bn": "🎯 IELTS Speaking\n\n✨ Premium ফিচার!", "en": "🎯 IELTS Speaking\n\n✨ Premium feature!", "hi": "🎯 Premium!", "ru": "🎯 Premium!"},
    "ielts_title": {"bn": "🎯 IELTS Speaking", "en": "🎯 IELTS Speaking", "hi": "🎯 IELTS Speaking", "ru": "🎯 IELTS Speaking"},
    "ielts_welcome": {"bn": "🎯 IELTS Speaking Simulator\n\n৩টি অংশ:\n• Part 1\n• Part 2\n• Part 3\n\nচলুন!", "en": "🎯 IELTS Speaking\n\n3 parts:\n• Part 1\n• Part 2\n• Part 3\n\nLet's begin!", "hi": "🎯 IELTS\n\n3 भाग\n\nशुरू करें!", "ru": "🎯 IELTS\n\n3 части\n\nНачнём!"},
    "ielts_part1_start": {"bn": "📍 Part 1\n\nপ্রশ্ন {n}/৫:", "en": "📍 Part 1\n\nQuestion {n}/5:", "hi": "📍 Part 1\n\nप्रश्न {n}/5:", "ru": "📍 Part 1\n\nВопрос {n}/5:"},
    "ielts_part2_start": {"bn": "📍 Part 2 — Cue Card\n\n📋 টপিক:\n\n{cue}", "en": "📍 Part 2 — Cue Card\n\n📋 Topic:\n\n{cue}", "hi": "📍 Part 2\n\n{cue}", "ru": "📍 Part 2\n\n{cue}"},
    "ielts_part3_start": {"bn": "📍 Part 3\n\nপ্রশ্ন {n}/৪:", "en": "📍 Part 3\n\nQuestion {n}/4:", "hi": "📍 Part 3\n\nप्रश्न {n}/4:", "ru": "📍 Part 3\n\nВопрос {n}/4:"},
    "ielts_analyzing": {"bn": "📊 বিশ্লেষণ...", "en": "📊 Analyzing...", "hi": "📊 विश्लेषण...", "ru": "📊 Анализ..."},
    "ielts_done": {"bn": "✅ IELTS সম্পন্ন!", "en": "✅ IELTS Complete!", "hi": "✅ IELTS पूरा!", "ru": "✅ IELTS завершён!"},
    "ielts_cancel": {"bn": "❌ বাতিল: /cancelielts", "en": "❌ Cancel: /cancelielts", "hi": "❌ /cancelielts", "ru": "❌ /cancelielts"},
    "ielts_cancelled": {"bn": "✅ বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "ielts_not_in": {"bn": "⚠️ টেস্টে নেই।", "en": "⚠️ Not in test.", "hi": "⚠️ टेस्ट में नहीं।", "ru": "⚠️ Не в тесте."},
    "ielts_answer_too_short": {"bn": "⚠️ অন্তত ২-৩ লাইন।", "en": "⚠️ Write 2-3 sentences.", "hi": "⚠️ 2-3 वाक्य लिखें।", "ru": "⚠️ Напишите 2-3 предложения."},
    "ielts_end_btn": {"bn": "🛑 শেষ", "en": "🛑 End", "hi": "🛑 खत्म", "ru": "🛑 Завершить"},
    "pdfquiz_premium": {"bn": "🧠 Quiz from PDF\n\n✨ Premium ফিচার!", "en": "🧠 Quiz from PDF\n\n✨ Premium feature!", "hi": "🧠 Premium!", "ru": "🧠 Premium!"},
    "pdfquiz_title": {"bn": "🧠 Quiz from PDF", "en": "🧠 Quiz from PDF", "hi": "🧠 Quiz", "ru": "🧠 Викторина"},
    "pdfquiz_prompt": {"bn": "🧠 Quiz from PDF\n\n📄 PDF পাঠান।\n\n❌ বাতিল: /cancelpdfquiz", "en": "🧠 Quiz from PDF\n\n📄 Send PDF.\n\n❌ /cancelpdfquiz", "hi": "🧠 Quiz\n\n📄 PDF भेजें।", "ru": "🧠 Quiz\n\n📄 Отправьте PDF."},
    "pdfquiz_processing": {"bn": "📄 PDF পড়া হচ্ছে...", "en": "📄 Reading PDF...", "hi": "📄 PDF पढ़ रहा...", "ru": "📄 Читаю PDF..."},
    "pdfquiz_generating": {"bn": "🤖 কুইজ তৈরি...", "en": "🤖 Generating quiz...", "hi": "🤖 क्विज़...", "ru": "🤖 Создаю викторину..."},
    "pdfquiz_fail": {"bn": "❌ কুইজ ব্যর্থ।", "en": "❌ Quiz failed.", "hi": "❌ क्विज़ नहीं बना।", "ru": "❌ Не удалось создать."},
    "pdfquiz_q": {"bn": "❓ প্রশ্ন {n}/10", "en": "❓ Question {n}/10", "hi": "❓ प्रश्न {n}/10", "ru": "❓ Вопрос {n}/10"},
    "pdfquiz_score": {"bn": "📊 স্কোর", "en": "📊 Score", "hi": "📊 स्कोर", "ru": "📊 Результат"},
    "pdfquiz_correct": {"bn": "✅ সঠিক!", "en": "✅ Correct!", "hi": "✅ सही!", "ru": "✅ Верно!"},
    "pdfquiz_wrong": {"bn": "❌ ভুল!", "en": "❌ Wrong!", "hi": "❌ गलत!", "ru": "❌ Неверно!"},
    "pdfquiz_answer": {"bn": "✅ সঠিক উত্তর", "en": "✅ Correct answer", "hi": "✅ सही उत्तर", "ru": "✅ Правильный ответ"},
    "pdfquiz_cancelled": {"bn": "✅ বাতিল।", "en": "✅ Cancelled.", "hi": "✅ रद्द।", "ru": "✅ Отменено."},
    "pdfquiz_not_in": {"bn": "⚠️ মোডে নেই।", "en": "⚠️ Not in mode.", "hi": "⚠️ मोड में नहीं।", "ru": "⚠️ Не в режиме."},
    "pdfquiz_done": {"bn": "🎉 কুইজ শেষ!", "en": "🎉 Quiz Complete!", "hi": "🎉 पूरा!", "ru": "🎉 Завершено!"},
}

"force_sub_title": {
    "bn": "🔒 Force Subscribe প্রয়োজন",
    "en": "🔒 Force Subscribe Required",
    "hi": "🔒 Force Subscribe Required",
    "ru": "🔒 Force Subscribe Required",
},
"force_sub_desc": {
    "bn": "বট ব্যবহার করতে হলে আমাদের Grammar Channel-এ join করুন।\n\n👇 নিচের বাটনে ক্লিক করুন:",
    "en": "To use this bot, please join our Grammar Channel.\n\n👇 Click below:",
    "hi": "बॉट का उपयोग करने के लिए चैनल join करें।",
    "ru": "Чтобы использовать бота, присоединитесь к каналу.",
},
"force_sub_join_btn": {
    "bn": "📢 Channel-এ Join করুন",
    "en": "📢 Join Channel",
    "hi": "📢 Join Channel",
    "ru": "📢 Join Channel",
},
"force_sub_check_btn": {
    "bn": "✅ Join করেছি — চেক করুন",
    "en": "✅ I Joined — Check",
    "hi": "✅ Check",
    "ru": "✅ Check",
},
"force_sub_not_joined": {
    "bn": "❌ আপনি এখনো Join করেননি। Channel-এ Join করে আবার চেষ্টা করুন।",
    "en": "❌ You haven't joined yet. Please join and try again.",
    "hi": "❌ पहले join करें।",
    "ru": "❌ Вы ещё не присоединились. Присоединитесь и попробуйте снова.",
},
"force_sub_thanks": {
    "bn": "🎉 ধন্যবাদ! এখন আপনি বট ব্যবহার করতে পারবেন।",
    "en": "🎉 Thanks! You can now use the bot.",
    "hi": "🎉 धन्यवाद!",
    "ru": "🎉 Спасибо!",
},

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

PROMPT_BEGINNER = """
You are EduMate AI, a patient English teacher for beginners.
1. Language Rule: Reply in the SAME language the user wrote in.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use asterisks (*), bold (**), or markdown.
3. Tone: Be highly encouraging. Keep responses short (under 1500 characters).
4. Chat naturally.

⚠️ CRITICAL INSTRUCTION: You MUST ALWAYS end your response with exactly 3 follow-up questions.
Format them EXACTLY like this at the very end: [SUGGESTIONS] Question 1 | Question 2 | Question 3
"""

PROMPT_INTERMEDIATE = """
You are EduMate AI, an English tutor for intermediate learners.
1. Language Rule: Reply in the user's language.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use markdown.
3. Style: Moderate length (under 2500 characters).

⚠️ CRITICAL INSTRUCTION: You MUST ALWAYS end your response with exactly 3 follow-up questions.
Format them EXACTLY like this at the very end: [SUGGESTIONS] Question 1 | Question 2 | Question 3
"""

PROMPT_ADVANCED = """
You are EduMate AI, a strict IELTS examiner.
1. Language Rule: Reply ONLY in English.
2. Formatting Rule: Use ONLY plain text and emojis. NEVER use markdown.
3. Style: Advanced vocabulary (under 3500 characters).

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
    if user.get("language"):
        parts.append(f"Preferred language: {user['language']}")
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
            "max_tokens": 2000,
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
            "1. NEVER use markdown. "
            "2. Use PLAIN TEXT only with emojis. "
            "3. Separate each item with a BLANK LINE. "
            "4. Keep responses under 1500 characters. "
            "5. Reply in the user's language. "
            "6. Start with a 1-line summary, then bullet points."
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
    def clean(s):
        return re.sub(r'[^\w\s]', ' ', s.lower()).split()

    target_words = clean(target)
    said_words = clean(said)

    if not target_words:
        return 0, []

    matcher = difflib.SequenceMatcher(None, target_words, said_words)
    score = int(matcher.ratio() * 100)

    wrong = []
    sm = difflib.SequenceMatcher(None, target_words, said_words)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != 'equal':
            wrong_segment = " ".join(target_words[i1:i2]).strip()
            if wrong_segment:
                wrong.append(wrong_segment)

    return score, wrong[:8]


def parse_quiz_json(text):
    if not text:
        return None
    match = re.search(r'\[\s*\{.*\}\s*\]', text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        if not isinstance(data, list) or len(data) == 0:
            return None
        for item in data:
            if not all(k in item for k in ("q", "options", "answer")):
                return None
            if not isinstance(item["options"], list) or len(item["options"]) < 2:
                return None
            if not isinstance(item["answer"], int):
                return None
        return data[:10]
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

    logger.info("Attempting DB connect...")

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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_premium BOOLEAN DEFAULT FALSE
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS c_progress (
                    user_id BIGINT,
                    course VARCHAR(20),
                    current_day INTEGER DEFAULT 0,
                    final_score INTEGER DEFAULT 0,
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    PRIMARY KEY (user_id, course)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS c_lessons (
                    course VARCHAR(20),
                    day INTEGER,
                    content TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (course, day)
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS c_quizzes (
                    course VARCHAR(20),
                    day INTEGER,
                    content TEXT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (course, day)
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
            try:
                await conn.execute(
                    "ALTER TABLE s_files ADD COLUMN IF NOT EXISTS is_premium BOOLEAN DEFAULT FALSE"
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


async def save_file(file_id, file_name, caption, uploaded_by, is_premium=False):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO s_files (file_id, file_name, caption, uploaded_by, is_premium) "
                "VALUES ($1, $2, $3, $4, $5) ON CONFLICT (file_id) DO NOTHING",
                file_id, file_name, caption, uploaded_by, is_premium
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
                "SELECT id, file_name, caption, COALESCE(is_premium, FALSE) AS is_premium "
                "FROM s_files ORDER BY id DESC"
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def get_free_files():
    files = await get_all_files()
    return [f for f in files if not f.get("is_premium")]


async def get_premium_files():
    files = await get_all_files()
    return [f for f in files if f.get("is_premium")]


async def get_file_by_db_id(fid):
    if db_pool is None:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT file_id, file_name, caption, COALESCE(is_premium, FALSE) AS is_premium "
                "FROM s_files WHERE id = $1", fid
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
# COURSE MODE — DB Helpers
# ==========================================================
async def get_course_progress(uid, course):
    if db_pool is None:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM c_progress WHERE user_id=$1 AND course=$2",
                uid, course
            )
            return dict(row) if row else None
    except Exception:
        return None


async def get_all_course_progress(uid):
    if db_pool is None:
        return []
    try:
        async with db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM c_progress WHERE user_id=$1", uid
            )
            return [dict(r) for r in rows]
    except Exception:
        return []


async def start_course(uid, course):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO c_progress (user_id, course, current_day)
                VALUES ($1, $2, 0)
                ON CONFLICT (user_id, course) DO NOTHING
            """, uid, course)
        return True
    except Exception as e:
        logger.error(f"start_course: {e}")
        return False


async def complete_course_day(uid, course, day):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE c_progress
                SET current_day=$3, last_activity=NOW()
                WHERE user_id=$1 AND course=$2
            """, uid, course, day)
        return True
    except Exception as e:
        logger.error(f"complete_course_day: {e}")
        return False


async def complete_course(uid, course, final_score):
    if db_pool is None:
        return False
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                UPDATE c_progress
                SET completed_at=NOW(), final_score=$3
                WHERE user_id=$1 AND course=$2
            """, uid, course, final_score)
        return True
    except Exception as e:
        logger.error(f"complete_course: {e}")
        return False


async def get_cached_lesson(course, day):
    if db_pool is None:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM c_lessons WHERE course=$1 AND day=$2",
                course, day
            )
            return row["content"] if row else None
    except Exception:
        return None


async def save_cached_lesson(course, day, content):
    if db_pool is None:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO c_lessons (course, day, content)
                VALUES ($1, $2, $3)
                ON CONFLICT (course, day) DO NOTHING
            """, course, day, content)
    except Exception:
        pass


async def get_cached_quiz(course, day):
    if db_pool is None:
        return None
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT content FROM c_quizzes WHERE course=$1 AND day=$2",
                course, day
            )
            return row["content"] if row else None
    except Exception:
        return None


async def save_cached_quiz(course, day, content):
    if db_pool is None:
        return
    try:
        async with db_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO c_quizzes (course, day, content)
                VALUES ($1, $2, $3)
                ON CONFLICT (course, day) DO NOTHING
            """, course, day, content)
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
    join_url = FORCE_SUB_GROUP_LINK or "https://t.me/"
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
        [InlineKeyboardButton("📚 MY COURSE — Start / Continue", callback_data="course_home")],
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
        [InlineKeyboardButton("🇮🇳 हिन्दी", callback_data="setlang_hi"),
         InlineKeyboardButton("🇷🇺 Русский", callback_data="setlang_ru")],
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
                "ielts_speaking", "pdf_quiz", "pdf_quiz_mode",
                "pending_file_caption", "pending_file_id_save", "pending_file_name_save"]:
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
        f"📸 Photos: {user.get('photos_sent') or 0}\n"
        f"🎤 Voices: {user.get('voices_sent') or 0}\n"
        f"📄 PDFs: {user.get('pdfs_sent') or 0}\n"
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
        text = ("📖 Help\n\n/start /menu /profile /daily /leaderboard\n/coins /invite /mistakes /achievements\n/level /reminder /language /reset\n/practice /review /memory /endroleplay /endgame\n/pronounce /ielts /pdfquiz (Premium)\n\n📸 Photo 🎤 Voice 📄 PDF\n🆘 @asikul_echo")
    elif lang == "hi":
        text = ("📖 सहायता\n\n/start /menu /profile\n/pronounce /ielts /pdfquiz\n🆘 @asikul_echo")
    elif lang == "ru":
        text = ("📖 Помощь\n\n/start /menu /profile\n/pronounce /ielts /pdfquiz\n🆘 @asikul_echo")
    else:
        text = ("📖 সাহায্য\n\n/start /menu /profile /daily /leaderboard\n/coins /invite /mistakes /achievements\n/level /reminder /language /reset\n/practice /review /memory /endroleplay /endgame\n/pronounce /ielts /pdfquiz (Premium)\n\n📸 ছবি 🎤 ভয়েস 📄 PDF\n🆘 @asikul_echo")
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
    topic = get_next_item(uid, "daily", DAILY_TOPICS, context)
    await update.message.chat.send_action("typing")
    prompt = (
        f"Give today's short English lesson on this EXACT topic: {topic}.\n"
        f"Include: 1 new word (with meaning + pronunciation + example), "
        f"1 grammar tip with 2 examples, 1 practice question. Plain text."
    )
    answer, suggestions = await asyncio.to_thread(ask_groq, prompt, None, user)
    if not answer:
        answer = "📚 Word: Persistent - Meaning: continuing firmly\nExample: Be persistent."
    kb = suggestions_kb(suggestions, context)
    await safe_reply(
        update.message,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n"
        f"📌 Topic: {topic}\n\n{answer}",
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
            "Usage:\n1. /broadcast your message\n"
            "2. Reply to any message with /broadcast"
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
        await update.message.reply_text(
            "Usage: /approve <user_id> [1m|3m|6m]\nDefault: 1m"
        )
        return
    try:
        target_uid = int(context.args[0])
        plan_key = context.args[1] if len(context.args) > 1 else "1m"
        plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
        days = plan["days"]

        until = datetime.now() + timedelta(days=days)
        await update_user(target_uid, is_premium=True, premium_until=until)

        target_lang = await get_user_lang(target_uid)
        await update.message.reply_text(
            f"✅ User {target_uid} granted Premium for {days} days ({plan_key})!"
        )

        try:
            await context.bot.send_message(
                target_uid,
                t("premium_success", target_lang, days=days)
            )
        except Exception:
            pass

        premium_files = await get_premium_files()
        if premium_files:
            try:
                await context.bot.send_message(target_uid, t("premium_files_sent", target_lang))
            except Exception:
                pass
            for f in premium_files:
                try:
                    await context.bot.send_document(
                        chat_id=target_uid,
                        document=f['file_id'],
                        caption=f.get('caption') or f.get('file_name') or ""
                    )
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"Premium file send to {target_uid} failed: {e}")
        else:
            try:
                await context.bot.send_message(target_uid, t("premium_no_files", target_lang))
            except Exception:
                pass

        try:
            await check_achievements(target_uid)
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
    context.user_data.pop('pending_file_caption', None)
    context.user_data.pop('pending_file_id_save', None)
    context.user_data.pop('pending_file_name_save', None)
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
        tag = "🔐" if f.get("is_premium") else "🆓"
        text += f"🆔 {f['id']} {tag} — {f['file_name']}\n"
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
    for k in ['awaiting_file', 'awaiting_file_caption', 'pending_file_id', 'pending_file_name',
              'pending_file_caption', 'pending_file_id_save', 'pending_file_name_save']:
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
        context.user_data['pending_file_id_save'] = file_id
        context.user_data['pending_file_name_save'] = file_name
        context.user_data['pending_file_caption'] = ""
        await update.message.reply_text(
            t("addfile_ask_type", "en", name=file_name),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("addfile_free_btn", "en"), callback_data="savetype_free")],
                [InlineKeyboardButton(t("addfile_premium_btn", "en"), callback_data="savetype_premium")],
                [InlineKeyboardButton("❌ Cancel", callback_data="savetype_cancel")],
            ])
        )


# ==========================================================
# PRONUNCIATION
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
# IELTS SPEAKING
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
        'stage': 1, 'q_index': 0, 'history': [],
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
        'stage': 1, 'q_index': 0, 'history': [],
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
    if ielts['history']:
        await generate_ielts_feedback(q.message, context, q.from_user.id, ielts, await get_user(q.from_user.id))
    else:
        await safe_edit(q, "❌ No answers given.", reply_markup=back_kb(lang))
    context.user_data.pop('ielts_speaking', None)


async def generate_ielts_feedback(message_obj, context, uid, ielts, user):
    lang = await get_user_lang(uid)
    analyzing_msg = await message_obj.reply_text(t("ielts_analyzing", lang))

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
        "Format with emojis and plain text. No markdown. Keep under 2500 characters."
    )

    prompt = (
        f"Candidate's IELTS Speaking Test transcript:\n\n{transcript}\n\n"
        f"Evaluate and give the band score and detailed feedback."
    )

    try:
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

    if user:
        await update_user(uid, last_active=datetime.now())
        earned = set(filter(None, (user.get("achievements") or "").split(",")))
        if "ielts_done" not in earned:
            earned.add("ielts_done")
            await update_user(uid, achievements=",".join(earned))


async def process_ielts_answer(message, context, user, text):
    ielts = context.user_data.get('ielts_speaking')
    if not ielts:
        return

    lang = user.get("language") or "bn"
    user_answer = text.strip()

    if len(user_answer) < 15:
        await message.reply_text(t("ielts_answer_too_short", lang))
        return

    ielts['history'].append({'q': ielts.get('current_q', ''), 'a': user_answer})
    ielts['q_index'] += 1
    qi = ielts['q_index']
    stage = ielts['stage']

    if stage == 1:
        if qi < len(IELTS_PART1_QUESTIONS):
            next_q = IELTS_PART1_QUESTIONS[qi]
            ielts['current_q'] = next_q
            await message.reply_text(
                f"{t('ielts_part1_start', lang, n=qi+1)}\n\n❓ {next_q}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("ielts_end_btn", lang), callback_data="ielts_end")],
                ])
            )
        else:
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
            await generate_ielts_feedback(message, context, user['user_id'], ielts, user)
            context.user_data.pop('ielts_speaking', None)


# ==========================================================
# PDF QUIZ
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
    lang = user.get("language") or "bn"
    gen_msg = await message.reply_text(t("pdfquiz_generating", lang))

    system_prompt = (
        "You are an expert quiz maker. Create 10 multiple-choice questions from the given content. "
        "Return ONLY a JSON array. No explanation, no markdown fences.\n\n"
        "Format exactly:\n"
        '[{"q": "Question text?", "options": ["Option A", "Option B", "Option C", "Option D"], "answer": 0}, ...]\n\n'
        "Rules:\n- Exactly 10 questions\n- Each question 4 options\n"
        "- 'answer' is index (0-3) of correct option\n- Simple, clear English"
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

    context.user_data['pdf_quiz'] = {
        'questions': quiz, 'current': 0, 'score': 0, 'answers': [],
    }
    context.user_data.pop('pdf_quiz_mode', None)

    await send_quiz_question(message, context, uid, user)


async def send_quiz_question(message, context, uid, user):
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
    lang = user.get("language") or "bn"
    state = context.user_data.pop('pdf_quiz', None)
    if not state:
        return
    total = len(state['questions'])
    score = state['score']
    pct = int(score / total * 100) if total > 0 else 0

    if pct >= 80:
        emoji = "🏆"; label = "Outstanding!"
    elif pct >= 60:
        emoji = "🎉"; label = "Very Good!"
    elif pct >= 40:
        emoji = "👍"; label = "Good"
    else:
        emoji = "📚"; label = "Keep Learning"

    text = (
        f"{t('pdfquiz_done', lang)}\n\n"
        f"{t('pdfquiz_score', lang)}\n"
        f"{emoji} {score}/{total} ({pct}%) — {label}\n\n"
        f"👉 /pdfquiz — Try another PDF\n"
        f"👉 /menu — Main menu"
    )
    await safe_reply(message, text)


async def process_quiz_answer(update, context, option_idx):
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
    "Tell me about your best friend.",
    "What is your favorite season and why?",
    "Describe your daily routine.",
    "What hobby would you like to learn?",
    "What is your dream job?",
    "Do you prefer mornings or evenings? Why?",
    "What is the last movie you watched?",
    "How do you relax after work?",
    "What is your favorite childhood memory?",
    "If you could travel anywhere, where would you go?",
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
        question = get_next_item(uid, "speaking", SPEAKING_QUESTIONS, context)
        prompt = f"Start English speaking practice. Ask this EXACT question:\n\n{question}\n\nWait for the answer. Plain text."
    elif data == "student_tenses":
        tense = get_next_item(uid, "tenses", TENSES_LIST, context)
        prompt = f"Teach ONE English tense: {tense}. Explain: usage, structure, 2 examples, common mistake, 1 practice question. Plain text."
    elif data == "student_learn":
        topic = get_next_item(uid, "learn", LEARN_TOPICS, context)
        prompt = f"Teach a short English lesson on this EXACT topic: {topic}.\nExplain simply, give 2 examples, then ONE practice question. Plain text."
    elif data == "student_vocab":
        word = get_next_item(uid, "vocab", VOCAB_WORDS, context)
        prompt = f"Teach this EXACT English word: {word}.\nInclude: meaning, pronunciation, part of speech, example sentence.\nThen ONE practice question. Plain text."
    elif data == "student_grammar":
        topic = get_next_item(uid, "grammar", GRAMMAR_TOPICS, context)
        prompt = f"Teach this EXACT English grammar point: {topic}.\nInclude: rule, explanation, 2 examples, common mistake, 1 practice question.\nPlain text."
    elif data == "student_writing":
        task = get_next_item(uid, "writing", WRITING_TASKS, context)
        prompt = f"Give this EXACT English writing task to the student:\n\n{task}\n\nWait for the student's answer. Plain text."
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
    topic = get_next_item(uid, "daily", DAILY_TOPICS, context)
    await q.edit_message_text(t("loading", lang))
    prompt = (
        f"Give today's short English lesson on this EXACT topic: {topic}.\n"
        f"Include: 1 new word (with meaning + pronunciation + example), "
        f"1 grammar tip with 2 examples, 1 practice question. Plain text."
    )
    answer, suggestions = await asyncio.to_thread(ask_groq, prompt, None, user)
    if not answer:
        answer = "📚 Word: Diligent - hardworking\nExample: She is a diligent student."
    kb = suggestions_kb(suggestions, context)
    await safe_edit(
        q,
        f"{t('daily_title', lang)} ({t('streak', lang)}: {streak} {t('days', lang)})\n"
        f"{t('bonus_coins', lang)}: +{bonus}\n"
        f"📌 Topic: {topic}\n\n{answer}",
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
    word = get_next_item(uid, "word_of_day", WORD_OF_DAY_POOL, context)
    await q.edit_message_text(t("loading", lang))
    prompt = (
        f"Teach this EXACT English word: {word}.\n"
        f"Include: word, meaning, pronunciation, part of speech, 2 examples, 2 synonyms.\n"
        f"Plain text."
    )
    answer, suggestions = await asyncio.to_thread(ask_groq, prompt, None, user)
    if not answer:
        answer = f"🔤 Word: {word}\n📖 Meaning: ..."
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

    rows = []
    for plan_key, plan in PREMIUM_PLANS.items():
        label = plan.get(f"label_{lang}") or plan["label_en"]
        rows.append([InlineKeyboardButton(
            f"💎 {label} — ৳{plan['bdt']} / {plan['stars']}⭐",
            callback_data=f"plan_{plan_key}"
        )])
    rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])

    await safe_edit(
        q,
        f"💎 Premium Membership\n\n{t('premium_choose', lang)}",
        reply_markup=InlineKeyboardMarkup(rows),
    )


async def cb_plan_selected(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    plan_key = q.data.replace("plan_", "")
    plan = PREMIUM_PLANS.get(plan_key)
    if not plan:
        return
    context.user_data["premium_plan"] = plan_key
    label = plan.get(f"label_{lang}") or plan["label_en"]

    await safe_edit(
        q,
        t("premium_plan_body", lang, label=label, bdt=plan["bdt"],
          stars=plan["stars"], usdt=plan["usdt"], days=plan["days"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"⭐ Stars ({plan['stars']})", callback_data=f"buy_{plan_key}")],
            [InlineKeyboardButton(f"💳 bKash ({plan['bdt']}৳)", callback_data=f"paybk_{plan_key}")],
            [InlineKeyboardButton(f"💳 Rocket ({plan['bdt']}৳)", callback_data=f"payrk_{plan_key}")],
            [InlineKeyboardButton("🪙 USDT (TRC20)", callback_data=f"paytrc_{plan_key}")],
            [InlineKeyboardButton("🪙 USDT (BSC20)", callback_data=f"paybsc_{plan_key}")],
            [InlineKeyboardButton("⬅️ Back", callback_data="m_premium")],
        ])
    )


async def cb_buy_premium(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    plan_key = q.data.replace("buy_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    try:
        await context.bot.send_invoice(
            chat_id=uid,
            title=f"💎 Premium — {plan['days']} days",
            description=f"Premium access for {plan['days']} days",
            payload=f"premium_{uid}_{plan_key}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="Premium", amount=plan['stars'])],
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
    free_files = await get_free_files()
    premium_files = await get_premium_files()

    if not free_files and not premium_files:
        await safe_edit(q, t("files_none", lang), reply_markup=back_kb(lang))
        return

    rows = []
    text_lines = []

    if free_files:
        text_lines.append(t("files_free_title", lang))
        for f in free_files:
            name = f['file_name'] or "file"
            display = name if len(name) < 30 else name[:27] + "..."
            rows.append([InlineKeyboardButton(f"🆓 {display}", callback_data=f"fget_{f['id']}")])

    if premium_files:
        text_lines.append("")
        text_lines.append(t("files_premium_title", lang))
        for f in premium_files:
            name = f['file_name'] or "file"
            display = name if len(name) < 30 else name[:27] + "..."
            rows.append([InlineKeyboardButton(f"🔐 {display}", callback_data=f"fget_{f['id']}")])

    rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])
    await safe_edit(
        q,
        "\n".join(text_lines),
        reply_markup=InlineKeyboardMarkup(rows)
    )


async def cb_file_send(update, context):
    q = update.callback_query
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    try:
        fid = int(q.data.split("_")[1])
    except Exception:
        await q.answer()
        return

    file = await get_file_by_db_id(fid)
    if not file:
        await q.answer(t("file_not_found", lang), show_alert=True)
        return

    if file.get("is_premium"):
        user = await get_user(uid)
        if not user or not user.get("is_premium"):
            await q.answer()
            await safe_edit(
                q,
                t("premium_file_locked", lang, name=file['file_name']),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💎 View Premium Plans", callback_data="m_premium")],
                    [InlineKeyboardButton("⬅️ Files", callback_data="m_files")],
                    [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
                ])
            )
            return

    await q.answer(t("file_sending", lang))
    try:
        await context.bot.send_document(
            chat_id=uid, document=file['file_id'], caption=file.get('caption') or ""
        )
    except Exception as e:
        logger.error(f"Send file error: {e}")
        await q.message.reply_text(t("file_send_fail", lang))


async def cb_save_file_type(update, context):
    q = update.callback_query
    uid = q.from_user.id
    if uid not in ADMIN_IDS:
        await q.answer("⛔", show_alert=True)
        return
    await q.answer()

    action = q.data.replace("savetype_", "")

    if action == "cancel":
        for k in ['pending_file_caption', 'pending_file_id_save', 'pending_file_name_save']:
            context.user_data.pop(k, None)
        await safe_edit(q, "❌ Cancelled.")
        return

    is_premium = (action == "premium")
    file_id = context.user_data.pop('pending_file_id_save', None)
    file_name = context.user_data.pop('pending_file_name_save', 'file')
    caption = context.user_data.pop('pending_file_caption', '')

    if not file_id:
        await safe_edit(q, t("addfile_nothing", "en"))
        return

    ok = await save_file(file_id, file_name, caption, uid, is_premium=is_premium)
    if ok:
        file_type = "🔐 Premium" if is_premium else "🆓 Free"
        await safe_edit(
            q,
            t("addfile_type_saved", "en",
              name=file_name, type=file_type, caption=caption or "(none)")
        )
    else:
        await safe_edit(q, t("addfile_save_fail", "en"))


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
    plan_key = q.data.replace("paybk_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'bKash'
    context.user_data['premium_plan'] = plan_key
    text = f"{t('pay_bkash_title', lang)}\n\n{t('pay_bkash_desc', lang, number=BKASH_NUMBER, amount=plan['bdt'])}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_bkash")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_rocket(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    plan_key = q.data.replace("payrk_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'Rocket'
    context.user_data['premium_plan'] = plan_key
    text = f"{t('pay_rocket_title', lang)}\n\n{t('pay_rocket_desc', lang, number=ROCKET_NUMBER, amount=plan['bdt'])}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_rocket")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_trc20(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    plan_key = q.data.replace("paytrc_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (TRC20)'
    context.user_data['premium_plan'] = plan_key
    text = f"{t('pay_trc20_title', lang)}\n\n{t('pay_trc20_desc', lang, amount=plan['usdt'], address=TRC20_ADDRESS)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_trc20")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
    ])
    await safe_edit(q, text, reply_markup=markup)


async def cb_pay_bsc20(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    plan_key = q.data.replace("paybsc_", "")
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    context.user_data['awaiting_payment'] = True
    context.user_data['payment_method'] = 'USDT (BSC20)'
    context.user_data['premium_plan'] = plan_key
    text = f"{t('pay_bsc20_title', lang)}\n\n{t('pay_bsc20_desc', lang, amount=plan['usdt'], address=BSC20_ADDRESS)}"
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton(t("copy_btn", lang), callback_data="copy_bsc20")],
        [InlineKeyboardButton(t("cancel_payment_btn", lang), callback_data="cancel_payment")],
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
    context.user_data.pop("premium_plan", None)
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
    payload = ""
    try:
        payload = update.message.successful_payment.invoice_payload
    except Exception:
        pass
    plan_key = "1m"
    if payload and payload.startswith("premium_"):
        parts = payload.split("_")
        if len(parts) >= 3:
            plan_key = parts[2]
    plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
    days = plan["days"]

    until = datetime.now() + timedelta(days=days)
    await update_user(uid, is_premium=True, premium_until=until)
    await update.message.reply_text(t("premium_success", lang, days=days))

    premium_files = await get_premium_files()
    if premium_files:
        try:
            await update.message.reply_text(t("premium_files_sent", lang))
        except Exception:
            pass
        for f in premium_files:
            try:
                await context.bot.send_document(
                    chat_id=uid,
                    document=f['file_id'],
                    caption=f.get('caption') or f.get('file_name') or ""
                )
                await asyncio.sleep(0.3)
            except Exception as e:
                logger.error(f"Premium file send failed: {e}")
    else:
        await update.message.reply_text(t("premium_no_files", lang))

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
                "📸 Photos, 🎤 Voice, 📄 PDFs\n🆘 @asikul_echo")
    elif lang == "hi":
        text = ("ℹ️ सहायता\n\n🎓 Learn 📚 Vocabulary 📝 Grammar\n🎭 Role-Play 🎯 Quiz\n🎤 Pronunciation 🎯 IELTS\n🆘 @asikul_echo")
    elif lang == "ru":
        text = ("ℹ️ Помощь\n\n🎓 Learn 📚 Vocabulary 📝 Grammar\n🎭 Role-Play 🎯 Quiz\n🎤 Pronunciation 🎯 IELTS\n🆘 @asikul_echo")
    else:
        text = ("ℹ️ সাহায্য\n\n"
                "🎓 Learn, 📚 Vocabulary, 📝 Grammar, ⏱ Tenses, 🗣 Speaking, ✍️ Writing\n"
                "🎭 Role-Play, 🔁 Review, 🎯 Quiz, 💬 Translate\n"
                "🔥 Daily, 📖 Word of Day, 📊 Progress, 🏆 Leaderboard\n"
                "🎁 Invite, ⭐ Premium, 📚 Mistakes, 🏅 Achievements\n"
                "🧠 Memory, 🔔 Reminder, 🌍 Language\n"
                "🎤 Pronunciation, 🎯 IELTS Speaking, 🧠 Quiz from PDF\n\n"
                "📸 ছবি, 🎤 ভয়েস, 📄 PDF\n🆘 @asikul_echo")
    await safe_edit(q, text, reply_markup=back_kb(lang))


# ==========================================================
# COURSE MODE HANDLERS
# ==========================================================
async def cb_course_home(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    if not await is_user_joined(context.bot, uid):
        return

    if not HAS_COURSES:
        await safe_edit(q, "❌ Course module not loaded.\n\nPlease add courses.py file.",
                        reply_markup=back_kb(lang))
        return

    progresses = await get_all_course_progress(uid)

    if not progresses:
        text = (
            "📚 MY COURSE\n\n"
            "🎓 ৩০ দিনের কোর্স থেকে বেছে নিন:\n\n"
            f"🟢 Beginner\n{get_course_desc('beginner', lang)}\n\n"
            f"🟡 Intermediate\n{get_course_desc('intermediate', lang)}\n\n"
            f"🔴 Advanced\n{get_course_desc('advanced', lang)}\n\n"
            "👇 নিচে থেকে বেছে নিন:"
        )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 Beginner Course", callback_data="course_pick_beginner")],
            [InlineKeyboardButton("🟡 Intermediate Course", callback_data="course_pick_intermediate")],
            [InlineKeyboardButton("🔴 Advanced Course", callback_data="course_pick_advanced")],
            [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
        ])
        await safe_edit(q, text, reply_markup=kb)
        return

    lines = ["📚 MY COURSE\n"]
    rows = []
    for p in progresses:
        c = p["course"]
        cd = p["current_day"] or 0
        name = get_course_name(c, lang)
        if p.get("completed_at"):
            status = "🏆 Completed!"
            rows.append([InlineKeyboardButton(
                f"🎓 {name} — Certificate",
                callback_data=f"course_cert_{c}"
            )])
        else:
            pct = int(cd / COURSE_TOTAL_DAYS * 100)
            status = f"Day {cd}/{COURSE_TOTAL_DAYS} ({pct}%)"
            next_day = cd + 1 if cd < COURSE_TOTAL_DAYS else cd
            rows.append([InlineKeyboardButton(
                f"▶️ {name} — Day {next_day}",
                callback_data=f"course_day_{c}_{next_day}"
            )])
        lines.append(f"{name}\n{status}")

    if len(progresses) < 3:
        rows.append([InlineKeyboardButton("➕ আরেকটা কোর্স", callback_data="course_more")])

    rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])
    await safe_edit(q, "\n\n".join(lines), reply_markup=InlineKeyboardMarkup(rows))


async def cb_course_more(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    progresses = await get_all_course_progress(uid)
    enrolled = {p["course"] for p in progresses}

    rows = []
    for c in ["beginner", "intermediate", "advanced"]:
        if c not in enrolled:
            rows.append([InlineKeyboardButton(
                get_course_name(c, lang),
                callback_data=f"course_pick_{c}"
            )])
    rows.append([InlineKeyboardButton("⬅️ Back", callback_data="course_home")])
    await safe_edit(q, "📚 আরেকটা কোর্স বেছে নিন:", reply_markup=InlineKeyboardMarkup(rows))


async def cb_course_pick(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    course = q.data.replace("course_pick_", "")
    if course not in COURSE_DATA:
        return

    name = get_course_name(course, lang)
    desc = get_course_desc(course, lang)

    prog = await get_course_progress(uid, course)
    if prog:
        cd = prog["current_day"] or 0
        next_day = cd + 1 if cd < COURSE_TOTAL_DAYS else cd
        await safe_edit(q,
            f"{name}\n\n{desc}\n\n"
            f"📊 Day {cd}/{COURSE_TOTAL_DAYS}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    f"▶️ Continue Day {next_day}",
                    callback_data=f"course_day_{course}_{next_day}"
                )],
                [InlineKeyboardButton("⬅️ Back", callback_data="course_home")],
            ])
        )
        return

    text = (
        f"{name}\n\n"
        f"{desc}\n\n"
        f"📅 ৩০ দিন\n"
        f"⏱️ প্রতিদিন ১৫ মিনিট\n"
        f"📚 Vocabulary + Grammar + Dialogue + Quiz\n"
        f"🏆 শেষে সনদ\n\n"
        f"শুরু করতে চাপুন 👇"
    )
    await safe_edit(q, text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ Start Day 1", callback_data=f"course_start_{course}")],
        [InlineKeyboardButton("⬅️ Back", callback_data="course_home")],
    ]))

async def cb_course_start(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    course = q.data.replace("course_start_", "")
    await start_course(uid, course)
    q.data = f"course_day_{course}_1"
    await cb_course_day(update, context)

async def cb_course_day(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)

    parts = q.data.split("_")
    try:
        course = parts[2]
        day = int(parts[3])
    except Exception:
        return

    if course not in COURSE_DATA or day < 1 or day > COURSE_TOTAL_DAYS:
        return

    prog = await get_course_progress(uid, course)
    if not prog:
        await start_course(uid, course)
        prog = await get_course_progress(uid, course)

    current_day = (prog["current_day"] if prog else 0) or 0
    if day > current_day + 1:
        await q.answer(f"⚠️ আগে Day {current_day + 1} শেষ করুন!", show_alert=True)
        return

    topic = get_topic_display(course, day, lang)

    # ===== Check static / cache first =====
    lesson_text = None
    if course == "beginner" and lang == "bn" and HAS_STATIC_BN:
        lesson_text = get_static_lesson_bn(course, day)

    if not lesson_text:
        lesson_text = await get_cached_lesson(course, day)

    # ===== If no cache, generate with NEW loading message =====
    loading_msg = None
    if not lesson_text:
        try:
            loading_msg = await q.message.reply_text(
                f"📅 Day {day}/{COURSE_TOTAL_DAYS}\n"
                f"📌 {topic}\n\n"
                f"⏳ Lesson তৈরি হচ্ছে...\n"
                f"অনুগ্রহ করে ১০-১৫ সেকেন্ড অপেক্ষা করুন।"
            )
        except Exception:
            pass

        prompt = build_lesson_prompt(course, day, lang)
        if prompt:
            lesson_text, _ = await asyncio.to_thread(ask_groq, prompt, None, None)

        if not lesson_text:
            lesson_text = "❌ Lesson generate failed. আবার চেষ্টা করুন।"
        else:
            await save_cached_lesson(course, day, lesson_text)

    # ===== Delete loading message =====
    if loading_msg:
        try:
            await loading_msg.delete()
        except Exception:
            pass

    # ===== Render content =====
    header = (
        f"📅 Day {day}/{COURSE_TOTAL_DAYS} — {get_course_name(course, lang)}\n"
        f"📌 {topic}\n\n"
        f"━━━━━━━━━━━━━━━━━\n\n"
    )

    if len(lesson_text) > 3000:
        body = lesson_text[:3000] + "..."
    else:
        body = lesson_text

    practice_hint = (
        "\n\n━━━━━━━━━━━━━━━━━\n"
        "💡 শেখার নিয়ম:\n"
        "1. লেসনটা একবার পড়ুন\n"
        "2. জোরে পড়ুন ২ বার\n"
        "3. Practice-এর ৩টা বাক্য নিজে লিখুন\n"
        "4. এই মেসেজে REPLY দিয়ে পাঠান\n"
        "5. আমি ভুল ঠিক করে দেব ✅\n"
    )
    body = body + practice_hint

    kb_rows = []
    kb_rows.append([InlineKeyboardButton(
        f"🎯 Take Quiz — Day {day}",
        callback_data=f"course_quiz_{course}_{day}"
    )])

    nav_row = []
    if day > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"course_day_{course}_{day-1}"))
    nav_row.append(InlineKeyboardButton("🏠 Course", callback_data="course_home"))
    if day < current_day:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"course_day_{course}_{day+1}"))
    kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])

    await safe_edit(q, header + body, reply_markup=InlineKeyboardMarkup(kb_rows))

    practice_hint = (
        "\n\n━━━━━━━━━━━━━━━━━\n"
        "💡 শেখার নিয়ম:\n"
        "1. লেসনটা একবার পড়ুন\n"
        "2. জোরে পড়ুন ২ বার\n"
        "3. Practice-এর ৩টা বাক্য নিজে লিখুন\n"
        "4. এই মেসেজে REPLY দিয়ে পাঠান\n"
        "5. আমি ভুল ঠিক করে দেব ✅\n"
    )
    body = body + practice_hint

    kb_rows = []
    kb_rows.append([InlineKeyboardButton(
        f"🎯 Take Quiz — Day {day}",
        callback_data=f"course_quiz_{course}_{day}"
    )])

    nav_row = []
    if day > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"course_day_{course}_{day-1}"))
    nav_row.append(InlineKeyboardButton("🏠 Course", callback_data="course_home"))
    if day < current_day:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"course_day_{course}_{day+1}"))
    kb_rows.append(nav_row)
    kb_rows.append([InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")])

    await safe_edit(q, header + body, reply_markup=InlineKeyboardMarkup(kb_rows))


async def cb_course_quiz(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)

    parts = q.data.split("_")
    try:
        course = parts[2]
        day = int(parts[3])
    except Exception:
        return

    cached = await get_cached_quiz(course, day)
    quiz_data = None
    if cached:
        try:
            quiz_data = json.loads(cached)
        except Exception:
            quiz_data = None

    if not quiz_data:
        await safe_edit(q, "⏳ Quiz তৈরি হচ্ছে...", reply_markup=None)
        prompt = build_quiz_prompt(course, day, lang)
        if not prompt:
            await safe_edit(q, "❌ Quiz error.", reply_markup=back_kb(lang))
            return
        raw, _ = await asyncio.to_thread(ask_groq, prompt, None, None, None, True)
        if raw:
            m = re.search(r'\[\s*\{.*\}\s*\]', raw, re.DOTALL)
            if m:
                try:
                    quiz_data = json.loads(m.group(0))
                except Exception:
                    pass
        if not quiz_data or len(quiz_data) < 1:
            await safe_edit(q, "❌ Quiz generate failed. আবার চেষ্টা করুন।",
                            reply_markup=back_kb(lang))
            return
        await save_cached_quiz(course, day, json.dumps(quiz_data))

    context.user_data[f"cq_{course}_{day}"] = {
        "quiz": quiz_data[:3],
        "current": 0,
        "score": 0,
        "course": course,
        "day": day,
    }
    await send_cq_question(q, context, uid, lang, course, day)


async def send_cq_question(q, context, uid, lang, course, day):
    state = context.user_data.get(f"cq_{course}_{day}")
    if not state:
        return
    idx = state["current"]
    quiz = state["quiz"]

    if idx >= len(quiz):
        score = state["score"]
        total = len(quiz)
        pct = int(score / total * 100)

        prog = await get_course_progress(uid, course)
        current_day = (prog["current_day"] if prog else 0) or 0
        if day > current_day:
            await complete_course_day(uid, course, day)
            await add_coins(uid, 10)

        if day == COURSE_TOTAL_DAYS:
            await complete_course(uid, course, score)
            text = (
                f"🏆 FINAL TEST সম্পন্ন!\n\n"
                f"📊 Score: {score}/{total} ({pct}%)\n\n"
                f"🎉 অভিনন্দন! আপনি {get_course_name(course, lang)} শেষ করেছেন!\n\n"
                f"🎓 আপনার সনদ দেখতে চাপুন 👇"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🎓 Certificate দেখুন",
                                      callback_data=f"course_cert_{course}")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        else:
            next_day = day + 1
            text = (
                f"✅ Day {day} সম্পন্ন!\n\n"
                f"📊 Score: {score}/{total} ({pct}%)\n"
                f"🎁 +10 coins\n\n"
                f"▶️ Day {next_day} unlock হয়েছে!"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"▶️ Start Day {next_day}",
                                      callback_data=f"course_day_{course}_{next_day}")],
                [InlineKeyboardButton("🏠 Course Home", callback_data="course_home")],
                [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
            ])
        context.user_data.pop(f"cq_{course}_{day}", None)
        await safe_edit(q, text, reply_markup=kb)
        return

    question = quiz[idx]
    letters = ["A", "B", "C", "D"]
    text = (
        f"🎯 Day {day} Quiz — প্রশ্ন {idx + 1}/{len(quiz)}\n\n"
        f"❓ {question['q']}"
    )
    rows = []
    for i, opt in enumerate(question['options'][:4]):
        label = f"{letters[i]}) {opt[:45]}"
        rows.append([InlineKeyboardButton(label, callback_data=f"cq_{course}_{day}_{i}")])
    await safe_edit(q, text, reply_markup=InlineKeyboardMarkup(rows))


async def cb_cq_answer(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)

    parts = q.data.split("_")
    try:
        course = parts[1]
        day = int(parts[2])
        option = int(parts[3])
    except Exception:
        return

    state = context.user_data.get(f"cq_{course}_{day}")
    if not state:
        await q.answer("Expired", show_alert=True)
        return

    idx = state["current"]
    quiz = state["quiz"]
    if idx >= len(quiz):
        return
    question = quiz[idx]
    correct = question["answer"]
    letters = ["A", "B", "C", "D"]

    if option == correct:
        state["score"] += 1
        fb = "✅ সঠিক!"
    else:
        fb = f"❌ ভুল\n\n✅ সঠিক উত্তর: {letters[correct]}) {question['options'][correct]}"

    try:
        await q.message.reply_text(fb)
    except Exception:
        pass

    state["current"] += 1
    await send_cq_question(q, context, uid, lang, course, day)


async def cb_course_cert(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = await get_user_lang(uid)
    course = q.data.replace("course_cert_", "")

    prog = await get_course_progress(uid, course)
    if not prog or not prog.get("completed_at"):
        await safe_edit(q, "❌ এই কোর্স এখনো শেষ হয়নি।", reply_markup=back_kb(lang))
        return

    user = await get_user(uid)
    name = (user or {}).get("name") or "Student"
    score = prog.get("final_score", 0)
    completed = prog.get("completed_at")
    if isinstance(completed, datetime):
        date_str = completed.strftime("%d %B %Y")
    else:
        date_str = str(completed)[:10]

    cert = (
        "╔══════════════════════════════╗\n"
        "║      🎓 CERTIFICATE          ║\n"
        "║      OF COMPLETION           ║\n"
        "╚══════════════════════════════╝\n\n"
        "This certifies that\n\n"
        f"      ✨ {name} ✨\n\n"
        f"has successfully completed the\n"
        f"    {get_course_name(course, 'en')}\n\n"
        f"📅 Date: {date_str}\n"
        f"📊 Final Score: {score}/3\n"
        f"⏱️ Duration: 30 days\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🏆 Keep learning, keep growing!\n"
        "      — EduMate AI\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    await safe_edit(q, cert, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Course Home", callback_data="course_home")],
        [InlineKeyboardButton(t("menu_btn", lang), callback_data="m_menu")],
    ]))


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

    if context.user_data.get('awaiting_file_caption') and uid in ADMIN_IDS and message.text:
        caption = message.text.strip()
        file_id = context.user_data.pop('pending_file_id', None)
        file_name = context.user_data.pop('pending_file_name', 'file')
        context.user_data.pop('awaiting_file_caption', None)
        if file_id:
            context.user_data['pending_file_id_save'] = file_id
            context.user_data['pending_file_name_save'] = file_name
            context.user_data['pending_file_caption'] = caption
            await message.reply_text(
                t("addfile_ask_type", "en", name=file_name),
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(t("addfile_free_btn", "en"), callback_data="savetype_free")],
                    [InlineKeyboardButton(t("addfile_premium_btn", "en"), callback_data="savetype_premium")],
                    [InlineKeyboardButton("❌ Cancel", callback_data="savetype_cancel")],
                ])
            )
        return

    ielts = context.user_data.get('ielts_speaking')
    if ielts:
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
            if message.text and not message.text.startswith("/"):
                await message.reply_text(
                    "🎤 Please send a VOICE message.\n"
                    "❌ /cancelpronounce to exit."
                )
                return

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

    pdf_quiz = context.user_data.get('pdf_quiz')
    if pdf_quiz and message.text and not message.text.startswith("/"):
        await message.reply_text(
            "👆 Please click one of the option buttons above.\n"
            "🛑 To stop, click Stop Quiz."
        )
        return

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

    if message.document:
        doc = message.document
        file_size = doc.file_size or 0
        file_name = doc.file_name or "document.pdf"
        mime = (doc.mime_type or "").lower()

        if uid in ADMIN_IDS and context.user_data.get('awaiting_file'):
            context.user_data['pending_file_id'] = doc.file_id
            context.user_data['pending_file_name'] = file_name
            context.user_data['awaiting_file'] = False
            context.user_data['awaiting_file_caption'] = True
            await message.reply_text(t("addfile_received", "en", name=file_name))
            return

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
                    f"Analyze the PDF and answer the user's request."
                )
            else:
                prompt = (
                    f"The user sent a PDF file named '{file_name}'.\n\n"
                    f"PDF Content:\n{pdf_text}\n\n"
                    f"Please: 1) Give a short summary, 2) List 5-7 key points, "
                    f"3) Suggest what the user can learn from it."
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

    if message.photo:
        if context.user_data.get('awaiting_payment'):
            method = context.user_data.get('payment_method', 'Unknown')
            plan_key = context.user_data.get('premium_plan', '1m')
            plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
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
                        f"🆔 User ID: `{uid}`\n"
                        f"📦 Plan: {plan_key} ({plan['days']} days)\n\n"
                        f"Approve with:\n`/approve {uid} {plan_key}`"
                    )
                except Exception as e:
                    logger.error(f"Fwd proof fail: {e}")
            await message.reply_text(t("payment_proof_sent", lang))
            context.user_data.pop('awaiting_payment', None)
            context.user_data.pop('payment_method', None)
            context.user_data.pop('premium_plan', None)
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
        plan_key = context.user_data.get('premium_plan', '1m')
        plan = PREMIUM_PLANS.get(plan_key, PREMIUM_PLANS["1m"])
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
                    f"🆔 User ID: `{uid}`\n"
                    f"📦 Plan: {plan_key} ({plan['days']} days)\n\n"
                    f"Approve with: `/approve {uid} {plan_key}`"
                )
            except Exception as e:
                logger.error(f"Text fwd fail: {e}")
        await message.reply_text(t("payment_info_sent", lang))
        context.user_data.pop('awaiting_payment', None)
        context.user_data.pop('payment_method', None)
        context.user_data.pop('premium_plan', None)
        return

    replied_text = ""
    if (message.reply_to_message
            and message.reply_to_message.from_user
            and message.reply_to_message.from_user.id == context.bot.id):
        replied_text = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        ).strip()

    if chat.type == "private":
        user_text = message.text.strip()
        if not user_text:
            return
    else:
        bot_username = context.bot.username
        if not bot_username:
            return
        is_reply_to_bot = bool(replied_text)
        mention = f"@{bot_username.lower()}"
        if mention not in message.text.lower() and not is_reply_to_bot:
            return
        user_text = message.text.replace(f"@{bot_username}", "").strip()
        if not user_text:
            user_text = "Please help me with English."

    if replied_text:
        ctx = replied_text[:800]
        ai_input = (
            f"[CONTEXT: The user is REPLYING to a specific message you sent earlier.]\n"
            f"[Your original message was:]\n"
            f"\"\"\"\n{ctx}\n\"\"\"\n\n"
            f"[The user's reply is:]\n"
            f"\"{user_text}\"\n\n"
            f"⚠️ INTERPRETATION RULES:\n"
            f"1. If your original message ASKED a question or gave a task "
            f"(like 'practice these sentences', 'answer these questions'), "
            f"the user is trying to ANSWER it.\n"
            f"2. CHECK their answer carefully. If correct → praise them. "
            f"If wrong → gently correct and show the right version.\n"
            f"3. If the user is asking about your message → explain it.\n"
            f"4. Stay in {user.get('language', 'bn')} language.\n"
            f"5. Be encouraging. Under 1500 characters."
        )
    else:
        ai_input = user_text

    await update_user(uid, last_active=datetime.now())
    await check_streak(uid)
    await save_history(uid, "user", user_text)
    history = await get_history(uid)
    try:
        await message.chat.send_action("typing")
    except Exception:
        pass
    answer, suggestions = await asyncio.to_thread(ask_groq, ai_input, history, user)
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
        application.add_handler(CallbackQueryHandler(cb_save_file_type, pattern="^savetype_"))

        application.add_handler(CallbackQueryHandler(cb_course_home, pattern="^course_home$"))
        application.add_handler(CallbackQueryHandler(cb_course_more, pattern="^course_more$"))
        application.add_handler(CallbackQueryHandler(cb_course_pick, pattern="^course_pick_"))
        application.add_handler(CallbackQueryHandler(cb_course_start, pattern="^course_start_"))
        application.add_handler(CallbackQueryHandler(cb_course_day, pattern="^course_day_"))
        application.add_handler(CallbackQueryHandler(cb_course_quiz, pattern="^course_quiz_"))
        application.add_handler(CallbackQueryHandler(cb_cq_answer, pattern="^cq_"))
        application.add_handler(CallbackQueryHandler(cb_course_cert, pattern="^course_cert_"))

        application.add_handler(CallbackQueryHandler(cb_plan_selected, pattern="^plan_"))
        application.add_handler(CallbackQueryHandler(cb_buy_premium, pattern="^buy_"))
        application.add_handler(CallbackQueryHandler(cb_pay_bkash, pattern="^paybk_"))
        application.add_handler(CallbackQueryHandler(cb_pay_rocket, pattern="^payrk_"))
        application.add_handler(CallbackQueryHandler(cb_pay_trc20, pattern="^paytrc_"))
        application.add_handler(CallbackQueryHandler(cb_pay_bsc20, pattern="^paybsc_"))
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
