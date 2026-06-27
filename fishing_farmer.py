import time, random, sys, os
try:
    import mss, numpy as np, pyautogui, cv2
except ImportError:
    print("pip install mss pyautogui opencv-python numpy keyboard"); sys.exit(1)

try:
    import keyboard; HAS_KEYBOARD = True
except ImportError:
    HAS_KEYBOARD = False

try:
    import win32gui, win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False
    print("[INFO] pywin32 non installé — pip install pywin32")

# ── Fenêtre Minecraft — taille et position exactes depuis ta photo ──
MC_WIN_X      = 110
MC_WIN_Y      = 64
MC_WIN_WIDTH  = 1617
MC_WIN_HEIGHT = 967

def setup_minecraft_window():
    if not HAS_WIN32:
        print("[WARN] pywin32 non disponible — taille non forcée")
        return False
    windows = []
    def callback(h, _):
        title = win32gui.GetWindowText(h)
        if title: windows.append((h, title))
    win32gui.EnumWindows(callback, None)
    for h, title in windows:
        if any(k in title for k in ["Minecraft", "Paladium", "Java"]):
            print(f"[WINDOW] Trouvé : '{title}'")
            win32gui.ShowWindow(h, win32con.SW_RESTORE)
            time.sleep(0.2)
            win32gui.SetWindowPos(h, win32con.HWND_TOP,
                                  MC_WIN_X, MC_WIN_Y,
                                  MC_WIN_WIDTH, MC_WIN_HEIGHT, 0)
            win32gui.SetForegroundWindow(h)
            time.sleep(0.3)
            print(f"[WINDOW] {MC_WIN_WIDTH}x{MC_WIN_HEIGHT} — premier plan OK")
            return True
    print("[WARN] Fenêtre Minecraft introuvable")
    return False

# ── Template ──
TEMPLATE_PATH = "template_peche.png"
if not os.path.exists(TEMPLATE_PATH):
    print(f"ERREUR : '{TEMPLATE_PATH}' introuvable"); sys.exit(1)

template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_GRAYSCALE)
TEMPLATE_SCORE_MIN = 0.6

# ── Régions ──
BAR_REGION      = {"left": 460, "top": 590, "width": 900, "height": 24}
TEMPLATE_REGION = {"left": 0,   "top": 0,   "width": 1920, "height": 1080}

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

WHITE_MIN      = 10
CAST_TIMEOUT   = 60  

running  = True
stats    = {"casts": 0, "hits": 0, "misses": 0}
current_slot = 1
failed_casts = 0

def stop():
    global running, failed_casts; running = False; print("\n[STOP]")

if HAS_KEYBOARD:
    keyboard.add_hotkey("F8", stop)

def count(img, lo, hi):
    return np.count_nonzero(cv2.inRange(img, lo, hi))

def grab_bar(sct):
    shot = sct.grab(BAR_REGION)
    return cv2.cvtColor(np.array(shot), cv2.COLOR_BGRA2BGR)

def is_menu_visible(sct):
    shot = sct.grab(TEMPLATE_REGION)
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

def scan_bar_colors(bar_img):
    present = set()
    mid = bar_img.shape[0] // 2
    for x in range(bar_img.shape[1]):
        p = bar_img[mid, x].reshape(1,1,3)
        if cv2.inRange(p, C_RED_LO,    C_RED_HI).any():    present.add("red")
        if cv2.inRange(p, C_PURPLE_LO, C_PURPLE_HI).any(): present.add("purple")
        if cv2.inRange(p, C_ORANGE_LO, C_ORANGE_HI).any(): present.add("orange")
    return present

def get_target_zone(present_colors):
    if "purple" in present_colors: return "purple"
    if "orange" in present_colors: return "orange"
    return "red"


