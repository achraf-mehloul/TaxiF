import requests

token = "37bd2447-2f9a-4d1d-a235-99715fbffcbf"

url = "https://api-sandbox.onde.app/dispatch/v1/company/"


headers = {
    "Authorization": f"Bearer {token}",
    "User-Agent": "MyApp/1.0",  
    "Content-Type": "application/json"
}

try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code == 200:
        print("✅ التوكن شغال")
        print("📦 بيانات الشركة:", response.json())
    elif response.status_code == 401:
        print("❌ فشل التحقق: التوكن منتهي أو غير صالح")
    else:
        print(f"❌ خطأ: {response.status_code} - {response.text}")
except requests.exceptions.RequestException as e:
    print(f"❌ مشكلة في الاتصال: {e}")
