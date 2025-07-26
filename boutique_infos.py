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
    "paladium-ingot": "Paladium Ore",
}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
UUID_ME = "820c5f51-4d1a-4d63-ba6c-1126cc96ae58"

LOWEST_FILE = "lowest_prices.json"

if os.path.exists(LOWEST_FILE):
    with open(LOWEST_FILE, "r") as f:
        lowest_prices = json.load(f)
else:
    lowest_prices = {}

def save_lowest_prices():
    with open(LOWEST_FILE, "w") as f:
        json.dump(lowest_prices, f)

def fetch_listings(item_id):
    url = f"https://api.paladium.games/v1/paladium/shop/market/items/{item_id}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=5)
        response.raise_for_status()
        return response.json().get("listing", [])
    except Exception as e:
        print(f"❌ Erreur pour {item_id} : {e}")
        return []

def generate_dashboard_embed():
    embeds = []
    for item_id, item_name in ITEMS.items():
        listings = fetch_listings(item_id)
        if not listings:
            continue

        listings_sorted = sorted(listings, key=lambda x: x["price"])
        lowest_listing = listings_sorted[0]
        lowest_price = lowest_listing["price"]
        seller = lowest_listing["seller"]

        my_listings = [l for l in listings if l["seller"] == UUID_ME]
        my_price = my_listings[0]["price"] if my_listings else None

        # Suggestion de prix
        suggested_price = lowest_price if seller == UUID_ME else max(1, lowest_price - 1)
        is_me_lowest = seller == UUID_ME

        lowest_prices[item_id] = lowest_price
        save_lowest_prices()

        embed = {
            "title": f"📊 {item_name}",
            "color": 0x00ff99 if is_me_lowest else 0xFFA500,
            "fields": [
                {"name": "📉 Prix le + bas", "value": f"{lowest_price} ⛃ (par {'toi' if is_me_lowest else 'autre'})", "inline": True},
                {"name": "📦 Ton prix", "value": f"{my_price} ⛃" if my_price else "Aucune vente", "inline": True},
                {"name": "💡 À vendre", "value": f"{suggested_price} ⛃", "inline": True}
            ],
            "footer": {"text": f"Mis à jour le {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }

        embeds.append(embed)

    return embeds

def send_dashboard():
    embeds = generate_dashboard_embed()
    if not embeds:
        return

    payload = {"embeds": embeds}
    try:
        requests.post(WEBHOOK_URL, json=payload)
        print(f"📤 Dashboard envoyé à {datetime.now().strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi du webhook : {e}")

def monitor_loop():
    print("🚨 Surveillance du marché (dashboard toutes les 30s)...")
    while True:
        send_dashboard()
        time.sleep(30)

if __name__ == "__main__":
    monitor_loop()
