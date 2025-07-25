import requests
from datetime import datetime
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

ITEMS = {
    "tile-amethyst-ore": "Amethyst Ore",
}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

STATE_FILE = "last_created_timestamps.json"

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, "r") as f:
        last_created_timestamps = json.load(f)
    last_created_timestamps = {k: int(v) for k, v in last_created_timestamps.items()}
else:
    last_created_timestamps = {item_id: 0 for item_id in ITEMS}

def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(last_created_timestamps, f)

def fetch_listings(item_id):
    url = f"https://api.paladium.games/v1/paladium/shop/market/items/{item_id}"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        return data.get("listing", [])
    except Exception as e:
        print(f"Erreur pour {item_id} : {e}")
        return []

def send_to_webhook(item):
    embed = {
        "title": f"📦 {item['name']}",
        "description": (
            f"**Quantité :** {item['quantity']}\n"
            f"**Prix :** {item['price']} ⛃\n"
            f"**Vendeur :** `{item['seller']}`\n"
            f"**Date :** {item['created_at']}"
        ),
        "color": 0x00ff99
    }
    payload = {"embeds": [embed]}
    requests.post(WEBHOOK_URL, json=payload)

def monitor_market():
    print("🚨 Surveillance du marché lancée...")
    while True:
        for item_id, item_name in ITEMS.items():
            listings = fetch_listings(item_id)
            listings_sorted = sorted(listings, key=lambda x: x["createdAt"])
            for listing in listings_sorted:
                created_at_raw = listing["createdAt"]
                if created_at_raw > last_created_timestamps.get(item_id, 0):
                    last_created_timestamps[item_id] = created_at_raw
                    save_state()
                    data = {
                        "name": item_name,
                        "quantity": listing["quantity"],
                        "price": listing["price"],
                        "seller": listing["seller"],
                        "created_at_raw": created_at_raw,
                        "created_at": datetime.fromtimestamp(created_at_raw / 1000).strftime('%Y-%m-%d %H:%M:%S')
                    }
                    send_to_webhook(data)
                    print(f"✅ Nouvelle vente détectée pour {item_name}")
            time.sleep(1)
        time.sleep(10)

if __name__ == "__main__":
    monitor_market()
