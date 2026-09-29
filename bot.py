import os
import time
import threading
from flask import Flask
import telebot
from groq import Groq

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running!"

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Hi! I am Sir English!")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    if message.chat.type in ['group', 'supergroup']:
        bot_name = bot.get_me().username
        text = message.text or ""
        if f"@{bot_name}" not in text:
            if not (message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id):
                return
        text = text.replace(f"@{bot_name}", "").strip()
        if not text: return
    else:
        text = message.text

    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":"You are Sir English teacher, explain in Bangla+English short."},{"role":"user","content":text}]
        )
        bot.reply_to(message, res.choices[0].message.content)
    except Exception as e:
        print(e)

def run_bot():
    bot.remove_webhook()
    time.sleep(2)
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
