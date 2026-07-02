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
    s = s.lower()
    # Tout ce qui n'est pas alphanumérique (y compris les sauts de ligne) devient
    # un espace, pour ne pas coller deux mots ensemble sur du texte multi-lignes.
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.strip()


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

def scan_buildings_rows(hwnd_mc, cfg, debug=True):
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

        # Le coût peut apparaître n'importe où dans le texte OCR de la ligne
        cost = None
        m_cost = re.search(r"[\d ]{4,}", text)
        if m_cost:
            cost = parse_number_fr(m_cost.group())

        # Le nom est toujours sur la 1ère ligne utile ; les lignes suivantes ne
        # sont que du bruit (icônes/décorations qui débordent dans la zone).
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        first_line = lines[0] if lines else ""

        # On retire TOUS les chiffres (pas seulement les séquences de 4+), pour
        # aussi enlever le petit badge "quantité possédée" (ex: "31") qui colle
        # au nom sur la même ligne.
        name_part = re.sub(r"\d+", "", first_line)
        name_part = re.sub(r"\s{2,}", " ", name_part).strip(" .")

        if debug:
            print(f"    [debug] ligne #{i} (y={y0}) -> nom lu : {name_part!r} | coût lu : {cost}")
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


# Couleur de fond typique des infobulles Paladium (violet très sombre), en BGR.
_TOOLTIP_BG_BGR_RANGE = {
    "b": (10, 48),
    "g": (0, 20),
    "r": (8, 45),
}


def detect_tooltip_box(img_bgr, min_area=3000):
    """Détecte la boîte d'infobulle dans une image en repérant son fond violet
    très sombre caractéristique. Retourne (x, y, w, h) ou None si non trouvée."""
    b = img_bgr[:, :, 0].astype(int)
    g = img_bgr[:, :, 1].astype(int)
    r = img_bgr[:, :, 2].astype(int)
    mask = (
        (r >= _TOOLTIP_BG_BGR_RANGE["r"][0]) & (r <= _TOOLTIP_BG_BGR_RANGE["r"][1]) &
        (g >= _TOOLTIP_BG_BGR_RANGE["g"][0]) & (g <= _TOOLTIP_BG_BGR_RANGE["g"][1]) &
        (b >= _TOOLTIP_BG_BGR_RANGE["b"][0]) & (b <= _TOOLTIP_BG_BGR_RANGE["b"][1]) &
        (b > g) & (r > g)
    ).astype(np.uint8) * 255

    kernel = np.ones((17, 17), np.uint8)
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < min_area:
        return None
    return cv2.boundingRect(largest)


