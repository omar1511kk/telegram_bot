import os
import difflib
import unicodedata
import sqlite3
from datetime import datetime
from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)

# ---------------------------
# 📦 قاعدة بيانات المستخدمين
# ---------------------------
DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            country TEXT,
            timezone TEXT
        )
    """)
    conn.commit()
    conn.close()

# ---------------------------
# 🔤 تطبيع النص (إزالة التشكيل والهمزات)
# ---------------------------
def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

# ---------------------------
# 📚 قاعدة بيانات الكتب
# ---------------------------
FILES = {
    "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf",
    "القواعد الأربعة محمد بن عبد الوهاب": "files/القواعد_الأربعة_محمد_بن_عبد_الوهاب.pdf",
    "شروط الصلاة، وأركانها، وواجباتها.": "files/شروط_الصلاة_وأركانها_وواجباتها.pdf",
    "كتاب التوحيد محمد بن عبد الوهاب.": "files/كتاب_التوحيد_محمد_بن_عبد_الوهاب.pdf",
    "محمد بن عبد الوهاب ثلاثة الأصول وأدلتها.": "files/محمد_بن_عبد_الوهاب_ثلاثة_الأصول_وأدلتها.pdf",
    "نواقض الإسلام": "files/نواقض_الاسلام.pdf",
    "خلاصة تعظيم العلم صالح العصيمي": "files/خلاصة_تعظيم_العلم_صالح_العصيمي.pdf"
}

# ---------------------------
# ⏳ حماية من السبام
# ---------------------------
last_message_time = {}

def is_spam(user_id):
    now = datetime.now()
    last_time = last_message_time.get(user_id)
    if last_time and (now - last_time).total_seconds() < 5:
        return True
    last_message_time[user_id] = now
    return False

# ---------------------------
# 🔍 البحث الذكي
# ---------------------------
def smart_search(query):
    norm_query = normalize(query)
    norm_titles = {normalize(title): title for title in FILES}
    
    exact_matches = [original for norm, original in norm_titles.items() if norm_query in norm]
    if exact_matches:
        return exact_matches[0]
    
    close_matches = difflib.get_close_matches(norm_query, norm_titles.keys(), n=1, cutoff=0.5)
    return norm_titles[close_matches[0]] if close_matches else None

# ---------------------------
# 📥 استقبال الرسائل والرد بالكتب
# ---------------------------
async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_spam(user_id):
        await update.message.reply_text("⌛ الرجاء الانتظار بضع ثوانٍ قبل إرسال رسالة جديدة.")
        return
    
    query = update.message.text
    match = smart_search(query)

    if match:
        file_path = FILES[match]
        await update.message.reply_text(f"📘 تم العثور على: {match}")
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب. تأكد من كتابة الاسم بشكل صحيح.")

# ---------------------------
# ✅ أمر /start
# ---------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_spam(user_id):
        await update.message.reply_text("⌛ الرجاء الانتظار بضع ثوانٍ قبل استخدام الأمر مرة أخرى.")
        return

    username = update.effective_user.first_name or "أخي الكريم"

    # ✅ تسجيل المستخدم في قاعدة البيانات
    language_code = update.effective_user.language_code or "unknown"
    country_code = language_code.split("-")[-1] if "-" in language_code else language_code
    timezone = "UTC"  # يمكن لاحقًا تحديثه حسب الدولة المختارة

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO users (user_id, username, country, timezone)
        VALUES (?, ?, ?, ?)
    """, (user_id, username, country_code, timezone))
    conn.commit()
    conn.close()

    print(f"✅ تم حفظ المستخدم: {user_id}, الاسم: {username}, الدولة: {country_code}, اللغة: {language_code}")

    keyboard = [[InlineKeyboardButton("📚 عرض الكتب", callback_data="show_books")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"السلام عليكم ورحمة الله وبركاته، {username} 🌿\n"
        "قال رسول الله ﷺ:\n"
        "«من صلى عليَّ صلاة، صلى الله عليه بها عشرًا» (رواه مسلم)\n\n"
        "🌟 لا تحرم نفسك من هذا الأجر، صلِّ على النبي ﷺ.\n\n"
        "✍ أرسل اسم الكتاب للحصول على نسخة PDF، أو اضغط على الزر أدناه لعرض جميع الكتب ⬇",
        reply_markup=reply_markup
    )

# ---------------------------
# 📖 أمر /books لعرض الكتب
# ---------------------------
async def list_books(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_spam(user_id):
        await update.message.reply_text("⌛ الرجاء الانتظار قبل استخدام الأمر مرة أخرى.")
        return

    books = "\n".join([f"{i+1}⃣ {title}" for i, title in enumerate(FILES.keys())])
    await update.message.reply_text(f"📚 الكتب المتوفرة:\n\n{books}\n\n✍ أرسل اسم الكتاب كما هو أو قريبًا منه.")

# ---------------------------
# 🔘 عند الضغط على زر "📚 عرض الكتب"
# ---------------------------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    if is_spam(user_id):
        await query.answer("⌛ الرجاء الانتظار قبل إعادة الضغط.", show_alert=True)
        return

    await query.answer()

    if query.data == "show_books":
        books = "\n".join([f"{i+1}⃣ {title}" for i, title in enumerate(FILES.keys())])
        await query.edit_message_text(f"📚 الكتب المتوفرة:\n\n{books}\n\n✍ أرسل اسم الكتاب كما هو أو قريبًا منه.")

# ---------------------------
# 🛠 إعداد التطبيق
# ---------------------------
TOKEN = os.getenv("BOT_TOKEN")
application = Application.builder().token(TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("books", list_books))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# ---------------------------
# 🌐 Webhook
# ---------------------------
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

async def on_startup(app):
    webhook_url = os.getenv("WEBHOOK_URL")
    await application.bot.set_webhook(webhook_url)
    await application.initialize()
    await application.start()
    init_db()  # 🧱 تهيئة قاعدة البيانات

web_app = web.Application()
web_app.router.add_post("/webhook", handle_webhook)
web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(web_app, port=8000)