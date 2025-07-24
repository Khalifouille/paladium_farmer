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

print("🔥 Anti-AFK cuisson lancé. Appuie sur Échap pour arrêter.")
time.sleep(2)

last_action_time = time.time()

try:
    while not stop_script:
        now = time.time()

        if now - last_action_time > random.uniform(6, 12):
            action = random.choice([
                'move_mouse',
                'jump',
                'strafe',
                'forward_backward',
                'sneak'
            ])

            if action == 'move_mouse':
                dx = random.randint(-10, 10)
                dy = random.randint(-5, 5)
                pyautogui.moveRel(dx, dy, duration=0.1)

            elif action == 'jump':
                pyautogui.keyDown('space')
                time.sleep(random.uniform(0.1, 0.3))
                pyautogui.keyUp('space')

            elif action == 'strafe':
                key = random.choice(['a', 'd'])
                pyautogui.keyDown(key)
                time.sleep(random.uniform(0.2, 0.4))
                pyautogui.keyUp(key)

            elif action == 'forward_backward':
                key = random.choice(['w', 's'])
                pyautogui.keyDown(key)
                time.sleep(random.uniform(0.2, 0.4))
                pyautogui.keyUp(key)

            elif action == 'sneak':
                pyautogui.keyDown('ctrl')
                time.sleep(random.uniform(0.3, 0.6))
                pyautogui.keyUp('ctrl')

            last_action_time = now

        time.sleep(0.1)

finally:
    print("👋 Script anti-AFK cuisson terminé.")
