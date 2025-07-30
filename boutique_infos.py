import requests
from datetime import datetime
import time
import json
import os
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()

TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBHOOK_ID = WEBHOOK_URL.split('/')[-2]
WEBHOOK_TOKEN = WEBHOOK_URL.split('/')[-1]

ITEMS = {
    "tile-amethyst-ore": "Bloc d'Amethyst",
    "paladium-ingot": "Lingot de Paladium",
    "food": "Bouffe du Dancarock",
}

API_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
UUID_ME = "820c5f51-4d1a-4d63-ba6c-1126cc96ae58"

LOWEST_FILE = "lowest_prices.json"
MESSAGE_FILE = "last_message.json"
LAST_ANNOUNCES_FILE = "my_last_announces.json"
FOOD_ALERT_FILE = "food_alert_message.json"

# ---- Utils --------------------------------------------------------------

def format_price(p: int) -> str:
    return f"{p:,}".replace(",", " ")

def short_dt(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000).strftime('%d/%m %H:%M')

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

# ---- State -------------------------------------------------------------

lowest_prices = load_json(LOWEST_FILE, {})

def save_lowest_prices():
    save_json(LOWEST_FILE, lowest_prices)

def get_last_message_id():
    data = load_json(MESSAGE_FILE, {})
    return data.get("message_id")

def save_message_id(mid: str):
    save_json(MESSAGE_FILE, {"message_id": mid})

def get_food_alert_message_id():
    data = load_json(FOOD_ALERT_FILE, {})
    return data.get("message_id")

def save_food_alert_message_id(mid: str):
    save_json(FOOD_ALERT_FILE, {"message_id": mid})

def delete_food_alert_message():
    mid = get_food_alert_message_id()
    if mid:
        url = f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}/messages/{mid}"
        print(f"➡️ Suppression du message ID : {mid}")
        resp = requests.delete(url, headers={"Content-Type": "application/json"})
        if resp.status_code in (200, 204):
            print("🗑️ Alerte nourriture supprimée.")
            save_json(FOOD_ALERT_FILE, {})
        else:
            print(f"❌ Échec suppression alerte nourriture : {resp.status_code} - {resp.text}")

# ---- API ---------------------------------------------------------------

def fetch_listings(item_id: str):
    url = f"https://api.paladium.games/v1/paladium/shop/market/items/{item_id}"
    try:
        r = requests.get(url, headers=API_HEADERS, timeout=6)
        r.raise_for_status()
        return r.json().get("listing", [])
    except Exception as e:
        print(f"❌ Erreur pour {item_id} : {e}")
        return []

