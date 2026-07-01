"""
Clicker Auto Buyer — Paladium
==============================

Automatise l'achat du bâtiment recommandé par PalaTracker (site web) directement
dans le panneau "BUILDINGS" du Clicker Minecraft, en se basant sur l'heure
"Achetable le ..." affichée par le site.

Usage :
    python clicker_auto_buyer.py --calibrate     # à faire une seule fois (ou si tu bouges les fenêtres)
    python clicker_auto_buyer.py                 # lance le bot

Prérequis : voir README.md
"""

import argparse
import difflib
import json
import os
import re
import time
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path

import cv2
import mss
import numpy as np
import pytesseract
import win32api
import win32con
import win32gui

CONFIG_PATH = Path(__file__).parent / "config.json"

# Chemin par défaut de Tesseract sur Windows (modifiable via --tesseract)
_default_tesseract = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if os.path.exists(_default_tesseract):
    pytesseract.pytesseract.tesseract_cmd = _default_tesseract


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(
            "config.json introuvable. Lance d'abord :\n"
            "    python clicker_auto_buyer.py --calibrate"
        )
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Fenêtres (pywin32)
# ---------------------------------------------------------------------------

def find_window(partial_title):
    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if partial_title.lower() in title.lower():
                result.append(hwnd)

    win32gui.EnumWindows(callback, None)
    if not result:
        raise SystemExit(f"Fenêtre introuvable pour le titre contenant : '{partial_title}'")
    return result[0]


def get_client_rect_on_screen(hwnd):
    """Zone CLIENT (sans bordure/barre de titre) en coordonnées écran absolues."""
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    left, top = win32gui.ClientToScreen(hwnd, (left, top))
    right, bottom = win32gui.ClientToScreen(hwnd, (right, bottom))
    return left, top, right, bottom


def bring_to_foreground(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(hwnd)
    except Exception:
        pass
    time.sleep(0.15)


def click_at(abs_x, abs_y):
    win32api.SetCursorPos((abs_x, abs_y))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def click_in_window(hwnd, rel_x, rel_y, focus=True):
    """rel_x/rel_y : décalage en pixels depuis le coin haut-gauche de la zone CLIENT."""
    if focus:
        bring_to_foreground(hwnd)
    left, top, _, _ = get_client_rect_on_screen(hwnd)
    click_at(left + rel_x, top + rel_y)


def hover_in_window(hwnd, rel_x, rel_y, focus=True):
    """Déplace juste le curseur (sans cliquer), pour déclencher l'affichage d'une infobulle."""
    if focus:
        bring_to_foreground(hwnd)
    left, top, _, _ = get_client_rect_on_screen(hwnd)
    win32api.SetCursorPos((left + rel_x, top + rel_y))


# ---------------------------------------------------------------------------
# Capture écran (mss) — la fenêtre doit rester visible à l'écran
# ---------------------------------------------------------------------------

_sct = mss.mss()


def capture_region(hwnd, region):
    """region : {left, top, width, height} relatif à la zone client de la fenêtre."""
    left, top, _, _ = get_client_rect_on_screen(hwnd)
    box = {
        "left": left + region["left"],
        "top": top + region["top"],
        "width": region["width"],
        "height": region["height"],
    }
    shot = _sct.grab(box)
    img = np.array(shot)  # BGRA
    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)


# ---------------------------------------------------------------------------
# OCR
# ---------------------------------------------------------------------------

def preprocess_variant(img_bgr, scale, invert):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    _, thresh = cv2.threshold(gray, 0, 255, thresh_type | cv2.THRESH_OTSU)
    # Dilatation légère pour épaissir les traits fins de la police pixel-art
    kernel = np.ones((2, 2), np.uint8)
    thresh = cv2.dilate(thresh, kernel, iterations=1)
    return thresh


def preprocess_for_ocr(img_bgr, scale=2):
    return preprocess_variant(img_bgr, scale, invert=False)


def ocr_text(img_bgr, psm=7):
    proc = preprocess_for_ocr(img_bgr)
    config = f"--psm {psm}"
    try:
        return pytesseract.image_to_string(proc, config=config, lang="fra")
    except pytesseract.TesseractError:
        # Si le pack langue 'fra' n'est pas installé, on retombe sur l'anglais
        return pytesseract.image_to_string(proc, config=config)


