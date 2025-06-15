import os
import sqlite3
import logging
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# === إعداد Google Drive باستخدام حساب خدمة ===
service_account_json = os.getenv("GDRIVE_CREDENTIALS_JSON")
if not service_account_json:
    raise Exception("متغير البيئة GDRIVE_CREDENTIALS_JSON غير موجود!")

with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix=".json") as tmp:
    tmp.write(service_account_json)
    service_account_path = tmp.name

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = service_account.Credentials.from_service_account_file(service_account_path, scopes=SCOPES)
drive_service = build('drive', 'v3', credentials=creds)

# === إعداد قاعدة البيانات ===
conn = sqlite3.connect("books.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scholar TEXT,
    title TEXT,
    url TEXT
)
''')
conn.commit()

# === إعداد البوت ===
TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")  # مثال: https://yourdomain.com
ADMIN_ID = 5650658004

# --- أوامر البوت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT DISTINCT scholar FROM books")
    scholars = cursor.fetchall()
    if not scholars:
        return await update.message.reply_text("لا توجد كتب مضافة حالياً.")
    keyboard = [[InlineKeyboardButton(s[0], callback_data=f"scholar:{s[0]}")] for s in scholars]
    await update.message.reply_text("اختر اسم العالم:", reply_markup=InlineKeyboardMarkup(keyboard))

async def scholar_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    scholar = q.data.split(":", 1)[1]
    cursor.execute("SELECT title FROM books WHERE scholar = ?", (scholar,))
    books = cursor.fetchall()
    if not books:
        return await q.edit_message_text("لا توجد كتب لهذا العالم.")
    kb = [[InlineKeyboardButton(t[0], callback_data=f"book:{t[0]}")] for t in books]
    await q.edit_message_text(f"📚 كتب {scholar}:", reply_markup=InlineKeyboardMarkup(kb))

async def book_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    title = q.data.split(":", 1)[1]
    cursor.execute("SELECT url FROM books WHERE title = ?", (title,))
    res = cursor.fetchone()
    if not res:
        return await q.edit_message_text("الكتاب غير موجود.")
    await q.message.reply_document(document=res[0], caption=title)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.from_user.id != ADMIN_ID:
        return await msg.reply_text("ليس لديك صلاحية.")
    if not context.args or msg.document is None:
        return await msg.reply_text("الاستخدام:\n/add [اسم_العالم] [عنوان_الكتاب] مع إرفاق PDF")
    scholar = context.args[0]
    title = " ".join(context.args[1:])
    doc = await msg.document.get_file()
    local = f"{title}.pdf"
    await doc.download_to_drive(local)
    meta = {'name': local}
    media = MediaFileUpload(local, mimetype='application/pdf')
    uploaded = drive_service.files().create(body=meta, media_body=media, fields='id').execute()
    file_id = uploaded.get('id')
    drive_service.permissions().create(fileId=file_id, body={'type':'anyone','role':'reader'}).execute()
    file_url = f"https://drive.google.com/uc?id={file_id}&export=download"
    cursor.execute("INSERT INTO books (scholar,title,url) VALUES (?,?,?)", (scholar, title, file_url))
    conn.commit()
    os.remove(local)
    await msg.reply_text(f"✅ أضيف الكتاب بنجاح:\n*{title}*\n[رابط التحميل]({file_url})", parse_mode="Markdown")

async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg.from_user.id != ADMIN_ID:
        return await msg.reply_text("ليس لديك صلاحية.")
    if not context.args:
        return await msg.reply_text("الاستخدام:\n/delete [عنوان_الكتاب]")
    title = " ".join(context.args)
    cursor.execute("SELECT url FROM books WHERE title = ?", (title,))
    if not cursor.fetchone():
        return await msg.reply_text("الكتاب غير موجود.")
    cursor.execute("DELETE FROM books WHERE title = ?", (title,))
    conn.commit()
    await msg.reply_text("✅ تم حذف الكتاب.")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    cursor.execute("SELECT title,url FROM books WHERE title LIKE ?", (f"%{txt}%",))
    rows = cursor.fetchall()
    if not rows:
        return await update.message.reply_text("لم يتم العثور على كتاب.")
    for t, u in rows:
        await update.message.reply_document(document=u, caption=t)

# --- تشغيل مع Webhook ---
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("delete", delete))
    app.add_handler(CallbackQueryHandler(scholar_cb, pattern="^scholar:"))
    app.add_handler(CallbackQueryHandler(book_cb, pattern="^book:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    # إعداد Webhook
    webhook_url = f"{WEBHOOK_BASE_URL}/telegram-webhook/{TOKEN}"
    async def on_startup(app):
        await app.bot.set_webhook(webhook_url)
    async def on_shutdown(app):
        await app.bot.delete_webhook()
    app.on_startup(on_startup)
    app.on_shutdown(on_shutdown)

    # تشغيل خادم لاستقبال الطلبات
    port = int(os.getenv("PORT", "8443"))
    from aiohttp import web
    from telegram.ext import aiohttp_helpers
    server = aiohttp_helpers.WebhookServer(application=app, path=f"/telegram-webhook/{TOKEN}")
    web.run_app(server, host="0.0.0.0", port=port)