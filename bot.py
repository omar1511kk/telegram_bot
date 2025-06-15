import os
import sqlite3
import logging
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes

# إعداد تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# إعداد Google Drive
service_account_json = os.getenv("GDRIVE_CREDENTIALS_JSON")
if not service_account_json:
    raise Exception("متغير البيئة GDRIVE_CREDENTIALS_JSON غير موجود!")

with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix=".json") as temp:
    temp.write(service_account_json)
    service_account_path = temp.name

SCOPES = ['https://www.googleapis.com/auth/drive']
credentials = service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=credentials)

# إعداد قاعدة البيانات
conn = sqlite3.connect("books.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholar TEXT,
    title TEXT,
    url TEXT
)''')
conn.commit()

# إعداد التوكن
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("متغير البيئة BOT_TOKEN غير موجود!")

# معرف الأدمن
ADMIN_ID = 5650658004

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT DISTINCT scholar FROM books")
    scholars = cursor.fetchall()
    if not scholars:
        await update.message.reply_text("لا توجد كتب مضافة حالياً.")
        return
    keyboard = [[InlineKeyboardButton(s[0], callback_data=f"scholar:{s[0]}")] for s in scholars]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر اسم العالم:", reply_markup=reply_markup)

# عرض كتب العالم
async def scholar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    scholar = query.data.split(":")[1]
    cursor.execute("SELECT title FROM books WHERE scholar = ?", (scholar,))
    books = cursor.fetchall()
    if not books:
        await query.edit_message_text("لا توجد كتب لهذا العالم.")
        return
    keyboard = [[InlineKeyboardButton(title[0], callback_data=f"book:{title[0]}")] for title in books]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"📚 كتب {scholar}:", reply_markup=reply_markup)

# إرسال الكتاب
async def book_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    title = query.data.split(":")[1]
    cursor.execute("SELECT url FROM books WHERE title = ?", (title,))
    result = cursor.fetchone()
    if result:
        await query.message.reply_document(document=result[0], caption=title)
    else:
        await query.edit_message_text("الكتاب غير موجود.")

# إضافة كتاب (للأدمن فقط)
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("ليس لديك صلاحية.")
        return

    if not context.args or len(context.args) < 2 or not update.message.document:
        await update.message.reply_text("الاستخدام:\n/add [اسم العالم] [اسم الكتاب] مع رفع ملف PDF")
        return

    scholar = context.args[0]
    title = " ".join(context.args[1:])
    file = await update.message.document.get_file()
    file_path = f"{title}.pdf"
    await file.download_to_drive(file_path)

    # رفع الملف إلى Google Drive
    file_metadata = {'name': file_path}
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    uploaded_file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    file_id = uploaded_file.get('id')

    # جعل الملف عامًا (قابلًا للتحميل بدون تسجيل دخول)
    drive_service.permissions().create(
        fileId=file_id,
        body={'type': 'anyone', 'role': 'reader'},
    ).execute()

    file_url = f"https://drive.google.com/uc?id={file_id}&export=download"

    # حفظ في قاعدة البيانات
    cursor.execute("INSERT INTO books (scholar, title, url) VALUES (?, ?, ?)", (scholar, title, file_url))
    conn.commit()
    os.remove(file_path)

    await update.message.reply_text(
        f"✅ تم رفع الملف إلى Google Drive بنجاح!\n\n📘 {title}\n🔗 [رابط التحميل المباشر]({file_url})",
        parse_mode="Markdown"
    )

# حذف كتاب
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("ليس لديك صلاحية.")
        return

    if not context.args:
        await update.message.reply_text("الاستخدام:\n/delete [اسم الكتاب]")
        return

    title = " ".join(context.args)
    cursor.execute("SELECT url FROM books WHERE title = ?", (title,))
    result = cursor.fetchone()
    if result:
        cursor.execute("DELETE FROM books WHERE title = ?", (title,))
        conn.commit()
        await update.message.reply_text("تم حذف الكتاب بنجاح 🗑")
    else:
        await update.message.reply_text("الكتاب غير موجود.")

# البحث بالاسم
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    cursor.execute("SELECT title, url FROM books WHERE title LIKE ?", (f"%{query}%",))
    results = cursor.fetchall()
    if results:
        for title, url in results:
            await update.message.reply_document(document=url, caption=title)
    else:
        await update.message.reply_text("لم يتم العثور على كتاب بهذا الاسم.")

# تشغيل البوت
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CallbackQueryHandler(scholar_callback, pattern="^scholar:"))
    app.add_handler(CallbackQueryHandler(book_callback, pattern="^book:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot is running...")
    app.run_polling()