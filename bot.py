import os
import difflib
import unicodedata
import sqlite3
import hashlib
import re
import json

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)
from aiohttp import web

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ======================== إعدادات ==========================

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ADMIN_ID = 5650658004
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

# =================== Google Drive API ======================

# تحميل بيانات الاعتماد من متغير البيئة كنص JSON
creds_json = os.getenv("GDRIVE_CREDENTIALS_JSON")
if not creds_json:
    raise ValueError("❌ لم يتم العثور على متغير البيئة GDRIVE_CREDENTIALS_JSON")

creds_dict = json.loads(creds_json)
creds = service_account.Credentials.from_service_account_info(
    creds_dict, scopes=["https://www.googleapis.com/auth/drive"]
)
drive_service = build("drive", "v3", credentials=creds)

def upload_to_gdrive(file_path, filename):
    file_metadata = {"name": filename, "parents": [GDRIVE_FOLDER_ID]}
    media = MediaFileUpload(file_path, mimetype="application/pdf")
    file = drive_service.files().create(
        body=file_metadata, media_body=media, fields="id"
    ).execute()
    file_id = file.get("id")
    drive_service.permissions().create(
        fileId=file_id, body={"role": "reader", "type": "anyone"}
    ).execute()
    return f"https://drive.google.com/uc?id={file_id}&export=download"

# ================== قاعدة البيانات =========================

def init_db():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            gdrive_url TEXT NOT NULL,
            original_name TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def load_books():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("SELECT author, title, gdrive_url, original_name FROM books")
    books = {}
    for author, title, url, original in cursor.fetchall():
        books.setdefault(author, {})[title] = url
    conn.close()
    return books

def save_book(author, title, gdrive_url, original_name):
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO books (author, title, gdrive_url, original_name)
        VALUES (?, ?, ?, ?)
    """, (author, title, gdrive_url, original_name))
    conn.commit()
    conn.close()

def remove_book(author, title):
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM books WHERE author = ? AND title = ?", (author, title))
    conn.commit()
    conn.close()

# ================== أدوات مساعدة ==========================

def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

def smart_search(query):
    norm_query = normalize(query)
    FILES = load_books()
    flat = {
        normalize(f"{author} {title}"): (author, title)
        for author, books in FILES.items()
        for title in books
    }
    if norm_query in flat:
        return flat[norm_query]
    matches = [v for k, v in flat.items() if norm_query in k]
    if matches:
        return matches[0]
    close = difflib.get_close_matches(norm_query, flat.keys(), n=1, cutoff=0.6)
    return flat[close[0]] if close else None

# ================== أوامر البوت ===========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    FILES = load_books()
    username = update.effective_user.first_name or "أخي الكريم"
    keyboard = []

    authors = list(FILES.keys())
    for i in range(0, len(authors), 2):
        row = []
        for author in authors[i:i + 2]:
            aid = hashlib.md5(author.encode()).hexdigest()[:8]
            row.append(InlineKeyboardButton(author, callback_data=f"author|{aid}"))
            context.chat_data[aid] = author
        keyboard.append(row)

    if update.effective_user.id == ADMIN_ID:
        keyboard.append([
            InlineKeyboardButton("➕ إضافة كتاب", callback_data="add_book"),
            InlineKeyboardButton("🗑 حذف كتاب", callback_data="delete_book"),
        ])

    await update.message.reply_text(
        f"السلام عليكم {username} 🌿\nاختر اسم العالم أو أرسل اسم الكتاب مباشرة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_books_by_author(update: Update, context: ContextTypes.DEFAULT_TYPE, author):
    FILES = load_books()
    books = FILES.get(author, {})
    if not books:
        await update.callback_query.edit_message_text("❌ لا توجد كتب لهذا العالم.")
        return

    buttons = []
    row = []
    for title in books:
        bid = hashlib.md5(f"{author}|{title}".encode()).hexdigest()[:8]
        context.chat_data[bid] = (author, title)
        row.append(InlineKeyboardButton(title, callback_data=f"book|{bid}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    buttons.append([InlineKeyboardButton("🔙 العودة", callback_data="start")])
    await update.callback_query.edit_message_text(
        f"📚 كتب {author}:", reply_markup=InlineKeyboardMarkup(buttons)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    await update.callback_query.answer()

    if data == "start":
        await start(update, context)

    elif data.startswith("author|"):
        aid = data.split("|")[1]
        author = context.chat_data.get(aid)
        if author:
            await show_books_by_author(update, context, author)

    elif data.startswith("book|"):
        bid = data.split("|")[1]
        author, title = context.chat_data.get(bid, (None, None))
        FILES = load_books()
        if author and title and FILES.get(author, {}).get(title):
            url = FILES[author][title]
            await update.callback_query.message.reply_document(
                document=url, filename=f"{author} - {title}.pdf"
            )
        else:
            await update.callback_query.message.reply_text("❌ الكتاب غير موجود.")

    elif data == "add_book" and update.effective_user.id == ADMIN_ID:
        await update.callback_query.edit_message_text("📤 أرسل ملف PDF مع تعليق بصيغة: المؤلف - العنوان")

    elif data == "delete_book" and update.effective_user.id == ADMIN_ID:
        await update.callback_query.edit_message_text("🗑 أرسل اسم الكتاب لحذفه: /delete اسم الكتاب")

async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = smart_search(update.message.text)
    if result:
        author, title = result
        FILES = load_books()
        url = FILES[author][title]
        await update.message.reply_document(
            document=url, filename=f"{author} - {title}.pdf"
        )
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    doc = update.message.document
    caption = update.message.caption or ""

    if not doc or not doc.file_name.endswith(".pdf") or "-" not in caption:
        return await update.message.reply_text("❗ أرسل ملف PDF مع تعليق بصيغة: المؤلف - العنوان")

    author, title = [s.strip() for s in caption.split("-", 1)]
    os.makedirs("temp", exist_ok=True)
    file_path = f"temp/{doc.file_name}"
    await doc.get_file().download_to_drive(file_path)

    try:
        gdrive_url = upload_to_gdrive(file_path, f"{author} - {title}.pdf")
        save_book(author, title, gdrive_url, doc.file_name)
        await update.message.reply_text(
            f"✅ تم رفع الكتاب إلى Google Drive:\n📘 {title}\n👤 {author}"
        )
    finally:
        os.remove(file_path)

async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    title = " ".join(context.args)
    result = smart_search(title)
    if result:
        author, real_title = result
        remove_book(author, real_title)
        await update.message.reply_text(f"✅ تم حذف الكتاب: {real_title}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# ================== إعداد التطبيق =========================

def main():
    init_db()
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
        return web.Response(text="✅ البوت يعمل بنجاح")

    web_app = web.Application()
    web_app.router.add_post("/webhook", handle_webhook)
    web_app.router.add_get("/", handle_home)
    web_app.on_startup.append(on_startup)

    port = int(os.getenv("PORT", 8000))
    web.run_app(web_app, port=port)

if __name__== "__main__":
    main()