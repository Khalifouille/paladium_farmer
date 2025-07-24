import pyautogui
import keyboard
import threading
import time
import random

stop_script = False

def stop_listener():
    global stop_script
    keyboard.wait('esc')
    stop_script = True
    print("\n🛑 Script stoppé par touche ESC.")

threading.Thread(target=stop_listener, daemon=True).start()

print("⌛ Démarrage dans 5 secondes, place ta souris correctement (face à la stone)")
time.sleep(5)

initial_mouse_pos = pyautogui.position()
print(f"📍 Position initiale enregistrée : {initial_mouse_pos}")

print("⛏️ Minage + anti-AFK lancé. Appuie sur Échap pour arrêter.")

# État de direction : True = droite, False = gauche
direction_right = True

# Commencer à miner
pyautogui.mouseDown(button='left')
pyautogui.keyDown('w')

last_action_time = time.time()
last_reset_time = time.time()
last_direction_change = time.time()

try:
    while not stop_script:
        now = time.time()

        # 🔄 Réajustement souris à la position initiale toutes les 60 secondes
        if now - last_reset_time > 60:
            print("🔄 Réajustement souris à la position initiale.")
            pyautogui.moveTo(initial_mouse_pos.x, initial_mouse_pos.y, duration=0.2)
            last_reset_time = now

        # 🔁 Changement de direction toutes les 60 secondes
        if now - last_direction_change > 60:
            print("🔁 Changement de direction.")

            # Stopper les touches
            pyautogui.mouseUp(button='left')
            pyautogui.keyUp('w')
            time.sleep(0.5)

            # Tourner la souris à droite ou à gauche
            angle = 250  # Valeur à adapter selon ta sensibilité
            if direction_right:
                print("➡️ Tourne à droite")
                pyautogui.moveRel(angle, 0, duration=0.2)
            else:
                print("⬅️ Tourne à gauche")
                pyautogui.moveRel(-angle, 0, duration=0.2)

            # Repart miner
            pyautogui.mouseDown(button='left')
            pyautogui.keyDown('w')

            direction_right = not direction_right
            last_direction_change = now
            last_reset_time = now  # réinitialise le timer de position

        # 🎯 Anti-AFK
        if now - last_action_time > random.uniform(6, 12):
            action = random.choice(['move_mouse', 'jump', 'strafe'])

            if action == 'move_mouse':
                dx = random.randint(-15, 15)
                duration = random.uniform(0.05, 0.05)
                pyautogui.moveRel(dx, 0, duration)

            elif action == 'jump':
                pyautogui.keyDown('space')
                time.sleep(random.uniform(0.1, 0.3))
                pyautogui.keyUp('space')

            elif action == 'strafe':
                key = random.choice(['a', 'd'])
                pyautogui.keyDown(key)
                time.sleep(random.uniform(0.2, 0.4))
                pyautogui.keyUp(key)

            last_action_time = now

        time.sleep(0.1)

finally:
    pyautogui.mouseUp(button='left')
    pyautogui.keyUp('w')
    print("👋 Script arrêté proprement.")
