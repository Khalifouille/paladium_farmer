import threading
import time
import random
import os
import win32api
import win32con
import win32gui
import ctypes
import keyboard

VK_W = 0x57
VK_A = 0x41
VK_D = 0x44
VK_T = 0x54
VK_ESC = 0x1B
VK_SPACE = 0x20
VK_CONTROL = 0x11
VK_RETURN = 0x0D

WINDOW_TITLE = "Paladium - Khalifou" 

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

def send_mouse_click(x, y):
    lParam = win32api.MAKELONG(x, y)
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_DOWN, win32con.MK_LBUTTON, lParam)
    time.sleep(0.1)
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_UP, 0, lParam)

def send_mouse_down():
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_DOWN, win32con.MK_LBUTTON, 0)

def send_mouse_up():
    win32gui.PostMessage(minecraft_hwnd, MOUSE_LEFT_UP, 0, 0)

def send_chat_command(command):
    send_key_down(VK_T)
    send_key_up(VK_T)
    time.sleep(0.5)
    
    for char in command:
        vk = ord(char.upper()) 
        try:
            win32api.keybd_event(vk, 0, 0, 0) 
            time.sleep(0.05)
            win32api.keybd_event(vk, 0, win32con.KEYEVENTF_KEYUP, 0)
        except:
            print(f"[ATTENTION] Caractère '{char}' non supporté directement par keybd_event sans mapping.")
            pass

    time.sleep(0.5)
    win32api.keybd_event(VK_RETURN, 0, 0, 0) 
    time.sleep(0.05)
    win32api.keybd_event(VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
    time.sleep(0.5)
    
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
    print("[VENTE] Petite pause commerce ! Vente automatique lancée...")
    
    send_mouse_up()
    send_key_up(VK_W)
    clean_strafe_keys()
    time.sleep(1) 

    send_chat_command('shop')
    time.sleep(2) 

    print("[VENTE] Clics sur l'interface de vente...")
    
    send_mouse_click(X_COBBLESTONE_REL, Y_COBBLESTONE_REL)
    time.sleep(0.5)

    send_key_down(VK_CONTROL)
    send_mouse_click(X_BOUTON_VENDRE_REL, Y_BOUTON_VENDRE_REL)
    time.sleep(1) 
    send_key_up(VK_CONTROL)

    send_key_down(VK_ESC)
    send_key_up(VK_ESC)
    time.sleep(1)
    
    send_mouse_down() 
    send_key_down(VK_W) 
    print("[MINE] Inventaire vidé. Reprise du minage !")

def rotate_view(angle_dx):
    ctypes.windll.user32.mouse_event(win32con.MOUSEEVENTF_MOVE, angle_dx, 0, 0, 0)

threading.Thread(target=stop_listener, daemon=True).start()

if not find_minecraft_window():
    os._exit(1)

print("--- FARMER LANCE (MODE NON-INTRUSIF COMPLET) ---")
print("NOTE: La rotation et la vente sont réactivées. Cela peut causer des conflits si la solution Alt+Tab n'est pas parfaite.")
print("Préparation : 5 secondes pour te placer devant la pierre. **La fenêtre DOIT rester ouverte, non minimisée.**")
time.sleep(5)

print("Minage, anti-AFK, Rotation et Vente activés. Bonne chance ! (ESC pour stopper)")

direction_right = True
send_mouse_down()
send_key_down(VK_W)

last_action_time = time.time()
last_direction_change = time.time()
last_sell_time = time.time() 

try:
    while not stop_script:
        now = time.time()

        if now - last_sell_time > 600:
            vendre_cobblestone()
            last_sell_time = now 
            last_direction_change = now 

        if now - last_direction_change > 60:
            print("[AFK] Changement de direction pour ne pas être kick...")

            send_mouse_up()
            send_key_up(VK_W)
            clean_strafe_keys()
            time.sleep(0.5) 
            
            angle = 250  
            if direction_right:
                print("-> Tourne à droite")
                rotate_view(angle)
            else:
                print("<- Tourne à gauche")
                rotate_view(-angle)

            send_mouse_down()
            
            time.sleep(1.5) 
            
            send_key_down(VK_W)

            direction_right = not direction_right
            last_direction_change = now

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