from PIL import Image, ImageDraw
import os

# Erstelle ein 256x256 PNG mit BaluDesk-Farben
img = Image.new('RGB', (256, 256), color='#0f172a')
draw = ImageDraw.Draw(img, 'RGBA')

# Zeichne einen Kreis mit Cloud-Farbe
draw.ellipse([48, 48, 208, 208], outline='#06b6d4', width=2)

# Zeichne eine einfache Cloud-Form
points = [(80, 120), (100, 85), (130, 85), (160, 120), (185, 110), (185, 140), (70, 140), (70, 110)]
draw.polygon(points, fill='#06b6d4')

# Speichern
os.makedirs('F:\Programme (x86)\Baluhost\baludesk\frontend\public', exist_ok=True)
img.save('F:\Programme (x86)\Baluhost\baludesk\frontend\public\icon.png')
print('Icon erstellt!')
