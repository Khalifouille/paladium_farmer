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
    "paladium-ingot": "Paladium Ingot",
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

def send_embed(embed):
    payload = {"embeds": [embed]}
    requests.post(WEBHOOK_URL, json=payload)

def format_price(p):
    return f"{p:,}".replace(",", " ")

def monitor_market():
    print("🚀 Surveillance du marché...")
    while True:
        description = ""
        color = 0x800080 
        has_paladium = False

        for item_id, item_name in ITEMS.items():
            listings = fetch_listings(item_id)
            if not listings:
                continue

            listings.sort(key=lambda x: x["price"])
            lowest = listings[0]
            price = lowest["price"]
            quantity = lowest["quantity"]
            created_at = datetime.fromtimestamp(lowest["createdAt"] / 1000).strftime('%d/%m %H:%M')
            seller = "Moi" if lowest["seller"] == UUID_ME else lowest["seller"]

            lowest_prices[item_id] = price
            save_lowest_prices()

            if "paladium" in item_id:
                has_paladium = True

            description += (
                f"**{item_name}**\n"
                f"🪙 `{format_price(price)} ⛃` | 📦 `{quantity}` | 👤 `{seller}` | ⏱ `{created_at}`\n\n"
            )

        if not description:
            print("⚠️ Aucun item détecté.")
        else:
            embed = {
                "title": "📊 Résumé du Marché - Meilleurs prix actuels",
                "description": description.strip(),
                "color": 0xFFA500 if has_paladium else 0x800080
            }
            send_embed(embed)
            print("✅ Embed marché envoyé.")

        time.sleep(30)

if __name__ == "__main__":
    monitor_market()
