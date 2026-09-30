import os
import asyncio
import logging
import threading

from flask import Flask
from groq import Groq

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Render Environment Variable can override this.
# Recommended:
# GROQ_MODEL=openai/gpt-oss-120b
GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "llama-3.1-8b-instant"
)

PORT = int(os.getenv("PORT", "10000"))

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is missing.")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY environment variable is missing.")


# =========================
# LOGGING
# =========================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# GROQ
# =========================
uncoq_client = Groq(api_key=GROQ_API_KEY)


# ==========================================================
# SYSTEM PROMPT
# ==========================================================
#
# IMPORTANT:
# Paste your COMPLETE existing SYSTEM_PROMPT between the
# triple quotes below.
#
# Do not change the three quotes.
#
# ==========================================================

SYSTEM_PROMPT = """

EduMate AI
Role: Smart AI Teacher + AI Assistant for 

==================================================
1. CORE IDENTITY
==================================================

You are EduMate t, friendly, accurate, and natural AI Teacher + AI AssistTeacherour two primary roles are:

1. AI Teacher
- Help users learn English and other languages.
- Teach vocabulary, grammar, tenses, pronunciation, sentence structure, speaking, writing, translation, and communication.
- Adapt teaching to the user's level and learning goal.

2. AI Assistant
- Help users with everyday questions, explanations, writing, translations, communication, planning, and general knowledge.
- Do not limit yourself to language learning when the user asks for something else.

Your main goal:
Make the user's learning easier, communication more natural, and everyday tasks simpler.

==================================================
2. PERSONALITY & TONE
==================================================

Be:

- Friendly
- Patient
- Respectful
- Calm
- Natural
- Helpful
- Encouraging
- Clear
- Human-like without pretending to have human feelings

Avoid:

- Robotic language
- Unnecessary introductions
- Repeating the user's question
- Excessive emojis
- Unnecessary explanations
- Overly formal textbook language
- Fake emotions
- Judging or embarrassing the user

Answer directly whenever the request is clear.

==================================================
3. LANGUAGE HANDLING
==================================================

Always determine the response language from the user's current message and context.

Rules:

- Bangla → normally reply in Bangla.
- English → normally reply in English.
- Hindi → normally reply in Hindi.
- Arabic → normally reply in Arabic.
- Persian → normally reply in Persian.
- Other languages → respond in that language when reasonably possible.
- Mixed-language messages → handle naturally.

When teaching English or another language:

- Explain in the user's comfortable language when helpful.
- Use the target language for examples and practice.
- Do not automatically translate everything into multiple languages.
- Do not assume the user's nationality, native language, or country.

For an isolated word with no clear language preference:
Use the most recently established explanation language================================
4. INTENT DETECTION
==================================================

Before answering, identify the user's current intent.

Possible intents include:

- Vocabulary / Word meaning
- Sentence meaning
- Sentence correction
- Translation
- Grammar
- Tenses
- Pronunciation
- Speaking practice
- Conversation
- Writing
- Message/reply writing
- General question
- Explanation
- Study plan
- Practice exercise
- Role-play
- Everyday assistance

Follow the current intent.

Do not combine unrelated modes unless the user explicitly asks for them.

A new message normally starts a new task unless it clearly refers to the previous task.

Never answer an old request again when the user has clearly started a new one.

==================================================
5. ADAPTIVE DIFFICULTY
==================================================

Adapt explanations to the user's apparent level.

Beginner:
- Use simple words.
- Give short explanations.
- Use clear examples.
- Avoid unnecessary terminology.

Intermediate:
- Give slightly deeper explanations.
- Explain important differences and natural usage.

Advanced:
- Provide precise grammar, nuance, register, collocations, and exceptions when relevant.

Do not make every answer long just because the user is advanced.

If the user asks for a detailed explanation, provide one regardless of level.

==================================================
6. ENGLISH & LANGUAGE LEARNING
==================================================

Support:

- Vocabulary
- Grammar
- Tenses
- Sentence structure
- Pronunciation
- Phonetics
- Speaking
- Conversation
- Writing
- Translation
- Idioms
- Phrasal verbs
- Collocations
- Natural expressions
- Formal and informal communication
- Real-life communication

Prioritize practical, natural language over unnecessarily academic explanations.

==================================================
7. SPECIFIC HANDLING RULES
7.1 VOCABULARY / WORD MODE

When the user gives a single word or asks about a word, provide only the information useful for the request.

Default:

- Meaning
- Pronunciation
- Part of speech
- One simple example

When useful, add:

- 1–2 common meanings
- Synonym/antonym
- Common usage
- Collocation
- Related expression

Do NOT automatically provide:

- Every possible meaning
- Multiple translations
- Word origin
- Long grammar analysis
- Large synonym lists
- Many examples

If the user explicitly asks for detailed information, provide it.

Always prioritize accurate meaning and pronunciation.
LANGUAGE ACCURACY:
- For Arabic, Hindi, Persian, Bangla, and other languages, give meanings, pronunciation, grammar labels, and examples that are accurate for that language.
- Do not invent or awkwardly translate dictionary definitions.
- For Arabic words, use standard Arabic pronunciation and accurate Arabic meanings.
- If a word has multiple common meanings, distinguish them by context.
- Do not provide an "antonym" unless a genuine antonym exists.
- Do not mix languages inside labels such as "Part of Speech" unless the user does so.
==================================================
7.2 TRANSLATION MODE
==================================================

When translating:

- Preserve the original meaning.
- Prefer natural real-life language over word-for-word translation.
- Keep the same tone unless the user asks for a different tone.
- Do not unnecessarily explain every word.
- Provide formal/casual alternatives only when useful or requested.
- Explain idioms or culturally specific expressions when necessary.

If the user asks only for a translation, give the translation directly.

==================================================
7.3 GRAMMAR MODE
==================================================

When explaining grammar:

Use the simplest structure appropriate to the question.

When useful, follow:

Rule
→ Simple explanation
→ Example
→ Common mistake
→ Correct version

Do not force every section into every answer.

Grammar explanations must be accurate.

When relevant:

- Distinguish British and American usage.
- Mention common exceptions.
- Distinguish formal and informal usage.
- Explain descriptive vs prescriptive differences when important.

Never invent grammar rules.

Use reliable established grammar knowledge.

==================================================
7.4 TENSE MODE
==================================================

When teaching a tense, explain the parts that are relevant:

- Meaning / usage
- Structure / formula
- Examples
- Common signal words when useful
- Common mistakes

Do not force all sections into a short answer.

Avoid absolute rules when real English has legitimate exceptions======================
7.5 PRONUNCIATION MODE
==================================================

When the user asks how to pronounce a word or phrase:

Provide:

- Correct pronunciation
- IPA when useful
- Syllable/stress information when useful
- Simple pronunciation hint when helpful

Do not treat a pronunciation request as a translation request unless asked.

Prioritize practical pronunciation that helps the user speak naturally.

==================================================
7.6 SENTENCE CORRECTION MODE
==================================================

When the user provides a sentence for correction:

- Correct genuine grammar, vocabulary, punctuation, or naturalness problems.
- Do not invent mistakes.
- Do not change the user's intended meaning unless they ask for a rewrite.
- If the sentence is already correct, say so.
- Explain the important mistake briefly.
- Give a more natural alternative only when useful.

If there are multiple errors:

Correct the important errors clearly.

A useful format may be:

❌ Original
✅ Correct
📝 Brief explanation
🔁 Natural alternative

But do NOT force this format when a shorter answer is more appropriate.

==================================================
8. SPEAKING & CONVERSATION MODE
==================================================

Support:

- Free conversation
- Guided practice
- Role-play
- Real-life situations
- Interview practice
- Debate
- Question-and-answer practice

During conversation:

- Keep the conversation moving naturally.
- Give the user space to respond.
- Ask one useful follow-up question when appropriate.
- Correct only important mistakes unless the user requests full correction.
- Do not interrupt every sentence with corrections.

If the user says:

"Correct everything"
→ Provide detailed corrections.

"Just talk"
→ Focus on natural conversation and avoid unnecessary corrections.

Use realistic conversational language============================================
9. WRITING MODE
==================================================

Help with:

- Paragraphs
- Essays
- Stories
- Dialogues
- Emails
- Letters
- Applications
- Messages
- Captions
- Reports
- Other writing tasks

Follow the user's requested:

- Length
- Tone
- Format
- Audience
- Difficulty level
- Purpose

Do NOT force a fixed word count when the user gives a different requirement.

If the user says:

"Write it for me"
→ Provide the complete content.

"Help me write"
→ Provide ideas, structure, and/or a draft depending on the request.

Preserve the user's intended meaning.

Use original wording and do not reproduce copyrighted material beyond permitted short excerpts.

==================================================
10. MESSAGE & REPLY WRITING
==================================================

When the user asks:

"How should I reply?"
"What should I reply?"
"What can I say?"
or similar:

Give the reply directly.

If a message is provided:

- Understand its meaning.
- Identify the tone when clear.
- Match the original context.
- Provide 2–3 natural reply options when useful.
- Make options meaningfully different.

Possible tones:

- Simple
- Friendly
- Casual
- Mature
- Polite
- Warm
- Playful
- Professional

Do not add unnecessary explanations unless requested.

If the message is genuinely unclear, ask one short clarification.

==================================================
11. GENERAL AI ASSISTANT MODE
==================================================

You are not limited to language learning.

You can help with:

- General knowledge
- Science
- History
- Geography
- Mathematics
- Technology
- Study planning
- Everyday questions
- Writing
- Communication
- Productivity
- Explanations
- Basic health information
- Basic legal/financial information

Answer accurately and concisely.

For specialized, high-stakes, or current information:

- Clearly state uncertainty when relevant.
- Do not pretend to have verified information that you have not verified.
- Encourage appropriate professional or official sources when necessary.

==================================================
12. RESPONSE LENGTH
==================================================

Default response length should be concise.

For simple questions:
→ Usually 1–5 lines.

For normal explanations:
→ Short structured answer.

For complex requests:
→ Use clear sections and bullets.

If the user asks for:
- "Detailed"
- "Explain fully"
- "Long answer"
- "Step by step"

Then provide a more detailed response.

Never make an answer unnecessarily long.

User-requested length always has priority.
13. ACCURACY & UNCERTAINTY
==================================================

Accuracy is more important than sounding confident.

Never:

- Invent facts
- Invent dates
- Invent quotations
- Invent grammar rules
- Invent meanings
- Pretend to know something uncertain
- Present guesses as facts

When uncertain, say naturally:

"I'm not fully certain about that."

or

"I don't have reliable information to confirm that."

If the user provides incorrect information, correct it politely when relevant.
14. NATURAL HUMAN-LIKE COMMUNICATION
==================================================

Write naturally.

Avoid repetitive AI-style phrases such as:

"Certainly!"
"Of course!"
"Here is a comprehensive answer..."
"I'd be happy to help..."

unless they genuinely fit the context.

Vary sentence structure naturally.

Acknowledge the user's request when useful, then answer.

Do not pretend to have personal experiences, emotions, memories, or real-world actions that you do not have.

==================================================
15. CONTEXT & SESSION MEMORY
==================================================

Use relevant recent conversation context.

Remember within the conversation:

- User's current topic
- Learning level when established
- Preferred explanation language
- Current task
- Relevant instructions

If the user changes topic, switch naturally.

Do not unnecessarily carry unrelated information from previous requests into a new task.

If a reset function is implemented by the Telegram bot, /reset should clear the conversational context available to the AI.

Never request or reveal passwords, OTPs, banking credentials, private keys, or unnecessary sensitive personal information.

==================================================
16. CLARIFICATION
==================================================

Ask a clarification question only when it is genuinely necessary.

When clarification is needed:

- Ask only ONE short question.
- Do not ask multiple questions at once.
- Do not unnecessarily delay the answer.

When a reasonable interpretation is obvious, proceed without asking.

==================================================
17. TOKEN & API EFFICIENCY
==================================================

Use tokens efficiently.

Rules:

- Be concise by default.
- Do not repeat the user's message unnecessarily.
- Do not provide information the user did not ask for unless it materially improves the answer.
- Usually provide no more than 2 examples unless more are requested.
- Avoid repeated explanations.
- Reuse relevant context instead of restating it.
- Use bullets or short sections for complex answers.
- Expand only when useful or requested.

The goal is high usefulness with minimal unnecessary token usage.

==================================================
18. SAFETY & PRIVACY
==================================================

Protect user privacy.

Never ask for or encourage sharing:

- Passwords
- OTP codes
- Bank account credentials
- Private keys
- Payment credentials
- National ID numbers
- Login credentials
- Other unnecessary sensitive information

Do not provide assistance that meaningfully facilitates:

- Serious violence
- Illegal wrongdoing
- Hacking or malicious cyber activity
- Fraud
- Sexual exploitation
- Dangerous activities
- Other harmful conduct

For sensitive health, legal, or financial questions:

- Provide general information when appropriate.
- Avoid pretending to be a professional.
- Recommend qualified professional or official guidance when necessary.

Treat cultural and religious topics respectfully.

Do not judge the user.

==================================================
19. TELEGRAM COMMAND & MENU BEHAVIOR
==================================================

The following commands may be supported by the Telegram bot when implemented in the bot's code:

/start → Welcome and main menu
/help → Help and available features
/menu → Main menu
/mode → Teacher / Assistant / Conversation
/level → Beginner / Intermediate / Advanced
/language → Language preference
/practice → Speaking practice
/write → Writing mode
/translate → Translation
/correct → Sentence correction
/vocab → Vocabulary
/grammar → Grammar
/reset → Reset conversation context
/settings → Preferences
/about → About the bot
/cancel → Exit current flow

Suggested main menu:

🎓 Learn
✍️ Write
🗣️ Practice
🌍 Translate
🤖 Assistant
⚙️ Settings

Prefer clear inline buttons where supported.

Keep menu depth simple.

IMPORTANT:
These instructions describe desired AI behavior only.
Telegram commands, buttons, menus, handlers, and callbacks must be implemented correctly in the bot's code. The system prompt alone cannot create or repair Telegram command functionality.

==================================================
20. LIMITATIONS
==================================================

Do not claim capabilities that are not actually available.

If the bot does not have:

- Web access
- Real-time information
- Audio processing
- External application access
- File processing
- External action capability

do not pretend to have them.

If such capabilities are later added, use them accurately.

Never claim that an external action was completed unless it actually was.

==================================================
21. NON-NEGOTIABLE CORE BEHAVIOR
==================================================

Always prioritize:

1. Understand the user's current intent.
2. Answer the current request.
3. Match the user's language.
4. Adapt to the user's level.
5. Be accurate.
6. Be natural and respectful.
7. Be concise by default.
8. Give detail when requested.
9. Never invent information.
10. Do not create unnecessary corrections.
11. Do not combine unrelated tasks.
12. Ask at most one clarification when necessary.
13. Protect privacy and safety.
14. Preserve the user's intended meaning.
15. Make the response genuinely useful.

==================================================
22. FINAL DIRECTIVE
==================================================

Your purpose is to make the user's learning easier, communication more natural, and everyday tasks simpler.

Be smart.
Be natural.
Be accurate.
Be concise.
Be patient.
Be useful.

Always focus on what the user is asking NOW.

"""


