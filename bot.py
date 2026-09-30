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
from telegram.error import Conflict, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)


# ==========================================================
# CONFIG
# ==========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

GROQ_MODEL = os.getenv(
    "GROQ_MODEL",
    "openai/gpt-oss-120b",
)

PORT = int(os.getenv("PORT", "10000"))


if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is missing."
    )

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY environment variable is missing."
    )


# ==========================================================
# LOGGING
# ==========================================================

logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ==========================================================
# GROQ
# ==========================================================

groq_client = Groq(
    api_key=GROQ_API_KEY
)


# ==========================================================
# SYSTEM PROMPT
# ==========================================================

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
- Vocabulary
- Translation
- Grammar
- Tenses
- Pronunciation
- Speaking
- Writing
- Sentence correction
- Reply/message writing
- General questions
- Study help
- Practice
- Conversation

Follow the current intent and do not unnecessarily combine unrelated tasks.

ADAPTIVE LEVEL:
Beginner:
- Simple words
- Short explanations
- Clear examples

Intermediate:
- Deeper explanations when useful
- Natural usage and important differences

Advanced:
- Nuance, register, collocations, and exceptions when relevant

VOCABULARY:
When explaining a word, normally provide:
- Meaning
- Pronunciation
- Part of speech
- One simple example

Only add synonyms, antonyms, collocations, or extra meanings when useful
or requested.

LANGUAGE ACCURACY:
- Give accurate meanings, pronunciation, grammar labels, and examples.
- Do not invent dictionary meanings.
- For Arabic, use accurate standard Arabic pronunciation and meanings.
- Distinguish multiple common meanings by context.
- Do not give an antonym unless a genuine antonym exists.
- Do not mix languages inside labels unnecessarily.

TRANSLATION:
- Preserve the original meaning.
- Prefer natural real-life language over word-for-word translation.
- Keep the original tone unless the user asks for another tone.
- If the user asks only for translation, give the translation directly.

GRAMMAR:
When useful:
Rule
-> Simple explanation
-> Example
-> Common mistake
-> Correct version

Do not invent grammar rules.

TENSES:
Explain usage, structure, examples, signal words, and common mistakes
when relevant. Do not make unnecessary absolute rules.

PRONUNCIATION:
Give accurate pronunciation.
Use IPA when useful.
Mention stress or syllables when helpful.

SENTENCE CORRECTION:
Correct genuine grammar, vocabulary, punctuation, or naturalness problems.
Do not invent mistakes.
Preserve the user's intended meaning.
If already correct, say so.

SPEAKING:
Keep conversations natural.
Ask useful follow-up questions when appropriate.
Correct only important mistakes unless the user asks for full correction.

WRITING:
Follow the user's requested length, tone, format, audience, and purpose.
Preserve the user's intended meaning.

MESSAGE / REPLY WRITING:
When asked what to reply:
- Understand the original message.
- Match its tone and context.
- Give natural replies.
- Options may be simple, friendly, casual, mature, polite, warm,
  playful, or professional.

GENERAL ASSISTANT:
You can help with general knowledge, science, history, geography,
technology, mathematics, study planning, writing, communication,
productivity, and explanations.

ACCURACY:
Never invent facts, dates, quotations, meanings, or grammar rules.
If uncertain, clearly say that you are not fully certain.

RESPONSE LENGTH:
Be concise by default.
Simple questions -> short answers.
Complex questions -> structured answers.
If the user asks for detailed or step-by-step help, provide more detail.

NATURAL COMMUNICATION:
Avoid repetitive AI phrases such as:
"Certainly!"
"Of course!"
"Here is a comprehensive answer..."

Do not pretend to have real-world experiences or actions.

CONTEXT:
Use relevant recent conversation context.
If the user changes topic, switch naturally.

CLARIFICATION:
Ask only one short clarification when genuinely necessary.
If a reasonable interpretation is obvious, proceed.

PRIVACY:
Never ask for passwords, OTPs, private keys, banking credentials,
payment credentials, national ID numbers, or unnecessary sensitive data.

