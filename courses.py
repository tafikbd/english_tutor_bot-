"""
Sir English — Multi-language Course System
Supports 15 languages: bn, en, hi, ru, ar, es, fr, pt, id, ur, tr, de, zh, it, vi
Static content: Bengali Beginner, English Beginner
AI-generated: all other combinations
"""

COURSE_TOTAL_DAYS = 30

# ==========================================================
# LANGUAGE CONFIGURATION
# ==========================================================
LANGUAGES = {
    "bn": {"flag": "🇧🇩", "native": "বাংলা",     "english": "Bengali",    "name": "Bengali"},
    "en": {"flag": "🇬🇧", "native": "English",   "english": "English",    "name": "English"},
    "hi": {"flag": "🇮🇳", "native": "हिन्दी",      "english": "Hindi",      "name": "Hindi"},
    "ru": {"flag": "🇷🇺", "native": "Русский",   "english": "Russian",    "name": "Russian"},
    "ar": {"flag": "🇸🇦", "native": "العربية",   "english": "Arabic",     "name": "Arabic"},
    "es": {"flag": "🇪🇸", "native": "Español",   "english": "Spanish",    "name": "Spanish"},
    "fr": {"flag": "🇫🇷", "native": "Français",  "english": "French",     "name": "French"},
    "pt": {"flag": "🇵🇹", "native": "Português", "english": "Portuguese", "name": "Portuguese"},
    "id": {"flag": "🇮🇩", "native": "Indonesia", "english": "Indonesian", "name": "Indonesian"},
    "ur": {"flag": "🇵🇰", "native": "اردو",      "english": "Urdu",       "name": "Urdu"},
    "tr": {"flag": "🇹🇷", "native": "Türkçe",    "english": "Turkish",    "name": "Turkish"},
    "de": {"flag": "🇩🇪", "native": "Deutsch",   "english": "German",     "name": "German"},
    "zh": {"flag": "🇨🇳", "native": "中文",       "english": "Chinese",    "name": "Chinese"},
    "it": {"flag": "🇮🇹", "native": "Italiano",  "english": "Italian",    "name": "Italian"},
    "vi": {"flag": "🇻🇳", "native": "Tiếng Việt","english": "Vietnamese", "name": "Vietnamese"},
}

# ==========================================================
# COURSE TOPICS (canonical English — AI translates)
# ==========================================================
BEGINNER_TOPICS = [
    "Greetings", "Self Introduction", "Family Members", "Numbers and Counting",
    "Colors and Shapes", "Days of the Week", "Months and Seasons", "Food and Drinks",
    "Daily Routine", "My House", "At the Market", "Weather",
    "Clothes and Shopping", "Transportation", "Body Parts", "Feelings and Emotions",
    "Hobbies", "At School", "Jobs and Occupations", "Animals",
    "At the Restaurant", "Giving Directions", "Time and Clock", "Making Requests",
    "Polite Expressions", "Phone Conversations", "Doctor and Health", "Travel Basics",
    "Emergency Phrases", "Review and Final Test",
]

INTERMEDIATE_TOPICS = [
    "Past Simple", "Present Perfect", "Future Forms", "Comparatives and Superlatives",
    "Modals of Ability", "Modals of Advice", "First Conditional", "Second Conditional",
    "Passive Voice", "Reported Speech", "Phrasal Verbs", "Prepositions of Time",
    "Articles (a, an, the)", "Gerunds and Infinitives", "Relative Clauses",
    "Present Continuous", "Past Continuous", "Used to / Would", "Question Tags",
    "Adverbs of Frequency", "Conjunctions", "Countable vs Uncountable",
    "Some vs Any", "Much vs Many", "Subject-Verb Agreement", "Adjective Order",
    "Direct vs Indirect Objects", "Time Clauses", "Purpose Clauses", "Review and Final Test",
]

