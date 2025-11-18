#!/usr/bin/env python3
"""
Quick test script to verify enrichment works with the scraped data.
"""
from pathlib import Path
import pandas as pd
from utils.enrich import StyleEnricher

def test_enrichment():
    """Test enrichment on a small sample of the data."""
    
    # Load the data
    data_file = Path("data/processed/cos_mens_knitwear.csv")
    
    if not data_file.exists():
        print(f"❌ File not found: {data_file}")
        print("   Please place cos_mens_knitwear.csv in data/processed/")
        return
    
    df = pd.read_csv(data_file)
    print(f"✅ Loaded {len(df)} products from {data_file.name}\n")
    
    # Check data quality
    has_desc = df['description'].notna() & (df['description'].str.len() > 0)
    has_images = df['primary_image'].notna() & (df['primary_image'].str.len() > 0)
    
    print("📊 Data Quality Check:")
    print(f"  Products with descriptions: {has_desc.sum()}/{len(df)} ({has_desc.sum()/len(df)*100:.1f}%)")
    print(f"  Products with images: {has_images.sum()}/{len(df)} ({has_images.sum()/len(df)*100:.1f}%)")
    print()
    
    # Show products without descriptions
    missing_desc = df[~has_desc]
    if len(missing_desc) > 0:
        print(f"⚠️  {len(missing_desc)} products missing descriptions:")
        for idx, row in missing_desc.iterrows():
            print(f"  - {row['name']}")
        print()
    
    # Test enrichment on first 3 products (quick test)
    print("🧪 Testing enrichment on first 3 products...\n")
    sample_df = df.head(3).copy()
    
    try:
        # Initialize enricher
        print("Initializing StyleEnricher...")
        enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
        print()
        
        # Enrich sample
        enriched_df = enricher.enrich_dataframe(
            sample_df,
            save_embeddings_separately=False,  # Don't save for test
            output_dir=None
        )
        
        # Show results
        print("\n" + "="*60)
        print("ENRICHMENT TEST RESULTS")
        print("="*60)
        
        for idx, row in enriched_df.iterrows():
            print(f"\n📦 {row['name']}")
            print(f"   Price: ${row.get('price', 'N/A')}")
            
            # Style attributes
            if row.get('colors'):
                print(f"   Colors: {row['colors']}")
            if row.get('materials'):
                print(f"   Materials: {row['materials']}")
            if row.get('style_keywords'):
                print(f"   Style: {row['style_keywords']}")
            
            # Embeddings
            print(f"   Visual embedding: {'✅' if row.get('has_visual_embedding') else '❌'}")
            print(f"   Text embedding: {'✅' if row.get('has_text_embedding') else '❌'}")
        
        print("\n" + "="*60)
        print("✅ Enrichment test successful!")
        print("="*60)
        print("\n💡 Next steps:")
        print("   1. Run full enrichment: python utils/enrich.py")
        print("   2. Or use the StyleEnricher class in your code")
        
    except Exception as e:
        print(f"\n❌ Error during enrichment: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure dependencies are installed: pip install -r requirements.txt")
        print("  2. Check that Fashion CLIP can download (requires internet)")
        print("  3. Try with use_fashion_clip=False to use OpenAI CLIP instead")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_enrichment()

