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
print("Préparation : 5 secondes pour te placer devant la pierre. Regarde bien TOUT DROIT.")
time.sleep(5)

print("[INIT] Position enregistrée. Minage et anti-AFK activés. (ESC pour stopper)")
direction_right = True
current_angle = 0  # 0 = tout droit. On va traquer l'angle de la caméra ici.

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
            # On ne reset pas last_direction_change ici pour garder le cycle de minage

        # --- BLOC ANTI-AFK (ALTERNANCE DROITE / GAUCHE) ---
        if now - last_direction_change > 60:
            pyautogui.mouseUp(button='left')
            pyautogui.keyUp('w')
            clean_strafe_keys()
            time.sleep(0.1)

            # Calcul de l'angle visé (ex: 250 = Droite, -250 = Gauche)
            target_angle = 250 if direction_right else -250
            
            # De combien de pixels on doit bouger la souris pour atteindre cet angle ?
            # Si on est à 250 et qu'on veut aller à -250, il faut faire -500 !
            movement_needed = target_angle - current_angle 

            if direction_right:
                print(f"[AFK] Rotation vers la DROITE (Mouvement souris: {movement_needed})")
            else:
                print(f"[AFK] Rotation vers la GAUCHE (Mouvement souris: {movement_needed})")

            pyautogui.moveRel(movement_needed, 0, duration=0.5)
            
            # Mise à jour de l'angle actuel et préparation du prochain tour
            current_angle = target_angle
            direction_right = not direction_right

            time.sleep(0.2)
            pyautogui.mouseDown(button='left')
            time.sleep(1.5)
            pyautogui.keyDown('w')

            last_direction_change = now

        # --- BLOC MACRO ACTIONS ALEATOIRES SECURISÉ ---
        if now - last_action_time > random.uniform(6, 12):
            action = random.choice(['move_mouse', 'jump', 'strafe'])

            if action == 'move_mouse':
                # Jitter de la souris, mais on annule le mouvement juste après pour ne pas dévier
                dx = random.randint(-15, 15)
                duration = random.uniform(0.05, 0.1)
                pyautogui.moveRel(dx, 0, duration)
                time.sleep(0.1)
                pyautogui.moveRel(-dx, 0, duration) 

            elif action == 'jump':
                pyautogui.keyDown('space')
                time.sleep(random.uniform(0.1, 0.3))
                pyautogui.keyUp('space')

            elif action == 'strafe':
                # Strafe aller-retour obligatoire pour ne pas s'enfoncer dans le mur
                strafe_duration = random.uniform(0.2, 0.4)
                if random.choice([True, False]):
                    pyautogui.keyDown('a')
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('a')
                    pyautogui.keyDown('d') # On revient
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('d')
                else:
                    pyautogui.keyDown('d')
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('d')
                    pyautogui.keyDown('a') # On revient
                    time.sleep(strafe_duration)
                    pyautogui.keyUp('a')

            last_action_time = now

        time.sleep(0.1)

finally:
    pyautogui.mouseUp(button='left')
    pyautogui.keyUp('w')
    clean_strafe_keys()
    print("--- SCRIPT ARRÊTÉ ---")