import os
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# بيانات الكتب
FILES = {
    "محمد بن عبد الوهاب ثلاثة الأصول وأدلتها": "files/ثلاثة_الاصول.pdf",
    "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf",
    "القواعد الأربعة محمد بن عبد الوهاب": "files/القواعد_الاربعة.pdf",
    "خلاصة تعظيم العلم صالح العصيمي": "files/خلاصة_تعظيم_العلم.pdf",
    "شروط الصلاة،وأركانها، وواجباتها": "files/شروط_الصلاة.pdf",
    "كتاب التوحيد محمد بن عبد الوهاب": "files/كتاب_التوحيد.pdf",
    "نواقض الإسلام": "files/نواقض_الاسلام.pdf",
}

# توكن البوت
TOKEN = os.getenv("BOT_TOKEN")

# التطبيق
application = Application.builder().token(TOKEN).build()

# أوامر ومهام
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحبًا بك في البوت الإسلامي 🌙\nأرسل اسم الكتاب للحصول عليه.")

async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if query in FILES:
        file_path = FILES[query]
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب. تأكد من كتابة الاسم بشكل صحيح.")

# إضافة الهاندلرز
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# webhook handler
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

# عند بدء التشغيل
async def on_startup(app):
    await application.initialize()
    webhook_url = os.getenv("WEBHOOK_URL") or "https://telegram-bot-uho8.onrender.com/webhook"
    await application.bot.set_webhook(webhook_url)
    await application.start()

# إعداد السيرفر
web_app = web.Application()
web_app.router.add_post("/webhook", handle_webhook)
web_app.on_startup.append(on_startup)

# تشغيل الخادم
if __name__ == "__main__":
    web.run_app(web_app, port=8000)