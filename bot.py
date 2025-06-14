import os
import difflib
import unicodedata
import time
import sqlite3
import hashlib

from aiohttp import web
from telegram import Update, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, CallbackQueryHandler, filters
)

# ✅ إعداد قواعد البيانات
def init_db():
    # قاعدة بيانات المستخدمين
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

    # قاعدة بيانات الكتب
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT,
            title TEXT,
            file_path TEXT
        )
    """)
    conn.commit()
    conn.close()

# ✅ تحميل الكتب من قاعدة البيانات
def load_books():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("SELECT author, title, file_path FROM books")
    rows = cursor.fetchall()
    conn.close()

    books = {}
    for author, title, path in rows:
        if author not in books:
            books[author] = {}
        books[author][title] = path
    return books

FILES = load_books()

# ✅ إعدادات عامة
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5650658004  # 👑 معرف الأدمن

# ✅ إزالة التشكيل والهمزات لتسهيل البحث
def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

# ✅ البحث الذكي عن الكتب
def smart_search(query):
    norm_query = normalize(query)
    flat_files = {
        normalize(title): (author, title)
        for author, books in FILES.items()
        for title in books
    }

    exact_matches = [original for norm, original in flat_files.items() if norm_query in norm]
    if exact_matches:
        return exact_matches[0]

    close_matches = difflib.get_close_matches(norm_query, flat_files.keys(), n=1, cutoff=0.8)
    return flat_files[close_matches[0]] if close_matches else None

# ✅ أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.first_name or "أخي الكريم"
    user_id = update.effective_user.id

    keyboard = [[InlineKeyboardButton(name, callback_data=f"author|{name}")] for name in FILES.keys()]

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

# ✅ عرض كتب عالم معين
async def show_books_by_author(update: Update, context: ContextTypes.DEFAULT_TYPE, author):
    books = FILES.get(author, {})
    if not books:
        await update.callback_query.edit_message_text("❌ لا توجد كتب لهذا العالم حاليًا.")
        return

    buttons = []
    row = []
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
        f"📚 كتب {author}:", reply_markup=InlineKeyboardMarkup(buttons)
    )

# ✅ الرد على ضغط الأزرار
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
        await query.edit_message_text("📥 أرسل الآن ملف PDF الذي تريد إضافته. اسمه يجب أن يكون: اسم_العالم - اسم_الكتاب.pdf")

    elif data == "delete_book" and user_id == ADMIN_ID:
        await query.edit_message_text("🗑 أرسل الآن اسم الكتاب الذي تريد حذفه باستخدام الأمر:\n/delete اسم الكتاب", parse_mode="Markdown")

# ✅ إرسال الكتاب عند الطلب
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

# ✅ إضافة كتاب
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

    # حفظ في FILES
    if author not in FILES:
        FILES[author] = {}
    FILES[author][title] = file_path

    # حفظ في قاعدة البيانات
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (author, title, file_path) VALUES (?, ?, ?)", (author, title, file_path))
    conn.commit()
    conn.close()

    await update.message.reply_text(f"✅ تم إضافة الكتاب: {title}\n👤 المؤلف: {author}")

# ✅ حذف كتاب
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

        # حذف من قاعدة البيانات
        conn = sqlite3.connect("books.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM books WHERE author = ? AND title = ?", (author, real_title))
        conn.commit()
        conn.close()

        await update.message.reply_text(f"✅ تم حذف الكتاب: {real_title} (المؤلف: {author})")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# ✅ تشغيل التطبيق
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
    application.run_polling()

if __name__ == "__main__":
    main()