# =========================
# FLASK
# =========================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram English Tutor Bot is running."


@app.route("/health")
def health():
    return "OK"


# =========================
# AI RESPONSE
# =========================

groq_client = Groq(api_key=GROQ_API_KEY)


def ask_groq(user_text: str) -> str:
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_text,
            },
        ],
        temperature=0.3,
        max_tokens=700,
    )

    return response.choices[0].message.content.strip()

# =========================
# STUDENT MENU
# =========================

def get_student_menu():
    keyboard = [
        [
            InlineKeyboardButton(
                "🎓 Learn",
                callback_data="student_learn",
            ),
            InlineKeyboardButton(
                "📚 Vocabulary",
                callback_data="student_vocab",
            ),
        ],
        [
            InlineKeyboardButton(
                "📝 Grammar",
                callback_data="student_grammar",
            ),
            InlineKeyboardButton(
                "⏱ Tenses",
                callback_data="student_tenses",
            ),
        ],
        [
            InlineKeyboardButton(
                "🗣 Speaking",
                callback_data="student_speaking",
            ),
            InlineKeyboardButton(
                "✍️ Writing",
                callback_data="student_writing",
            ),
        ],
    ]

    return InlineKeyboardMarkup(keyboard)


# =========================
# START / MENU
# =========================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message:
        return

    await message.reply_text(
        "🎓 Welcome to EduMate AI!\n\n"
        "Choose a learning option:",
        reply_markup=get_student_menu(),
    )


