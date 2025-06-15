# main.py

import os
import json
import sqlite3
import logging

from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# إعدادات البوت
API_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = 5650658004

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


# إعداد Google Drive
creds_info = json.loads(os.getenv("GDRIVE_CREDENTIALS_JSON"))
creds = Credentials.from_service_account_info(creds_info)
drive_service = build("drive", "v3", credentials=creds)


# إعداد قاعدة البيانات
conn = sqlite3.connect("books.db")
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scholar TEXT NOT NULL,
        title TEXT NOT NULL,
        url TEXT NOT NULL
    )
""")
conn.commit()


# ======== Google Drive Functions ========

def create_or_get_folder():
    """إنشاء أو الحصول على مجلد TelegramBooks في Google Drive"""
    results = drive_service.files().list(
        q="mimeType='application/vnd.google-apps.folder' and name='TelegramBooks' and trashed=false",
        spaces='drive'
    ).execute()

    items = results.get('files', [])
    if items:
        return items[0]['id']

    file_metadata = {
        'name': 'TelegramBooks',
        'mimeType': 'application/vnd.google-apps.folder'
    }
    folder = drive_service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')


def upload_to_drive(file_path, file_name):
    """رفع ملف PDF إلى Google Drive وإرجاع رابط التحميل المباشر"""
    folder_id = create_or_get_folder()
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='application/pdf')
    file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()

    file_id = file.get('id')
    drive_service.permissions().create(fileId=file_id, body={
        'type': 'anyone',
        'role': 'reader'
    }).execute()

    return f"https://drive.google.com/uc?id={file_id}&export=download"


# ======== Handlers ========

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    """عرض قائمة العلماء"""
    c.execute("SELECT DISTINCT scholar FROM books")
    scholars = c.fetchall()

    if not scholars:
        await message.answer("لا توجد كتب حالياً.")
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    for s in scholars:
        keyboard.insert(InlineKeyboardButton(s[0], callback_data=f"scholar:{s[0]}"))

    await message.answer("اختر اسم العالم لعرض كتبه:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("scholar:"))
async def show_books(callback_query: types.CallbackQuery):
    """عرض كتب عالم معين"""
    scholar = callback_query.data.split(":")[1]
    c.execute("SELECT title FROM books WHERE scholar=?", (scholar,))
    books = c.fetchall()

    if not books:
        await callback_query.message.answer("لا توجد كتب لهذا العالم.")
        return

    keyboard = InlineKeyboardMarkup(row_width=2)
    for b in books:
        keyboard.insert(InlineKeyboardButton(b[0], callback_data=f"book:{b[0]}|{scholar}"))

    await callback_query.message.answer(f"كتب الشيخ {scholar}:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("book:"))
async def send_book(callback_query: types.CallbackQuery):
    """إرسال كتاب PDF"""
    data = callback_query.data.split(":")[1]
    title, scholar = data.split("|")
    c.execute("SELECT url FROM books WHERE title=? AND scholar=?", (title, scholar))
    result = c.fetchone()

    if result:
        await callback_query.message.answer_document(types.InputFile.from_url(result[0]), caption=title)
    else:
        await callback_query.message.answer("لم يتم العثور على الملف.")


@dp.message_handler(commands=['add'])
async def add_book(message: types.Message):
    """أمر إضافة كتاب (للأدمن فقط)"""
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("أرسل الكتاب بصيغة PDF مع عنوانه واسم العالم بهذا الشكل:\nالشيخ: ...\nالعنوان: ...")


@dp.message_handler(content_types=types.ContentType.DOCUMENT)
async def handle_document(message: types.Message):
    """استقبال ملف PDF وإضافته إلى Google Drive والقاعدة"""
    if message.from_user.id != ADMIN_ID:
        return

    caption = message.caption
    if not caption or "الشيخ:" not in caption or "العنوان:" not in caption:
        await message.answer("يرجى كتابة الوصف بالشكل الصحيح.")
        return

    scholar = caption.split("الشيخ:")[1].split("\n")[0].strip()
    title = caption.split("العنوان:")[1].strip()

    file = await message.document.download()
    file_path = file.name

    try:
        drive_url = upload_to_drive(file_path, title + ".pdf")
        c.execute("INSERT INTO books (scholar, title, url) VALUES (?, ?, ?)", (scholar, title, drive_url))
        conn.commit()
        await message.answer(f"تمت إضافة الكتاب \"{title}\" تحت \"{scholar}\" بنجاح.")
    finally:
        os.remove(file_path)


@dp.message_handler(commands=['delete'])
async def delete_book(message: types.Message):
    """أمر حذف كتاب (للأدمن فقط)"""
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer("أرسل اسم العالم والعنوان بهذا الشكل:\nالشيخ: ...\nالعنوان: ...")


@dp.message_handler(lambda m: m.text and "الشيخ:" in m.text and "العنوان:" in m.text)
async def confirm_delete(message: types.Message):
    """تنفيذ حذف كتاب من القاعدة"""
    if message.from_user.id != ADMIN_ID:
        return

    scholar = message.text.split("الشيخ:")[1].split("\n")[0].strip()
    title = message.text.split("العنوان:")[1].strip()

    c.execute("DELETE FROM books WHERE scholar=? AND title=?", (scholar, title))
    conn.commit()

    await message.answer("تم حذف الكتاب بنجاح.")


# ======== تشغيل البوت ========
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    executor.start_polling(dp, skip_updates=True)