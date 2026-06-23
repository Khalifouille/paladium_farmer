import mss
from PIL import Image
import time

print("Passe sur Minecraft (3 secondes)...")
time.sleep(3)

with mss.mss() as sct:
    # Capture tout l'écran pour voir ce que mss voit vraiment
    shot = sct.grab(sct.monitors[1])
    img = Image.frombytes("RGB", shot.size, shot.rgb)
    img.save("fullscreen_debug.png")
    print(f"Écran capturé : {shot.size}")
    print("Sauvegardé : fullscreen_debug.png")