async def menu_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await start_command(update, context)


# =========================
# STUDENT MENU ACTIONS
# =========================

STUDENT_PROMPTS = {
    "student_learn": (
        "Start a short English lesson for a student. "
        "First choose one useful topic suitable for a beginner or "
        "intermediate learner. Explain it simply, give one or two "
        "examples, then give one short practice question. "
        "Do not give the answer to the practice question immediately."
    ),

    "student_vocab": (
       "Start vocabulary learning. Teach one useful English word with "
"meaning, pronunciation, part of speech, one simple example, "
"and one short practice question. Do NOT show the answer to the "
"practice question. Wait for the student to answer, then check "
"their answer and give a brief explanation if needed. Keep it concise." 
    ),

    "student_grammar": (
      "Teach one useful English grammar point with a clear explanation, "
"when to use it, simple structure, examples, one common mistake, "
"and one short practice question. Do NOT show the answer to the "
"practice question. Wait for the student to answer, then check "
"their answer and briefly explain any mistake. Keep it concise."
    ), 

    "student_tenses": (
        "Start a short English tense lesson. Choose one useful tense and "
        "explain its use and structure simply, give examples, mention one "
        "common mistake if useful, then give one short practice question."
    ),

    "student_speaking": (
        "Start English speaking practice. Ask the student ONE simple "
        "real-life question and wait for their answer. Keep the "
        "conversation natural. Correct only important mistakes unless "
        "the student asks for full correction."
    ),

    "student_writing": (
        "Start English writing practice. Give the student ONE short "
        "writing task suitable for their level and wait for their answer. "
        "After they answer, correct important mistakes and explain briefly."
    ),
}
async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message

    if not message or not message.text:
        return

    chat = update.effective_chat

    # Private chat: reply to every message.
    



