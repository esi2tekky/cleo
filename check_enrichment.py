#!/usr/bin/env python3
"""Check enrichment results."""
import pandas as pd

df = pd.read_csv('data/processed/enriched_cos_mens_knitwear.csv')

print('='*60)
print('ENRICHMENT RESULTS SUMMARY')
print('='*60)
print(f'\nTotal products: {len(df)}')
print(f'\nNew columns: {len([c for c in df.columns if c not in ["gender", "category", "name", "price", "url", "description", "primary_image", "all_images"]])}')

# Check products with missing descriptions
missing_desc = df[df['description'].isna() | (df['description'].astype(str).str.len() < 10)]
print(f'\nProducts with missing descriptions: {len(missing_desc)}')
print('(These were enriched using image-based extraction)\n')

for idx, row in missing_desc.iterrows():
    print(f"📦 {row['name']}")
    print(f"   Colors: {row.get('colors', 'None')}")
    print(f"   Materials: {row.get('materials', 'None')}")
    print(f"   Patterns: {row.get('patterns', 'None')}")
    print(f"   Style: {row.get('style_keywords', 'None')}")
    print()

print('='*60)
print('Sample enriched product (with description):')
print('='*60)
sample = df[df['description'].notna() & (df['description'].astype(str).str.len() > 10)].iloc[0]
print(f"\n{sample['name']}")
print(f"  Colors: {sample.get('colors', 'N/A')}")
print(f"  Materials: {sample.get('materials', 'N/A')}")
print(f"  Patterns: {sample.get('patterns', 'N/A')}")
print(f"  Style keywords: {sample.get('style_keywords', 'N/A')}")
print(f"\n  Color matching:")
print(f"    Complementary: {sample.get('complementary_colors', 'N/A')}")
print(f"    Neutral: {sample.get('neutral_colors', 'N/A')}")
print(f"    Monochrome: {sample.get('monochrome_colors', 'N/A')}")