def extract_tooltip_title(box_crop_bgr):
    """Isole et lit le TITRE (toujours en rose/magenta) dans une infobulle,
    peu importe sa hauteur totale (qui varie selon le nombre de conditions
    affichées en dessous)."""
    b, g, r = cv2.split(box_crop_bgr.astype(int))
    mask = (g < 30) & (r > 100) & (b > 100) & (np.abs(r - b) < 40)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        return ""
    y0, y1 = max(0, ys.min() - 6), min(box_crop_bgr.shape[0], ys.max() + 6)
    x0, x1 = max(0, xs.min() - 6), min(box_crop_bgr.shape[1], xs.max() + 6)
    mask_u8 = (mask.astype(np.uint8) * 255)[y0:y1, x0:x1]
    mask_u8 = cv2.resize(mask_u8, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    mask_u8 = cv2.dilate(mask_u8, np.ones((2, 2), np.uint8), iterations=1)
    try:
        return pytesseract.image_to_string(mask_u8, config="--psm 7").strip()
    except pytesseract.TesseractError:
        return ""


def read_upgrade_tooltip(hwnd_mc, icon_center_x, icon_center_y):
    """Capture une zone généreuse autour du curseur (l'infobulle apparaît en
    général au-dessus), détecte automatiquement la boîte, puis en extrait le
    titre. Ne nécessite AUCUNE calibration manuelle."""
    margin_left, margin_right = 280, 280
    margin_top, margin_bottom = 320, 40
    region = {
        "left": max(0, icon_center_x - margin_left),
        "top": max(0, icon_center_y - margin_top),
        "width": margin_left + margin_right,
        "height": margin_top + margin_bottom,
    }
    img = capture_region(hwnd_mc, region)

    box = detect_tooltip_box(img)
    if box is None:
        return ""
    x, y, w, h = box
    pad = 18
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(img.shape[1], x + w + pad), min(img.shape[0], y + h + pad)
    crop = img[y0:y1, x0:x1]
    return extract_tooltip_title(crop)


def find_and_click_upgrade(hwnd_mc, target_name, cfg, debug=True):
    """Survole chaque icône de la grille Upgrades, lit le titre de son infobulle
    (détection automatique, hauteur variable gérée), et clique si ça correspond
    au nom recherché. Retourne True si un achat a été tenté."""
    if "upgrades" not in cfg["regions"]:
        return False

    grid = cfg["regions"]["upgrades"]
    icon_w, icon_h = grid["icon_w"], grid["icon_h"]
    wait_s = cfg["behavior"].get("tooltip_wait_seconds", 0.6)

    bring_to_foreground(hwnd_mc)

    for i, (x, y) in enumerate(generate_upgrade_icon_positions(grid)):
        center_x, center_y = x + icon_w // 2, y + icon_h // 2
        hover_in_window(hwnd_mc, center_x, center_y, focus=False)
        time.sleep(wait_s)
        tooltip_title = read_upgrade_tooltip(hwnd_mc, center_x, center_y)

        if not tooltip_title:
            # Une 2e tentative au cas où l'infobulle a mis du temps à apparaître
            time.sleep(wait_s)
            tooltip_title = read_upgrade_tooltip(hwnd_mc, center_x, center_y)

        if debug:
            print(f"    [debug] icône #{i} ({center_x},{center_y}) -> titre lu : {tooltip_title!r}")

        if not tooltip_title:
            continue

        if names_match(target_name, tooltip_title):
            click_in_window(hwnd_mc, center_x, center_y, focus=False)
            return True

    return False


# ---------------------------------------------------------------------------
# Boucle principale
# ---------------------------------------------------------------------------

def scroll_buildings_list(hwnd_mc, notches, cfg):
    """Fait défiler la liste des Bâtiments via la molette de la souris.
    notches > 0 fait remonter (vers le haut), notches < 0 fait descendre
    (révèle les bâtiments suivants)."""
    region = cfg["regions"]["ingame_buildings_list"]
    center_x = region["left"] + region["width"] // 2
    center_y = region["top"] + region["height"] // 2

    bring_to_foreground(hwnd_mc)
    left, top, _, _ = get_client_rect_on_screen(hwnd_mc)
    win32api.SetCursorPos((left + center_x, top + center_y))
    time.sleep(0.05)
    win32api.mouse_event(win32con.MOUSEEVENTF_WHEEL, 0, 0, notches * 120, 0)


def find_building_with_scroll(hwnd_mc, target_name, cfg, debug=True):
    """Cherche le bâtiment recommandé, en faisant défiler la liste si besoin.
    Remonte tout en haut d'abord (état connu), puis scanne page par page en
    descendant, jusqu'à trouver une correspondance ou détecter la fin de la
    liste (le contenu ne bouge plus après un défilement)."""
    behavior = cfg["behavior"]
    max_scrolls = behavior.get("max_scroll_steps", 12)
    scroll_notches = behavior.get("scroll_notches_per_step", 3)
    retries_per_position = 2

    scroll_buildings_list(hwnd_mc, 30, cfg)  # remonte tout en haut
    time.sleep(0.3)

    previous_fingerprint = None
    for step in range(max_scrolls + 1):
        rows = []
        row = None
        for attempt in range(retries_per_position):
            rows = scan_buildings_rows(hwnd_mc, cfg, debug=(debug and attempt == 0))
            row = find_matching_row(target_name, rows)
            if row is not None:
                return row
            if attempt < retries_per_position - 1:
                time.sleep(0.5)  # une 2e capture, au cas où l'échec vient d'une animation

        fingerprint = tuple(r["name"] for r in rows)
        if step > 0 and fingerprint == previous_fingerprint:
            if debug:
                print("    [debug] défilement sans effet, fin de la liste atteinte.")
            break
        previous_fingerprint = fingerprint

        if step < max_scrolls:
            if debug:
                print(f"    [debug] non trouvé sur cette page, défilement #{step + 1}...")
            scroll_buildings_list(hwnd_mc, -scroll_notches, cfg)
            time.sleep(0.35)

    return None


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

        # --- Tentative d'achat : on cherche d'abord parmi les Bâtiments (avec scroll) ---
        row = find_building_with_scroll(hwnd_mc, rec["name"], cfg)

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

def calibrate_upgrades(hwnd_mc):
    """Calibre la grille d'icônes Upgrades (position/espacement). La lecture de
    l'infobulle (nom) est entièrement automatique — pas de calibration nécessaire."""

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

    # Test immédiat : on survole la 1ère icône et on vérifie que la détection
    # automatique de l'infobulle fonctionne bien, pour rassurer l'utilisateur
    # tout de suite (au lieu de découvrir un souci seulement au lancement du bot).
    print("\nTest de la détection automatique d'infobulle sur la 1ère icône...")
    center_x, center_y = icon_left + icon_w // 2, icon_top + icon_h // 2
    hover_in_window(hwnd_mc, center_x, center_y)
    time.sleep(0.8)
    title = read_upgrade_tooltip(hwnd_mc, center_x, center_y)
    if title:
        print(f"  -> Titre détecté : {title!r}")
        print("  (Si ce n'est pas le bon texte, ce n'est pas grave : la détection")
        print("   s'adapte automatiquement à chaque icône, pas besoin de recalibrer.)")
    else:
        print(
            "  [!] Aucune infobulle détectée. Vérifie que la souris est bien restée sur "
            "l'icône et que rien ne la cache, puis relance si besoin."
        )

    return grid


def pick_relative_point(hwnd, label):
    """Demande de placer la souris à un endroit précis, retourne la position
    en coordonnées relatives à la zone CLIENT de la fenêtre."""
    input(f"Place la souris sur : {label}, puis appuie sur Entrée...")
    abs_point = win32api.GetCursorPos()
    left, top, _, _ = get_client_rect_on_screen(hwnd)
    return abs_point[0] - left, abs_point[1] - top


def pick_box(hwnd, label):
    x1, y1 = pick_relative_point(hwnd, f"coin HAUT-GAUCHE de : {label}")
    x2, y2 = pick_relative_point(hwnd, f"coin BAS-DROITE de : {label}")
    return {"left": min(x1, x2), "top": min(y1, y2), "width": abs(x2 - x1), "height": abs(y2 - y1)}


REGION_LABELS = {
    "rec_name": "le NOM du bâtiment/upgrade recommandé (vise LARGE pour couvrir les noms longs)",
    "rec_cost": "le COÛT",
    "rec_date": "la date/heure 'Achetable le'",
}


def debug_snapshot_buildings_list(cfg):
    """Sauvegarde une image de la zone 'ingame_buildings_list' actuellement configurée,
    pour vérifier visuellement si elle pointe au bon endroit sans lancer toute la boucle."""
    hwnd_mc = find_window(cfg["window_titles"]["minecraft"])
    region = cfg["regions"]["ingame_buildings_list"]
    img = capture_region(hwnd_mc, region)
    path = Path(__file__).parent / "buildings_list_debug.png"
    cv2.imwrite(str(path), img)
    print(f"Capture enregistrée ici : {path}")
    print("Ouvre cette image : si elle est vide/floue/décalée par rapport à la vraie liste,")
    print("recalibre avec : python clicker_auto_buyer.py --recalibrate-region ingame_buildings_list")


def recalibrate_region(region_key):
    """Recalibre une seule zone du config.json existant, sans repasser par tout le reste."""
    cfg = load_config()

    if region_key in REGION_LABELS:
        hwnd = find_window(cfg["window_titles"]["browser"])
        cfg["regions"][region_key] = pick_box(hwnd, REGION_LABELS[region_key])

    elif region_key == "refresh_button":
        hwnd = find_window(cfg["window_titles"]["browser"])
        x, y = pick_relative_point(hwnd, "le bouton 'Mettre à jour les données'")
        cfg["regions"]["refresh_button"] = {"left": x, "top": y}

    elif region_key == "ingame_buildings_list":
        hwnd = find_window(cfg["window_titles"]["minecraft"])
        box = pick_box(
            hwnd,
            "la liste des bâtiments (coin HAUT-GAUCHE de la 1ère ligne, "
            "puis BAS-DROITE de la dernière ligne visible)",
        )
        n = input("Combien de lignes de bâtiments sont visibles dans cette zone ? [9]: ").strip()
        n = int(n) if n else 9
        cfg["regions"]["ingame_buildings_list"] = box
        cfg["behavior"]["building_row_height"] = max(1, box["height"] // n)

    else:
        raise SystemExit(f"Zone inconnue : {region_key}")

    save_config(cfg)
    print(f"\nZone '{region_key}' recalibrée et enregistrée dans {CONFIG_PATH}")


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
    ans = input(
        "\nVeux-tu aussi calibrer les UPGRADES (icônes sans texte, ex: section "
        "'UPGRADES' du Click Shop) ? (o/n) [n]: "
    ).strip().lower()
    if ans.startswith("o"):
        upgrades_grid = calibrate_upgrades(hwnd_mc)

    regions = {
        "rec_name": rec_name,
        "rec_cost": rec_cost,
        "rec_date": rec_date,
        "refresh_button": refresh_button,
        "ingame_buildings_list": list_region,
    }
    if upgrades_grid is not None:
        regions["upgrades"] = upgrades_grid

    cfg = {
        "window_titles": {"browser": browser_title, "minecraft": mc_title},
        "regions": regions,
        "behavior": {
            "poll_interval_seconds": 5,
            "buy_buffer_seconds": 6,
            "building_row_height": row_height,
            "tooltip_wait_seconds": 0.6,
            "max_scroll_steps": 12,
            "scroll_notches_per_step": 3,
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
    parser.add_argument(
        "--recalibrate-region",
        choices=["rec_name", "rec_cost", "rec_date", "refresh_button", "ingame_buildings_list"],
        help="Recalibre uniquement une zone précise (garde le reste de la config existante)",
    )
    parser.add_argument(
        "--debug-buildings",
        action="store_true",
        help="Sauvegarde une capture de la zone liste des bâtiments pour vérification visuelle",
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
            grid = calibrate_upgrades(hwnd_mc)
            cfg["regions"]["upgrades"] = grid
            cfg["regions"].pop("upgrades_tooltip_offset", None)  # obsolète, plus utilisé
            save_config(cfg)
            print(f"\nSection Upgrades mise à jour dans {CONFIG_PATH}")
        elif args.recalibrate_region:
            recalibrate_region(args.recalibrate_region)
        elif args.debug_buildings:
            debug_snapshot_buildings_list(load_config())
        else:
            run(load_config())
    except KeyboardInterrupt:
        print("\nArrêt du bot.")