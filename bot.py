import os
import threading
from flask import Flask
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters
from groq import Groq

# Flask for Render Port
app = Flask('')
@app.route('/')
def home(): return "Bot is Running!"

# Groq Client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

def start(update, context):
    update.message.reply_text("Hi! I am your English Tutor Bot. Send me any English sentence!")

def handle_message(update, context):
    user_text = update.message.text
    try:
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a friendly English tutor. Correct the user's English and teach them."},
                {"role": "user", "content": user_text}
            ],
            model="openai/gpt-oss-20b",
        )
        reply = chat_completion.choices[0].message.content
        update.message.reply_text(reply)
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def main():
    TOKEN = os.environ.get("TELEGRAM_TOKEN")
    # Start Flask in background
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=10000)).start()

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
