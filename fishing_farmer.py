"""
=============================================================
  AUTO-PÊCHE PALADIUM  —  1920x1080 fullscreen
=============================================================
  INSTALLATION :
      pip install mss pyautogui opencv-python numpy keyboard

  UTILISATION :
      1. Minecraft en 1920x1080 fullscreen, canne en main
      2. python peche_paladium.py
      3. Passe sur Minecraft avant les 3 secondes
      4. F8 pour stopper | souris coin haut-gauche = arrêt urgence
=============================================================
"""

import time
import random
import sys

try:
    import mss
    import numpy as np
    import pyautogui
    import cv2
except ImportError:
    print("Modules manquants. Lance :")
    print("  pip install mss pyautogui opencv-python numpy keyboard")
    sys.exit(1)

try:
    import keyboard
    HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False
    print("[INFO] 'keyboard' non installé — arrêt via Ctrl+C uniquement")

# ─────────────────────────────────────────────
#   COORDONNÉES — calibrées depuis debug_barre.png
# ─────────────────────────────────────────────

BAR_REGION = {
    "left":   250,
    "top":    598,
    "width": 1300,
    "height":  42,
}

# ─────────────────────────────────────────────
#   COULEURS (BGR pour OpenCV)
#   Extraites pixel par pixel depuis le vrai screenshot
# ─────────────────────────────────────────────

# Blanc — curseur (255,255,255)
COLOR_WHITE_LOW  = np.array([230, 230, 230], dtype=np.uint8)
COLOR_WHITE_HIGH = np.array([255, 255, 255], dtype=np.uint8)

# Vert X1 — à ÉVITER (94,212,42) RGB → (42,212,94) BGR
COLOR_GREEN_LOW  = np.array([ 20, 170,  60], dtype=np.uint8)
COLOR_GREEN_HIGH = np.array([ 80, 255, 130], dtype=np.uint8)

# Rouge X2 — objectif (255,57,57) RGB → (57,57,255) BGR
COLOR_RED_LOW  = np.array([ 30,  20, 200], dtype=np.uint8)
COLOR_RED_HIGH = np.array([ 90,  90, 255], dtype=np.uint8)

# Violet X5 (boosté)
COLOR_PURPLE_LOW  = np.array([120,   0,  80], dtype=np.uint8)
COLOR_PURPLE_HIGH = np.array([255,  80, 200], dtype=np.uint8)

# Orange LVL-UP
COLOR_ORANGE_LOW  = np.array([  0, 120, 180], dtype=np.uint8)
COLOR_ORANGE_HIGH = np.array([ 60, 210, 255], dtype=np.uint8)

# Fond gris de la barre (50,50,50) — pour détecter menu fermé
COLOR_BGGRAY_LOW  = np.array([ 35,  35,  35], dtype=np.uint8)
COLOR_BGGRAY_HIGH = np.array([ 70,  70,  70], dtype=np.uint8)

# Seuil pixels blancs pour confirmer curseur présent
WHITE_PIXEL_THRESHOLD = 15

# ─────────────────────────────────────────────
#   DÉLAIS
# ─────────────────────────────────────────────
DELAY_AFTER_CAST = (1.5, 3.5)
POLL_INTERVAL    = 0.008
REACTION_DELAY   = (0.04, 0.09)
RECAST_DELAY     = (0.8, 1.5)

# ─────────────────────────────────────────────
#   ÉTAT GLOBAL
# ─────────────────────────────────────────────
running = True
stats = {"casts": 0, "hits": 0, "misses": 0}

def stop_script():
    global running
    running = False
    print("\n[STOP] Script arrêté.")

if HAS_KEYBOARD:
    keyboard.add_hotkey("F8", stop_script)

# ─────────────────────────────────────────────
#   FONCTIONS
# ─────────────────────────────────────────────

def capture_bar(sct):
    shot = sct.grab(BAR_REGION)
    img = np.array(shot)
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

def is_menu_visible(bar_img):
    """
    Détecte le menu en cherchant :
    1. Le fond gris de la barre (50,50,50) — confirme que la barre est là
    2. Des pixels blancs — confirme que le curseur est présent
    """
    # Vérifie fond gris barre
    mask_gray = cv2.inRange(bar_img, COLOR_BGGRAY_LOW, COLOR_BGGRAY_HIGH)
    if np.count_nonzero(mask_gray) < 100:
        return False
    # Vérifie curseur blanc
    mask_white = cv2.inRange(bar_img, COLOR_WHITE_LOW, COLOR_WHITE_HIGH)
    return np.count_nonzero(mask_white) >= WHITE_PIXEL_THRESHOLD

