import os
import difflib
import unicodedata
import time
import sqlite3

from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

# ✅ إنشاء قاعدة البيانات وتخزين الدولة لكل مستخدم
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

# إعدادات عامة
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = 5650658004  # 👑 معرّف الأدمن

# ✅ قاعدة بيانات الكتب حسب العلماء
FILES = {
    "ابن تيمية": {
        "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf"
    },
    "محمد بن عبد الوهاب": {
        "القواعد الأربعة": "files/القواعد_الأربعة_محمد_بن_عبد_الوهاب.pdf",
        "ثلاثة الأصول وأدلتها": "files/محمد_بن_عبد_الوهاب_ثلاثة_الأصول_وأدلتها.pdf",
        "كتاب التوحيد": "files/كتاب_التوحيد_محمد_بن_عبد_الوهاب.pdf"
    },
    "صالح العصيمي": {
        "خلاصة تعظيم العلم": "files/خلاصة_تعظيم_العلم_صالح_العصيمي.pdf"
    },
    "ابن عثيمين": {
        "شروط الصلاة، وأركانها، وواجباتها": "files/شروط_الصلاة_وأركانها_وواجباتها.pdf"
    },
    "صالح الفوزان": {
        "نواقض الإسلام": "files/نواقض_الاسلام.pdf"
    },
    "ابن باز": {
        # كتب ابن باز يمكن إضافتها لاحقًا
    }
}

# إزالة التشكيل والهمزات لتسهيل البحث
def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

# البحث الذكي عن الكتب
def smart_search(query):
    norm_query = normalize(query)
    flat_files = {
        normalize(title): (author, title)
        for author, books in FILES.items()
        for title in books
    }

    exact_matches = [
        original for norm, original in flat_files.items()
        if norm_query in norm
    ]
    if exact_matches:
        return exact_matches[0]

    close_matches = difflib.get_close_matches(norm_query, flat_files.keys(), n=1, cutoff=0.5)
    return flat_files[close_matches[0]] if close_matches else None

# ✅ أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.first_name or "أخي الكريم"
    user_id = update.effective_user.id

    keyboard = [[InlineKeyboardButton(name, callback_data=f"author_{name}")] for name in FILES.keys()]

    if user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("➕ إضافة كتاب (اضغط هنا)", callback_data="add_book"),
            InlineKeyboardButton("🗑 حذف كتاب (اضغط هنا)", callback_data="delete_book")
        ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"السلام عليكم ورحمة الله وبركاته، {username} 🌿\n"
        "قال رسول الله ﷺ:\n"
        "«من صلى عليَّ صلاة، صلى الله عليه بها عشرًا» (رواه مسلم)\n\n"
        "🌟 لا تحرم نفسك من هذا الأجر، صلِّ على النبي ﷺ.\n\n"
        "✍ أرسل اسم الكتاب للحصول على نسخه PDF، أو اضغط على أحد الأزرار أدناه ⬇",
        reply_markup=reply_markup
    )

# عرض كتب عالم معين
async def show_books_by_author(update: Update, context: ContextTypes.DEFAULT_TYPE, author):
    books = FILES.get(author, {})
    if not books:
        await update.callback_query.edit_message_text("❌ لا توجد كتب لهذا العالم حاليًا.")
        return

    buttons = [
        [InlineKeyboardButton(title, callback_data=f"book|{author}|{title}")]
        for title in books
    ]
    await update.callback_query.edit_message_text(f"📚 كتب {author}:", reply_markup=InlineKeyboardMarkup(buttons))

# الرد على ضغط الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    await query.answer()

    if data.startswith("author_"):
        author = data.split("author_")[1]
        await show_books_by_author(update, context, author)

    elif data.startswith("book|"):
        _, author, title = data.split("|", 2)
        file_path = FILES.get(author, {}).get(title)
        if file_path:
            with open(file_path, "rb") as f:
                await query.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
        else:
            await query.message.reply_text("❌ لم يتم العثور على الكتاب.")

    elif data == "add_book" and user_id == ADMIN_ID:
        await query.edit_message_text("📥 أرسل الآن ملف PDF الذي تريد إضافته. اسمه يجب أن يكون: اسم_العالم - اسم_الكتاب.pdf")

    elif data == "delete_book" and user_id == ADMIN_ID:
        await query.edit_message_text("🗑 أرسل الآن اسم الكتاب الذي تريد حذفه باستخدام الأمر:\n/delete اسم الكتاب", parse_mode="Markdown")

# إرسال الكتاب عند الطلب
async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    now = time.time()
    last_time = context.user_data.get("last_request_time", 0)
    if now - last_time < 5:
        await update.message.reply_text("⏳ الرجاء الانتظار قليلاً قبل طلب كتاب آخر.")
        return

    context.user_data["last_request_time"] = now
    query = update.message.text
    result = smart_search(query)

    if result:
        author, title = result
        file_path = FILES[author][title]
        await update.message.reply_text(f"📘 تم العثور على: {title}\n👤 المؤلف: {author}")
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب. تأكد من كتابة الاسم بشكل صحيح.")

# ✅ إضافة كتاب (للأدمن فقط)
async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرف فقط.")
        return

    if not update.message.document:
        await update.message.reply_text("📎 أرسل ملف PDF مع العنوان بهذا الشكل: اسم_العالم - اسم_الكتاب.pdf")
        return

    doc = update.message.document
    name = doc.file_name.replace(".pdf", "")
    if "-" not in name:
        await update.message.reply_text("❗ اسم الملف غير صحيح. يجب أن يكون بصيغة: اسم_العالم - اسم_الكتاب.pdf")
        return

    author, title = [part.strip().replace("_", " ") for part in name.split("-", 1)]
    file_path = f"files/{doc.file_name}"
    file = await doc.get_file()
    await file.download_to_drive(file_path)

    if author not in FILES:
        FILES[author] = {}
    FILES[author][title] = file_path

    await update.message.reply_text(f"✅ تم إضافة الكتاب: {title}\n👤 المؤلف: {author}")

# حذف كتاب (للأدمن فقط)
async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("🚫 هذا الأمر مخصص للمشرف فقط.")
        return

    title = " ".join(context.args)
    result = smart_search(title)

    if result:
        author, real_title = result
        try:
            os.remove(FILES[author][real_title])
        except FileNotFoundError:
            pass
        del FILES[author][real_title]
        await update.message.reply_text(f"✅ تم حذف الكتاب: {real_title} (المؤلف: {author})")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# إعداد التطبيق
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("delete", delete_book))
application.add_handler(CallbackQueryHandler(button_handler))
application.add_handler(MessageHandler(filters.Document.PDF, add_book))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# Webhook و UptimeRobot
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