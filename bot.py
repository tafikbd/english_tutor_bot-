import os
import time
import telebot
from groq import Groq

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")

bot = telebot.TeleBot(TOKEN)
client = Groq(api_key=GROQ_KEY)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Hi! I am Sir English. Send me any English sentence, I will correct it!")

@bot.message_handler(func=lambda m: True)
def handle_all(message):
    # Group হলে শুধু Mention / Reply হলে উত্তর দেবে
    if message.chat.type in ['group', 'supergroup']:
        bot_name = bot.get_me().username
        text = message.text or ""
        if f"@{bot_name}" not in text:
            if not (message.reply_to_message and message.reply_to_message.from_user.id == bot.get_me().id):
                return
        text = text.replace(f"@{bot_name}", "").strip()
        if not text:
            return
    else:
        text = message.text

    if not text:
        return

    try:
        res = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are Sir English. Correct grammar and explain in short Bangla + English."},
                {"role": "user", "content": text}
            ]
        )
        reply = res.choices[0].message.content
        bot.reply_to(message, reply)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    print("Bot is running...")
    bot.remove_webhook()
    time.sleep(2)
    bot.infinity_polling(skip_pending=True)
