# ✅ استيراد المكتبات الضرورية
import os
import difflib
import unicodedata
import sqlite3
import hashlib
import uuid
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
# ✅ قاعدة البيانات لتخزين الكتب
# =====================================================

def init_db():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            author TEXT NOT NULL,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            original_name TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def load_books():
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("SELECT author, title, file_path, original_name FROM books")
    books = {}
    for author, title, path, original_name in cursor.fetchall():
        books.setdefault(author, {})[title] = path
    conn.close()
    return books

def save_book(author, title, file_path, original_name):
    conn = sqlite3.connect("books.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO books (author, title, file_path, original_name) VALUES (?, ?, ?, ?)",
                   (author, title, file_path, original_name))
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
    text = text.replace("_", " ")  # معالجة الشرطات السفلية
    return text.lower().strip()

def smart_search(query):
    norm_query = normalize(query)
    flat = {
        normalize(f"{author} {title}"): (author, title)
        for author, books in FILES.items()
        for title in books
    }

    # البحث الدقيق أولاً
    exact_matches = [original for norm, original in flat.items() if norm_query == norm]
    if exact_matches:
        return exact_matches[0]
    
    # ثم البحث الجزئي
    partial_matches = [original for norm, original in flat.items() if norm_query in norm]
    if partial_matches:
        return partial_matches[0]
    
    # ثم البحث التقريبي
    close = difflib.get_close_matches(norm_query, flat.keys(), n=1, cutoff=0.6)
    return flat[close[0]] if close else None

