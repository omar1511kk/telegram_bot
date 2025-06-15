# ✅ استيراد المكتبات
import os
import difflib
import unicodedata
import time
import sqlite3
import hashlib
import re

from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from aiohttp import web

# ✅ إعداد التوكن ورابط الويبهوك ومعرّف الأدمن
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = 5650658004

# =====================================================
# ✅ قاعدة البيانات
# =====================================================

def init_db():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def load_books():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("SELECT author, title, file_path FROM books")
    books = {}
    for author, title, path in cursor.fetchall():
        books.setdefault(author, {})[title] = path
    conn.close()
    return books

def save_book(author, title, file_path):
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (author, title, file_path) VALUES (?, ?, ?)",
                   (author, title, file_path))
    conn.commit()
    conn.close()

def remove_book(author, title):
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM books WHERE author = ? AND title = ?", (author, title))
    conn.commit()
    conn.close()

# =====================================================
# ✅ الأدوات المساعدة
# =====================================================

def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

def smart_search(query):
    norm_query = normalize(query)

    # دمج اسم المؤلف مع عنوان الكتاب للبحث
    flat = {
        normalize(f"{author} {title}"): (author, title)
        for author, books in FILES.items()
        for title in books
    }

    close = difflib.get_close_matches(norm_query, flat.keys(), n=1, cutoff=0.6)
    if close:
        return flat[close[0]]

    return None

# =====================================================
# ✅ الأوامر
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.first_name or "أخي الكريم"
    user_id = update.effective_user.id
    keyboard = [
        [InlineKeyboardButton(name, callback_data=f"author|{name}")]
        for name in FILES
    ]

    if user_id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("➕ إضافة كتاب", callback_data="add_book"),
            InlineKeyboardButton("🗑 حذف كتاب", callback_data="delete_book"),
        ])

    await update.message.reply_text(
        f"السلام عليكم ورحمة الله وبركاته، {username} 🌿\n"
        "✍ أرسل اسم الكتاب أو اختر من الأزرار:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_books_by_author(update: Update, context: ContextTypes.DEFAULT_TYPE, author):
    books = FILES.get(author, {})
    if not books:
        await update.callback_query.edit_message_text("❌ لا توجد كتب لهذا العالم.")
        return

    buttons, row = [], []
    for title in books:
        book_id = hashlib.md5(f"{author}|{title}".encode()).hexdigest()
        context.chat_data[book_id] = (author, title)
        row.append(InlineKeyboardButton(title, callback_data=f"book|{book_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    await update.callback_query.edit_message_text(
        f"📚 كتب {author}:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data
    await query.answer()

    if data.startswith("author|"):
        author = data.split("author|")[1]
        await show_books_by_author(update, context, author)

    elif data.startswith("book|"):
        book_id = data.split("book|")[1]
        author, title = context.chat_data.get(book_id, (None, None))
        if author and title:
            file_path = FILES.get(author, {}).get(title)
            if file_path:
                with open(file_path, "rb") as f:
                    await query.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
                return
        await query.message.reply_text("❌ لم يتم العثور على الكتاب.")

    elif data == "add_book" and user_id == ADMIN_ID:
        await query.edit_message_text("📥 أرسل ملف PDF بصيغة: اسم_العالم - اسم_الكتاب.pdf")

    elif data == "delete_book" and user_id == ADMIN_ID:
        await query.edit_message_text("🗑 أرسل اسم الكتاب لحذفه باستخدام:\n/delete اسم الكتاب")

async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    result = smart_search(query)

    if result:
        author, title = result
        file_path = FILES[author][title]
        await update.message.reply_text(f"📘 {title}\n👤 المؤلف: {author}")
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 هذا الأمر للأدمن فقط.")

    doc = update.message.document
    if not doc or not doc.file_name.endswith(".pdf"):
        return await update.message.reply_text("📎 أرسل ملف PDF بصيغة: اسم_العالم - اسم_الكتاب.pdf")

    name = doc.file_name.replace(".pdf", "")
    if not re.match(r"^[\u0600-\u06FFa-zA-Z0-9_ ]+ - [\u0600-\u06FFa-zA-Z0-9_ ]+$", name):
        return await update.message.reply_text("❗ اسم الملف يجب أن يكون بصيغة: اسم_العالم - اسم_الكتاب.pdf")

    author, title = [part.strip().replace("_", " ") for part in name.split(" - ", 1)]
    file_path = f"files/{doc.file_name}"

    file = await doc.get_file()
    await file.download_to_drive(file_path)

    save_book(author, title, file_path)
    FILES.setdefault(author, {})[title] = file_path

    await update.message.reply_text(f"✅ تم إضافة: {title}\n👤 {author}")

async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 هذا الأمر للأدمن فقط.")

    title = " ".join(context.args)
    result = smart_search(title)
    if result:
        author, real_title = result
        try:
            os.remove(FILES[author][real_title])
        except FileNotFoundError:
            pass
        del FILES[author][real_title]
        remove_book(author, real_title)
        await update.message.reply_text(f"✅ تم حذف الكتاب: {real_title}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# =====================================================
# ✅ التشغيل بواسطة Webhook
# =====================================================

def main():
    init_db()
    global FILES
    FILES = load_books()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete", delete_book))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Document.PDF, add_book))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

    async def on_startup(app):
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(WEBHOOK_URL)

    async def handle_webhook(request):
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response()

    async def handle_home(request):
        return web.Response(text="✅ Bot is running!", status=200)

    web_app = web.Application()
    web_app.router.add_post("/webhook", handle_webhook)
    web_app.router.add_get("/", handle_home)
    web_app.on_startup.append(on_startup)

    port = int(os.getenv("PORT", 8000))
    web.run_app(web_app, port=port)

if __name__ == "__main__":
    main()