ADVANCED_TOPICS = [
    "All Conditionals (0-3)", "Advanced Passive Voice", "Inversion", "Subjunctive Mood",
    "Cleft Sentences", "Participle Clauses", "Advanced Reported Speech",
    "Hedging and Modality", "Nominalization", "Cohesion and Coherence",
    "Advanced Phrasal Verbs", "Idioms and Collocations", "Formal vs Informal Register",
    "Academic Vocabulary", "IELTS Writing Task 1 Language", "IELTS Writing Task 2 Language",
    "IELTS Speaking Band 8+ Phrases", "Business English", "Presentation Skills",
    "Negotiation Language", "Debate and Argumentation", "Nuanced Opinion Expression",
    "Advanced Connectors", "Discourse Markers", "Emphasis and Focus",
    "Tone and Register", "Irony and Sarcasm", "Literary Devices", "Advanced Review", "Final Mastery Test",
]

# ==========================================================
# COURSE DATA
# ==========================================================
COURSE_DATA = {
    "beginner": {
        "name": {
            "bn": "🟢 Beginner", "en": "🟢 Beginner", "hi": "🟢 शुरुआती",
            "ru": "🟢 Начальный", "ar": "🟢 مبتدئ", "es": "🟢 Principiante",
            "fr": "🟢 Débutant", "pt": "🟢 Iniciante", "id": "🟢 Pemula",
            "ur": "🟢 ابتدائی", "tr": "🟢 Başlangıç", "de": "🟢 Anfänger",
            "zh": "🟢 初级", "it": "🟢 Principiante", "vi": "🟢 Sơ cấp",
        },
        "desc": {
            "bn": "একদম শুরু থেকে — ৩০ দিনে বেসিক ইংরেজি",
            "en": "From absolute zero — learn basic English in 30 days",
            "hi": "शुरुआत से — 30 दिनों में बेसिक इंग्लिश",
            "ru": "С нуля — базовый английский за 30 дней",
            "ar": "من الصفر — الإنجليزية الأساسية في 30 يومًا",
            "es": "Desde cero — inglés básico en 30 días",
            "fr": "De zéro — anglais de base en 30 jours",
            "pt": "Do zero — inglês básico em 30 dias",
            "id": "Dari nol — bahasa Inggris dasar dalam 30 hari",
            "ur": "بالکل شروع سے — 30 دن میں بنیادی انگریزی",
            "tr": "Sıfırdan — 30 günde temel İngilizce",
            "de": "Von Null — Basis-Englisch in 30 Tagen",
            "zh": "从零开始 — 30天基础英语",
            "it": "Da zero — inglese base in 30 giorni",
            "vi": "Từ con số 0 — tiếng Anh cơ bản trong 30 ngày",
        },
        "topics": BEGINNER_TOPICS,
    },
    "intermediate": {
        "name": {
            "bn": "🟡 Intermediate", "en": "🟡 Intermediate", "hi": "🟡 मध्यवर्ती",
            "ru": "🟡 Средний", "ar": "🟡 متوسط", "es": "🟡 Intermedio",
            "fr": "🟡 Intermédiaire", "pt": "🟡 Intermediário", "id": "🟡 Menengah",
            "ur": "🟡 درمیانی", "tr": "🟡 Orta", "de": "🟡 Mittelstufe",
            "zh": "🟡 中级", "it": "🟡 Intermedio", "vi": "🟡 Trung cấp",
        },
        "desc": {
            "bn": "বেসিক জানেন — এখন fluency-র দিকে",
            "en": "You know the basics — now move toward fluency",
            "hi": "बेसिक्स जानते हैं — अब fluency की ओर",
            "ru": "Знаете основы — движемся к беглости",
            "ar": "تعرف الأساسيات — الآن نحو الطلاقة",
            "es": "Sabes lo básico — ahora hacia la fluidez",
            "fr": "Vous connaissez les bases — vers la fluidité",
            "pt": "Você sabe o básico — agora fluência",
            "id": "Anda tahu dasar — sekarang menuju kefasihan",
            "ur": "بنیادی جانتے ہیں — اب روانی کی طرف",
            "tr": "Temelleri biliyorsunuz — şimdi akıcılığa",
            "de": "Du kennst die Grundlagen — jetzt zur Flüssigkeit",
            "zh": "你懂基础 — 现在提高流利度",
            "it": "Conosci le basi — ora verso la fluidità",
            "vi": "Bạn biết cơ bản — giờ hướng đến lưu loát",
        },
        "topics": INTERMEDIATE_TOPICS,
    },
    "advanced": {
        "name": {
            "bn": "🔴 Advanced", "en": "🔴 Advanced", "hi": "🔴 उन्नत",
            "ru": "🔴 Продвинутый", "ar": "🔴 متقدم", "es": "🔴 Avanzado",
            "fr": "🔴 Avancé", "pt": "🔴 Avançado", "id": "🔴 Lanjutan",
            "ur": "🔴 اعلی", "tr": "🔴 İleri", "de": "🔴 Fortgeschritten",
            "zh": "🔴 高级", "it": "🔴 Avanzato", "vi": "🔴 Nâng cao",
        },
        "desc": {
            "bn": "Fluency + IELTS/BCS লেভেল ইংরেজি",
            "en": "Fluency + IELTS/BCS level English",
            "hi": "Fluency + IELTS/BCS स्तर की इंग्लिश",
            "ru": "Беглость + IELTS/BCS уровень",
            "ar": "الطلاقة + مستوى IELTS/BCS",
            "es": "Fluidez + nivel IELTS/BCS",
            "fr": "Fluidité + niveau IELTS/BCS",
            "pt": "Fluência + nível IELTS/BCS",
            "id": "Kefasihan + level IELTS/BCS",
            "ur": "روانی + IELTS/BCS لیول",
            "tr": "Akıcılık + IELTS/BCS seviyesi",
            "de": "Flüssigkeit + IELTS/BCS-Niveau",
            "zh": "流利度 + IELTS/BCS 水平",
            "it": "Fluidità + livello IELTS/BCS",
            "vi": "Lưu loát + trình độ IELTS/BCS",
        },
        "topics": ADVANCED_TOPICS,
    },
}


