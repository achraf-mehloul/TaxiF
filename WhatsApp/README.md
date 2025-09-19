# 🚖 Taxi WhatsApp Bot - README

## 📦 المتطلبات
- Python 3.9 أو أحدث
- حساب Meta for Developers مفعّل مع **WhatsApp Business Platform**
- حساب Onde API (مع Token صالح)
- مفتاح Google Maps API

---

## ⚙️ الإعداد

1. فك الضغط عن الملف المضغوط.

2. ثبّت المكتبات:
   ```bash
   pip install -r requirements.txt
   ```

3. عدّل ملف **config.py** وضع القيم الصحيحة:
   ```python
   # WhatsApp API
   WHATSAPP_ACCESS_TOKEN = "ضع التوكن هنا"
   WHATSAPP_PHONE_NUMBER_ID = "ضع رقم الهاتف ID"
   WHATSAPP_VERIFY_TOKEN = "ضع رمز التحقق"

   # Onde API
   ONDE_API_TOKEN = "ضع التوكن من Onde"
   ONDE_HOST = "api.onde.app"

   # Google Maps
   GOOGLE_MAPS_API_KEY = "ضع مفتاح Google Maps"
   ```

4. شغّل البوت محليًا:
   ```bash
   python app.py
   ```

---

## 🧪 الاختبار
- استعمل Postman أو curl لإرسال رسالة تجريبية عبر WhatsApp Cloud API.
- إذا كل شيء مضبوط، رح يرد البوت بالبيانات من Onde API.
