try:
    from course_content_bn import BEGINNER_BN, get_static_lesson_bn
    HAS_STATIC_BN = True
except ImportError:
    HAS_STATIC_BN = False
    BEGINNER_BN = {}
    def get_static_lesson_bn(k, d): return None
        
# courses.py
# 📚 Course Mode — Beginner / Intermediate / Advanced
# 3 courses × 30 days each

COURSE_TOTAL_DAYS = 30

COURSE_DATA = {
    # ================================================================
    # 🟢 BEGINNER COURSE
    # ================================================================
    "beginner": {
        "name_bn": "🟢 Beginner Course",
        "name_en": "🟢 Beginner Course",
        "name_hi": "🟢 Beginner Course",
        "name_ru": "🟢 Начальный курс",
        "desc_bn": "একদম শূন্য থেকে — ৩০ দিনে দৈনন্দিন ইংরেজি",
        "desc_en": "Start from zero — daily English in 30 days",
        "desc_hi": "शून्य से शुरू — 30 दिनों में रोज़मर्रा की अंग्रेज़ी",
        "desc_ru": "С нуля — разговорный английский за 30 дней",
        "days": {
            1:  {"t": "Greetings", "tb": "শুভেচ্ছা",
                 "v": ["hello", "hi", "good morning", "good night", "goodbye"],
                 "g": "Hi, I'm ___"},
            2:  {"t": "Self Introduction", "tb": "নিজের পরিচয়",
                 "v": ["name", "live", "city", "country", "student"],
                 "g": "My name is..."},
            3:  {"t": "Yes/No Questions", "tb": "হ্যাঁ/না প্রশ্ন",
                 "v": ["yes", "no", "please", "thanks", "sorry"],
                 "g": "Are you ___?"},
            4:  {"t": "Numbers 1-100", "tb": "সংখ্যা ১-১০০",
                 "v": ["one", "ten", "twenty", "fifty", "hundred"],
                 "g": "How old are you?"},
            5:  {"t": "Review Day 1-4", "tb": "পুনরাবৃত্তি ১-৪",
                 "v": [], "g": "Review"},
            6:  {"t": "Time & Days", "tb": "সময় ও দিন",
                 "v": ["Monday", "Sunday", "morning", "hour", "clock"],
                 "g": "What time is it?"},
            7:  {"t": "Food & Drinks", "tb": "খাবার ও পানীয়",
                 "v": ["rice", "water", "tea", "bread", "fruit"],
                 "g": "I like ___"},
            8:  {"t": "At Home", "tb": "বাড়িতে",
                 "v": ["room", "kitchen", "bed", "door", "table"],
                 "g": "There is / There are"},
            9:  {"t": "Daily Routine", "tb": "দৈনন্দিন রুটিন",
                 "v": ["wake up", "breakfast", "work", "sleep", "evening"],
                 "g": "Present Simple"},
            10: {"t": "Review Day 6-9", "tb": "পুনরাবৃত্তি ৬-৯",
                 "v": [], "g": "Review"},
            11: {"t": "Shopping", "tb": "শপিং",
                 "v": ["money", "price", "cheap", "expensive", "buy"],
                 "g": "How much?"},
            12: {"t": "At the Market", "tb": "বাজারে",
                 "v": ["seller", "buyer", "fresh", "kilo", "packet"],
                 "g": "I want to buy..."},
            13: {"t": "Directions", "tb": "পথনির্দেশ",
                 "v": ["left", "right", "straight", "near", "far"],
                 "g": "Where is ___?"},
            14: {"t": "Transport", "tb": "যাতায়াত",
                 "v": ["bus", "train", "ticket", "station", "stop"],
                 "g": "How do I get to?"},
            15: {"t": "Review Day 11-14", "tb": "পুনরাবৃত্তি ১১-১৪",
                 "v": [], "g": "Review"},
            16: {"t": "Describing People", "tb": "মানুষের বর্ণনা",
                 "v": ["tall", "short", "young", "old", "kind"],
                 "g": "He is a ___ man"},
            17: {"t": "Emotions", "tb": "আবেগ",
                 "v": ["happy", "sad", "angry", "tired", "excited"],
                 "g": "I feel ___"},
            18: {"t": "Hobbies", "tb": "শখ",
                 "v": ["reading", "cooking", "singing", "drawing", "playing"],
                 "g": "I enjoy ___"},
            19: {"t": "Likes & Dislikes", "tb": "পছন্দ/অপছন্দ",
                 "v": ["love", "like", "hate", "prefer", "enjoy"],
                 "g": "I don't like ___"},
            20: {"t": "Review Day 16-19", "tb": "পুনরাবৃত্তি ১৬-১৯",
                 "v": [], "g": "Review"},
            21: {"t": "At the Doctor", "tb": "ডাক্তারের কাছে",
                 "v": ["sick", "medicine", "pain", "fever", "doctor"],
                 "g": "I have a ___"},
            22: {"t": "Phone Calls", "tb": "ফোন কল",
                 "v": ["call", "number", "message", "ring", "answer"],
                 "g": "Can I speak to?"},
            23: {"t": "Emergency", "tb": "আপদকালীন",
                 "v": ["help", "danger", "police", "hospital", "urgent"],
                 "g": "I need help!"},
            24: {"t": "At the Bank", "tb": "ব্যাংকে",
                 "v": ["account", "cash", "send", "deposit", "withdraw"],
                 "g": "I want to ___"},
            25: {"t": "Review Day 21-24", "tb": "পুনরাবৃত্তি ২১-২৪",
                 "v": [], "g": "Review"},
            26: {"t": "Small Talk", "tb": "হালকা আলাপ",
                 "v": ["weather", "weekend", "busy", "fine", "nice"],
                 "g": "How's it going?"},
            27: {"t": "Storytelling", "tb": "গল্প বলা",
                 "v": ["yesterday", "ago", "story", "first", "then"],
                 "g": "Past Simple"},
            28: {"t": "Making Plans", "tb": "পরিকল্পনা",
                 "v": ["plan", "meeting", "tomorrow", "together", "ready"],
                 "g": "Let's ___"},
            29: {"t": "Full Conversation", "tb": "পূর্ণ কথোপকথন",
                 "v": ["conversation", "practice", "review", "speak", "listen"],
                 "g": "All tenses review"},
            30: {"t": "FINAL TEST", "tb": "চূড়ান্ত পরীক্ষা",
                 "v": [], "g": "Final Test"},
        }
    },

    # ================================================================
    # 🟡 INTERMEDIATE COURSE
    # ================================================================
    "intermediate": {
        "name_bn": "🟡 Intermediate Course",
        "name_en": "🟡 Intermediate Course",
        "name_hi": "🟡 Intermediate Course",
        "name_ru": "🟡 Средний курс",
        "desc_bn": "বেসিক জানেন — এখন Fluency-র দিকে এগিয়ে যান",
        "desc_en": "You know basics — move toward fluency",
        "desc_hi": "बेसिक आता है — अब fluency की ओर",
        "desc_ru": "Знаете основы — двигаемся к беглости",
        "days": {
            1:  {"t": "Past Simple", "tb": "Past Simple",
                 "v": ["yesterday", "last week", "ago", "went", "saw"],
                 "g": "Regular & irregular verbs"},
            2:  {"t": "Present Perfect", "tb": "Present Perfect",
                 "v": ["already", "just", "yet", "ever", "never"],
                 "g": "have/has + V3"},
            3:  {"t": "Past Continuous", "tb": "Past Continuous",
                 "v": ["while", "when", "was doing", "were going", "suddenly"],
                 "g": "was/were + V-ing"},
            4:  {"t": "Future Forms", "tb": "ভবিষ্যৎ কাল",
                 "v": ["will", "going to", "plan", "intend", "hope"],
                 "g": "will vs going to"},
            5:  {"t": "Review Day 1-4", "tb": "পুনরাবৃত্তি ১-৪",
                 "v": [], "g": "Review"},
            6:  {"t": "Professional Emails", "tb": "পেশাদার ইমেইল",
                 "v": ["regards", "sincerely", "attach", "forward", "cc"],
                 "g": "Formal email structure"},
            7:  {"t": "Meeting Vocabulary", "tb": "মিটিং শব্দ",
                 "v": ["agenda", "minutes", "consensus", "deadline", "proposal"],
                 "g": "Business tone"},
            8:  {"t": "Presentations", "tb": "উপস্থাপনা",
                 "v": ["firstly", "furthermore", "in conclusion", "highlight", "demonstrate"],
                 "g": "Signposting language"},
            9:  {"t": "Business Phone Calls", "tb": "ব্যবসায়িক ফোন",
                 "v": ["hold on", "put through", "callback", "available", "convenient"],
                 "g": "Polite requests"},
            10: {"t": "Review Day 6-9", "tb": "পুনরাবৃত্তি ৬-৯",
                 "v": [], "g": "Review"},
            11: {"t": "Daily Phrasal Verbs", "tb": "দৈনন্দিন Phrasal Verbs",
                 "v": ["get up", "put on", "turn off", "wake up", "look after"],
                 "g": "Phrasal verbs in context"},
            12: {"t": "Work Phrasal Verbs", "tb": "কাজের Phrasal Verbs",
                 "v": ["look for", "give up", "take over", "carry on", "fill in"],
                 "g": "Work-related phrasal verbs"},
            13: {"t": "Common Idioms", "tb": "সাধারণ Idioms",
                 "v": ["piece of cake", "hit the sack", "under the weather",
                       "break the ice", "once in a blue moon"],
                 "g": "Idiomatic expressions"},
            14: {"t": "Business Idioms", "tb": "ব্যবসায়িক Idioms",
                 "v": ["on the same page", "cut corners", "think outside the box",
                       "get the ball rolling", "in the loop"],
                 "g": "Office idioms"},
            15: {"t": "Review Day 11-14", "tb": "পুনরাবৃত্তি ১১-১৪",
                 "v": [], "g": "Review"},
            16: {"t": "Expressing Opinions", "tb": "মত প্রকাশ",
                 "v": ["I think", "in my opinion", "from my perspective",
                       "I believe", "as far as I know"],
                 "g": "Opinion phrases"},
            17: {"t": "Agree & Disagree", "tb": "একমত/ভিন্নমত",
                 "v": ["absolutely", "I see your point", "I'm afraid",
                       "I beg to differ", "fair enough"],
                 "g": "Polite disagreement"},
            18: {"t": "Storytelling", "tb": "গল্প বলা",
                 "v": ["once", "suddenly", "in the end", "meanwhile", "eventually"],
                 "g": "Narrative tenses"},
            19: {"t": "Making Requests", "tb": "অনুরোধ",
                 "v": ["could you", "would you mind", "do you think",
                       "I was wondering", "if possible"],
                 "g": "Polite requests"},
            20: {"t": "Review Day 16-19", "tb": "পুনরাবৃত্তি ১৬-১৯",
                 "v": [], "g": "Review"},
            21: {"t": "Email Writing", "tb": "ইমেইল লেখা",
                 "v": ["subject", "attachment", "response", "query", "appreciate"],
                 "g": "Formal vs informal"},
            22: {"t": "Report Writing", "tb": "রিপোর্ট লেখা",
                 "v": ["findings", "suggest", "recommend", "regarding", "purpose"],
                 "g": "Report structure"},
            23: {"t": "Complaint Letter", "tb": "অভিযোগ পত্র",
                 "v": ["dissatisfied", "disappointed", "refund", "resolve", "prompt"],
                 "g": "Formal complaint"},
            24: {"t": "Short Essay", "tb": "ছোট রচনা",
                 "v": ["introduction", "body", "conclusion", "moreover", "however"],
                 "g": "Essay structure"},
            25: {"t": "Review Day 21-24", "tb": "পুনরাবৃত্তি ২১-২৪",
                 "v": [], "g": "Review"},
            26: {"t": "Interview Practice", "tb": "ইন্টারভিউ",
                 "v": ["experience", "strength", "weakness", "challenge", "opportunity"],
                 "g": "Interview answers"},
            27: {"t": "Group Discussion", "tb": "গ্রুপ আলোচনা",
                 "v": ["point", "agree", "add", "raise", "support"],
                 "g": "Discussion phrases"},
            28: {"t": "Problem Solving", "tb": "সমস্যা সমাধান",
                 "v": ["issue", "approach", "solution", "alternative", "solve"],
                 "g": "Problem-solving language"},
            29: {"t": "Long Conversation", "tb": "দীর্ঘ কথোপকথন",
                 "v": ["actually", "basically", "however", "anyway", "by the way"],
                 "g": "Connectors"},
            30: {"t": "FINAL TEST", "tb": "চূড়ান্ত পরীক্ষা",
                 "v": [], "g": "Final Test"},
        }
    },

    # ================================================================
    # 🔴 ADVANCED COURSE
    # ================================================================
    "advanced": {
        "name_bn": "🔴 Advanced Course",
        "name_en": "🔴 Advanced Course",
        "name_hi": "🔴 Advanced Course",
        "name_ru": "🔴 Продвинутый курс",
        "desc_bn": "ফ্লুয়েন্সি ও IELTS/BCS লেভেল ইংরেজি",
        "desc_en": "Fluency + IELTS/BCS level English",
        "desc_hi": "Fluency और IELTS/BCS level",
        "desc_ru": "Беглость + уровень IELTS/BCS",
        "days": {
            1:  {"t": "Conditionals", "tb": "Conditionals",
                 "v": ["if", "would", "had", "unless", "provided"],
                 "g": "Zero, 1st, 2nd, 3rd conditionals"},
            2:  {"t": "Passive Voice", "tb": "Passive Voice",
                 "v": ["be + V3", "by", "was built", "is being", "has been"],
                 "g": "All tenses passive"},
            3:  {"t": "Reported Speech", "tb": "Reported Speech",
                 "v": ["said", "told", "claimed", "according to", "reported"],
                 "g": "Direct to indirect"},
            4:  {"t": "Subjunctive", "tb": "Subjunctive",
                 "v": ["suggest that", "insist that", "recommend that",
                       "demand that", "wish"],
                 "g": "Subjunctive after verbs"},
            5:  {"t": "Review Day 1-4", "tb": "পুনরাবৃত্তি ১-৪",
                 "v": [], "g": "Review"},
            6:  {"t": "Academic Vocabulary", "tb": "একাডেমিক শব্দ",
                 "v": ["hypothesis", "analysis", "significant",
                       "correlation", "framework"],
                 "g": "Academic tone"},
            7:  {"t": "Report Writing", "tb": "রিপোর্ট লেখা",
                 "v": ["consequently", "furthermore", "in contrast",
                       "on the basis", "it appears"],
                 "g": "Formal connectors"},
            8:  {"t": "Formal Register", "tb": "আনুষ্ঠানিক ভাষা",
                 "v": ["hence", "thereby", "notwithstanding", "pursuant", "herein"],
                 "g": "Register switching"},
            9:  {"t": "Data Description", "tb": "ডেটা বর্ণনা",
                 "v": ["plummet", "surge", "fluctuate", "plateau", "peak"],
                 "g": "Describing graphs"},
            10: {"t": "Review Day 6-9", "tb": "পুনরাবৃত্তি ৬-৯",
                 "v": [], "g": "Review"},
            11: {"t": "IELTS Part 1", "tb": "IELTS Part 1",
                 "v": ["hometown", "hobby", "work", "study", "typically"],
                 "g": "Extended answers"},
            12: {"t": "IELTS Part 2", "tb": "IELTS Part 2",
                 "v": ["describe", "experience", "memorable", "vividly", "notably"],
                 "g": "2-minute speech"},
            13: {"t": "IELTS Part 3", "tb": "IELTS Part 3",
                 "v": ["analyse", "compare", "argue", "justify", "speculate"],
                 "g": "Abstract discussion"},
            14: {"t": "Full Mock Test", "tb": "সম্পূর্ণ মক টেস্ট",
                 "v": ["fluency", "coherence", "lexical", "grammar", "pronunciation"],
                 "g": "Full IELTS practice"},
            15: {"t": "Review Day 11-14", "tb": "পুনরাবৃত্তি ১১-১৪",
                 "v": [], "g": "Review"},
            16: {"t": "Advanced Idioms", "tb": "Advanced Idioms",
                 "v": ["bite the bullet", "burn the midnight oil",
                       "cut to the chase", "hit the nail", "piece of mind"],
                 "g": "Idiom usage"},
            17: {"t": "Cultural References", "tb": "সাংস্কৃতিক রেফারেন্স",
                 "v": ["white lie", "red tape", "blue moon",
                       "green light", "black sheep"],
                 "g": "Color idioms"},
            18: {"t": "Humor & Sarcasm", "tb": "হাস্যরস",
                 "v": ["irony", "sarcasm", "tongue-in-cheek", "deadpan", "pun"],
                 "g": "Tone & nuance"},
            19: {"t": "Collocations", "tb": "Collocations",
                 "v": ["make a decision", "take a risk", "pay attention",
                       "draw a conclusion", "raise concern"],
                 "g": "Word pairs"},
            20: {"t": "Review Day 16-19", "tb": "পুনরাবৃত্তি ১৬-১৯",
                 "v": [], "g": "Review"},
            21: {"t": "Debate Techniques", "tb": "ডিবেট কৌশল",
                 "v": ["concede", "rebut", "contend",
                       "substantiate", "counter-argument"],
                 "g": "Argument structure"},
            22: {"t": "Public Speaking", "tb": "পাবলিক স্পিকিং",
                 "v": ["audience", "engage", "deliver", "pace", "emphasize"],
                 "g": "Speaking techniques"},
            23: {"t": "Negotiation", "tb": "আলোচনা",
                 "v": ["leverage", "concede", "compromise",
                       "walk away", "bottom line"],
                 "g": "Negotiation language"},
            24: {"t": "Leadership English", "tb": "নেতৃত্বের ইংরেজি",
                 "v": ["delegate", "empower", "envision", "align", "execute"],
                 "g": "Leadership vocabulary"},
            25: {"t": "Review Day 21-24", "tb": "পুনরাবৃত্তি ২১-২৪",
                 "v": [], "g": "Review"},
            26: {"t": "Complex Sentences", "tb": "জটিল বাক্য",
                 "v": ["although", "whereas", "not only",
                       "despite", "inasmuch as"],
                 "g": "Complex structures"},
            27: {"t": "Nuance & Tone", "tb": "সূক্ষ্ম ভাব",
                 "v": ["subtle", "implying", "suggesting",
                       "conveying", "undertone"],
                 "g": "Reading between lines"},
            28: {"t": "Advanced Conversation", "tb": "উন্নত কথোপকথন",
                 "v": ["elaborate", "clarify", "anecdote",
                       "integrate", "coherent"],
                 "g": "Extended discourse"},
            29: {"t": "Final Review", "tb": "চূড়ান্ত রিভিউ",
                 "v": ["review", "summarize", "recall", "master", "fluent"],
                 "g": "Comprehensive review"},
            30: {"t": "FINAL TEST", "tb": "চূড়ান্ত পরীক্ষা",
                 "v": [], "g": "Final Test"},
        }
    }
}


