from flask import Flask, request
import requests
import asyncio
import threading

from config import WHATSAPP_ACCESS_TOKEN, WHATSAPP_PHONE_NUMBER_ID, WHATSAPP_VERIFY_TOKEN
from onde_api import prepare_order, confirm_order, get_order_offer, get_trip_summary
from maps_api import geocode_address, get_route_info
from storage import load_orders, save_orders
from websocket_listener import listen_notifications

app = Flask(__name__)

ORDERS = load_orders()
USER_TEMP = {}

def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v17.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    r = requests.post(url, headers=headers, json=payload)
    return r.json()

@app.route("/whatsapp/webhook", methods=["GET", "POST"])
def whatsapp_webhook():
    if request.method == "GET":
        if request.args.get("hub.verify_token") == WHATSAPP_VERIFY_TOKEN:
            return request.args.get("hub.challenge")
        return "Error", 403

    if request.method == "POST":
        data = request.get_json()
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                for msg in messages:
                    handle_message(msg, value.get("contacts", [])[0])
        return "ok", 200

def handle_message(msg, contact):
    from_number = contact["wa_id"]
    text = msg.get("text", {}).get("body", "").strip()

    if text == "طلب تكسي":
        USER_TEMP[from_number] = {}
        send_whatsapp_message(from_number, "📍 أرسل عنوان الانطلاق:")
    elif "from" not in USER_TEMP.get(from_number, {}):
        geo = geocode_address(text)
        if geo:
            USER_TEMP[from_number]["from"] = geo
            send_whatsapp_message(from_number, "✅ تم تسجيل نقطة الانطلاق.\nالآن أرسل عنوان الوجهة:")
        else:
            send_whatsapp_message(from_number, "❌ ما قدرناش نلقاو العنوان. جرب تكتب عنوان أدق.")
    elif "to" not in USER_TEMP[from_number]:
        geo = geocode_address(text)
        if geo:
            USER_TEMP[from_number]["to"] = geo
            route = get_route_info(
                (USER_TEMP[from_number]["from"]["lat"], USER_TEMP[from_number]["from"]["lng"]),
                (geo["lat"], geo["lng"])
            )
            if route:
                send_whatsapp_message(from_number, f"📏 المسافة: {route['distance_text']}\n⏱️ الوقت: {route['duration_text']}\nاكتب 'تأكيد' باش نحجز التاكسي.")
        else:
            send_whatsapp_message(from_number, "❌ ما قدرناش نلقاو الوجهة.")
    elif text.lower() == "تأكيد":
        temp = USER_TEMP[from_number]
        waypoints = [
            {"exactLatLng":{"lat":temp['from']['lat'],"lng":temp['from']['lng']}},
            {"exactLatLng":{"lat":temp['to']['lat'],"lng":temp['to']['lng']}}
        ]
        prep = prepare_order(waypoints)
        order_id = prep.get("orderId")
        conf_id = prep.get("confirmationId")
        client = {"clientId": from_number, "name": contact.get("profile", {}).get("name", "WhatsAppUser"), "phone": from_number}
        conf = confirm_order(order_id, conf_id, client)
        ORDERS[order_id] = {"user": from_number, "status": "CREATED"}
        save_orders(ORDERS)
        send_whatsapp_message(from_number, f"✅ تم تأكيد رحلتك!\nرقم الطلب: {order_id}")

async def ws_listener(data):
    order_id = data.get("orderId")
    status = data.get("status")
    if not order_id or not status:
        return
    order = ORDERS.get(order_id)
    if not order:
        return
    user = order["user"]
    text = f"🔔 تحديث الحالة: {status}"
    if status == "FINISHED_PAID":
        summary = get_trip_summary(order_id)
        if summary:
            text = f"🏁 الرحلة انتهت. السعر النهائي: {summary.get('finalCost')} {summary.get('currency')}"
    send_whatsapp_message(user, text)
    ORDERS[order_id]["status"] = status
    save_orders(ORDERS)

def run_ws():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(listen_notifications(ws_listener))

if __name__ == "__main__":
    threading.Thread(target=run_ws, daemon=True).start()
    app.run(port=5000, debug=True)