def find_white_cursor(bar_img):
    """Position X centrale du curseur blanc."""
    mask = cv2.inRange(bar_img, COLOR_WHITE_LOW, COLOR_WHITE_HIGH)
    cols = np.where(mask.any(axis=0))[0]
    if len(cols) == 0:
        return None
    return int(cols.mean())

def get_zone_at(bar_img, x, tol=8):
    """Zone colorée sous le curseur à position x."""
    if x is None:
        return None
    h = bar_img.shape[0]
    mid_y = h // 2
    xs = [max(0, min(bar_img.shape[1] - 1, x + dx)) for dx in range(-tol, tol + 1)]
    pixels = bar_img[mid_y, xs]

    scores = {"red": 0, "purple": 0, "orange": 0, "green": 0}
    for px in pixels:
        p = px.reshape(1, 1, 3)
        if cv2.inRange(p, COLOR_RED_LOW,    COLOR_RED_HIGH).any():    scores["red"]    += 1
        if cv2.inRange(p, COLOR_PURPLE_LOW, COLOR_PURPLE_HIGH).any(): scores["purple"] += 1
        if cv2.inRange(p, COLOR_ORANGE_LOW, COLOR_ORANGE_HIGH).any(): scores["orange"] += 1
        if cv2.inRange(p, COLOR_GREEN_LOW,  COLOR_GREEN_HIGH).any():  scores["green"]  += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "gray"

def should_press(zone):
    return zone in ("red", "purple", "orange")

def human_delay(r):
    time.sleep(random.uniform(*r))

def cast_rod():
    pyautogui.click(button="right")
    stats["casts"] += 1
    print(f"[LANCÉ] #{stats['casts']} | Hits: {stats['hits']} | Misses: {stats['misses']}")

def press_space():
    human_delay(REACTION_DELAY)
    pyautogui.press("space")

# ─────────────────────────────────────────────
#   BOUCLE PRINCIPALE
# ─────────────────────────────────────────────

def main():
    global running

    print("=" * 60)
    print("  AUTO-PÊCHE PALADIUM — démarrage dans 3 secondes")
    print("  Passe sur Minecraft !")
    if HAS_KEYBOARD:
        print("  F8 pour arrêter | souris coin haut-gauche = urgence")
    else:
        print("  Ctrl+C pour arrêter | souris coin haut-gauche = urgence")
    print("=" * 60)
    time.sleep(3)

    pyautogui.FAILSAFE = True

    with mss.mss() as sct:
        cast_rod()
        human_delay(DELAY_AFTER_CAST)

        while running:
            bar_img = capture_bar(sct)

            if not is_menu_visible(bar_img):
                time.sleep(0.05)
                continue

            print("[MENU] Détecté — scan en cours...")
            pressed_this_round = False

            while running:
                bar_img = capture_bar(sct)
                mask_white = cv2.inRange(bar_img, COLOR_WHITE_LOW, COLOR_WHITE_HIGH)

                # Menu fermé si curseur disparu
                if np.count_nonzero(mask_white) < WHITE_PIXEL_THRESHOLD:
                    break

                cursor_x = find_white_cursor(bar_img)
                zone = get_zone_at(bar_img, cursor_x)

                print(f"  cursor_x={cursor_x} zone={zone}    ", end="\r")

                if should_press(zone) and not pressed_this_round:
                    pressed_this_round = True
                    stats["hits"] += 1
                    print(f"\n  [APPUI] Zone={zone} | x={cursor_x}")
                    press_space()
                    time.sleep(0.3)
                    break

                time.sleep(POLL_INTERVAL)

            if not pressed_this_round:
                stats["misses"] += 1
                print(f"\n  [MISS] Curseur manqué ou zone verte/grise")

            human_delay(RECAST_DELAY)
            if running:
                cast_rod()
                human_delay(DELAY_AFTER_CAST)

    print("\n[FIN] Stats :")
    print(f"  Lancés : {stats['casts']}")
    print(f"  Hits   : {stats['hits']}")
    print(f"  Misses : {stats['misses']}")
    if stats["casts"] > 0:
        print(f"  Taux   : {stats['hits'] / stats['casts'] * 100:.1f}%")

if __name__ == "__main__":
    main()