def ocr_value(img_bgr, parser, whitelist=None, psms=(7, 6), scales=(3, 4)):
    """Essaie plusieurs combinaisons (échelle x inversion x psm), fait un vote
    majoritaire entre toutes les lectures valides (parser(texte) non-None).
    Retourne (valeur_la_plus_fréquente, dernier_texte_brut)."""
    whitelist_cfg = f" -c tessedit_char_whitelist={whitelist}" if whitelist else ""
    last_text = ""
    candidates = []
    for scale in scales:
        for invert in (False, True):
            proc = preprocess_variant(img_bgr, scale, invert)
            for psm in psms:
                config = f"--psm {psm}{whitelist_cfg}"
                try:
                    text = pytesseract.image_to_string(proc, config=config)
                except pytesseract.TesseractError:
                    continue
                last_text = text
                value = parser(text)
                if value is not None:
                    candidates.append(value)
    if not candidates:
        return None, last_text
    value, _count = Counter(candidates).most_common(1)[0]
    return value, last_text


def parse_number_fr(text):
    digits = re.sub(r"[^0-9]", "", text)
    return int(digits) if digits else None


def parse_datetime_fr(text):
    m = re.search(
        r"(\d{1,2})/(\d{1,2})/(\d{4}).*?(\d{1,2}):(\d{1,2}):(\d{1,2})", text, re.DOTALL
    )
    if not m:
        return None
    d, mo, y, h, mi, s = map(int, m.groups())
    # Garde-fou : si l'OCR a mal lu un chiffre (ex: mois > 12), on rejette
    # plutôt que de planter, et on le signale à l'appelant via None.
    if not (1 <= mo <= 12 and 1 <= d <= 31 and 0 <= h <= 23 and 0 <= mi <= 59 and 0 <= s <= 59):
        return None
    try:
        return datetime(y, mo, d, h, mi, s)
    except ValueError:
        return None


