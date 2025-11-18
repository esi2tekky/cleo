#!/usr/bin/env python3
"""Test image-based style attribute extraction."""
from utils.enrich import StyleEnricher
import pandas as pd

e = StyleEnricher(use_clip=True, use_fashion_clip=True)
df = pd.read_csv('data/processed/cos_mens_knitwear.csv')

# Find items with missing descriptions
missing_desc = df[df['description'].isna() | (df['description'].astype(str).str.len() < 10)]
print(f'Testing items with missing descriptions ({len(missing_desc)} items):\n')

for idx, row in missing_desc.head(3).iterrows():
    print(f"📦 {row['name']}")
    
    # Text-based extraction
    text_attrs = e.extract_style_attributes(
        str(row.get('description', '')),
        str(row.get('name', '')),
        str(row.get('url', ''))
    )
    
    # Image-based extraction
    img_attrs = {}
    if row.get('primary_image'):
        img_attrs = e.extract_style_attributes_from_image(
            row['primary_image'],
            threshold=-0.08
        )
    
    # Combined
    combined = {
        'colors': list(set(text_attrs['colors'] + img_attrs.get('colors', []))),
        'materials': list(set(text_attrs['materials'] + img_attrs.get('materials', []))),
        'patterns': list(set(text_attrs['patterns'] + img_attrs.get('patterns', []))),
    }
    
    print(f"  Text-based: colors={text_attrs['colors']}, materials={text_attrs['materials']}")
    print(f"  Image-based: colors={img_attrs.get('colors', [])}, materials={img_attrs.get('materials', [])}")
    print(f"  Combined: colors={combined['colors']}, materials={combined['materials']}")
    print()