# ================================================================
# HELPERS
# ================================================================
def get_course_name(course_key, lang):
    c = COURSE_DATA.get(course_key, {})
    return c.get(f"name_{lang}") or c.get("name_en") or course_key


def get_course_desc(course_key, lang):
    c = COURSE_DATA.get(course_key, {})
    return c.get(f"desc_{lang}") or c.get("desc_en") or ""


def get_day_info(course_key, day):
    return COURSE_DATA.get(course_key, {}).get("days", {}).get(day)


def get_topic_display(course_key, day, lang):
    d = get_day_info(course_key, day)
    if not d:
        return "—"
    if lang == "bn" and d.get("tb"):
        return f"{d['t']} ({d['tb']})"
    return d["t"]


LANG_NAMES = {
    "bn": "Bangla (Bengali script)",
    "en": "English",
    "hi": "Hindi (Devanagari script)",
    "ru": "Russian (Cyrillic script)",
}
def build_lesson_prompt(course, day, lang="bn"):
    topic = get_topic_display(course, day, lang)
    course_name = get_course_name(course, lang)
    return f"""You are an English teacher creating a lesson for a {course_name} student.

📅 Course: {course_name}
📅 Day: {day}
📌 Topic: {topic}

CRITICAL INSTRUCTION: Follow this EXACT structure. NEVER skip any section.

📅 DAY {day} — {topic}

━━━━━━━━━━━━━━━━━
🔤 VOCABULARY
━━━━━━━━━━━━━━━━━
Give 5 English words related to the topic. For each word show:
1️⃣ word  /pronunciation/
   📖 অর্থ: Bangla meaning
   ✏️ Example sentence in English.
   🇧🇩 Bangla translation of the example.

━━━━━━━━━━━━━━━━━
📝 GRAMMAR
━━━━━━━━━━━━━━━━━
Give 1 grammar rule related to the topic with:
🎯 নিয়ম: [Explanation in Bangla]
   [English structure]
✏️ Example 1 in English.
🇧🇩 Bangla translation.
✏️ Example 2 in English.
🇧🇩 Bangla translation.

━━━━━━━━━━━━━━━━━
💬 USEFUL PHRASES
━━━━━━━━━━━━━━━━━
Give 4-5 useful phrases related to the topic with Bangla meanings.
Format: • English phrase — Bangla meaning

━━━━━━━━━━━━━━━━━
🎭 DIALOGUE
━━━━━━━━━━━━━━━━━
Write a 4-line conversation between A and B related to the topic.
Format:
A: English sentence.
🇧🇩 Bangla translation.

B: English sentence.
🇧🇩 Bangla translation.

A: English sentence.
🇧🇩 Bangla translation.

B: English sentence.
🇧🇩 Bangla translation.

━━━━━━━━━━━━━━━━━
✍️ PRACTICE (say aloud)
━━━━━━━━━━━━━━━━━
Give 3 practice sentences in English with Bangla translations.
Format:
1. English sentence.
   🇧🇩 Bangla translation.

2. English sentence.
   🇧🇩 Bangla translation.

3. English sentence.
   🇧🇩 Bangla translation.

RULES:
- Reply in Bengali + English mix.
- ALWAYS include ALL 5 sections above (Vocabulary, Grammar, Phrases, Dialogue, Practice).
- Use plain text with emojis only. Never use markdown like asterisks or bold.
- Use Bangla script for translations.
- Keep it clear and educational.
"""

    vocab_str = ", ".join(vocab)

    return (
        f"You are an expert English teacher. Teach Day {day}/30 of {course_name}.\n\n"
        f"Topic: {topic}\n"
        f"Grammar focus: {grammar}\n"
        f"5 vocabulary words: {vocab_str}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"CRITICAL LANGUAGE RULES:\n"
        f"1. Student's language = {user_lang}.\n"
        f"2. ALL explanations in {user_lang}.\n"
        f"3. English words STAY in English, but meaning is in {user_lang}.\n"
        f"4. Every English sentence must have {user_lang} translation below.\n"
        f"5. Use {user_lang} script (Bangla letters if Bangla, Devanagari if Hindi, Cyrillic if Russian).\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"FORMAT (follow EXACTLY):\n\n"
        f"DAY {day} — {topic}\n\n"
        f"1. VOCABULARY:\n"
        f"• [english_word] / [pronunciation] — [meaning in {user_lang}]\n"
        f"  Example: [English example sentence]\n"
        f"  Translation: [Translation in {user_lang}]\n"
        f"(Do this for all 5 words)\n\n"
        f"2. GRAMMAR:\n"
        f"• [Rule explained in {user_lang}]\n"
        f"• [English example 1] — [{user_lang} translation]\n"
        f"• [English example 2] — [{user_lang} translation]\n\n"
        f"3. PHRASES (4):\n"
        f"• [English phrase] — [meaning in {user_lang}]\n\n"
        f"4. DIALOGUE:\n"
        f"A: [English line]\n"
        f"   [{user_lang} translation]\n"
        f"B: [English line]\n"
        f"   [{user_lang} translation]\n"
        f"A: [English line]\n"
        f"   [{user_lang} translation]\n"
        f"B: [English line]\n"
        f"   [{user_lang} translation]\n\n"
        f"5. PRACTICE (3 sentences):\n"
        f"• [English sentence] — [{user_lang} translation]\n\n"
        f"RULES: Plain text + emojis. NO markdown (*, **, #). Under 1800 chars."
    )


def build_quiz_prompt(course_key, day, lang):
    """Quiz prompt: question in user's language, options in English."""
    d = get_day_info(course_key, day)
    if not d:
        return None

    topic = d["t"]
    vocab = ", ".join(d.get("v", [])) or topic
    user_lang = LANG_NAMES.get(lang, "English")

    return (
        f"Create 3 multiple-choice questions for Day {day} of an English course.\n\n"
        f"Topic: {topic}\n"
        f"Vocabulary: {vocab}\n"
        f"Student's language: {user_lang}\n\n"
        f"LANGUAGE RULES:\n"
        f"1. The question ('q') must be in {user_lang}.\n"
        f"2. The 4 options MUST be English words/phrases (from the vocabulary).\n"
        f"3. The correct answer is the right English word.\n\n"
        f"Return ONLY a JSON array. No markdown. No explanation.\n"
        f"Format:\n"
        f'[{{"q":"[question in {user_lang}]","options":["English1","English2","English3","English4"],"answer":0}},...]\n\n'
        f"RULES:\n"
        f"- Exactly 3 questions\n"
        f"- 4 options each (English)\n"
        f"- 'answer' = index 0-3 of correct option\n"
        f"- Questions in {user_lang}"
    )