def next_rod():
    global current_slot, running

    if current_slot >= 9:
        print("\n[STOP] Plus de cannes disponibles")
        running = False
        return

    current_slot += 1
    pyautogui.press(str(current_slot))
    print(f"\n[CANNE] Passage au slot {current_slot}")
    time.sleep(0.5)

def recast():
    """Reprend l'hameçon et relance."""
    print("\n[RECAST] Timeout — reprise + nouveau lancé")
    pyautogui.click(button="right")   # reprend l'hameçon
    time.sleep(random.uniform(0.6, 1.0))
    pyautogui.click(button="right")   # nouveau lancé
    stats["casts"] += 1
    print(f"[LANCÉ] #{stats['casts']} | Hits:{stats['hits']} Misses:{stats['misses']}")

def cast():
    pyautogui.click(button="right")
    stats["casts"] += 1
    print(f"[LANCÉ] #{stats['casts']} | Hits:{stats['hits']} Misses:{stats['misses']}")

def press_space():
    pyautogui.press("space")

def main():
    global running, failed_casts
    print("=" * 50)
    print(f"  Template: {template.shape} | Seuil: {TEMPLATE_SCORE_MIN}")
    print("  Démarrage dans 3s...")
    if HAS_KEYBOARD:
        print("  F8 pour arrêter | coin haut-gauche = urgence")
    print("=" * 50)
    # Force la taille et met Minecraft au premier plan
    setup_minecraft_window()
    time.sleep(3)
    pyautogui.FAILSAFE = True

    with mss.mss() as sct:
        cast()
        cast_time = time.time()

        while running:
            score = is_menu_visible(sct)
            elapsed_cast = time.time() - cast_time
            print(f"  [WAIT] score={score:.3f} t={elapsed_cast:.0f}s    ", end="\r")

            # Timeout : hameçon à l'eau depuis trop longtemps sans mini-jeu
            if elapsed_cast > CAST_TIMEOUT:
                failed_casts += 1
                print(f"\n[TIMEOUT] #{failed_casts}")

                if failed_casts >= 2:
                    # 2 timeouts consécutifs → change de canne
                    next_rod()
                    failed_casts = 0
                else:
                    # 1er timeout → reprend et relance simplement
                    recast()

                cast_time = time.time()
                time.sleep(random.uniform(1.5, 3.5))
                continue

            if score < TEMPLATE_SCORE_MIN:
                time.sleep(0.1)
                continue

            failed_casts = 0
            print(f"\n[MENU] Détecté ! score={score:.3f}")
            pressed = False

            # Scan initial de la barre pour déterminer la zone prioritaire
            bar_img      = grab_bar(sct)
            present      = scan_bar_colors(bar_img)
            target       = get_target_zone(present)
            print(f"  [SCAN] couleurs={present} → cible={target}")

            # Attend que le curseur arrive sur la zone cible
            while running:
                bar_img = grab_bar(sct)
                w = count(bar_img, C_WHITE_LO, C_WHITE_HI)

                # Curseur disparu = menu fermé naturellement
                if w < WHITE_MIN:
                    if not pressed:
                        stats["misses"] += 1
                        print("\n  [MISS] Menu fermé sans zone cible")
                    break

                cx = cursor_x(bar_img)
                z  = zone_at(bar_img, cx)
                print(f"  x={cx} zone={z} cible={target}    ", end="\r")

                if z == target and not pressed:
                    pressed = True
                    stats["hits"] += 1
                    print(f"\n  [APPUI] zone={z} x={cx}")
                    press_space()
                    time.sleep(0.3)
                    break

                time.sleep(0.008)

            time.sleep(random.uniform(0.8, 1.5))
            if running:
                cast()
                cast_time = time.time()
                time.sleep(random.uniform(1.5, 3.5))

    print(f"\n[FIN] Lancés:{stats['casts']} Hits:{stats['hits']} Misses:{stats['misses']}")
    if stats["casts"]:
        print(f"Taux: {stats['hits']/stats['casts']*100:.1f}%")

if __name__ == "__main__":
    main()