# ==========================================================
# PUBLIC FUNCTIONS
# ==========================================================
def get_course_name(course, lang="bn"):
    data = COURSE_DATA.get(course)
    if not data:
        return "Course"
    return data["name"].get(lang) or data["name"].get("en") or "Course"


def get_course_desc(course, lang="bn"):
    data = COURSE_DATA.get(course)
    if not data:
        return ""
    return data["desc"].get(lang) or data["desc"].get("en") or ""


def get_topic_display(course, day, lang="bn"):
    data = COURSE_DATA.get(course)
    if not data:
        return "—"
    topics = data.get("topics", [])
    if 1 <= day <= len(topics):
        return topics[day - 1]
    return "—"


def get_day_info(course, day):
    return get_topic_display(course, day, "en")


def is_language_rtl(lang):
    return lang in ("ar", "ur")


def get_language_flag(lang):
    return LANGUAGES.get(lang, {}).get("flag", "🌐")


def get_language_native(lang):
    return LANGUAGES.get(lang, {}).get("native", "Unknown")


def get_all_language_codes():
    return list(LANGUAGES.keys())


# ==========================================================
# LESSON PROMPT BUILDER (language-aware)
# ==========================================================
def build_lesson_prompt(course, day, lang="bn"):
    if course not in COURSE_DATA:
        return None
    
    topic = get_topic_display(course, day, lang)
    course_name = get_course_name(course, lang)
    
    lang_info = LANGUAGES.get(lang, LANGUAGES["bn"])
    target_lang = lang_info["english"]
    
    if lang == "en":
        translation_rule = (
            "The user is learning English. DO NOT provide any translation. "
            "Present everything in simple, clear English only."
        )
        translation_format = "(no translation needed — English only)"
    else:
        translation_rule = (
            f"The user's native language is {target_lang}. "
            f"You MUST provide translations in {target_lang} for EVERY English sentence. "
            f"Use native {target_lang} script (not Roman/English letters). "
            f"Translate accurately and naturally."
        )
        translation_format = f"[{target_lang} translation here]"
    
    if course == "beginner":
        level_tone = "Use VERY SIMPLE language. Explain like talking to a beginner. Short sentences."
    elif course == "intermediate":
        level_tone = "Use CLEAR, natural language. Assume basic knowledge. Give good examples."
    else:
        level_tone = "Use ADVANCED vocabulary. Include idioms, collocations, formal register."
    
    prompt = f"""You are an expert English teacher creating lesson content.

COURSE: {course_name}
DAY: {day}/30
TOPIC: {topic}
STUDENT LEVEL: {course.upper()}

LANGUAGE INSTRUCTION (MOST IMPORTANT):
{translation_rule}

LEVEL INSTRUCTION:
{level_tone}

REQUIRED STRUCTURE — DO NOT SKIP ANY SECTION:

📅 DAY {day} — {topic}

━━━━━━━━━━━━━━━━━
🔤 VOCABULARY (exactly 5 words)
━━━━━━━━━━━━━━━━━
For each word:
1️⃣ English word  /pronunciation/
   📖 Meaning: {translation_format}
   ✏️ Example: [English example]
   {translation_format}

(repeat for 5 words)

━━━━━━━━━━━━━━━━━
📝 GRAMMAR
━━━━━━━━━━━━━━━━━
🎯 Rule: [explanation in user's language]
   Structure: [English formula]
✏️ Example 1: [English]
{translation_format}
✏️ Example 2: [English]
{translation_format}

━━━━━━━━━━━━━━━━━
💬 USEFUL PHRASES (4 phrases)
━━━━━━━━━━━━━━━━━
• [English phrase] — {translation_format}
• [English phrase] — {translation_format}
• [English phrase] — {translation_format}
• [English phrase] — {translation_format}

━━━━━━━━━━━━━━━━━
🎭 DIALOGUE (4 lines, A and B)
━━━━━━━━━━━━━━━━━
A: [English line]
{translation_format}

B: [English line]
{translation_format}

A: [English line]
{translation_format}

B: [English line]
{translation_format}

━━━━━━━━━━━━━━━━━
✍️ PRACTICE (3 sentences)
━━━━━━━━━━━━━━━━━
1. [English sentence]
   {translation_format}
2. [English sentence]
   {translation_format}
3. [English sentence]
   {translation_format}

CRITICAL RULES:
- Use PLAIN TEXT only. No markdown (no **, no ##, no *).
- Use emojis for visual clarity.
- Include ALL 5 sections: Vocabulary, Grammar, Phrases, Dialogue, Practice.
- Keep entire lesson under 3000 characters.
- Translations MUST be in {target_lang} script.
- Do NOT translate the English vocabulary words themselves — only meanings/examples.
"""
    return prompt


# ==========================================================
# QUIZ PROMPT BUILDER (JSON output, English questions)
# ==========================================================
def build_quiz_prompt(course, day, lang="bn"):
    if course not in COURSE_DATA:
        return None
    
    topic = get_topic_display(course, day, lang)
    lang_info = LANGUAGES.get(lang, LANGUAGES["bn"])
    target_lang = lang_info["english"]
    
    if course == "beginner":
        difficulty = "very simple, basic vocabulary"
    elif course == "intermediate":
        difficulty = "moderate, testing understanding"
    else:
        difficulty = "challenging, IELTS-level reasoning"
    
    prompt = f"""Generate 3 multiple-choice quiz questions for an English lesson.

TOPIC: {topic}
LEVEL: {course} ({difficulty})
STUDENT'S NATIVE LANGUAGE: {target_lang}

Return ONLY a valid JSON array. No explanation, no markdown fences.

FORMAT (exact):
[
  {{
    "q": "Question text in English?",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "answer": 0
  }}
]

RULES:
- Exactly 3 questions
- 4 options each
- "answer" is 0-indexed integer (0, 1, 2, or 3)
- Questions test the lesson topic
- Use simple, clear English
"""
    return prompt
