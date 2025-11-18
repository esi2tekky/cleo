#!/usr/bin/env python3
"""Test black wool query."""
import pandas as pd

df = pd.read_csv('../data/processed/enriched_cos_mens_knitwear.csv')
query = 'black wool'
query_lower = query.lower()

results_df = df.copy()
print(f"Starting with {len(results_df)} items")

# Filter by material
materials = ['wool', 'cotton', 'cashmere', 'merino', 'silk', 'mohair', 'alpaca']
material_filters = []
for material in materials:
    if material in query_lower:
        material_filters.append(material)
        break

if material_filters:
    material = material_filters[0]
    results_df = results_df[
        results_df['materials'].astype(str).str.lower().str.contains(material, na=False)
    ]
    print(f"After material filter ({material}): {len(results_df)} items")

# Filter by color
colors = ['black', 'white', 'navy', 'beige', 'brown', 'grey', 'gray', 'red', 'blue']
color_filters = []
for color in colors:
    if color in query_lower:
        color_filters.append(color)

if color_filters:
    color_mask = pd.Series([False] * len(results_df), index=results_df.index)
    for color in color_filters:
        color_mask |= results_df['colors'].astype(str).str.lower().str.contains(color, na=False)
    results_df = results_df[color_mask]
    print(f"After color filter ({color_filters}): {len(results_df)} items")

if len(results_df) > 0:
    print("\nResults:")
    print(results_df[['name', 'colors', 'materials']].to_string())
else:
    print("\nNo results found!")

