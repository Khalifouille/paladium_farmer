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
    "tile-amethyst-ore": "Amethyst Ore",
    "paladium-ingot": "Paladium Ingot",
}

API_HEADERS = {"Authorization": f"Bearer {TOKEN}"}
UUID_ME = "820c5f51-4d1a-4d63-ba6c-1126cc96ae58"

LOWEST_FILE = "lowest_prices.json"
MESSAGE_FILE = "last_message.json"

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

    my_by_item = defaultdict(list)

    for item_id, item_name in ITEMS.items():
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

        mine = [l for l in listings if l["seller"] == UUID_ME]
        if mine:
            for l in mine:
                lp = l["price"]
                lq = l["quantity"]
                lt = short_dt(l["createdAt"])
                delta = lp - best_price
                if delta == 0:
                    status = "✅ Plus bas"
                elif delta > 0:
                    status = f"❌ +{format_price(delta)}"
                else:
                    status = f"⭐ {format_price(-delta)} moins cher"

                my_by_item[item_name].append(
                    f"• `{lq}x` @ `{format_price(lp)} ⛃` — {status} (⏱ {lt})"
                )

        if "paladium" in item_id:
            has_paladium = True

    save_lowest_prices()

    if my_by_item:
        for name, lines in my_by_item.items():
            my_lines.append(f"**{name}**\n" + "\n".join(lines))
    else:
        my_lines.append("✅ Tu as tout vendu !")

    if not market_lines:
        description = "⚠️ Aucun item détecté pour le moment."
    else:
        description = (
            "🔎 **Statistiques pour les ventes**\n\n" +
            "\n━━━━━━━━━━━━━━━\n\n".join(market_lines)
        )

    my_annonces_value = (
        "\n━━━━━━━━━━━━━━━\n"
        "\n📦 **Tes annonces en cours**\n\n" +
        ("\n\n".join(my_lines) if my_lines else "✅ Tu as tout vendu !")
    )

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

def monitor_market():
    print("🚀 Dashboard marché lancé…")
    while True:
        embed = build_dashboard()
        send_or_edit_embed(embed)
        time.sleep(30)

if __name__ == "__main__":
    monitor_market()