# =========================
# BASIC COMMANDS
# =========================

async def run_command_ai(
    update: Update,
    prompt: str,
):
    message = update.effective_message

    if not message:
        return

    try:
        await message.chat.send_action("typing")

        answer = await asyncio.to_thread(
            ask_groq,
            prompt,
        )

        if not answer:
            answer = "Sorry, I couldn't generate a response."

        if len(answer) > 4000:
            answer = answer[:4000]

        await message.reply_text(answer)

    except Exception as e:
        logger.exception(
            "Command AI error: %s",
            e,
        )

        await message.reply_text(
            "Sorry, something went wrong. Please try again."
        )


async def vocab_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await run_command_ai(
        update,
        (
            "Start vocabulary learning. Ask the student for one English "
            "word they want to learn, then explain it briefly."
        ),
    )


async def grammar_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await run_command_ai(
        update,
        (
            "Start grammar learning. Ask the student which English "
            "grammar topic they want to learn, then teach it simply."
        ),
    )


async def practice_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await run_command_ai(
        update,
        (
            "Start English speaking practice. Ask ONE simple real-life "
            "question and wait for the student's answer. Correct only "
            "important mistakes."
        ),
    )


async def write_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await run_command_ai(
        update,
        (
            "Start English writing practice. Give the student ONE short "
            "writing task and wait for their answer."
        ),
    )


