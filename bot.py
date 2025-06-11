import os
import difflib
import re
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# بيانات الكتب المتوفرة
FILES = {
    "ثلاثة الأصول وأدلتها - محمد بن عبد الوهاب": "files/ثلاثة_الاصول.pdf",
    "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf",
    "القواعد الأربعة - محمد بن عبد الوهاب": "files/القواعد_الاربعة.pdf",
    "خلاصة تعظيم العلم - صالح العصيمي": "files/خلاصة_تعظيم_العلم.pdf",
    "شروط الصلاة وأركانها وواجباتها": "files/شروط_الصلاة.pdf",
    "كتاب التوحيد - محمد بن عبد الوهاب": "files/كتاب_التوحيد.pdf",
    "نواقض الإسلام": "files/نواقض_الاسلام.pdf",
}

# دالة لتطبيع النص (إزالة الهمزات والتشكيل)
def normalize(text):
    text = text.lower()
    text = re.sub(r'[إأآا]', 'ا', text)
    text = re.sub(r'[ًٌٍَُِّْـ]', '', text)  # إزالة التشكيل
    text = re.sub(r'[^\w\s]', '', text)  # إزالة الرموز غير الحروف
    return text.strip()

# البحث الذكي في أسماء الكتب
def smart_search(query):
    query_norm = normalize(query)
    normalized_files = {normalize(k): k for k in FILES}

    # بحث تطابق جزئي
    for norm_title, orig_title in normalized_files.items():
        if query_norm in norm_title:
            return orig_title

    # بحث تقريبي
    close_matches = difflib.get_close_matches(query_norm, normalized_files.keys(), n=1, cutoff=0.4)
    if close_matches:
        return normalized_files[close_matches[0]]

    return None

# التوكن من متغير البيئة
TOKEN = os.getenv("BOT_TOKEN")

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("مرحبًا بك في البوت الإسلامي 🌛\nأرسل اسم الكتاب للحصول عليه.")

# التعامل مع الرسائل النصية
async def send_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    match = smart_search(query)

    if match:
        file_path = FILES[match]
        await update.message.reply_text(f"📘 تم العثور على: {match}")
        with open(file_path, "rb") as f:
            await update.message.reply_document(InputFile(f, filename=os.path.basename(file_path)))
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب. تأكد من كتابة الاسم بشكل صحيح.")

# إعداد التطبيق
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# إعداد webhook
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

# عند بدء السيرفر
async def on_startup(app):
    webhook_url = os.getenv("WEBHOOK_URL")
    await application.bot.set_webhook(webhook_url)
    await application.initialize()
    await application.start()

# إعداد السيرفر
web_app = web.Application()
web_app.router.add_post("/webhook", handle_webhook)
web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(web_app, port=8000)