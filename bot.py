import os
from groq import Groq
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = "You are Sir English, a friendly English Teacher from Bangladesh. Explain in Bangla + English with examples. Short and fun."

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Assalamu Alaikum! Ami Sir English. 😊\nKi shikhte chan? Grammar / Vocabulary / Spoken?")

async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text
    try:
        res = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"system","content":SYSTEM_PROMPT},{"role":"user","content":user_text}])
        await update.message.reply_text(res.choices[0].message.content)
    except Exception as e:
        await update.message.reply_text("Ektu problem hocche, abar message din.")

app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))
print("Sir English Bot Running!")
app.run_polling()