def fetch_my_announces():
    try:
        r = requests.get(
            f"https://api.paladium.games/v1/paladium/shop/market/players/{UUID_ME}/items",
            headers=API_HEADERS,
            timeout=6
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print(f"❌ Erreur récupération annonces perso : {e}")
        return []

# ---- Embed I/O ---------------------------------------------------------

def send_or_edit_embed(embed):
    payload = {"embeds": [embed]}
    msg_id = get_last_message_id()

    if msg_id:
        resp = requests.patch(
            f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}/messages/{msg_id}",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        if resp.status_code in (200, 204):
            print("🔁 Dashboard mis à jour.")
            return
        else:
            print(f"⚠️ PATCH échoué ({resp.status_code}) : {resp.text} -> nouvel envoi.")

    resp = requests.post(WEBHOOK_URL + "?wait=true", json=payload, headers={"Content-Type": "application/json"})
    if resp.status_code in (200, 204):
        try:
            data = resp.json()
            mid = data.get("id")
            if mid:
                save_message_id(mid)
                print("📤 Dashboard envoyé (nouveau).")
            else:
                print("⚠️ Réponse sans ID message (mais envoyé).")
        except Exception as e:
            print(f"⚠️ Impossible de parser la réponse du webhook : {e}")
    else:
        print(f"❌ POST échoué : {resp.status_code} - {resp.text}")

# ---- Dashboard builder -------------------------------------------------

def build_dashboard():
    market_lines = []
    my_lines = []
    has_paladium = False

    for item_id, item_name in ITEMS.items():
        if item_id == "food":
            continue 

        listings = fetch_listings(item_id)
        if not listings:
            continue

        listings.sort(key=lambda x: x["price"])
        best = listings[0]
        best_price = best["price"]
        best_qty = best["quantity"]
        best_seller = "Moi" if best["seller"] == UUID_ME else best["seller"]
        best_time = short_dt(best["createdAt"])
        suggested = max(best_price - (0 if best_seller == "Moi" else 1), 1)

        lowest_prices[item_id] = best_price

        market_lines.append(
            f"**{item_name}**\n"
            f"🪙 `{format_price(best_price)} ⛃` | 📦 `{best_qty}` | 👤 `{best_seller}` | ⏱ `{best_time}`\n"
            f"💡 **Vendre à :** `{format_price(suggested)} ⛃`\n"
        )

        if "paladium" in item_id:
            has_paladium = True

    save_lowest_prices()

    current_announces = fetch_my_announces()
    total_gains = 0
    total_potential_gains = 0
    annonces_lines = []

    previous_announces = load_json(LAST_ANNOUNCES_FILE, [])
    prev_set = {(a["item"]["name"], a["price"], a["item"]["quantity"]) for a in previous_announces}
    curr_set = {(a["item"]["name"], a["price"], a["item"]["quantity"]) for a in current_announces}
    sold = prev_set - curr_set

    for name, price, qty in sold:
        total_gains += price * qty

    if current_announces:
        for item in current_announces:
            raw_name = item["item"]["name"].replace("palamod:", "").replace("tile.", "").replace("-", " ").title()
            qte = item["item"]["quantity"]
            prix_unitaire = item["price"]
            prix_total = prix_unitaire * qte
            total_potential_gains += prix_total
            annonces_lines.append(f"• {qte}x {raw_name} @ {format_price(prix_unitaire)} ⛃")
    else:
        annonces_lines.append("✅ Tu as tout vendu !")

    save_json(LAST_ANNOUNCES_FILE, current_announces)

    if not market_lines:
        description = "⚠️ Aucun item détecté pour le moment."
    else:
        description = (
            "🔎 **Statistiques pour les ventes**\n\n" +
            "\n━━━━━━━━━━━━━━━\n\n".join(market_lines)
        )

    my_annonces_value = (
        "\n━━━━━━━━━━━━━━━\n"
        "\n📦 **Tes ventes en cours**\n\n" +
        "\n".join(annonces_lines)
    )

    if total_potential_gains > 0:
        my_annonces_value += f"\n\n💰 Tu pourrais gagner **{format_price(total_potential_gains)} ⛃** si tout se vend."

    if total_gains > 0:
        my_annonces_value += f"\n💸 Tu as gagné **{format_price(total_gains)} ⛃** grâce à tes ventes récentes."

    embed = {
        "title": "Paladium - Dashboard Marché",
        "description": description.strip(),
        "fields": [
            {
                "name": "⠀",
                "value": my_annonces_value[:1024],
                "inline": False
            }
        ],
        "color": 0xFFA500 if has_paladium else 0x800080,
        "thumbnail": {
            "url": f"https://api.mineatar.io/face/{UUID_ME}?scale=12"
        },
        "footer": {
            "text": "Dernière mise à jour"
        },
        "timestamp": datetime.utcnow().isoformat()
    }

    return embed

# ---- Loop --------------------------------------------------------------

def monitor_food_alert():
    listings = fetch_listings("food")
    cheap_food = [item for item in listings if item["price"] <= 4]

    if cheap_food:
        cheapest = min(cheap_food, key=lambda x: x["price"])
        price = cheapest["price"]
        quantity = cheapest["quantity"]
        seller = cheapest["seller"]
        time_posted = short_dt(cheapest["createdAt"])

        embed = {
            "title": "🍗 Alerte Nourriture Pas Chère !",
            "description": f"Un item **Food** est en vente à **{format_price(price)} ⛃** seulement !",
            "fields": [
                {"name": "Quantité", "value": str(quantity), "inline": True},
                {"name": "Vendeur", "value": seller, "inline": True},
                {"name": "Mis en vente", "value": time_posted, "inline": True}
            ],
            "color": 0x00FF00,
            "timestamp": datetime.utcnow().isoformat()
        }

        payload = {"embeds": [embed]}
        msg_id = get_food_alert_message_id()

        if msg_id:
            resp = requests.patch(
                f"https://discord.com/api/webhooks/{WEBHOOK_ID}/{WEBHOOK_TOKEN}/messages/{msg_id}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            if resp.status_code == 200:
                print("🔁 Alerte nourriture mise à jour.")
                return
        resp = requests.post(WEBHOOK_URL + "?wait=true", json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code == 200:
            mid = resp.json().get("id")
            if mid:
                save_food_alert_message_id(mid)
                print("📤 Alerte nourriture envoyée.")
    else:
        delete_food_alert_message()
        print("❌ Plus d’alerte nourriture (aucune en dessous de 5⛃).")

def monitor_market():
    print("🚀 Dashboard marché lancé…")
    while True:
        embed = build_dashboard()
        send_or_edit_embed(embed)
        monitor_food_alert()
        time.sleep(30)

if __name__ == "__main__":
    monitor_market()