SAFETY:
Do not meaningfully facilitate serious violence, illegal wrongdoing,
malicious hacking, fraud, sexual exploitation, dangerous activities,
or other harmful conduct.

TELEGRAM:
The Telegram bot code controls commands, buttons, menus, and callbacks.
Do not claim that a Telegram command exists unless it is implemented.

MAIN GOAL:
Make learning easier, communication more natural, and everyday tasks simpler.

Be smart.
Be natural.
Be accurate.
Be concise.
Be patient.
Be useful.
Focus on what the user is asking NOW.
"""


# ==========================================================
# AI FUNCTION
# ==========================================================

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


# ==========================================================
# FLASK
# ==========================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "Telegram English Tutor Bot is running."


@app.route("/health")
def health():
    return "OK"


# ==========================================================
# STUDENT MENU
# ==========================================================

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


# ==========================================================
# START / MENU
# ==========================================================

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

    await start_command(
        update,
        context,
    )


# ==========================================================
# STUDENT PROMPTS
# ==========================================================

STUDENT_PROMPTS = {

    "student_learn": (
        "Start a short English lesson for a beginner or intermediate "
        "student. Choose one useful topic. Explain it simply, give "
        "one or two examples, then give ONE short practice question. "
        "Do not give the answer immediately."
    ),

    "student_vocab": (
        "Teach ONE useful English word. Give its meaning, pronunciation, "
        "part of speech, and one simple example. Then give ONE short "
        "practice question. Do NOT show the answer."
    ),

    "student_grammar": (
        "Teach ONE useful English grammar point. Explain its use and "
        "structure simply, give examples, mention one common mistake, "
        "then give ONE short practice question. Do NOT show the answer."
    ),

    "student_tenses": (
        "Start a short English tense lesson. Choose ONE useful tense. "
        "Explain its use and structure simply, give examples, mention "
        "one common mistake if useful, then give ONE short practice "
        "question. Do not give the answer immediately."
    ),

    "student_speaking": (
        "Start English speaking practice. Ask the student ONE simple "
        "real-life question and wait for their answer. Keep the "
        "conversation natural. Correct only important mistakes."
    ),

    "student_writing": (
        "Start English writing practice. Give the student ONE short "
        "writing task suitable for their level and wait for their answer. "
        "After they answer, correct important mistakes briefly."
    ),
}


# ==========================================================
# STUDENT MENU CALLBACK
# ==========================================================

async def student_menu_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    query = update.callback_query

    if not query:
        return

    await query.answer()

    prompt = STUDENT_PROMPTS.get(
        query.data
    )

    if not prompt:
        return

    try:

        if query.message:
            await query.message.chat.send_action(
                "typing"
            )

        answer = await asyncio.to_thread(
            ask_groq,
            prompt,
        )

        if not answer:
            answer = (
                "Sorry, I couldn't generate a response."
            )

        if len(answer) > 4000:
            answer = answer[:4000]

        if query.message:
            await query.message.reply_text(
                answer
            )

    except Exception as e:

        logger.exception(
            "Student menu error: %s",
            e,
        )

        if query.message:
            await query.message.reply_text(
                "Sorry, something went wrong. Please try again."
            )


# ==========================================================
# COMMAND AI HELPER
# ==========================================================

async def run_command_ai(
    update: Update,
    prompt: str,
):

    message = update.effective_message

    if not message:
        return

    try:

        await message.chat.send_action(
            "typing"
        )

        answer = await asyncio.to_thread(
            ask_groq,
            prompt,
        )

        if not answer:
            answer = (
                "Sorry, I couldn't generate a response."
            )

        if len(answer) > 4000:
            answer = answer[:4000]

        await message.reply_text(
            answer
        )

    except Exception as e:

        logger.exception(
            "Command AI error: %s",
            e,
        )

        await message.reply_text(
            "Sorry, something went wrong. Please try again."
        )


# ==========================================================
# BASIC COMMANDS
# ==========================================================

async def vocab_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await run_command_ai(
        update,
        (
            "Start vocabulary learning. Teach ONE useful English word "
            "with meaning, pronunciation, part of speech, one example, "
            "and ONE short practice question. Do not show the answer."
        ),
    )


async def grammar_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    await run_command_ai(
        update,
        (
            "Start grammar learning. Teach ONE useful English grammar "
            "point simply, give examples, mention one common mistake, "
            "and give ONE short practice question. Do not show the answer."
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
            "question and wait for the student's answer. Keep it natural "
            "and correct only important mistakes."
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
            "writing task suitable for their level and wait for their answer."
        ),
    )


# ==========================================================
# TEXT MESSAGE HANDLER
# ==========================================================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message

    if not message:
        return

    if not message.text:
        return

    chat = update.effective_chat

    if not chat:
        return

    # ------------------------------------------------------
    # PRIVATE CHAT
    # ------------------------------------------------------

    if chat.type == "private":

        user_text = message.text.strip()

        if not user_text:
            return

    # ------------------------------------------------------
    # GROUP / SUPERGROUP
    # ------------------------------------------------------

    else:

        bot_username = context.bot.username

        if not bot_username:
            return

        is_reply_to_bot = (
            message.reply_to_message is not None
            and message.reply_to_message.from_user is not None
            and message.reply_to_message.from_user.id
            == context.bot.id
        )

        mention = f"@{bot_username.lower()}"

        is_mentioned = (
            mention in message.text.lower()
        )

        if not is_mentioned and not is_reply_to_bot:
            return

        user_text = message.text

        user_text = user_text.replace(
            f"@{bot_username}",
            "",
        ).strip()

        if not user_text:
            user_text = (
                "Please help me with English."
            )

    # ------------------------------------------------------
    # AI RESPONSE
    # ------------------------------------------------------

    try:

        await message.chat.send_action(
            "typing"
        )

        answer = await asyncio.to_thread(
            ask_groq,
            user_text,
        )

        if not answer:
            answer = (
                "Sorry, I couldn't generate a response."
            )

        if len(answer) > 4000:
            answer = answer[:4000]

        await message.reply_text(
            answer
        )

    except Exception as e:

        logger.exception(
            "AI message error: %s",
            e,
        )

        await message.reply_text(
            "Sorry, something went wrong. Please try again."
        )


# ==========================================================
# TELEGRAM BOT
# ==========================================================

def run_bot():

    async def start_bot():

        application = (
            Application.builder()
            .token(BOT_TOKEN)
            .build()
        )

        # --------------------------------------------------
        # COMMANDS
        # --------------------------------------------------

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

        # --------------------------------------------------
        # INLINE BUTTONS
        # --------------------------------------------------

        application.add_handler(
            CallbackQueryHandler(
                student_menu_callback,
            )
        )

        # --------------------------------------------------
        # NORMAL TEXT
        # --------------------------------------------------

        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                handle_message,
            )
        )

        try:

            await application.initialize()

            # Remove any old webhook before polling.
            await application.bot.delete_webhook(
                drop_pending_updates=False
            )

            logger.info(
                "Webhook removed."
            )

            await application.start()

            await application.updater.start_polling(
                drop_pending_updates=False
            )

            logger.info(
                "Telegram polling started successfully."
            )

            logger.info(
                "Bot username: @%s",
                (await application.bot.get_me()).username,
            )

            logger.info(
                "Using Groq model: %s",
                GROQ_MODEL,
            )

            # Keep Telegram bot alive.
            while True:
                await asyncio.sleep(3600)

        except Conflict:

            logger.error(
                "409 Conflict: another instance of this bot "
                "is already running."
            )

        except TelegramError as e:

            logger.exception(
                "Telegram error: %s",
                e,
            )

        except Exception as e:

            logger.exception(
                "Unexpected bot error: %s",
                e,
            )

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

    asyncio.run(
        start_bot()
    )


# ==========================================================
# MAIN
# ==========================================================

if __name__ == "__main__":

    logger.info(
        "Starting EduMate AI..."
    )

    bot_thread = threading.Thread(
        target=run_bot,
        daemon=True,
    )

    bot_thread.start()

    logger.info(
        "Telegram bot thread started."
    )

    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True,
    )
