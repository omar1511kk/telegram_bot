import os
import difflib
import unicodedata
from aiohttp import web
from telegram import Update, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

# ✅ إزالة التشكيل والهمزات والنormalization
def normalize(text):
    text = unicodedata.normalize("NFKD", text)
    text = ''.join([c for c in text if not unicodedata.combining(c)])  # إزالة التشكيل
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه")
    return text.lower().strip()

# ✅ قاعدة بيانات الكتب
FILES = {
    "العقيدة الواسطية": "files/العقيدة_الواسطية.pdf",
    "القواعد الأربعة محمد بن عبد الوهاب": "files/القواعد_الأربعة_محمد_بن_عبد_الوهاب.pdf",
    "شروط الصلاة، وأركانها، وواجباتها.": "files/شروط_الصلاة_وأركانها_وواجباتها.pdf",
    "كتاب التوحيد محمد بن عبد الوهاب.": "files/كتاب_التوحيد_محمد_بن_عبد_الوهاب.pdf",
    "محمد بن عبد الوهاب ثلاثة الأصول وأدلتها.": "files/محمد_بن_عبد_الوهاب_ثلاثة_الأصول_وأدلتها.pdf",
    "نواقض الإسلام": "files/نواقض_الاسلام.pdf",
    "خلاصة تعظيم العلم صالح العصيمي": "files/خلاصة_تعظيم_العلم_صالح_العصيمي.pdf"
}

# 🔍 البحث الذكي
def smart_search(query):
    norm_query = normalize(query)
    norm_titles = {normalize(title): title for title in FILES}
    exact_matches = [original for norm, original in norm_titles.items() if norm_query in norm]
    if exact_matches:
        return exact_matches[0]
    # محاولة تقريبية إن لم توجد مطابقة جزئية
    close_matches = difflib.get_close_matches(norm_query, norm_titles.keys(), n=1, cutoff=0.5)
    return norm_titles[close_matches[0]] if close_matches else None

# 📥 التعامل مع الرسائل
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

# ✅ رسالة /start الجديدة
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "السلام عليكم ورحمة الله وبركاته 🌿\n"
        "قال رسول الله ﷺ:\n"
        "«من صلى عليَّ صلاة، صلى الله عليه بها عشرًا» (رواه مسلم)\n\n"
        "🌟 لا تحرم نفسك من هذا الأجر، صلِّ على النبي ﷺ.\n\n"
        "أرسل اسم الكتاب للحصول على نسخه PDF."
    )

# إعداد التطبيق
TOKEN = os.getenv("BOT_TOKEN")
application = Application.builder().token(TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

# Webhook
async def handle_webhook(request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return web.Response()

# بدء التطبيق مع Webhook
async def on_startup(app):
    webhook_url = os.getenv("WEBHOOK_URL")
    await application.bot.set_webhook(webhook_url)
    await application.initialize()
    await application.start()

# إعداد خادم الويب
web_app = web.Application()
web_app.router.add_post("/webhook", handle_webhook)
web_app.on_startup.append(on_startup)

if __name__ == "__main__":
    web.run_app(web_app, port=8000)