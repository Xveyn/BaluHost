"""Simple icon creator for BaluHost Desktop Client."""
import tkinter as tk
from tkinter import Canvas
import sys

def create_icon():
    """Create a simple icon using tkinter."""
    root = tk.Tk()
    root.withdraw()
    
    # Create canvas for icon
    canvas = Canvas(root, width=256, height=256, bg='#0f172a', highlightthickness=0)
    
    # Draw gradient circle background
    canvas.create_oval(40, 40, 216, 216, fill='#6366f1', outline='#38bdf8', width=6)
    
    # Draw center circle
    canvas.create_oval(90, 90, 166, 166, fill='#38bdf8', outline='')
    
    # Draw inner dot
    canvas.create_oval(110, 110, 146, 146, fill='#0f172a', outline='')
    
    # Save as postscript
    canvas.update()
    ps = canvas.postscript(colormode='color')
    
    # Save to file
    with open('baluhost-icon.ps', 'w') as f:
        f.write(ps)
    
    print("✓ Icon template created: baluhost-icon.ps")
    print("  Convert to .ico using online converter or ImageMagick")
    root.destroy()

if __name__ == '__main__':
    create_icon()
