#!/usr/bin/env python3
"""
Script to enrich the new cos_all_products.csv file.
Run this to add style attributes, embeddings, and color matching.
"""
from pathlib import Path
import pandas as pd
from utils.enrich import StyleEnricher

def main():
    data_dir = Path("data/processed")
    csv_file = data_dir / "cos_all_products.csv"
    
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        return
    
    print(f"📂 Loading: {csv_file.name}")
    df = pd.read_csv(csv_file)
    print(f"✅ Loaded {len(df)} products\n")
    
    # Initialize enricher
    print("🔧 Initializing enricher (this may take a moment)...")
    enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
    print("✅ Enricher ready\n")
    
    # Enrich the data
    print("🎨 Starting enrichment process...")
    print("   This will process images and generate embeddings for all products.")
    print("   This may take 30-60 minutes depending on your system.\n")
    
    enriched_df = enricher.enrich_dataframe(
        df,
        save_embeddings_separately=True,
        output_dir=data_dir
    )
    
    # Save enriched data
    output_file = data_dir / "enriched_cos_all_products.csv"
    cols_to_save = [c for c in enriched_df.columns if 'embedding' not in c.lower()]
    enriched_df[cols_to_save].to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"\n✅ Saved enriched data to: {output_file}")
    
    # Also save JSON
    json_file = data_dir / "enriched_cos_all_products.json"
    enriched_df[cols_to_save].to_json(json_file, orient='records', indent=2)
    print(f"✅ Saved JSON to: {json_file}")
    
    print(f"\n🎉 Enrichment complete! {len(enriched_df)} products processed.")
    print("\nNext step: Update backend/app.py to load 'enriched_cos_all_products.csv'")

if __name__ == "__main__":
    main()

