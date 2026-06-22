import pyautogui
import keyboard
import threading
import time
import random
import os

X_COBBLESTONE = 789
Y_COBBLESTONE = 929
X_BOUTON_VENDRE = 1727
Y_BOUTON_VENDRE = 937

stop_script = False

def clean_strafe_keys():
    pyautogui.keyUp('a')
    pyautogui.keyUp('d')

def stop_listener():
    global stop_script
    keyboard.wait('esc')
    stop_script = True
    print("\n[INFO] Déconnexion immédiate demandée (touche Échap). Arrêt du script.")
    pyautogui.mouseUp(button='left')
    pyautogui.keyUp('w')
    clean_strafe_keys()
    os._exit(0)

def vendre_cobblestone():
    print("[VENTE] Petite pause commerce ! Vente automatique lancée...")
    pyautogui.mouseUp(button='left')
    pyautogui.keyUp('w')
    clean_strafe_keys()
    time.sleep(1)
    pyautogui.press('t')
    time.sleep(0.5)
    pyautogui.write('/shop', interval=0.1)
    pyautogui.press('enter')
    time.sleep(2)
    pyautogui.moveTo(X_COBBLESTONE, Y_COBBLESTONE, duration=0.2)
    pyautogui.click()
    time.sleep(0.5)
    print("[VENTE] Vente de toutes les cobblestones (Ctrl + Clic)...")
    pyautogui.keyDown('ctrl')
    pyautogui.moveTo(X_BOUTON_VENDRE, Y_BOUTON_VENDRE, duration=0.2)
    pyautogui.click()
    time.sleep(1)
    pyautogui.keyUp('ctrl')
    pyautogui.press('esc')
    time.sleep(1)
    pyautogui.mouseDown(button='left')
    pyautogui.keyDown('w')
    print("[MINE] Inventaire vidé. Reprise du minage !")

threading.Thread(target=stop_listener, daemon=True).start()

print("--- FARMER LANCE ---")
print("Préparation : 5 secondes pour te placer devant la pierre.")
time.sleep(5)

print("[INIT] Position enregistrée. Minage et anti-AFK activés. (ESC pour stopper)")
direction_right = True

pyautogui.mouseDown(button='left')
pyautogui.keyDown('w')

last_action_time = time.time()
last_direction_change = time.time()
last_sell_time = time.time()

try:
    while not stop_script:
        now = time.time()

        # --- BLOC VENTE ---
        if now - last_sell_time > 600:
            vendre_cobblestone()
            last_sell_time = now
            last_direction_change = now

        # --- BLOC ANTI-AFK CORRIGÉ ---
        if now - last_direction_change > 60:
            print("[AFK] Changement de direction pour ne pas être kick...")

            pyautogui.mouseUp(button='left')
            pyautogui.keyUp('w')
            clean_strafe_keys()
            time.sleep(0.1)

            angle = 250  
            if direction_right:
                print("-> Tourne à droite")
                pyautogui.moveRel(angle, 0, duration=0.2)
                time.sleep(0.5)
                print("[VISÉE] Recentrage...")
                pyautogui.moveRel(-angle, 0, duration=0.2) # Annulation exacte
            else:
                print("<- Tourne à gauche")
                pyautogui.moveRel(-angle, 0, duration=0.2)
                time.sleep(0.5)
                print("[VISÉE] Recentrage...")
                pyautogui.moveRel(angle, 0, duration=0.2) # Annulation exacte

            time.sleep(0.2)
            pyautogui.mouseDown(button='left')
            time.sleep(1.5)
            pyautogui.keyDown('w')

            direction_right = not direction_right
            last_direction_change = now

        # --- BLOC MACRO ACTIONS ALEATOIRES CORRIGÉ ---
        if now - last_action_time > random.uniform(6, 12):
            action = random.choice(['move_mouse', 'jump', 'strafe'])

            if action == 'move_mouse':
                # Si on bouge la souris pour simuler une action humaine, il faut la remettre au centre
                dx = random.randint(-15, 15)
                duration = random.uniform(0.05, 0.1)
                pyautogui.moveRel(dx, 0, duration)
                time.sleep(0.1)
                pyautogui.moveRel(-dx, 0, duration) # Retour à la position d'origine

            elif action == 'jump':
                pyautogui.keyDown('space')
                time.sleep(random.uniform(0.1, 0.3))
                pyautogui.keyUp('space')

            elif action == 'strafe':
                # Si on strafe, il faut obligatoirement revenir sur ses pas pour rester face au bloc
                strafe_duration = random.uniform(0.2, 0.4)
                if random.choice([True, False]):
                    pyautogui.keyDown('a')
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('a')
                    pyautogui.keyDown('d') # Retour à droite
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('d')
                else:
                    pyautogui.keyDown('d')
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('d')
                    pyautogui.keyDown('a') # Retour à gauche
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('a')

            last_action_time = now

        time.sleep(0.1)

finally:
    pyautogui.mouseUp(button='left')
    pyautogui.keyUp('w')
    clean_strafe_keys()
    print("--- SCRIPT ARRÊTÉ ---")