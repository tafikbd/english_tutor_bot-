import os
import threading
from flask import Flask
import telebot
from groq import Groq

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_API_KEY")

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_KEY)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Live!"

SYSTEM_PROMPT = "You are an English Tutor. Correct grammar and explain in Bangla + English."

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Hi! I am your English Tutor Bot. Send me any English sentence!")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
            ]
        )
        reply = response.choices[0].message.content
        bot.reply_to(message, reply)
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

def run_bot():
    print("Bot is running...")
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
