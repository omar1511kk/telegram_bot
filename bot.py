import os
import sqlite3
import logging
import hashlib
import difflib
import re
import time
import unicodedata

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# إعداد التوكن والمعرفات
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GDRIVE_FOLDER_ID = os.getenv("GDRIVE_FOLDER_ID")

# إعداد السجلات
logging.basicConfig(level=logging.INFO)

# الاتصال بقاعدة البيانات
conn = sqlite3.connect("books.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute(
    "CREATE TABLE IF NOT EXISTS books (id INTEGER PRIMARY KEY AUTOINCREMENT, author TEXT, title TEXT, url TEXT)"
)
conn.commit()


def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower()


def get_authors():
    cursor.execute("SELECT DISTINCT author FROM books")
    return [row[0] for row in cursor.fetchall()]


def get_books_by_author(author):
    cursor.execute("SELECT title FROM books WHERE author = ?", (author,))
    return cursor.fetchall()


def get_book_url(title, author):
    cursor.execute(
        "SELECT url FROM books WHERE title = ? AND author = ?", (title, author)
    )
    result = cursor.fetchone()
    return result[0] if result else None


def upload_to_gdrive(file_path, filename):
    credentials = service_account.Credentials.from_service_account_file(
        os.getenv("GDRIVE_CREDENTIALS_JSON")
    )
    service = build("drive", "v3", credentials=credentials)

    file_metadata = {
        "name": filename,
        "parents": [GDRIVE_FOLDER_ID],
    }
    media = MediaFileUpload(file_path, mimetype="application/pdf")

    uploaded_file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = uploaded_file.get("id")

    # جعل الملف عامًا
    service.permissions().create(
        fileId=file_id,
        body={"role": "reader", "type": "anyone"},
    ).execute()

    return f"https://drive.google.com/uc?id={file_id}&export=download"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("مرحبا بك! اختر أحد العلماء لعرض كتبه:")
    else:
        await update.message.reply_text("مرحبًا أيها المشرف! يمكنك إدارة الكتب بالأوامر.")

    authors = get_authors()
    buttons = [
        [InlineKeyboardButton(author, callback_data=f"author_{author}")]
        for author in authors
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("👨‍🏫 العلماء المتاحون:", reply_markup=reply_markup)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("author_"):
        author = data.split("_", 1)[1]
        books = get_books_by_author(author)

        if not books:
            await query.edit_message_text("لا توجد كتب لهذا العالم حالياً.")
            return

        buttons = [
            [InlineKeyboardButton(book[0], callback_data=f"book_{book[0]}_{author}")]
            for book in books
        ]
        buttons.append([InlineKeyboardButton("🔙 العودة", callback_data="back")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text(
            f"📚 كتب الشيخ {author}:", reply_markup=reply_markup
        )

    elif data.startswith("book_"):
        parts = data.split("_", 2)
        title = parts[1]
        author = parts[2]
        url = get_book_url(title, author)

        if url:
            await query.message.reply_text(
                f"📘 {title}\n👤 {author}\n\n📥 رابط التحميل:\n{url}"
            )
        else:
            await query.message.reply_text("عذراً، لم يتم العثور على رابط هذا الكتاب.")

    elif data == "back":
        authors = get_authors()
        buttons = [
            [InlineKeyboardButton(author, callback_data=f"author_{author}")]
            for author in authors
        ]
        reply_markup = InlineKeyboardMarkup(buttons)
        await query.edit_message_text("👨‍🏫 العلماء المتاحون:", reply_markup=reply_markup)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = normalize(update.message.text)
    authors = get_authors()

    for author in authors:
        books = get_books_by_author(author)
        for book in books:
            title = book[0]
            if normalize(title) in user_input or user_input in normalize(title):
                url = get_book_url(title, author)
                if url:
                    await update.message.reply_text(
                        f"📘 {title}\n👤 {author}\n\n📥 رابط التحميل:\n{url}"
                    )
                    return

    all_titles = [book[0] for author in authors for book in get_books_by_author(author)]
    close_matches = difflib.get_close_matches(user_input, all_titles, n=1, cutoff=0.6)

    if close_matches:
        matched_title = close_matches[0]
        for author in authors:
            if (matched_title,) in get_books_by_author(author):
                url = get_book_url(matched_title, author)
                if url:
                    await update.message.reply_text(
                        f"📘 {matched_title}\n👤 {author}\n\n📥 رابط التحميل:\n{url}"
                    )
                    return

    await update.message.reply_text("عذراً، لم يتم العثور على هذا الكتاب.")


async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    if not update.message.document:
        await update.message.reply_text("📎 أرسل ملف PDF لإضافته.")
        return

    try:
        author, title = update.message.caption.split(" - ")
        title = title.replace(".pdf", "").strip()
    except:
        await update.message.reply_text("❌ يجب أن يكون التسمية بهذا الشكل: اسم_العالم - عنوان الكتاب.pdf")
        return

    file = await update.message.document.get_file()
    file_path = f"{hashlib.md5(str(time.time()).encode()).hexdigest()}.pdf"
    await file.download_to_drive(file_path)

    try:
        gdrive_url = upload_to_gdrive(file_path, f"{author} - {title}.pdf")
        cursor.execute(
            "INSERT INTO books (author, title, url) VALUES (?, ?, ?)",
            (author, title, gdrive_url),
        )
        conn.commit()
        await update.message.reply_text("✅ تم رفع الكتاب بنجاح إلى Google Drive وإضافته.")
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء الرفع إلى Google Drive:\n{e}")
    finally:
        os.remove(file_path)


async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمشرف فقط.")
        return

    try:
        author, title = update.message.text.split(" - ")
        cursor.execute(
            "DELETE FROM books WHERE author = ? AND title = ?", (author, title)
        )
        conn.commit()
        await update.message.reply_text("🗑 تم حذف الكتاب بنجاح.")
    except:
        await update.message.reply_text("❌ يجب كتابة الأمر بهذا الشكل: اسم_العالم - عنوان الكتاب")


app = Application.builder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add_book))
app.add_handler(CommandHandler("delete", delete_book))
app.add_handler(MessageHandler(filters.Document.PDF, add_book))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
app.add_handler(CallbackQueryHandler(button_handler))

if __name__ == "__main__":
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        webhook_url=os.environ.get("WEBHOOK_URL"),
    )