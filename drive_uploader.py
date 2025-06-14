import os
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

# إعداد Google Drive مرة واحدة
gauth = GoogleAuth()
gauth.LocalWebserverAuth()  # سيفتح المتصفح لأول مرة لتسجيل الدخول
drive = GoogleDrive(gauth)

# دالة لرفع ملف PDF
def upload_pdf_to_drive(local_file_path, title):
    try:
        file_drive = drive.CreateFile({'title': title})
        file_drive.SetContentFile(local_file_path)
        file_drive.Upload()
        return file_drive['id']  # نعيد ID الخاص بالملف
    except Exception as e:
        print(f"❌ خطأ في رفع الملف إلى Google Drive: {e}")
        return None

# دالة للحصول على رابط التحميل المباشر من ID
def get_direct_download_link(file_id):
    return f"https://drive.google.com/uc?export=download&id={file_id}"