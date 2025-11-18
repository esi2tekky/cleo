#!/usr/bin/env python3
"""
Example script showing how to use the style enrichment module.
"""
from pathlib import Path
import sys
import pandas as pd

# Handle imports from project root or utils directory
try:
    from utils.enrich import StyleEnricher, find_similar_products, load_embeddings
except ImportError:
    from enrich import StyleEnricher, find_similar_products, load_embeddings


def example_basic_enrichment():
    """Example: Basic enrichment of scraped data."""
    print("=" * 60)
    print("Example 1: Basic Enrichment")
    print("=" * 60)
    
    # Load scraped data
    data_dir = Path("data/processed")
    csv_file = data_dir / "cos_mens_knitwear.csv"
    
    if not csv_file.exists():
        print(f"❌ File not found: {csv_file}")
        print("   Run the scraper first to generate data.")
        return
    
    df = pd.read_csv(csv_file)
    print(f"Loaded {len(df)} products")
    
    # Initialize enricher (uses Fashion CLIP by default)
    enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
    
    # Enrich (use small subset for demo)
    print("\nEnriching first 5 products as example...")
    sample_df = df.head(5).copy()
    enriched_df = enricher.enrich_dataframe(
        sample_df,
        save_embeddings_separately=True,
        output_dir=data_dir
    )
    
    # Show results
    print("\n" + "=" * 60)
    print("Enrichment Results")
    print("=" * 60)
    for idx, row in enriched_df.iterrows():
        print(f"\n{row['name']}")
        print(f"  Colors: {row.get('colors', 'N/A')}")
        print(f"  Materials: {row.get('materials', 'N/A')}")
        print(f"  Style: {row.get('style_keywords', 'N/A')}")
        print(f"  Visual embedding: {row.get('has_visual_embedding', False)}")
        print(f"  Text embedding: {row.get('has_text_embedding', False)}")


def example_style_query():
    """Example: Query products by style description."""
    print("\n" + "=" * 60)
    print("Example 2: Style-Based Query")
    print("=" * 60)
    
    # Load enriched data
    data_dir = Path("data/processed")
    csv_file = data_dir / "enriched_cos_mens_knitwear.csv"
    embeddings_file = data_dir / "embeddings.pkl"
    
    if not csv_file.exists() or not embeddings_file.exists():
        print("❌ Enriched data not found. Run enrichment first.")
        return
    
    df = pd.read_csv(csv_file)
    embeddings = load_embeddings(embeddings_file)
    
    # Initialize enricher
    enricher = StyleEnricher()
    
    # Query examples
    queries = [
        "minimalist black sweater",
        "wool knitwear",
        "casual relaxed fit",
    ]
    
    for query in queries:
        print(f"\n🔍 Query: '{query}'")
        print("-" * 60)
        
        results = find_similar_products(
            query_text=query,
            enricher=enricher,
            products_df=df,
            embeddings_dict=embeddings,
            top_k=3
        )
        
        if len(results) > 0:
            for idx, row in results.iterrows():
                print(f"  • {row['name']} (${row.get('price', 'N/A')})")
                if row.get('colors'):
                    print(f"    Colors: {row['colors']}")
                if row.get('style_keywords'):
                    print(f"    Style: {row['style_keywords']}")
        else:
            print("  No results found")


def example_attribute_filtering():
    """Example: Filter products by extracted attributes."""
    print("\n" + "=" * 60)
    print("Example 3: Attribute-Based Filtering")
    print("=" * 60)
    
    data_dir = Path("data/processed")
    csv_file = data_dir / "enriched_cos_mens_knitwear.csv"
    
    if not csv_file.exists():
        print("❌ Enriched data not found. Run enrichment first.")
        return
    
    df = pd.read_csv(csv_file)
    
    # Filter examples
    filters = [
        ("Black items", df['colors'].str.contains('black', na=False, case=False)),
        ("Wool items", df['materials'].str.contains('wool', na=False, case=False)),
        ("Minimalist style", df['style_keywords'].str.contains('minimalist', na=False, case=False)),
        ("Relaxed fit", df['fit'] == 'relaxed'),
    ]
    
    for filter_name, mask in filters:
        filtered = df[mask]
        print(f"\n{filter_name}: {len(filtered)} products")
        if len(filtered) > 0:
            for idx, row in filtered.head(3).iterrows():
                print(f"  • {row['name']} (${row.get('price', 'N/A')})")


if __name__ == "__main__":
    # Run examples
    example_basic_enrichment()
    # example_style_query()  # Uncomment after running enrichment
    # example_attribute_filtering()  # Uncomment after running enrichment

