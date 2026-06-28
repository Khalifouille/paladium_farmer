import requests
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv
import pyautogui
import threading
import pyperclip

load_dotenv()

# ── CONFIG ──────────────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL   = 50       
MIN_DISCOUNT_PCT = 5        
MAX_MARKET_CALLS = 45 
AUTO_BUY_ENABLED = True  # Active l'achat automatique
# ─────────────────────────────────────────────────────────────

# ── POSITIONS MARKET (à calibrer) ──
SEARCH_BAR_X, SEARCH_BAR_Y = 274, 402
PRICE_ROW_X, PRICE_ROW_Y = 1406, 530
BUY_BUTTON_X, BUY_BUTTON_Y = 919, 779
CLOSE_MODAL_X, CLOSE_MODAL_Y = 1671, 124
# ────────────────────────────────────

BASE_URL    = "https://api.paladium.games/v1/paladium/shop"
ADMIN_URL   = f"{BASE_URL}/admin/items"
MARKET_URL  = f"{BASE_URL}/market/items"

HEADERS = {
    "User-Agent": "PaladiumPriceBot/1.0",
    "Authorization": f"Bearer {TOKEN}"
}

already_alerted = {}
buy_queue = []  # Queue des items à acheter


def get_admin_items():
    all_items = {}
    offset = 0
    limit  = 100

    while True:
        try:
            r = requests.get(f"{ADMIN_URL}?offset={offset}&limit={limit}", headers=HEADERS, timeout=10)
            r.raise_for_status()
            data = r.json()
            items = data.get("data", [])
            total = data.get("totalCount", 0)

            if not items:
                break

            for i in items:
                if i.get("canSell") and i.get("sellPrice"):
                    all_items[i["name"]] = i

            offset += len(items)
            print(f"  [ADMIN] offset={offset}/{total} | {len(all_items)} vendables")

            if offset >= total or len(items) < limit:
                break

            time.sleep(2)  

        except Exception as e:
            print(f"[ERREUR] Admin shop offset {offset} : {e}")
            time.sleep(5)  
            break

    return all_items


