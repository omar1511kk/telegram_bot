import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# إعدادات البوت
TOKEN = "ضع التوكن هنا"
ADMIN_ID = 5650658004

# قاعدة البيانات للمستخدمين
conn = sqlite3.connect("users.db", check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        country TEXT
    )
""")
conn.commit()

# تخزين الكتب
FILES = {}  # {scholar: {title: filepath}}
BOOKS = {}  # {book_id: (scholar, title)}
BOOK_COUNTER = 0

def get_book_id(scholar, title):
    global BOOK_COUNTER
    BOOK_COUNTER += 1
    BOOKS[str(BOOK_COUNTER)] = (scholar, title)
    return str(BOOK_COUNTER)

def load_books():
    global BOOK_COUNTER
    for root, dirs, files in os.walk("books"):
        for file in files:
            if file.endswith(".pdf"):
                scholar = os.path.basename(root)
                title = os.path.splitext(file)[0]
                FILES.setdefault(scholar, {})[title] = os.path.join(root, file)
                get_book_id(scholar, title)

def build_main_menu():
    keyboard = [[InlineKeyboardButton(scholar, callback_data=f"s:{scholar}")] for scholar in FILES.keys()]
    keyboard.append([InlineKeyboardButton("➕ إضافة كتاب", callback_data="add_book")])
    return InlineKeyboardMarkup(keyboard)

def build_books_menu(scholar, is_admin=False):
    keyboard = []
    for title in FILES[scholar].keys():
        book_id = [k for k, v in BOOKS.items() if v == (scholar, title)][0]
        keyboard.append([InlineKeyboardButton(title, callback_data=f"b:{book_id}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

# بدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أهلاً بك في البوت الإسلامي! اختر أحد العلماء لعرض كتبه:",
        reply_markup=build_main_menu()
    )

# التعامل مع الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back":
        await query.edit_message_text(
            "أهلاً بك! اختر أحد العلماء:",
            reply_markup=build_main_menu()
        )

    elif data.startswith("s:"):
        scholar = data[2:]
        is_admin = query.from_user.id == ADMIN_ID
        await query.edit_message_text(
            f"📚 كتب {scholar}:",
            reply_markup=build_books_menu(scholar, is_admin)
        )

    elif data.startswith("b:"):
        book_id = data[2:]
        scholar, title = BOOKS.get(book_id, (None, None))
        if not scholar or not title:
            await query.edit_message_text("❌ لم يتم العثور على الكتاب.")
            return

        file_path = FILES[scholar].get(title)
        if not file_path:
            await query.edit_message_text("❌ الملف غير موجود.")
            return

        keyboard = []
        if query.from_user.id == ADMIN_ID:
            keyboard.append([
                InlineKeyboardButton("🗑 حذف الكتاب", callback_data=f"d:{book_id}")
            ])

        await context.bot.send_document(
            chat_id=query.message.chat_id,
            document=InputFile(file_path),
            caption=f"📖 {title}\n👤 {scholar}",
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
        )

    elif data.startswith("d:") and query.from_user.id == ADMIN_ID:
        book_id = data[2:]
        scholar, title = BOOKS.get(book_id, (None, None))
        if not scholar:
            await query.edit_message_text("❌ لم يتم العثور على الكتاب.")
            return

        path = FILES[scholar].pop(title, None)
        if path and os.path.exists(path):
            os.remove(path)
        BOOKS.pop(book_id, None)

        await query.edit_message_text("✅ تم حذف الكتاب.", reply_markup=build_main_menu())

    elif data == "add_book" and query.from_user.id == ADMIN_ID:
        await query.edit_message_text(
            "📤 أرسل الآن ملف PDF وسأضيفه تلقائيًا.\nصيغة الاسم: اسم_العالم - عنوان_الكتاب.pdf"
        )
        context.user_data["awaiting_file"] = True

# استقبال ملفات PDF من الأدمن
async def document_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("awaiting_file") and update.message.document:
        doc = update.message.document
        file_name = doc.file_name

        if not file_name.endswith(".pdf") or "-" not in file_name:
            await update.message.reply_text("⚠ يجب أن يكون الاسم بصيغة: العالم - الكتاب.pdf")
            return

        scholar, title = [x.strip() for x in file_name[:-4].split("-", 1)]
        os.makedirs(f"books/{scholar}", exist_ok=True)
        path = f"books/{scholar}/{title}.pdf"

        await doc.get_file().download_to_drive(path)
        FILES.setdefault(scholar, {})[title] = path
        get_book_id(scholar, title)

        await update.message.reply_text(f"✅ تم إضافة الكتاب: {title} 👤 {scholar}")
        context.user_data["awaiting_file"] = False

# تشغيل البوت
if __name__ == "__main__":
    load_books()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.PDF, document_handler))

    print("🤖 Bot is running...")
    app.run_polling()