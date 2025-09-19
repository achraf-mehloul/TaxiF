import requests
from config import ONDE_BASE_V2, ONDE_BASE_V1, ONDE_API_TOKEN

HEADERS = {
    "Authorization": f"Operator {ONDE_API_TOKEN}",
    "User-Agent": "telegram-taxi-bot/1.0",
    "Content-Type": "application/json"
}

def prepare_order(waypoints, currency=None, unit_of_length="KILOMETER", pickup_time=None, special_cost=None):
    url = f"{ONDE_BASE_V2}/order/prepare"
    body = {"waypoints": waypoints, "unitOfLength": unit_of_length}
    if currency:
        body["currency"] = currency
    if pickup_time:
        body["pickupTime"] = pickup_time
    if special_cost:
        body["specialCost"] = special_cost
    resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
    if resp.status_code == 401:
        raise requests.HTTPError("401 Unauthorized from Onde API. Check ONDE_API_TOKEN and ONDE_HOST.", response=resp)
    resp.raise_for_status()
    return resp.json()

def update_prepared_order(order_id, waypoints, currency=None, unit_of_length="KILOMETER"):
    url = f"{ONDE_BASE_V2}/order/prepare/{order_id}"
    body = {"waypoints": waypoints, "unitOfLength": unit_of_length}
    if currency:
        body["currency"] = currency
    resp = requests.put(url, json=body, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.json()

def confirm_order(order_id, confirmation_id, client, extra_options=None, number_of_seats=1, vehicle_type="CLASSIC", tariff_type="PRECISE", payment_methods=["CASH"], prepaid=False, manual_assign_driver=None):
    url = f"{ONDE_BASE_V2}/order/confirm/{order_id}"
    body = {
        "confirmationId": confirmation_id,
        "client": client,
        "numberOfSeats": number_of_seats,
        "vehicleType": vehicle_type,
        "tariffType": tariff_type,
        "paymentMethods": payment_methods,
        "prepaid": prepaid
    }
    if extra_options:
        body["extraOptions"] = extra_options
    if manual_assign_driver:
        body["manualAssignDriver"] = manual_assign_driver
    resp = requests.post(url, json=body, headers=HEADERS, timeout=20)
    if resp.status_code == 401:
        raise requests.HTTPError("401 Unauthorized when confirming order. Check ONDE_API_TOKEN and permissions.", response=resp)
    resp.raise_for_status()
    return resp.json()

def get_order_offer(order_id):
    url = f"{ONDE_BASE_V1}/order/{order_id}/offer"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 204:
        return None
    if resp.status_code == 401:
        raise requests.HTTPError("401 Unauthorized when fetching offer.", response=resp)
    resp.raise_for_status()

def get_order_update(order_id):
    url = f"{ONDE_BASE_V1}/order/{order_id}/update"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 404:
        return None
    resp.raise_for_status()

def get_trip_summary(order_id):
    url = f"{ONDE_BASE_V1}/order/{order_id}/summary"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code == 200:
        return resp.json()
    resp.raise_for_status()
