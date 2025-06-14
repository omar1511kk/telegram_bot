import os
import sqlite3
import json
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# إعدادات Google Drive باستخدام بيانات الخدمة من متغير البيئة
creds_json = os.getenv("GDRIVE_CREDENTIALS_JSON")
if creds_json:
    with open("service_account.json", "w") as f:
        f.write(creds_json)

# إعداد Google Drive
gauth = GoogleAuth()
gauth.LoadCredentialsFile("service_account.json")
drive = GoogleDrive(gauth)

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5650658004

# قاعدة البيانات
conn = sqlite3.connect("books.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholar TEXT,
    title TEXT,
    url TEXT
)
""")
conn.commit()

# تسجيل الأخطاء
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# عرض أسماء العلماء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT DISTINCT scholar FROM books")
    scholars = cursor.fetchall()
    keyboard = [
        [InlineKeyboardButton(scholar[0], callback_data=f"scholar:{scholar[0]}")]
        for scholar in scholars
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر اسم العالم:", reply_markup=reply_markup)

# عرض كتب العالم
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("scholar:"):
        scholar = data.split(":")[1]
        cursor.execute("SELECT title FROM books WHERE scholar=?", (scholar,))
        books = cursor.fetchall()
        keyboard = [
            [InlineKeyboardButton(book[0], callback_data=f"book:{book[0]}")]
            for book in books
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(text=f"كتب {scholar}:", reply_markup=reply_markup)

    elif data.startswith("book:"):
        title = data.split(":")[1]
        cursor.execute("SELECT url FROM books WHERE title=?", (title,))
        result = cursor.fetchone()
        if result:
            await query.message.reply_document(document=result[0], filename=f"{title}.pdf")
        else:
            await query.message.reply_text("الكتاب غير موجود.")

# البحث باسم الكتاب
async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    cursor.execute("SELECT title, url FROM books WHERE title LIKE ?", (f"%{query}%",))
    results = cursor.fetchall()
    if results:
        for title, url in results:
            await update.message.reply_document(document=url, filename=f"{title}.pdf")
    else:
        await update.message.reply_text("لم يتم العثور على كتاب بهذا الاسم.")

# إضافة كتاب (للأدمن فقط)
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ لا تملك صلاحية هذا الأمر.")
        return

    args = context.args
    if len(args) < 2 or not update.message.document:
        await update.message.reply_text("❗ استخدم الأمر هكذا:\n/add اسم_العالم اسم_الكتاب مع إرسال ملف PDF")
        return

    scholar = args[0]
    title = " ".join(args[1:])

    file = update.message.document
    file_path = await file.get_file()
    file_bytes = await file_path.download_as_bytearray()

    gfile = drive.CreateFile({'title': f"{title}.pdf"})
    gfile.SetContentString(file_bytes.decode("latin1", errors="ignore"))
    gfile.Upload()

    file_url = f"https://drive.google.com/uc?id={gfile['id']}&export=download"
    cursor.execute("INSERT INTO books (scholar, title, url) VALUES (?, ?, ?)", (scholar, title, file_url))
    conn.commit()

    await update.message.reply_text("✅ تم إضافة الكتاب بنجاح.")

# حذف كتاب (للأدمن فقط)
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("❌ لا تملك صلاحية هذا الأمر.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("❗ استخدم الأمر هكذا:\n/delete اسم_الكتاب")
        return

    title = " ".join(args)
    cursor.execute("SELECT url FROM books WHERE title=?", (title,))
    result = cursor.fetchone()

    if result:
        cursor.execute("DELETE FROM books WHERE title=?", (title,))
        conn.commit()
        await update.message.reply_text("✅ تم حذف الكتاب.")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# تشغيل البوت
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("add", add))
app.add_handler(CommandHandler("delete", delete))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search))
app.add_handler(CallbackQueryHandler(button))

app.run_polling()