"""
AUTO-PÊCHE PALADIUM
pip install mss pyautogui opencv-python numpy keyboard pillow
Mettre template_peche.png dans le même dossier
"""

import time, random, sys, os
try:
    import mss, numpy as np, pyautogui, cv2
except ImportError:
    print("pip install mss pyautogui opencv-python numpy keyboard"); sys.exit(1)

try:
    import keyboard; HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

# ── Template ──
TEMPLATE_PATH = "template_peche.png"
if not os.path.exists(TEMPLATE_PATH):
    print(f"ERREUR : '{TEMPLATE_PATH}' introuvable"); sys.exit(1)

template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_GRAYSCALE)
TEMPLATE_SCORE_MIN = 0.85

# ── Région barre ──
BAR_REGION = {"left": 442, "top": 576, "width": 721, "height": 24}

# ── Couleurs BGR ──
C_WHITE_LO  = np.array([240, 240, 240], dtype=np.uint8)
C_WHITE_HI  = np.array([255, 255, 255], dtype=np.uint8)
C_GREEN_LO  = np.array([ 30, 190,  70], dtype=np.uint8)
C_GREEN_HI  = np.array([ 60, 225, 110], dtype=np.uint8)
C_RED_LO    = np.array([ 45,  40, 235], dtype=np.uint8)
C_RED_HI    = np.array([ 70,  70, 255], dtype=np.uint8)
C_PURPLE_LO = np.array([220,  25, 155], dtype=np.uint8)
C_PURPLE_HI = np.array([255,  55, 200], dtype=np.uint8)
C_ORANGE_LO = np.array([  0, 120, 180], dtype=np.uint8)
C_ORANGE_HI = np.array([ 60, 210, 255], dtype=np.uint8)

WHITE_MIN        = 10
ANTI_AFK_EVERY   = 60   # secondes entre chaque mouvement anti-AFK
BAR_TIMEOUT      = 12   # secondes max pour attendre que le curseur arrive sur une zone

running   = True
stats     = {"casts": 0, "hits": 0, "misses": 0}
last_afk  = time.time()

def stop():
    global running; running = False; print("\n[STOP]")

if HAS_KEYBOARD:
    keyboard.add_hotkey("F8", stop)

def count(img, lo, hi):
    return np.count_nonzero(cv2.inRange(img, lo, hi))

def grab_bar(sct):
    shot = sct.grab(BAR_REGION)
    return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

def is_menu_visible(sct):
    shot = sct.grab(sct.monitors[1])
    gray = cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2GRAY)
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    return result.max()

def cursor_x(bar_img):
    cols = np.where(cv2.inRange(bar_img, C_WHITE_LO, C_WHITE_HI).any(axis=0))[0]
    return int(cols.mean()) if len(cols) else None

def zone_at(bar_img, x, tol=6):
    if x is None: return None
    mid = bar_img.shape[0] // 2
    xs = [max(0, min(bar_img.shape[1]-1, x+d)) for d in range(-tol, tol+1)]
    pxs = bar_img[mid, xs]
    scores = {k: 0 for k in ["red","purple","orange","green"]}
    for px in pxs:
        p = px.reshape(1,1,3)
        if cv2.inRange(p, C_RED_LO,    C_RED_HI).any():    scores["red"]    += 1
        if cv2.inRange(p, C_PURPLE_LO, C_PURPLE_HI).any(): scores["purple"] += 1
        if cv2.inRange(p, C_ORANGE_LO, C_ORANGE_HI).any(): scores["orange"] += 1
        if cv2.inRange(p, C_GREEN_LO,  C_GREEN_HI).any():  scores["green"]  += 1
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "gray"

