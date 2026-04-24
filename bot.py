import os
import telebot
from groq import Groq

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "👋 Salom! Men Groq AI yordamchi. Bepul va tez. Xabar yuboring!")

@bot.message_handler(func=lambda message: True)
def handle(message):
    try:
        # Groq orqali so'rov yuborish
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Bepul va kuchli model
            messages=[
                {"role": "user", "content": message.text}
            ],
            temperature=0.7,
            max_tokens=1000
        )
        answer = response.choices[0].message.content
        bot.reply_to(message, answer)
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}")

print("✅ Groq bot ishga tushdi...")
bot.infinity_polling()