def get_market_price(item_name):
    """Récupère le prix minimum + détails du vendeur."""
    try:
        r = requests.get(f"{MARKET_URL}/{item_name}", headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return None   
        r.raise_for_status()
        data = r.json()

        if not data.get("listing"):
            return None

        # Trouver le listing avec le prix minimum
        min_listing = None
        min_price = float('inf')
        
        for listing in data["listing"]:
            price = listing.get("price", 0)
            if 0 < price < min_price:
                min_price = price
                min_listing = listing

        if not min_listing:
            return None

        return {
            "min_price":   min_listing["price"],
            "seller":      min_listing.get("seller", "unknown"),  # UUID du vendeur
            "avg_price":   data.get("priceAverage", 0),
            "qty":         data.get("quantityAvailable", 0),
            "count":       data.get("countListings", 0),
        }
    except Exception as e:
        print(f"[ERREUR] Market {item_name} : {e}")
        return None

player_cache = {}

def get_player_name(uuid):
    if uuid in player_cache:
        return player_cache[uuid]

    try:
        r = requests.get(
            "https://vrc.lol/api",
            params={
                "username": uuid,
                "type": "all"
            },
            timeout=5
        )
        r.raise_for_status()

        data = r.json()

        username = None

        if data.get("java"):
            username = data["java"].get("username")

        if not username and data.get("bedrock"):
            username = data["bedrock"].get("username")

        if not username:
            username = uuid[:8]

        player_cache[uuid] = username
        return username

    except Exception as e:
        print(f"[WARN] Impossible de récupérer le username pour {uuid[:8]} : {e}")
        return uuid[:8]

def buy_item_market(item_name, seller_uuid, expected_price):
    """Automatise l'achat d'un item sur le market."""
    print(f"\n[AUTO-BUY] Démarrage pour {item_name} chez {seller_uuid[:8]}...")

    seller_name = get_player_name(seller_uuid)
    print(f"[AUTO-BUY] Vendeur : {seller_name}")

    try:
        # Prépare la commande
        item_search = item_name.replace("-", " ")
        command = f"/ah {item_search} @p:{seller_name}"

        print(f"[AUTO-BUY] Commande : {command}")

        # 1. Ouvre le chat
        pyautogui.press("t")
        time.sleep(0.8)

        # 2. Colle la commande complète
        pyperclip.copy(command)
        time.sleep(0.2)

        pyautogui.keyDown("ctrl")
        pyautogui.press("v")
        pyautogui.keyUp("ctrl")
        # 3. Envoie la commande
        pyautogui.press("enter")

        # Attendre le chargement des résultats
        time.sleep(5)

        # 4. Clique sur le premier résultat
        print("[AUTO-BUY] Clic sur le prix...")
        pyautogui.click(PRICE_ROW_X, PRICE_ROW_Y)
        time.sleep(2)

        # 5. Vérification (optionnelle)
        print(f"[AUTO-BUY] Modal ouvert — prix attendu : {expected_price}$")
        time.sleep(1)

        # 6. Clique sur BUY
        print("[AUTO-BUY] Clic sur BUY...")
        pyautogui.click(BUY_BUTTON_X, BUY_BUTTON_Y)
        time.sleep(2)

        print(f"[AUTO-BUY] ✅ Achat lancé pour {item_name}")
        return True

    except Exception as e:
        print(f"[AUTO-BUY] ❌ Erreur : {e}")

        try:
            pyautogui.click(CLOSE_MODAL_X, CLOSE_MODAL_Y)
        except:
            pass

        return False

def send_discord_alert(alerts):
    """Envoie alerte Discord ET ajoute à la queue d'achat."""
    if not alerts:
        return

    lines = []
    for a in alerts:
        seller = get_player_name(a["seller_uuid"])
        lines.append(
            f"**{a['name']}**\n"
            f"  Prix market  : `{a['market_price']:.2f}` pièces\n"
            f"  Prix admin   : `{a['sell_price']:.2f}` pièces\n"
            f"  @p: **{seller}**\n"
        )
        
        # Ajoute à la queue d'achat
        if AUTO_BUY_ENABLED:
            buy_queue.append({
                "item": a["name"],
                "seller_uuid": a["seller_uuid"],
                "price": a["market_price"],
                "timestamp": time.time()
            })

    embed = {
        "title": f"💹 {len(alerts)} deal(s) trouvé(s) !",
        "description": "\n".join(lines),
        "color": 0x2ECC71,
        "footer": {"text": f"Paladium Price Bot • {datetime.now().strftime('%H:%M:%S')}"},
    }

    try:
        r = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        if r.status_code == 204:
            print(f"[DISCORD] ✅ {len(alerts)} alerte(s) envoyée(s)")
            if AUTO_BUY_ENABLED:
                print(f"[AUTO-BUY] 📋 {len(alerts)} item(s) ajouté(s) à la queue")
        else:
            print(f"[DISCORD] ❌ Erreur {r.status_code}")
    except Exception as e:
        print(f"[DISCORD] Erreur : {e}")


def process_buy_queue():
    """Traite les achats en queue."""
    while True:
        if buy_queue:
            item = buy_queue.pop(0)
            print(f"\n[QUEUE] Traitement de {item['item']}")
            buy_item_market(item["item"], item["seller_uuid"], item["price"])
            time.sleep(10)  # Délai entre les achats
        time.sleep(1)


def check_prices():
    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Vérification des prix...")

    admin_items = get_admin_items()
    if not admin_items:
        print("  Impossible de récupérer l'admin shop.")
        return

    print(f"  {len(admin_items)} items dans l'admin shop.")

    alerts = []
    checked = 0

    for name, admin in admin_items.items():
        if checked >= MAX_MARKET_CALLS:
            print(f"  Limite de {MAX_MARKET_CALLS} appels atteinte.")
            break

        market = get_market_price(name)
        checked += 1

        if market is None:
            continue

        sell_price   = admin["sellPrice"]
        market_price = market["min_price"]

        profit       = sell_price - market_price
        profit_pct   = (profit / market_price) * 100 if market_price > 0 else 0

        if profit > 0 and profit_pct >= MIN_DISCOUNT_PCT:
            prev = already_alerted.get(name)
            if prev is None or abs(prev - market_price) > 0.01:
                alerts.append({
                    "name":          name,
                    "sell_price":    sell_price,
                    "market_price":  market_price,
                    "profit":        profit,
                    "seller_uuid":   market["seller"],
                })
                already_alerted[name] = market_price
        else:
            already_alerted.pop(name, None)

        time.sleep(0.3)

    if alerts:
        send_discord_alert(alerts)
    else:
        print("  Aucun deal trouvé.")


def main():
    print("=" * 55)
    print("  PALADIUM PRICE BOT + AUTO-BUY")
    print(f"  Intervalle   : {CHECK_INTERVAL}s")
    print(f"  Seuil alerte : {MIN_DISCOUNT_PCT}%")
    print(f"  Auto-buy     : {'🟢 ACTIVÉ' if AUTO_BUY_ENABLED else '🔴 DÉSACTIVÉ'}")
    print("=" * 55)

    if AUTO_BUY_ENABLED:
        # Lance le thread de traitement des achats
        buy_thread = threading.Thread(target=process_buy_queue, daemon=True)
        buy_thread.start()
        print("[AUTO-BUY] Thread démarré")

    while True:
        try:
            check_prices()
        except KeyboardInterrupt:
            print("\n[STOP] Arrêt demandé.")
            break
        except Exception as e:
            print(f"[ERREUR] {e}")

        print(f"  Prochain check dans {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()