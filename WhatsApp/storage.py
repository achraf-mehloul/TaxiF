import json
from config import ORDERS_DB_FILE

def load_orders():
    try:
        with open(ORDERS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception:
        return {}

def save_orders(data):
    with open(ORDERS_DB_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
