#!/usr/bin/env python3
"""Create BaluDesk app icon"""

from PIL import Image, ImageDraw
import os

# Erstelle öffentliches Verzeichnis
public_dir = os.path.join(
    os.path.dirname(__file__),
    'baludesk',
    'frontend',
    'public'
)
os.makedirs(public_dir, exist_ok=True)

# Farben
BG_COLOR = '#0f172a'  # Dunkelblau
CLOUD_COLOR = '#06b6d4'  # Cyan
ACCENT_COLOR = '#0ea5e9'  # Heller Blau

# Erstelle ein 256x256 PNG
img = Image.new('RGB', (256, 256), color=BG_COLOR)
draw = ImageDraw.Draw(img)

# Äußerer Kreis (Glow-Effekt)
draw.ellipse([40, 40, 216, 216], outline=ACCENT_COLOR, width=1)

# Cloud-Form (vereinfacht)
# Nutze mehrere Kreise um Cloud-Shape zu machen
positions = [
    (80, 100, 95, 130),   # Linke Beule
    (100, 85, 140, 125),  # Obere Mitte
    (150, 95, 165, 130),  # Rechte Beule
    (85, 120, 175, 155),  # Untere Fläche
]

# Zeichne Cloud mit Polygon
cloud_points = [
    (90, 140),   # Links unten
    (170, 140),  # Rechts unten
    (180, 115),  # Rechts oben
    (165, 90),   # Rechts-Mitte oben
    (140, 80),   # Mitte oben
    (110, 85),   # Links-Mitte oben
    (85, 105),   # Links
]

draw.polygon(cloud_points, fill=CLOUD_COLOR, outline=ACCENT_COLOR)

# Sync-Pfeile innen (vereinfacht)
# Rechter Pfeil
draw.line([(110, 110), (140, 110)], fill='white', width=2)
draw.polygon([(135, 105), (145, 110), (135, 115)], fill='white')

# Linker Pfeil  
draw.line([(150, 130), (120, 130)], fill='white', width=2)
draw.polygon([(125, 125), (115, 130), (125, 135)], fill='white')

# Speichern
icon_path = os.path.join(public_dir, 'icon.png')
img.save(icon_path)
print(f'✅ Icon erstellt: {icon_path}')

# Erstelle auch kleinere Variante für Tray (32x32)
img_small = img.resize((32, 32), Image.Resampling.LANCZOS)
tray_path = os.path.join(public_dir, 'icon-tray.png')
img_small.save(tray_path)
print(f'✅ Tray-Icon erstellt: {tray_path}')
