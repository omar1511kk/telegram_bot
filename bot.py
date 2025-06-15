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
    cursor.execute(
        "INSERT INTO books (author, title, file_path) VALUES (?, ?, ?)",
        (author, title, file_path)
    )
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
    flat = {
        normalize(title): (author, title)
        for author, books in FILES.items()
        for title in books
    }
    exact = [original for norm, original in flat.items() if norm_query in norm]
    if exact:
        return exact[0]
    close = difflib.get_close_matches(norm_query, flat.keys(), n=1, cutoff=0.8)
    return flat[close[0]] if close else None

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
    if not doc or not doc.file_name.lower().endswith(".pdf"):
        return await update.message.reply_text("📎 أرسل ملف PDF بصيغة: اسم_العالم - اسم_الكتاب.pdf")

    raw_name = doc.file_name.encode("utf-8").decode("utf-8", "ignore").replace(".pdf", "").strip()
    if "-" not in raw_name:
        return await update.message.reply_text("❗ اسم الملف يجب أن يكون بصيغة: اسم_العالم - اسم_الكتاب.pdf")

    parts = raw_name.split("-", 1)
    if len(parts) < 2:
        return await update.message.reply_text("❗ تعذر استخراج اسم العالم والكتاب من اسم الملف.")

    author = parts[0].replace("_", " ").strip()
    title = parts[1].replace("_", " ").strip()
    if not author or not title:
        return await update.message.reply_text("❗ تأكد من أن اسم الملف يحتوي على اسم العالم واسم الكتاب.")

    file_path = f"files/{doc.file_name}"
    await doc.get_file().download_to_drive(file_path)

    save_book(author, title, file_path)