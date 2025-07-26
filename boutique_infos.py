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

def send_embed_dashboard(embed_data):
    payload = {"embeds": embed_data}
    requests.post(WEBHOOK_URL, json=payload)

def format_price(p):
    return f"{p:,}".replace(",", " ")

def monitor_market():
    print("🚀 Surveillance du marché (mode dashboard)...")
    while True:
        embeds = []

        for item_id, item_name in ITEMS.items():
            listings = fetch_listings(item_id)
            if not listings:
                continue

            # Trier par prix croissant
            listings.sort(key=lambda x: x["price"])
            lowest_listing = listings[0]

            seller = "Moi" if lowest_listing["seller"] == UUID_ME else lowest_listing["seller"]
            price = lowest_listing["price"]
            quantity = lowest_listing["quantity"]
            created_at = datetime.fromtimestamp(lowest_listing["createdAt"] / 1000).strftime('%Y-%m-%d %H:%M:%S')

            lowest_prices[item_id] = price
            save_lowest_prices()

            color = 0xFFA500 if "paladium" in item_id else 0x800080  

            embed = {
                "title": f"📦 {item_name}",
                "description": (
                    f"**Prix le plus bas actuel :** {format_price(price)} ⛃\n"
                    f"**Quantité :** {quantity}\n"
                    f"**Vendeur :** `{seller}`\n"
                    f"**Mise en vente :** {created_at}"
                ),
                "color": color
            }

            embeds.append(embed)

        if embeds:
            send_embed_dashboard(embeds)
            print("✅ Dashboard envoyé avec les prix les plus bas.")
        else:
            print("⚠️ Aucun item récupéré.")

        time.sleep(30)  

if __name__ == "__main__":
    monitor_market()