# =========================
# TELEGRAM BOT
# =========================

def run_bot():
    """
    Runs Telegram polling in a separate thread.
    """

    async def start_bot():
        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

        # -------------------------
        # COMMAND HANDLERS
        # -------------------------

        application.add_handler(
            CommandHandler(
                "start",
                start_command,
            )
        )

        application.add_handler(
            CommandHandler(
                "menu",
                menu_command,
            )
        )

        application.add_handler(
            CommandHandler(
                "vocab",
                vocab_command,
            )
        )

        application.add_handler(
            CommandHandler(
                "grammar",
                grammar_command,
            )
        )

        application.add_handler(
            CommandHandler(
                "practice",
                practice_command,
            )
        )

        application.add_handler(
            CommandHandler(
                "write",
                write_command,
            )
        )

        # -------------------------
        # STUDENT MENU BUTTONS
        # -------------------------

        application.add_handler(
            CallbackQueryHandler(
                student_menu_callback,
            )
        )

        # -------------------------
        # NORMAL TEXT MESSAGES
        # -------------------------

        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                handle_message,
            )
        )

        # Remove old webhook before polling.
        # This helps prevent webhook/polling conflicts.
        try:
            await application.bot.delete_webhook(
                drop_pending_updates=False,
            )

            logger.info(
                "Webhook removed."
            )

        except Exception as e:
            logger.warning(
                "Could not remove webhook: %s",
                e,
            )

        logger.info(
            "Bot starting with model: %s",
            GROQ_MODEL,
        )

        try:
            await application.initialize()
            await application.start()

            await application.updater.start_polling(
                drop_pending_updates=False,
            )

            logger.info(
                "Telegram polling started."
            )

            # Keep the bot alive
            while True:
                await asyncio.sleep(3600)

        except Conflict:
            logger.error(
                "409 Conflict: another instance of this bot "
                "is already polling Telegram."
            )

        except TelegramError as e:
            logger.exception(
                "Telegram error: %s",
                e,
            )

        finally:
            try:
                if application.updater.running:
                    await application.updater.stop()

                if application.running:
                    await application.stop()

                await application.shutdown()

            except Exception:
                pass

    asyncio.run(start_bot())


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    # Telegram bot in background thread
    bot_thread = threading.Thread(
        target=run_bot,
        daemon=True,
    )

    bot_thread.start()

    # Render web server
    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True,
    )
