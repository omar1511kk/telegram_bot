import os
import difflib
import unicodedata
import time
import sqlite3
from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ✅ إعدادات عامة
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = 5650658004  # 👑 معرّف الأدمن

# ✅ قاعدة بيانات المستخدمين
def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            country TEXT
        )
    """)
    conn.commit()
    conn.close()

# ✅ قاعدة بيانات الكتب
FILES = {
    "ابن تيمية": {
        "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf"
    },
    "محمد بن عبد الوهاب": {
        "القواعد الأربعة": "files/القواعد_الأربعة_محمد_بن_عبد_الوهاب.pdf",
        "ثلاثة الأصول وأدلتها": "files/محمد_بن_عبد_الوهاب_ثلاثة_الأصول_وأدلتها.pdf",
        "كتاب التوحيد": "files/كتاب_التوحيد_محمد_بن_عبد_الوهاب.pdf",
        "نواقض الإسلام": "files/نواقض_الاسلام.pdf"
    },
    "ابن باز": {},
    "ابن عثيمين": {},
    "صالح العصيمي": {
        "خلاصة تعظيم العلم": "files/خلاصة_تعظيم_العلم_صالح_العصيمي.pdf"
    },
    "غير مصنّف": {
        "شروط الصلاة، وأركانها، وواجباتها.": "files/شروط_الصلاة_وأركانها_وواجباتها.pdf"
    }
}

# ✅ دالة لتنظيف النص
def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

# ✅ البحث الذكي
def smart_search(query):
    norm_query = normalize(query)
    for scholar, books in FILES.items():
        norm_titles = {normalize(title): title for title in books}
        exact_matches = [original for norm, original in norm_titles.items() if norm_query in norm]
        if exact_matches:
            return scholar, exact_matches[0]
        close_matches = difflib.get_close_matches(norm_query, norm_titles.keys(), n=1, cutoff=0.5)
        if close_matches:
            return scholar, norm_titles[close_matches[0]]
    return None, None

# ✅ بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.first_name or "أخي الكريم"
    keyboard = [
        [InlineKeyboardButton(scholar, callback_data=f"scholar:{scholar}")]
        for scholar in FILES.keys()
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        f"السلام عليكم ورحمة الله وبركاته، {username} 🌿\n"
        "✍ اختر اسم أحد العلماء لعرض كتبه، أو أرسل اسم كتاب مباشرة.\n\n"
        "📚 العلماء المتوفرون:",
        reply_markup=reply_markup
    )

# ✅ التعامل مع الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data.startswith("scholar:"):
        scholar = data.split(":", 1)[1]
        books = FILES.get(scholar, {})
        if not books:
            await query.edit_message_text(f"❌ لا توجد كتب حالياً تحت اسم: {scholar}")
            return

        keyboard = [
            [InlineKeyboardButton(title, callback_data=f"book:{scholar}:{title}")]
            for title in books
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(f"📚 كتب {scholar}:", reply_markup=reply_markup)

    elif data.startswith("book:"):
        _, scholar, title = data.split(":", 2)
        file_path = FILES[scholar].get(title)
        if file_path and os.path.exists(file_path):
            with open(file_path, "rb") as f:
                await query.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
        else:
            await query.edit_message_text("❌ لم يتم العثور على الملف المطلوب.")

# ✅ إرسال كتاب عبر البحث
async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last_time = context.user_data.get("last_request_time", 0)
    if now - last_time < 5:
        await update.message.reply_text("⏳ الرجاء الانتظار قليلاً قبل طلب كتاب آخر.")
        return

    context.user_data["last_request_time"] = now
    query = update.message.text
    scholar, match = smart_search(query)
    if match:
        file_path = FILES[scholar][match]
        await update.message.reply_text(f"📘 تم العثور على: {match}\n👤 العالم: {scholar}")
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب. تأكد من كتابة الاسم بشكل صحيح.")

# ✅ إضافة كتاب (أدمن فقط)
async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرف فقط.")
        return

    if not update.message.document:
        await update.message.reply_text(
            "📎 أرسل ملف PDF مع العنوان بهذا الشكل:\n`اسم العالم - اسم الكتاب.pdf`",
            parse_mode="Markdown"
        )
        return

    doc = update.message.document
    filename = doc.file_name.replace(".pdf", "")
    if "-" not in filename:
        await update.message.reply_text("❌ تأكد من أن اسم الملف يحتوي على '-' بين اسم العالم واسم الكتاب.")
        return

    scholar, title = map(str.strip, filename.split("-", 1))
    file_path = f"files/{doc.file_name}"
    file = await doc.get_file()
    await file.download_to_drive(file_path)

    if scholar not in FILES:
        FILES[scholar] = {}

    FILES[scholar][title] = file_path
    await update.message.reply_text(f"✅ تم إضافة الكتاب: {title}\n📚 تحت اسم العالم: {scholar}")

# ✅ حذف كتاب (أدمن فقط)
async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرف فقط.")
        return

    args = " ".join(context.args)
    if "-" not in args:
        await update.message.reply_text("❌ الصيغة الصحيحة: /delete اسم العالم - اسم الكتاب", parse_mode="Markdown")
        return

    scholar, title = map(str.strip, args.split("-", 1))
    if scholar in FILES and title in FILES[scholar]:
        try:
            os.remove(FILES[scholar][title])
        except FileNotFoundError:
            pass
        del FILES[scholar][title]
        await update.message.reply_text(f"✅ تم حذف الكتاب: {title} من تصنيف {scholar}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب تحت هذا التصنيف.")

# ✅ إعداد التطبيق
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("delete", delete_book))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.Document.PDF, add_book))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# ✅ Webhook aiohttp
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

async def handle_home(request):
    return web.Response(text="✅ Bot is running", status=200)

async def on_startup(app):
    init_db()
    await application.bot.set_webhook(WEBHOOK_URL)
    await application.initialize()
    await application.start()

web_app = web.Application()
web_app.router.add_post("/webhook", handle_webhook)
web_app.router.add_get("/", handle_home)
web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(web_app, port=8000)