def anti_afk():
    """Actions aléatoires pour éviter le kick AFK — uniquement hors mini-jeu."""
    global last_afk
    if time.time() - last_afk < ANTI_AFK_EVERY:
        return

    actions = random.sample([
        ("souris_droite",   lambda: (pyautogui.moveRel( random.randint(3,8), 0, duration=0.15), time.sleep(0.1), pyautogui.moveRel(-random.randint(3,8), 0, duration=0.15))),
        ("souris_gauche",   lambda: (pyautogui.moveRel(-random.randint(3,8), 0, duration=0.15), time.sleep(0.1), pyautogui.moveRel( random.randint(3,8), 0, duration=0.15))),
        ("saut",            lambda: (pyautogui.keyDown("space"), time.sleep(random.uniform(0.05, 0.1)), pyautogui.keyUp("space"))),
        ("accroupi",        lambda: (pyautogui.keyDown("shift"), time.sleep(random.uniform(0.1, 0.2)), pyautogui.keyUp("shift"))),
        ("avance_leger",    lambda: (pyautogui.keyDown("w"),     time.sleep(random.uniform(0.05, 0.12)), pyautogui.keyUp("w"))),
    ], k=random.randint(1, 3))  # 1 à 3 actions par cycle

    for name, action in actions:
        action()
        print(f"\n[AFK] {name}")
        time.sleep(random.uniform(0.2, 0.5))

    last_afk = time.time()

def cast():
    pyautogui.click(button="right")
    stats["casts"] += 1
    print(f"[LANCÉ] #{stats['casts']} | Hits:{stats['hits']} Misses:{stats['misses']}")

def press_space():
    time.sleep(random.uniform(0.04, 0.09))
    pyautogui.press("space")

def main():
    global running
    print("=" * 50)
    print(f"  Template: {template.shape} | Seuil: {TEMPLATE_SCORE_MIN}")
    print("  Démarrage dans 3s — passe sur Minecraft !")
    if HAS_KEYBOARD:
        print("  F8 pour arrêter | coin haut-gauche = urgence")
    print("=" * 50)
    time.sleep(3)
    pyautogui.FAILSAFE = True

    with mss.mss() as sct:
        cast()
        time.sleep(random.uniform(1.5, 3.5))

        while running:
            anti_afk()
            score = is_menu_visible(sct)
            print(f"  [WAIT] score={score:.3f}    ", end="\r")

            if score < TEMPLATE_SCORE_MIN:
                time.sleep(0.1)
                continue

            print(f"\n[MENU] Détecté ! score={score:.3f}")
            pressed    = False
            bar_start  = time.time()

            while running:
                # Timeout — si le curseur n'atteint pas de zone après BAR_TIMEOUT secondes
                if time.time() - bar_start > BAR_TIMEOUT:
                    print("\n  [TIMEOUT] Curseur n'a pas atteint de zone cible")
                    break

                bar_img = grab_bar(sct)
                w = count(bar_img, C_WHITE_LO, C_WHITE_HI)

                # Menu fermé = curseur disparu
                if w < WHITE_MIN:
                    break

                cx = cursor_x(bar_img)
                z  = zone_at(bar_img, cx)
                elapsed = time.time() - bar_start
                print(f"  x={cx} zone={z} blanc={w} t={elapsed:.1f}s    ", end="\r")

                if z in ("red", "purple", "orange") and not pressed:
                    pressed = True
                    stats["hits"] += 1
                    print(f"\n  [APPUI] zone={z} x={cx} t={elapsed:.1f}s")
                    press_space()
                    time.sleep(0.3)
                    break

                time.sleep(0.008)

            if not pressed:
                stats["misses"] += 1
                print("\n  [MISS]")

            time.sleep(random.uniform(0.8, 1.5))
            if running:
                cast()
                time.sleep(random.uniform(1.5, 3.5))

    print(f"\n[FIN] Lancés:{stats['casts']} Hits:{stats['hits']} Misses:{stats['misses']}")
    if stats["casts"]:
        print(f"Taux: {stats['hits']/stats['casts']*100:.1f}%")

if __name__ == "__main__":
    main()