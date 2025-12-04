import threading
import time
import random
import os
import win32api
import win32con
import win32gui
import ctypes
import keyboard

WINDOW_TITLE = "Paladium - Khalifou" 

VK_W = 0x57
VK_A = 0x41
VK_D = 0x44
VK_T = 0x54
VK_ESC = 0x1B
VK_SPACE = 0x20
VK_CONTROL = 0x11

X_COBBLESTONE_REL = 30000 
Y_COBBLESTONE_REL = 50000 
X_BOUTON_VENDRE_REL = 60000 
Y_BOUTON_VENDRE_REL = 50000 

stop_script = False
minecraft_hwnd = None

MOUSE_LEFT_DOWN = 0x0201
MOUSE_LEFT_UP = 0x0202

MOUSE_MOVE = 0x0200

def find_minecraft_window():
    global minecraft_hwnd
    minecraft_hwnd = win32gui.FindWindow(None, WINDOW_TITLE)
    if minecraft_hwnd == 0:
        print(f"[ERREUR] Fenêtre introuvable : '{WINDOW_TITLE}'. Vérifiez le titre.")
        return False
    print(f"[INFO] Fenêtre Minecraft trouvée (HWND: {minecraft_hwnd}).")
    return True

def send_key_down(vk_code):
    win32api.PostMessage(minecraft_hwnd, win32con.WM_KEYDOWN, vk_code, 0)

def send_key_up(vk_code):
    win32api.PostMessage(minecraft_hwnd, win32con.WM_KEYUP, vk_code, 0)

def send_mouse_down():
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_DOWN, win32con.MK_LBUTTON, 0)

def send_mouse_up():
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_UP, 0, 0)

def clean_strafe_keys():
    send_key_up(VK_A)
    send_key_up(VK_D)

def stop_listener():
    global stop_script
    keyboard.wait('esc') 
    stop_script = True
    print("\n[INFO] Déconnexion immédiate demandée (touche Échap). Arrêt du script.")
    
    send_mouse_up()
    send_key_up(VK_W)
    clean_strafe_keys()
    os._exit(0) 

def vendre_cobblestone():
    print("[AVERTISSEMENT] Vente désactivée en mode non-intrusif pour éviter l'interférence avec la souris/clavier.")
    pass

def rotate_view(angle_dx):
    print("[AVERTISSEMENT] Rotation désactivée en mode non-intrusif pour éviter l'interférence avec la souris/clavier.")
    pass

threading.Thread(target=stop_listener, daemon=True).start()

if not find_minecraft_window():
    os._exit(1)

print("--- FARMER LANCE (MODE NON-INTRUSIF / MINEUR PUR) ---")
print("NOTE: La rotation et la vente sont désactivées pour minimiser les conflits d'Alt+Tab.")
print("Préparation : 5 secondes pour te placer devant la pierre. **La fenêtre DOIT rester ouverte, non minimisée.**")
time.sleep(5)

print("Minage et anti-AFK activés. Bonne chance ! (ESC pour stopper)")

send_mouse_down()
send_key_down(VK_W)

last_action_time = time.time()

try:
    while not stop_script:
        now = time.time()

        if now - last_action_time > random.uniform(6, 12):
            action = random.choice(['jump', 'strafe'])
            
            if action == 'jump':
                send_key_down(VK_SPACE)
                time.sleep(random.uniform(0.1, 0.3))
                send_key_up(VK_SPACE)

            elif action == 'strafe':
                key_code = random.choice([VK_A, VK_D])
                send_key_down(key_code)
                time.sleep(random.uniform(0.2, 0.4))
                send_key_up(key_code)

            last_action_time = now

        time.sleep(0.1)

finally:
    send_mouse_up()
    send_key_up(VK_W)
    clean_strafe_keys()
    print("--- SCRIPT ARRÊTÉ ---")