import os
import telebot
from groq import Groq
import sqlite3
import threading
import time
from datetime import datetime
import io
from PIL import Image, ImageFilter, ImageEnhance
import whisper
import tempfile
import subprocess

BOT_TOKEN = os.environ["BOT_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

bot = telebot.TeleBot(BOT_TOKEN)
client = Groq(api_key=GROQ_API_KEY)

# Whisper modelini yuklash (ovozni matnga aylantirish uchun)
whisper_model = whisper.load_model("base")

# -------------------- DATABASE --------------------
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS reminders
                 (id INTEGER PRIMARY KEY, user_id TEXT, text TEXT, time TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS contacts
                 (id INTEGER PRIMARY KEY, user_id TEXT, contact_name TEXT, contact_id TEXT)''')
    conn.commit()
    conn.close()

init_db()

# -------------------- OVOZNI MATNGA AYLANTIRISH --------------------
@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    try:
        # Ovozli xabarni yuklab olish
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Vaqtinchalik faylga saqlash
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as temp_ogg:
            temp_ogg.write(downloaded_file)
            temp_ogg_path = temp_ogg.name
        
        # OGG ni WAV ga aylantirish (FFmpeg kerak)
        temp_wav_path = temp_ogg_path.replace(".ogg", ".wav")
        subprocess.run(["ffmpeg", "-i", temp_ogg_path, "-acodec", "pcm_s16le", "-ar", "16000", temp_wav_path, "-y"], check=True)
        
        # Whisper orqali matnga aylantirish
        result = whisper_model.transcribe(temp_wav_path, language="uz")
        transcribed_text = result["text"]
        
        # Tozalash
        os.unlink(temp_ogg_path)
        os.unlink(temp_wav_path)
        
        bot.reply_to(message, f"🎤 *Siz aytdingiz:*\n_{transcribed_text}_\n\nAI javobi tayyorlanmoqda...", parse_mode="Markdown")
        
        # Groq orqali AI javob
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": transcribed_text}]
        )
        answer = response.choices[0].message.content
        bot.send_message(message.chat.id, f"🤖 *Javob:*\n{answer}", parse_mode="Markdown")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}\n\n⚠️ FFmpeg o'rnatilmagan bo'lishi mumkin. Administratorga murojaat qiling.")

# -------------------- RASM TAHRIRLASH --------------------
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        # Rasmni yuklab olish
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # PIL Image ga o'zgartirish
        image = Image.open(io.BytesIO(downloaded_file))
        
        # Tahrirlash opsiyalarini ko'rsatish
        markup = telebot.types.InlineKeyboardMarkup(row_width=2)
        filters = [
            ("⚫ Grayscale", "gray"), ("🔍 Sharpen", "sharpen"),
            ("🌀 Blur", "blur"), ("🎨 Sepia", "sepia"),
            ("⬛ Contour", "contour"), ("Em 👁️ Emboss", "emboss"),
            ("🌞 Brightness (+)", "bright_up"), ("🌙 Brightness (-)", "bright_down")
        ]
        for name, callback in filters:
            markup.add(telebot.types.InlineKeyboardButton(name, callback_data=f"edit_{callback}"))
        markup.add(telebot.types.InlineKeyboardButton("❌ Bekor qilish", callback_data="edit_cancel"))
        
        # Rasmni va tahrirlash tugmalarini yuborish
        bio = io.BytesIO()
        image.save(bio, format="PNG")
        bio.seek(0)
        bot.send_photo(message.chat.id, bio, caption="🖼️ Rasmni tahrirlash uchun tugmani bosing:", reply_markup=markup)
        
        # Rasmni vaqtincha saqlash
        bot.user_data = getattr(bot, 'user_data', {})
        bot.user_data[message.chat.id] = image
        
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_"))
def edit_image_callback(call):
    action = call.data.replace("edit_", "")
    image = bot.user_data.get(call.message.chat.id)
    
    if not image:
        bot.answer_callback_query(call.id, "Rasm topilmadi!")
        return
    
    edited_image = image.copy()
    
    if action == "gray":
        edited_image = edited_image.convert("L")
    elif action == "sharpen":
        edited_image = edited_image.filter(ImageFilter.SHARPEN)
    elif action == "blur":
        edited_image = edited_image.filter(ImageFilter.BLUR)
    elif action == "sepia":
        sepia_filter = (0.393, 0.769, 0.189, 0, 0.349, 0.686, 0.168, 0, 0.272, 0.534, 0.131, 0)
        edited_image = edited_image.convert("RGB")
        width, height = edited_image.size
        pixels = edited_image.load()
        for x in range(width):
            for y in range(height):
                r, g, b = pixels[x, y]
                new_r = min(255, int(r * 0.393 + g * 0.769 + b * 0.189))
                new_g = min(255, int(r * 0.349 + g * 0.686 + b * 0.168))
                new_b = min(255, int(r * 0.272 + g * 0.534 + b * 0.131))
                pixels[x, y] = (new_r, new_g, new_b)
    elif action == "contour":
        edited_image = edited_image.filter(ImageFilter.CONTOUR)
    elif action == "emboss":
        edited_image = edited_image.filter(ImageFilter.EMBOSS)
    elif action == "bright_up":
        enhancer = ImageEnhance.Brightness(edited_image)
        edited_image = enhancer.enhance(1.5)
    elif action == "bright_down":
        enhancer = ImageEnhance.Brightness(edited_image)
        edited_image = enhancer.enhance(0.5)
    elif action == "cancel":
        bot.edit_message_caption(call.message.chat.id, call.message.message_id, caption="❌ Tahrirlash bekor qilindi.")
        bot.answer_callback_query(call.id)
        return
    
    # Tahrirlangan rasmni yuborish
    bio = io.BytesIO()
    edited_image.save(bio, format="PNG")
    bio.seek(0)
    bot.send_photo(call.message.chat.id, bio, caption="✅ Tahrirlangan rasm!")
    bot.answer_callback_query(call.id)

# -------------------- ESLATMALAR --------------------
@bot.message_handler(commands=['eslatma'])
def set_reminder(message):
    try:
        komanda = message.text.split(' ', 2)
        if len(komanda) < 3:
            bot.reply_to(message, "❌ Ishlatish: /eslatma 14:30 Eslatma matni")
            return
        
        vaqt = komanda[1]
        eslatma_matni = komanda[2]
        
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("INSERT INTO reminders (user_id, text, time) VALUES (?, ?, ?)",
                  (str(message.chat.id), eslatma_matni, vaqt))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Eslatma qo'shildi! ⏰ {vaqt} da eslataman: {eslatma_matni}")
        
        threading.Thread(target=check_reminders, args=(message.chat.id,), daemon=True).start()
        
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}")

def check_reminders(chat_id):
    while True:
        now = datetime.now().strftime("%H:%M")
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("SELECT text, time, id FROM reminders WHERE user_id = ?", (str(chat_id),))
        reminders = c.fetchall()
        
        for eslatma in reminders:
            if eslatma[1] == now:
                bot.send_message(chat_id, f"⏰ Eslatma: {eslatma[0]}")
                c.execute("DELETE FROM reminders WHERE id = ?", (eslatma[2],))
                conn.commit()
        conn.close()
        time.sleep(60)

# -------------------- KONTAKTLAR --------------------
@bot.message_handler(commands=['contact'])
def save_contact(message):
    try:
        komanda = message.text.split(' ', 2)
        if len(komanda) < 3:
            bot.reply_to(message, "❌ Ishlatish: /contact Ism @username")
            return
        
        ism = komanda[1]
        username = komanda[2].replace('@', '')
        
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("INSERT INTO contacts (user_id, contact_name, contact_id) VALUES (?, ?, ?)",
                  (str(message.chat.id), ism, username))
        conn.commit()
        conn.close()
        
        bot.reply_to(message, f"✅ Kontakt saqlandi: {ism} → @{username}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}")

@bot.message_handler(commands=['contacts'])
def list_contacts(message):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute("SELECT contact_name, contact_id FROM contacts WHERE user_id = ?", (str(message.chat.id),))
    contacts = c.fetchall()
    conn.close()
    
    if not contacts:
        bot.reply_to(message, "📭 Hali kontakt saqlamagansiz. /contact yordamida saqlang")
        return
    
    javob = "📋 Sizning kontaktlaringiz:\n"
    for ism, username in contacts:
        javob += f"• {ism} → @{username}\n"
    bot.reply_to(message, javob)

@bot.message_handler(commands=['xabar'])
def send_to_contact(message):
    try:
        komanda = message.text.split(' ', 2)
        if len(komanda) < 3:
            bot.reply_to(message, "❌ Ishlatish: /xabar Ism Xabar matni")
            return
        
        ism = komanda[1]
        xabar_matni = komanda[2]
        
        conn = sqlite3.connect('bot_data.db')
        c = conn.cursor()
        c.execute("SELECT contact_id FROM contacts WHERE user_id = ? AND contact_name = ?",
                  (str(message.chat.id), ism))
        result = c.fetchone()
        conn.close()
        
        if not result:
            bot.reply_to(message, f"❌ '{ism}' degan kontakt topilmadi.")
            return
        
        username = result[0]
        bot.send_message(message.chat.id, f"📤 Xabar @{username} ga yuborilmoqda...")
        bot.send_message(username, f"📩 Sizga {message.from_user.first_name} dan xabar:\n\n{xabar_matni}")
        bot.send_message(message.chat.id, "✅ Xabar yuborildi!")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Xatolik: {e}")

# -------------------- AI SUHBAT + START --------------------
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, """👋 Salom! Men AI yordamchi. Quyidagi buyruqlar mavjud:

📌 *Asosiy:*
/start - Botni qayta ishga tushirish

⏰ *Eslatmalar:*
/eslatma 14:30 Matn - Eslatma qo'shish

👥 *Kontaktlar:*
/contact Ism @username - Kontakt saqlash
/contacts - Kontaktlar ro'yxati
/xabar Ism Matn - Kontaktga xabar yuborish

🎨 *Rasm tahrirlash:*
Rasm yuboring -> Tahrirlash tugmalari chiqadi

🎤 *Ovozli xabarlar:*
Ovozli xabar yuboring -> Matnga aylanadi + AI javob

💬 *Boshqa har qanday matn* -> AI orqali javob beradi""", parse_mode="Markdown")

@bot.message_handler(func=lambda message: True)
def ai_response(message):
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": message.text}]
        )
        bot.reply_to(message, response.choices[0].message.content)
    except Exception as e:
        bot.reply_to(message, f"❌ AI xatolik: {e}")

print("✅ Bot ishga tushdi (Rasm tahrirlash + Ovozli xabarlar + AI)...")
bot.infinity_polling()