def normalize_name(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def names_match(target_name, candidate_name, threshold=0.6):
    """Compare deux noms de manière tolérante (accents, troncature, casse, fautes OCR)."""
    t = normalize_name(target_name)
    c = normalize_name(candidate_name)
    if not t or not c:
        return False
    c_stripped = c.rstrip(".").strip()
    if c_stripped and (t.startswith(c_stripped) or c_stripped in t or t in c_stripped):
        return True
    return difflib.SequenceMatcher(None, t, c).ratio() >= threshold


# ---------------------------------------------------------------------------
# Lecture de la recommandation (site PalaTracker)
# ---------------------------------------------------------------------------

def read_recommendation(hwnd_browser, cfg):
    regions = cfg["regions"]
    name_img = capture_region(hwnd_browser, regions["rec_name"])
    cost_img = capture_region(hwnd_browser, regions["rec_cost"])
    date_img = capture_region(hwnd_browser, regions["rec_date"])

    name_raw = ocr_text(name_img, psm=7).strip()
    cost, cost_raw = ocr_value(cost_img, parse_number_fr, whitelist="0123456789")
    dt, date_raw = ocr_value(date_img, parse_datetime_fr, whitelist="0123456789/:")

    name = name_raw

    if not name or cost is None or dt is None:
        print("    [debug] OCR brut -> nom:", repr(name_raw))
        print("    [debug] OCR brut -> coût:", repr(cost_raw))
        print("    [debug] OCR brut -> date:", repr(date_raw))
        return None
    return {"name": name, "cost": cost, "achetable_le": dt}


# ---------------------------------------------------------------------------
# Liste des bâtiments en jeu
# ---------------------------------------------------------------------------

def scan_buildings_rows(hwnd_mc, cfg):
    """Scanne les lignes visibles du panneau BUILDINGS.
    Retourne une liste de {name, cost, y_center} (y_center relatif à la zone de liste)."""
    region = cfg["regions"]["ingame_buildings_list"]
    row_h = cfg["behavior"]["building_row_height"]
    img = capture_region(hwnd_mc, region)
    rows = []
    n_rows = region["height"] // row_h
    for i in range(n_rows):
        y0 = i * row_h
        row_img = img[y0:y0 + row_h, :]
        text = ocr_text(row_img, psm=6)
        cost = None
        m_cost = re.search(r"[\d ]{4,}", text)
        if m_cost:
            cost = parse_number_fr(m_cost.group())
        name_part = re.sub(r"[\d ]{4,}", "", text).strip()
        rows.append({"name": name_part, "cost": cost, "y_center": y0 + row_h // 2})
    return rows


def find_matching_row(target_name, rows, threshold=0.55):
    target_norm = normalize_name(target_name)
    best, best_score = None, 0
    for row in rows:
        row_norm = normalize_name(row["name"])
        if not row_norm:
            continue
        if names_match(target_name, row["name"], threshold=threshold):
            return row
        score = difflib.SequenceMatcher(None, target_norm, row_norm).ratio()
        if score > best_score:
            best, best_score = row, score
    return best if best_score >= threshold else None


# ---------------------------------------------------------------------------
# Upgrades en jeu (grille d'icônes + infobulle au survol)
# ---------------------------------------------------------------------------

def generate_upgrade_icon_positions(grid):
    """Retourne la liste des coins HAUT-GAUCHE (x, y) de chaque icône de la grille,
    en partant de start_x/start_y, dans l'ordre ligne par ligne."""
    positions = []
    for r in range(grid["rows"]):
        for c in range(grid["columns"]):
            x = grid["start_x"] + c * grid["spacing_x"]
            y = grid["start_y"] + r * grid["spacing_y"]
            positions.append((x, y))
    return positions


def read_upgrade_tooltip(hwnd_mc, icon_left, icon_top, cfg):
    offset = cfg["regions"]["upgrades_tooltip_offset"]
    region = {
        "left": icon_left + offset["left"],
        "top": icon_top + offset["top"],
        "width": offset["width"],
        "height": offset["height"],
    }
    img = capture_region(hwnd_mc, region)
    return ocr_text(img, psm=7).strip()


def find_and_click_upgrade(hwnd_mc, target_name, cfg):
    """Survole chaque icône de la grille Upgrades, lit son infobulle, et clique
    si elle correspond au nom recherché. Retourne True si un achat a été tenté."""
    if "upgrades" not in cfg["regions"]:
        return False

    grid = cfg["regions"]["upgrades"]
    icon_w, icon_h = grid["icon_w"], grid["icon_h"]
    wait_s = cfg["behavior"].get("tooltip_wait_seconds", 0.6)

    bring_to_foreground(hwnd_mc)

    for x, y in generate_upgrade_icon_positions(grid):
        center_x, center_y = x + icon_w // 2, y + icon_h // 2
        hover_in_window(hwnd_mc, center_x, center_y, focus=False)
        time.sleep(wait_s)
        tooltip_text = read_upgrade_tooltip(hwnd_mc, x, y, cfg)

        if not tooltip_text:
            # Une 2e tentative au cas où l'infobulle a mis du temps à apparaître
            time.sleep(wait_s)
            tooltip_text = read_upgrade_tooltip(hwnd_mc, x, y, cfg)
            if not tooltip_text:
                continue

        if names_match(target_name, tooltip_text):
            click_in_window(hwnd_mc, center_x, center_y, focus=False)
            return True

    return False


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def run(cfg):
    hwnd_browser = find_window(cfg["window_titles"]["browser"])
    hwnd_mc = find_window(cfg["window_titles"]["minecraft"])
    poll = cfg["behavior"]["poll_interval_seconds"]
    buffer_s = cfg["behavior"]["buy_buffer_seconds"]

    print("Bot démarré. Ctrl+C pour arrêter.\n")
    last_target = None

    while True:
        try:
            rec = read_recommendation(hwnd_browser, cfg)
        except Exception as e:
            print(f"[!] Erreur de lecture du site : {e}")
            time.sleep(poll)
            continue

        if rec is None:
            print("[!] OCR n'a pas réussi à lire la recommandation, nouvelle tentative...")
            time.sleep(poll)
            continue

        now = datetime.now()
        wait_s = (rec["achetable_le"] - now).total_seconds()

        if last_target != rec["name"]:
            print(
                f"-> Prochain achat : {rec['name']} | Coût : {rec['cost']:,} | "
                f"Achetable le {rec['achetable_le']:%d/%m/%Y à %H:%M:%S}"
            )
            last_target = rec["name"]

        if wait_s > buffer_s:
            time.sleep(min(wait_s - buffer_s, poll))
            continue

        if wait_s > 0:
            time.sleep(wait_s)

        # --- Tentative d'achat : on cherche d'abord parmi les Bâtiments ---
        rows = scan_buildings_rows(hwnd_mc, cfg)
        row = find_matching_row(rec["name"], rows)

        if row is not None:
            region = cfg["regions"]["ingame_buildings_list"]
            click_x = region["left"] + region["width"] // 2
            click_y = region["top"] + row["y_center"]
            click_in_window(hwnd_mc, click_x, click_y)
            print(f"[OK] Achat tenté (Bâtiment) : {rec['name']} (coût {rec['cost']:,})")
        else:
            # Pas trouvé parmi les Bâtiments -> on tente parmi les Upgrades
            print(f"[i] '{rec['name']}' introuvable parmi les Bâtiments, recherche dans les Upgrades...")
            found = find_and_click_upgrade(hwnd_mc, rec["name"], cfg)
            if found:
                print(f"[OK] Achat tenté (Upgrade) : {rec['name']} (coût {rec['cost']:,})")
            else:
                print(
                    f"[!] '{rec['name']}' introuvable (ni Bâtiment ni Upgrade visible). "
                    f"Vérifie qu'il est affiché à l'écran, ou que les Upgrades sont calibrés "
                    f"(--calibrate)."
                )
                time.sleep(poll)
                continue

        time.sleep(2)

        # Rafraîchit la recommandation sur le site
        btn = cfg["regions"]["refresh_button"]
        click_in_window(hwnd_browser, btn["left"], btn["top"])
        time.sleep(2)


# ---------------------------------------------------------------------------
# Calibration interactive
# ---------------------------------------------------------------------------

def pick_two_points_on_image(img_bgr, window_title="Clique sur les 2 coins", display_scale=3):
    """Affiche une image dans une fenêtre et laisse l'utilisateur cliquer 2 points
    dessus (coin haut-gauche puis bas-droite). Échap pour annuler.
    Retourne [(x1, y1), (x2, y2)] en coordonnées de l'image ORIGINALE (pas zoomée)."""
    display_img = cv2.resize(
        img_bgr, None, fx=display_scale, fy=display_scale, interpolation=cv2.INTER_NEAREST
    ).copy()
    points = []

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 2:
            points.append((x // display_scale, y // display_scale))
            cv2.drawMarker(display_img, (x, y), (0, 0, 255), cv2.MARKER_CROSS, 16, 2)
            cv2.imshow(window_title, display_img)

    cv2.namedWindow(window_title)
    cv2.setMouseCallback(window_title, on_mouse)
    cv2.imshow(window_title, display_img)

    while len(points) < 2:
        key = cv2.waitKey(30) & 0xFF
        if key == 27:  # Échap
            cv2.destroyWindow(window_title)
            raise SystemExit("Calibration annulée (Échap).")

    cv2.waitKey(400)  # petite pause pour voir les 2 croix avant de fermer
    cv2.destroyWindow(window_title)
    return points


def calibrate_upgrades(hwnd_mc):
    """Calibre la grille d'icônes Upgrades + la zone où apparaît l'infobulle (nom)."""

    def pick_point(label):
        input(f"Place la souris sur : {label}, puis appuie sur Entrée...")
        return win32api.GetCursorPos()

    def rel_point(hwnd, abs_point):
        left, top, _, _ = get_client_rect_on_screen(hwnd)
        return abs_point[0] - left, abs_point[1] - top

    print("\n=== Calibration des Upgrades ===")
    print("Vise la 1ère icône d'Upgrade visible (la plus à gauche, ex: dans Click Shop).")
    p1 = pick_point("coin HAUT-GAUCHE de la 1ère icône")
    p2 = pick_point("coin BAS-DROITE de cette même icône")
    x1, y1 = rel_point(hwnd_mc, p1)
    x2, y2 = rel_point(hwnd_mc, p2)
    icon_left, icon_top = min(x1, x2), min(y1, y2)
    icon_w, icon_h = abs(x2 - x1), abs(y2 - y1)

    p3 = pick_point("coin HAUT-GAUCHE de la 2ème icône (juste à droite de la 1ère)")
    x3, y3 = rel_point(hwnd_mc, p3)
    spacing_x = x3 - icon_left

    cols = input("Combien d'icônes vois-tu sur cette ligne au total ? [7]: ").strip()
    cols = int(cols) if cols else 7

    has_second_row = input("Y a-t-il une 2ème ligne d'icônes visible en dessous ? (o/n) [n]: ").strip().lower()
    if has_second_row.startswith("o"):
        p4 = pick_point("coin HAUT-GAUCHE de l'icône juste EN DESSOUS de la 1ère")
        x4, y4 = rel_point(hwnd_mc, p4)
        spacing_y = y4 - icon_top
        rows = input("Combien de lignes au total ? [2]: ").strip()
        rows = int(rows) if rows else 2
    else:
        spacing_y = icon_h + 10
        rows = 1

    grid = {
        "start_x": icon_left,
        "start_y": icon_top,
        "icon_w": icon_w,
        "icon_h": icon_h,
        "spacing_x": spacing_x,
        "spacing_y": spacing_y,
        "columns": cols,
        "rows": rows,
    }

    # --- Calibration de la zone d'infobulle : capture automatique + lecture par l'utilisateur ---
    print("\nLe bot va survoler la 1ère icône pour faire apparaître son infobulle...")
    bring_to_foreground(hwnd_mc)
    left, top, _, _ = get_client_rect_on_screen(hwnd_mc)
    center_x, center_y = icon_left + icon_w // 2, icon_top + icon_h // 2
    win32api.SetCursorPos((left + center_x, top + center_y))
    time.sleep(1.0)

    margin_left, margin_top, margin_right, margin_bottom = 80, 160, 250, 40
    snap_region = {
        "left": max(0, icon_left - margin_left),
        "top": max(0, icon_top - margin_top),
        "width": icon_w + margin_left + margin_right,
        "height": icon_h + margin_top + margin_bottom,
    }
    snap_img = capture_region(hwnd_mc, snap_region)
    snap_path = Path(__file__).parent / "tooltip_calibration.png"
    cv2.imwrite(str(snap_path), snap_img)

    print(f"\nImage enregistrée ici : {snap_path}")
    print("Une fenêtre va s'ouvrir avec cette image, zoomée x3 pour plus de précision.")
    print("Clique d'abord sur le coin HAUT-GAUCHE du texte du NOM dans l'infobulle,")
    print("puis sur son coin BAS-DROITE. (Échap pour annuler)")
    (tl_x, tl_y), (br_x, br_y) = pick_two_points_on_image(
        snap_img, "Upgrade — clique coin HAUT-GAUCHE puis BAS-DROITE du nom"
    )

    tooltip_offset = {
        "left": snap_region["left"] + tl_x - icon_left,
        "top": snap_region["top"] + tl_y - icon_top,
        "width": br_x - tl_x,
        "height": br_y - tl_y,
    }

    return grid, tooltip_offset


def calibrate():
    print("=== Calibration ===")
    print("Place le navigateur (PalaTracker) et Minecraft là où ils resteront pendant")
    print("que le bot tourne (les deux doivent rester visibles à l'écran).\n")

    browser_title = input("Texte (partiel) du titre de la fenêtre navigateur [PalaTracker]: ").strip() or "PalaTracker"
    mc_title = input("Texte (partiel) du titre de la fenêtre Minecraft [Minecraft]: ").strip() or "Minecraft"

    hwnd_browser = find_window(browser_title)
    hwnd_mc = find_window(mc_title)

    def pick_point(label):
        input(f"Place la souris sur : {label}, puis appuie sur Entrée...")
        return win32api.GetCursorPos()

    def rel_point(hwnd, abs_point):
        left, top, _, _ = get_client_rect_on_screen(hwnd)
        return abs_point[0] - left, abs_point[1] - top

    print("\n--- Nom du bâtiment recommandé (ex: 'Ruche bourdonnante') ---")
    p1 = pick_point("coin HAUT-GAUCHE du nom")
    p2 = pick_point("coin BAS-DROITE du nom")
    x1, y1 = rel_point(hwnd_browser, p1)
    x2, y2 = rel_point(hwnd_browser, p2)
    rec_name = {"left": min(x1, x2), "top": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}

    print("\n--- Coût (ex: 256 331) ---")
    p1 = pick_point("coin HAUT-GAUCHE du coût")
    p2 = pick_point("coin BAS-DROITE du coût")
    x1, y1 = rel_point(hwnd_browser, p1)
    x2, y2 = rel_point(hwnd_browser, p2)
    rec_cost = {"left": min(x1, x2), "top": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}

    print("\n--- 'Achetable le ...' (la date ET l'heure) ---")
    p1 = pick_point("coin HAUT-GAUCHE de la date/heure")
    p2 = pick_point("coin BAS-DROITE de la date/heure")
    x1, y1 = rel_point(hwnd_browser, p1)
    x2, y2 = rel_point(hwnd_browser, p2)
    rec_date = {"left": min(x1, x2), "top": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}

    print("\n--- Bouton 'Mettre à jour les données' ---")
    p1 = pick_point("le bouton 'Mettre à jour les données'")
    x, y = rel_point(hwnd_browser, p1)
    refresh_button = {"left": x, "top": y}

    print("\n--- Liste des bâtiments en jeu (panneau BUILDINGS) ---")
    print("Vise le coin HAUT-GAUCHE de la 1ère ligne visible (ex: 'Mine abandonnée'),")
    print("puis le coin BAS-DROITE de la dernière ligne visible.")
    p1 = pick_point("coin HAUT-GAUCHE de la 1ère ligne")
    p2 = pick_point("coin BAS-DROITE de la dernière ligne visible")
    x1, y1 = rel_point(hwnd_mc, p1)
    x2, y2 = rel_point(hwnd_mc, p2)
    list_region = {"left": min(x1, x2), "top": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}

    n = input("Combien de lignes de bâtiments sont visibles dans cette zone ? [9]: ").strip()
    n = int(n) if n else 9
    row_height = max(1, list_region["height"] // n)

    upgrades_grid = None
    tooltip_offset = None
    ans = input(
        "\nVeux-tu aussi calibrer les UPGRADES (icônes sans texte, ex: section "
        "'UPGRADES' du Click Shop) ? (o/n) [n]: "
    ).strip().lower()
    if ans.startswith("o"):
        upgrades_grid, tooltip_offset = calibrate_upgrades(hwnd_mc)

    regions = {
        "rec_name": rec_name,
        "rec_cost": rec_cost,
        "rec_date": rec_date,
        "refresh_button": refresh_button,
        "ingame_buildings_list": list_region,
    }
    if upgrades_grid is not None:
        regions["upgrades"] = upgrades_grid
        regions["upgrades_tooltip_offset"] = tooltip_offset

    cfg = {
        "window_titles": {"browser": browser_title, "minecraft": mc_title},
        "regions": regions,
        "behavior": {
            "poll_interval_seconds": 5,
            "buy_buffer_seconds": 6,
            "building_row_height": row_height,
            "tooltip_wait_seconds": 0.6,
        },
    }
    save_config(cfg)
    print(f"\nConfiguration enregistrée dans {CONFIG_PATH}")


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--calibrate", action="store_true", help="Lance la calibration interactive complète")
    parser.add_argument(
        "--calibrate-upgrades",
        action="store_true",
        help="Recalibre uniquement la section Upgrades (garde le reste de la config existante)",
    )
    parser.add_argument("--tesseract", help="Chemin vers tesseract.exe si non détecté automatiquement")
    args = parser.parse_args()

    if args.tesseract:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    try:
        if args.calibrate:
            calibrate()
        elif args.calibrate_upgrades:
            cfg = load_config()
            hwnd_mc = find_window(cfg["window_titles"]["minecraft"])
            grid, tooltip_offset = calibrate_upgrades(hwnd_mc)
            cfg["regions"]["upgrades"] = grid
            cfg["regions"]["upgrades_tooltip_offset"] = tooltip_offset
            save_config(cfg)
            print(f"\nSection Upgrades mise à jour dans {CONFIG_PATH}")
        else:
            run(load_config())
    except KeyboardInterrupt:
        print("\nArrêt du bot.")