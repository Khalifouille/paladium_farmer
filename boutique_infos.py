import requests
from datetime import datetime
import time
import json
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_ID = WEBHOOK_URL.split('/')[-2]
WEBHOOK_TOKEN = WEBHOOK_URL.split('/')[-1]

ITEMS = {
    "tile-amethyst-ore": "Amethyst Ore",
    "paladium-ingot": "Paladium Ingot",
}
HEADERS = {"Authorization": f"Bearer {TOKEN}"}
UUID_ME = "820c5f51-4d1a-4d63-ba6c-1126cc96ae58"

LOWEST_FILE = "lowest_prices.json"
MESSAGE_FILE = "last_message.json"

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

def send_or_edit_embed(embed):
    message_id = None
    if os.path.exists(MESSAGE_FILE):
        try:
            with open(MESSAGE_FILE, "r") as f:
                message_id = json.load(f).get("message_id")
        except:
            pass

    payload = {"embeds": [embed]}

    if message_id:
        r = requests.patch(
            f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}/messages/{message_id}",
            json=payload
        )
        if r.status_code == 200:
            print("🔁 Message mis à jour.")
            return
        else:
            print(f"⚠️ Erreur modification message ({r.status_code}) : {r.text}")
            message_id = None

    r = requests.post(WEBHOOK_URL, json=payload)
    if r.status_code == 200:
        message_id = r.json().get("id")
        with open(MESSAGE_FILE, "w") as f:
            json.dump({"message_id": message_id}, f)
        print("📤 Nouveau message envoyé.")
    else:
        print(f"❌ Erreur envoi message : {r.status_code} - {r.text}")

def format_price(p):
    return f"{p:,}".replace(",", " ")

def monitor_market():
    print("🚀 Surveillance du marché...")
    while True:
        description = ""
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
            suggested_price = max(price - 1, 1)

            lowest_prices[item_id] = price
            save_lowest_prices()

            if "paladium" in item_id:
                has_paladium = True

            description += (
                f"**{item_name}**\n"
                f"🪙 `{format_price(price)} ⛃` | 📦 `{quantity}` | 👤 `{seller}` | ⏱ `{created_at}`\n"
                f"💡 **Vends à :** `{format_price(suggested_price)} ⛃`\n\n"
            )

        if not description:
            print("⚠️ Aucun item détecté.")
        else:
            embed = {
                "title": "📊 Résumé du Marché - Meilleurs prix & Suggestions",
                "description": description.strip(),
                "color": 0xFFA500 if has_paladium else 0x800080, 
                "timestamp": datetime.utcnow().isoformat()
            }
            send_or_edit_embed(embed)

        time.sleep(30)

if __name__ == "__main__":
    monitor_market()
