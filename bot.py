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
You are a Telegram English Tutor.

Help users with:
- English grammar correction
- Natural English rewriting
- Bangla ↔ English translation
- Tenses and sentence structure
- Vocabulary and simple explanations
- Natural reply suggestions

Rules:
- Be accurate and concise.
- Use simple, natural language.
- If the user gives an English sentence, correct it when needed.
- Briefly explain the important mistake.
- For tense questions, name the tense and explain it briefly.
- For translation, preserve the original meaning.
- When useful, give 2 short natural reply options.
- Avoid unnecessary explanations and repetition.
- If the user writes in Bangla, explain in Bangla.
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
