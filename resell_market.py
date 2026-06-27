"""
COMPARATEUR PRIX — Admin Shop vs Market Shop — Paladium
=======================================================
Installe : pip install requests

Configure WEBHOOK_URL et lance : python price_alert.py
Le script tourne en boucle et notifie Discord quand un item
du market est moins cher que le prix admin shop.
"""

import requests
import time
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# ── CONFIG ──────────────────────────────────────────────────
TOKEN = os.getenv("TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
CHECK_INTERVAL   = 120       
MIN_DISCOUNT_PCT = 5        
MAX_MARKET_CALLS = 50 
# ─────────────────────────────────────────────────────────────

BASE_URL    = "https://api.paladium.games/v1/paladium/shop"
ADMIN_URL   = f"{BASE_URL}/admin/items"
MARKET_URL  = f"{BASE_URL}/market/items"

HEADERS = {
    "User-Agent": "PaladiumPriceBot/1.0",
    "Authorization": f"Bearer {TOKEN}"
}

already_alerted = {}   


def get_admin_items():
    """Récupère TOUS les items de l'admin shop via offset/limit."""
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
    """Récupère le prix minimum du marché pour un item."""
    try:
        r = requests.get(f"{MARKET_URL}/{item_name}", headers=HEADERS, timeout=10)
        if r.status_code == 404:
            return None   
        r.raise_for_status()
        data = r.json()

        if not data.get("listing"):
            return None

        # Prix minimum parmi tous les listings actifs
        prices = [l["price"] for l in data["listing"] if l.get("price", 0) > 0]
        if not prices:
            return None

        return {
            "min_price":   min(prices),
            "avg_price":   data.get("priceAverage", 0),
            "qty":         data.get("quantityAvailable", 0),
            "count":       data.get("countListings", 0),
        }
    except Exception as e:
        print(f"[ERREUR] Market {item_name} : {e}")
        return None


def send_discord_alert(alerts):
    """Envoie une notification Discord avec tous les deals trouvés."""
    if not alerts:
        return

    lines = []
    for a in alerts:
        lines.append(
            f"**{a['name']}**\n"
            f"  Prix market  : `{a['market_price']:.2f}` pièces (achat)\n"
            f"  Prix admin   : `{a['sell_price']:.2f}` pièces (revente)\n"
            f"  Profit/unité : `+{a['profit']:.2f}` pièces (`+{a['profit_pct']:.1f}%`) 💹\n"
            f"  Dispo market : `{a['qty']}` unités ({a['count']} listings)\n"
            f"  Profit max   : `+{a['profit'] * a['qty']:.2f}` pièces (tout racheter)\n"
        )

    embed = {
        "title": f"💹 {len(alerts)} opportunité(s) d'arbitrage trouvée(s) !",
        "description": "\n".join(lines),
        "color": 0x2ECC71,
        "footer": {"text": f"Paladium Price Bot • {datetime.now().strftime('%H:%M:%S')}"},
    }

    try:
        r = requests.post(WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        if r.status_code == 204:
            print(f"[DISCORD] ✅ Alerte envoyée ({len(alerts)} items)")
        else:
            print(f"[DISCORD] ❌ Erreur {r.status_code} : {r.text}")
    except Exception as e:
        print(f"[DISCORD] Erreur envoi : {e}")


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
            print(f"  Limite de {MAX_MARKET_CALLS} appels market atteinte pour ce cycle.")
            break

        market = get_market_price(name)
        checked += 1

        if market is None:
            continue

        sell_price   = admin["sellPrice"]    
        market_price = market["min_price"]    

        profit       = sell_price - market_price
        profit_pct   = (profit / market_price) * 100 if market_price > 0 else 0

        print(f"  {name}: sell_admin={sell_price:.2f} market={market_price:.2f} profit={profit:+.2f} ({profit_pct:+.1f}%)")

        # Alerte si on peut acheter sur le market et revendre à l'admin avec un profit >= MIN_DISCOUNT_PCT%
        if profit > 0 and profit_pct >= MIN_DISCOUNT_PCT:
            prev = already_alerted.get(name)
            if prev is None or abs(prev - market_price) > 0.01:
                alerts.append({
                    "name":         name,
                    "sell_price":   sell_price,
                    "market_price": market_price,
                    "profit":       profit,
                    "profit_pct":   profit_pct,
                    "qty":          market["qty"],
                    "count":        market["count"],
                })
                already_alerted[name] = market_price
        else:
            already_alerted.pop(name, None)

        time.sleep(0.3)  

    if alerts:
        send_discord_alert(alerts)
    else:
        print("  Aucun deal trouvé ce cycle.")


def main():
    print("=" * 55)
    print("  PALADIUM PRICE BOT")
    print(f"  Intervalle   : {CHECK_INTERVAL}s")
    print(f"  Seuil alerte : -{MIN_DISCOUNT_PCT}% vs admin shop")
    print(f"  Webhook      : {'OK' if WEBHOOK_URL != 'METS_TON_WEBHOOK_ICI' else '⚠️  NON CONFIGURÉ'}")
    print("=" * 55)

    if WEBHOOK_URL == "METS_TON_WEBHOOK_ICI":
        print("\n⚠️  Configure WEBHOOK_URL en haut du script avant de lancer !")
        return

    while True:
        try:
            check_prices()
        except KeyboardInterrupt:
            print("\n[STOP] Arrêt demandé.")
            break
        except Exception as e:
            print(f"[ERREUR CRITIQUE] {e}")

        print(f"  Prochain check dans {CHECK_INTERVAL}s...")
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()