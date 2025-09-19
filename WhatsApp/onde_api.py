import requests
from config import ONDE_BASE_V2, ONDE_BASE_V1, ONDE_API_TOKEN

HEADERS = {
    "Authorization": f"Operator {ONDE_API_TOKEN}",
    "User-Agent": "whatsapp-taxi-bot/1.0",
    "Content-Type": "application/json"
}

def prepare_order(waypoints, currency=None, unit_of_length="KILOMETER"):
    url = f"{ONDE_BASE_V2}/order/prepare"
    body = {"waypoints": waypoints, "unitOfLength": unit_of_length}
    if currency:
        body["currency"] = currency
    resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()

def confirm_order(order_id, confirmation_id, client, payment_methods=["CASH"]):
    url = f"{ONDE_BASE_V2}/order/confirm/{order_id}"
    body = {
        "confirmationId": confirmation_id,
        "client": client,
        "paymentMethods": payment_methods
    }
    resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.json()

def get_order_offer(order_id):
    url = f"{ONDE_BASE_V1}/order/{order_id}/offer"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None

def get_trip_summary(order_id):
    url = f"{ONDE_BASE_V1}/order/{order_id}/summary"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    return None