# =====================================================
# ✅ الأوامر الرئيسية
# =====================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.first_name or "أخي الكريم"
    user_id = update.effective_user.id
    
    # إنشاء لوحة المفاتيح مع أسماء المؤلفين فقط
    keyboard = []
    authors = list(FILES.keys())
    for i in range(0, len(authors), 2):
        row = []
        for author in authors[i:i+2]:
            # إنشاء معرّف فريد مختصر للمؤلف
            author_id = hashlib.md5(author.encode()).hexdigest()[:8]
            row.append(InlineKeyboardButton(author, callback_data=f"author|{author_id}"))
            # تخزين الاسم الكامل مقابل المعرّف المختصر
            context.chat_data[author_id] = author
        keyboard.append(row)

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
    for title in books:  # عرض جميع الكتب
        # إنشاء معرّف فريد مختصر للكتاب
        book_id = hashlib.md5(f"{author}|{title}".encode()).hexdigest()[:8]
        # تخزين معلومات الكتاب مقابل المعرّف المختصر
        context.chat_data[book_id] = (author, title)
        row.append(InlineKeyboardButton(title, callback_data=f"book|{book_id}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # إضافة زر للعودة
    author_id = hashlib.md5(author.encode()).hexdigest()[:8]
    context.chat_data[author_id] = author  # تخزين مؤقت للمؤلف
    buttons.append([InlineKeyboardButton("🔙 العودة", callback_data=f"author|{author_id}")])

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
        author_id = data.split("author|")[1]
        author = context.chat_data.get(author_id)
        if author:
            await show_books_by_author(update, context, author)
        else:
            await query.message.reply_text("❌ لم يتم العثور على المؤلف.")

    elif data.startswith("book|"):
        book_id = data.split("book|")[1]
        book_info = context.chat_data.get(book_id)
        if book_info:
            author, title = book_info
            file_path = FILES.get(author, {}).get(title)
            if file_path:
                with open(file_path, "rb") as f:
                    await query.message.reply_document(
                        InputFile(f, filename=f"{author} - {title}.pdf")
                    )
                return
        await query.message.reply_text("❌ لم يتم العثور على الكتاب.")

    elif data == "add_book" and user_id == ADMIN_ID:
        await query.edit_message_text("📥 أرسل ملف PDF. يجب أن يكون اسم الملف بالصيغة: المؤلف - العنوان.pdf\n\n"
                                     "مثال: محمد بن عبد الوهاب - القواعد الأربعة.pdf")

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
            await update.message.reply_document(
                InputFile(f, filename=f"{author} - {title}.pdf")
            )
    else:
        # البحث التقريبي
        all_titles = [title for books in FILES.values() for title in books]
        close_matches = difflib.get_close_matches(query, all_titles, n=3, cutoff=0.5)
        
        if close_matches:
            response = "❌ لم أجد الكتاب، هل تقصد:\n"
            for match in close_matches:
                response += f"- {match}\n"
            await update.message.reply_text(response)
        else:
            await update.message.reply_text("❌ لم يتم العثور على الكتاب. جرب كتابة اسم الكتاب بشكل مختلف.")

async def add_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 هذا الأمر للأدمن فقط.")

    doc = update.message.document
    if not doc or not doc.file_name.lower().endswith(".pdf"):
        return await update.message.reply_text("📎 أرسل ملف PDF بصيغة: المؤلف - العنوان.pdf\n\n"
                                             "مثال: محمد بن عبد الوهاب - القواعد الأربعة.pdf")

    # حفظ الاسم الأصلي للملف
    original_name = doc.file_name
    
    # التحقق من صيغة اسم الملف
    if '-' not in original_name:
        return await update.message.reply_text("❗ اسم الملف يجب أن يحتوي على شرطة '-' لفصل المؤلف عن العنوان.\n\n"
                                             "مثال: محمد بن عبد الوهاب - القواعد الأربعة.pdf")

    # إزالة الامتداد .pdf
    name_without_ext = re.sub(r'\.pdf$', '', original_name, flags=re.IGNORECASE)
    
    # تقسيم الاسم إلى مؤلف وعنوان باستخدام الشرطة فقط
    parts = name_without_ext.split('-', 1)  # الانقسام على أول شرطة فقط
    if len(parts) < 2:
        return await update.message.reply_text("❗ تعذر استخراج المؤلف والعنوان. يرجى استخدام الصيغة: المؤلف - العنوان.pdf\n\n"
                                             "مثال: محمد بن عبد الوهاب - القواعد الأربعة.pdf")

    author = parts[0].strip()
    title = parts[1].strip()

    # إنشاء مجلد files إذا لم يكن موجوداً
    os.makedirs("files", exist_ok=True)
    
    # إنشاء اسم ملف آمن مع الحفاظ على المسافات
    safe_file_name = f"{author} - {title}.pdf"
    file_path = f"files/{safe_file_name}"

    # تحميل الملف
    try:
        file = await doc.get_file()
        await file.download_to_drive(file_path)
    except Exception as e:
        return await update.message.reply_text(f"❌ حدث خطأ أثناء تحميل الملف: {str(e)}")

    # حفظ في قاعدة البيانات
    save_book(author, title, file_path, original_name)
    FILES.setdefault(author, {})[title] = file_path

    # إرسال تأكيد مفصل
    await update.message.reply_text(
        f"✅ تم إضافة الكتاب بنجاح:\n"
        f"👤 المؤلف: {author}\n"
        f"📖 العنوان: {title}\n"
        f"📁 تم حفظه باسم: {safe_file_name}"
    )

async def delete_book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return await update.message.reply_text("🚫 هذا الأمر للأدمن فقط.")

    title = " ".join(context.args)
    if not title:
        return await update.message.reply_text("❗ يرجى تحديد اسم الكتاب\nمثال: /delete القواعد الأربعة")
    
    result = smart_search(title)
    if result:
        author, real_title = result
        try:
            os.remove(FILES[author][real_title])
        except FileNotFoundError:
            pass
        del FILES[author][real_title]
        remove_book(author, real_title)
        await update.message.reply_text(f"✅ تم حذف الكتاب: {real_title}")
    else:
        await update.message.reply_text("❌ لم يتم العثور على الكتاب.")

# =====================================================
# ✅ التشغيل بواسطة Webhook
# =====================================================

def main():
    # تهيئة قاعدة البيانات وملفات الكتب
    init_db()
    os.makedirs("files", exist_ok=True)
    
    global FILES
    FILES = load_books()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("delete", delete_book))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.Document.PDF, add_book))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, send_file))

    async def on_startup(app):
        await application.initialize()
        await application.start()
        await application.bot.set_webhook(WEBHOOK_URL)

    async def handle_webhook(request):
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
        return web.Response()

    async def handle_home(request):
        return web.Response(text="✅ البوت يعمل بنجاح!", status=200)

    web_app = web.Application()
    web_app.router.add_post("/webhook", handle_webhook)
    web_app.router.add_get("/", handle_home)
    web_app.on_startup.append(on_startup)

    port = int(os.getenv("PORT", 8000))
    web.run_app(web_app, port=port)

if __name__ == "__main__":
    main()