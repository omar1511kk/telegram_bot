import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.service_account import Credentials
from aiohttp import web

TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = 5650658004
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # مثل: https://your-app.onrender.com/telegram-webhook/yourtoken

# === Google Drive Auth ===
creds = Credentials.from_service_account_file("credentials.json", scopes=["https://www.googleapis.com/auth/drive"])
drive_service = build("drive", "v3", credentials=creds)

# === SQLite Setup ===
conn = sqlite3.connect("books.db")
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholar TEXT,
    title TEXT,
    drive_link TEXT
)""")
conn.commit()

# === أزرار العلماء ===
def get_scholars():
    cursor.execute("SELECT DISTINCT scholar FROM books")
    return [row[0] for row in cursor.fetchall()]

def get_books_by_scholar(scholar):
    cursor.execute("SELECT title FROM books WHERE scholar = ?", (scholar,))
    return [row[0] for row in cursor.fetchall()]

def get_link_by_title(title):
    cursor.execute("SELECT drive_link FROM books WHERE title = ?", (title,))
    row = cursor.fetchone()
    return row[0] if row else None

# === رفع إلى Google Drive ===
def upload_pdf_to_drive(local_path, title):
    media = MediaFileUpload(local_path, mimetype="application/pdf")
    file_metadata = {"name": title, "parents": [GOOGLE_DRIVE_FOLDER_ID]}
    file = drive_service.files().create(body=file_metadata, media_body=media, fields="id").execute()
    file_id = file.get("id")
    drive_service.permissions().create(fileId=file_id, body={"role": "reader", "type": "anyone"}).execute()
    return f"https://drive.google.com/uc?export=download&id={file_id}"

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    scholars = get_scholars()
    keyboard = [[InlineKeyboardButton(name, callback_data=f"scholar:{name}")] for name in scholars]
    await update.message.reply_text("اختر اسم العالم لرؤية كتبه:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    if data.startswith("scholar:"):
        scholar = data.split(":", 1)[1]
        books = get_books_by_scholar(scholar)
        keyboard = [[InlineKeyboardButton(book, callback_data=f"book:{book}")] for book in books]
        await query.edit_message_text(f"📚 كتب {scholar}:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif data.startswith("book:"):
        title = data.split(":", 1)[1]
        link = get_link_by_title(title)
        if link:
            await query.message.reply_document(document=link, filename=f"{title}.pdf")
        else:
            await query.message.reply_text("❌ الملف غير موجود.")

async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمسؤول فقط.")
        return
    await update.message.reply_text("أرسل ملف PDF مع الرسالة بالشكل التالي:\n`اسم العالم - اسم الكتاب`", parse_mode="Markdown")

async def handle_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر مخصص للمسؤول فقط.")
        return
    await update.message.reply_text("أرسل اسم الكتاب الذي تريد حذفه.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    doc = update.message.document
    caption = update.message.caption or update.message.text
    if not caption or "-" not in caption:
        await update.message.reply_text("❌ الصيغة غير صحيحة. استخدم: اسم العالم - اسم الكتاب", parse_mode="Markdown")
        return
    scholar, title = map(str.strip, caption.split("-", 1))
    file = await context.bot.get_file(doc.file_id)
    local_path = f"{title}.pdf"
    await file.download_to_drive(local_path)
    drive_link = upload_pdf_to_drive(local_path, title)
    cursor.execute("INSERT INTO books (scholar, title, drive_link) VALUES (?, ?, ?)", (scholar, title, drive_link))
    conn.commit()
    os.remove(local_path)
    await update.message.reply_text(f"✅ تم إضافة الكتاب: {title}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    title = update.message.text.strip()
    cursor.execute("DELETE FROM books WHERE title = ?", (title,))
    conn.commit()
    await update.message.reply_text(f"✅ تم حذف الكتاب: {title}")

# === Aiohttp server للـ Webhook و UptimeRobot ===
async def root_handler(request):
    return web.Response(text="✅ Bot is alive!")

async def webhook_handler(request):
    data = await request.json()
    await application.update_queue.put(Update.de_json(data, application.bot))
    return web.Response(text="OK")

# === post_init لإعداد webhook بعد التشغيل ===
async def post_init(application: Application):
    await application.bot.set_webhook(url=WEBHOOK_URL)

# === Main app setup ===
application = Application.builder().token(TOKEN).post_init(post_init).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("add", handle_add))
application.add_handler(CommandHandler("delete", handle_delete))
application.add_handler(CallbackQueryHandler(handle_query))
application.add_handler(MessageHandler(filters.Document.PDF, handle_document))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

# === Web server setup ===
aio_app = web.Application()
aio_app.router.add_get("/", root_handler)  # UptimeRobot
aio_app.router.add_post(f"/telegram-webhook/{TOKEN}", webhook_handler)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8443))
    web.run_app(aio_app, host="0.0.0.0", port=port)