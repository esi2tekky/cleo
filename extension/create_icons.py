#!/usr/bin/env python3
"""Create placeholder icons for the extension."""
from PIL import Image, ImageDraw
import os

os.makedirs('icons', exist_ok=True)

sizes = [16, 48, 128]
color = '#667eea'  # Purple gradient color

for size in sizes:
    img = Image.new('RGB', (size, size), color=color)
    draw = ImageDraw.Draw(img)
    
    # Draw a simple "C" for CLEO
    font_size = size // 2
    try:
        # Try to use a font, fallback to default
        from PIL import ImageFont
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = None
    
    text = 'C'
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    x = (size - text_width) // 2
    y = (size - text_height) // 2
    
    draw.text((x, y), text, fill='white', font=font)
    img.save(f'icons/icon{size}.png')
    print(f'✅ Created icon{size}.png')

print('\nIcons created! You can replace these with custom designs later.')

