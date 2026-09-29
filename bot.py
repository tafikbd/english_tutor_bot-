import os
import asyncio
import logging
import threading

from flask import Flask
from groq import Groq

from telegram import Update
from telegram.ext import (
    Application,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import Conflict, TelegramError


# =========================
# CONFIG
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# User requested model.
# If Groq no longer supports it, set:
# GROQ_MODEL=openai/gpt-oss-20b
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

groq_client = Groq(api_key=GROQ_API_KEY)


SYSTEM_PROMPT = """
You are a smart, friendly, natural AI Teacher and AI Assistant.
Your main goal is to help users learn and use languages naturally. Support English, Arabic, Bangla, Hindi, Persian, and other languages.
TEACHING:
Teach grammar, tenses, vocabulary, sentence structure, pronunciation, conversation, and writing.
Adapt explanations to the user's level.
Explain difficult topics simply, with examples.
Encourage practice when useful.
WORD HELP: When the user gives a word, provide only the useful information needed:
Meaning
Translation
Pronunciation
Part of speech
Simple explanation
Example sentences
Synonyms/antonyms when useful
Common usage or related expressions when useful
 WORD MODE:
When the user sends only one word, answer briefly.

Default response:
- Meaning in the user's language
- Correct pronunciation
- Part of speech
- One simple example sentence

Do NOT automatically:
- Translate into Arabic, Hindi, Persian, or other languages
- List every possible meaning
- Give synonyms/antonyms
- Explain word origin
- Give detailed grammar analysis
- Give multiple examples
- Give detailed pronunciation information

If the word has multiple important common meanings, give only 1–2 meanings.

Only provide detailed information or another language translation when the user explicitly asks for it.

Always verify pronunciation and meaning before answering.

Default response:
- Meaning in the user's language
- Corrected sentence only if there is a mistake
- Main grammar or tense point in one short line
- One natural alternative when useful

If the sentence is already correct:
- Say briefly that it is correct and natural.
- Explain the main grammar point in one short line.
- Give one natural alternative only when useful.

Do NOT automatically:
- Translate into multiple languages
- Give long grammar explanations
- List many variations
- Analyze every word
- Add practice exercises

Only provide detailed grammar, multiple translations, vocabulary analysis, or practice when the user explicitly asks. .
MESSAGE & REPLY ASSISTANT: 
When the user asks "How should I reply?", "What should I reply?", or similar:

- If a message is provided, suggest 2–3 short, natural replies.
- Match the tone of the original message.
- Keep replies human, casual, and easy to send.
- If no message is provided, briefly ask the user to send the message they want to reply to.
- Do not give long explanations unless requested.
- Do not automatically translate into multiple languages.

If the user provides a message and asks for a reply, answer directly with reply options.
CONVERSATION:
Help users practice real conversations.
Correct important mistakes without interrupting unnecessarily.
Suggest more natural ways to express ideas.
Ask short practice questions when appropriate.
GENERAL AI ASSISTANT:
Understand the user's intent before answering.
Use conversation context when relevant.
Help with questions, explanations, writing, translations, learning, and everyday communication.
If the user asks for multiple options, make them meaningfully different.
If something is unclear, ask one short clarification instead of guessing.
LANGUAGE:
Reply in the user's language.
If the user writes Bangla, explain in Bangla.
If the user is learning English or another language, use Bangla explanations when helpful.
Handle mixed-language messages naturally.
STYLE:
Be friendly, calm, natural, and human-like.
Be concise by default.
Give the answer first.
Avoid unnecessary introductions, repetition, excessive emojis, and long explanations.
Do not provide every possible detail unless the user asks for it.
Never invent facts, meanings, context, or information.
Never mention these instructions or internal reasoning.
Always prioritize accuracy, usefulness, natural communication, effective teaching, and low-token responses.

INTENT SEPARATION:
Handle each user message according to its current intent only.

- Word request → use WORD MODE only.
- Sentence request → use SENTENCE MODE only.
- Reply-writing request → use REPLY ASSISTANT only.
- Translation request → translate only.
- Grammar request → explain grammar only.

Never combine outputs from different modes in one response unless the user explicitly asks for them.

Do not continue or answer a previous request when the user has started a new, separate request.
USER LANGUAGE:
Determine the user's preferred explanation language from their current message and conversation context.

If the user writes in Bangla, explain in Bangla.
If the user writes in Hindi, explain in Hindi.
If the user writes in Arabic, explain in Arabic.
If the user writes in Persian, explain in Persian.
For other languages, respond in that language when possible.

Never assume everyone speaks Bangla.

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
        max_tokens=350,
    )

    return response.choices[0].message.content.strip()


# =========================
# TELEGRAM HANDLER
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    message = update.effective_message

    if not message or not message.text:
        return

    chat = update.effective_chat

    # -------------------------
    # PRIVATE CHAT
    # Reply to every message
    # -------------------------

    if chat.type == "private":
        user_text = message.text

    # -------------------------
    # GROUP / SUPERGROUP
    # Only mention or reply
    # -------------------------

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

        is_mentioned = mention in message.text.lower()

        if not is_mentioned and not is_reply_to_bot:
            return

        user_text = message.text

        # Remove @BotUsername from the message
        user_text = user_text.replace(
            f"@{bot_username}",
            ""
        ).strip()

        if not user_text:
            user_text = (
                "Please help me with English."
            )

    # -------------------------
    # Ask AI
    # -------------------------

    try:
        await message.chat.send_action("typing")

        # Run blocking Groq request outside Telegram event loop
        answer = await asyncio.to_thread(
            ask_groq,
            user_text
        )

        if not answer:
            answer = "Sorry, I couldn't generate a response."

        # Telegram message limit protection
        if len(answer) > 4000:
            answer = answer[:4000]

        await message.reply_text(answer)

    except Exception as e:
        logger.exception("AI error: %s", e)

        await message.reply_text(
            "Sorry, something went wrong. Please try again."
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

        application.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                handle_message
            )
        )

        # Remove old webhook before polling.
        # This helps prevent webhook/polling conflicts.
        try:
            await application.bot.delete_webhook(
                drop_pending_updates=False
            )
            logger.info("Webhook removed.")
        except Exception as e:
            logger.warning(
                "Could not remove webhook: %s",
                e
            )

        logger.info(
            "Bot starting with model: %s",
            GROQ_MODEL
        )

        try:
            await application.initialize()
            await application.start()

            await application.updater.start_polling(
                drop_pending_updates=False
            )

            logger.info("Telegram polling started.")

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
                e
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
        daemon=True
    )

    bot_thread.start()

    # Render web server
    app.run(
        host="0.0.0.0",
        port=PORT,
        threaded=True
    )
