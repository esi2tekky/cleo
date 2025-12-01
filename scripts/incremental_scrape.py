#!/usr/bin/env python3
"""
Incremental scraper to add missing products to existing CSV.
Scrapes only products that are not already in the CSV (by URL).
"""
import sys
import pandas as pd
from pathlib import Path
import asyncio

# Add scraping directory to path
sys.path.append(str(Path(__file__).parent.parent / "scraping"))
from visible_browser_scraper_mac import scrape_category_async

async def incremental_scrape_category(
    category_url: str,
    category_name: str,
    gender: str,
    existing_csv_path: Path,
    output_csv_path: Path
) -> int:
    """
    Scrape category and add only new products to existing CSV.
    
    Args:
        category_url: URL of category page
        category_name: Category name (e.g., 'knitwear')
        gender: 'men' or 'women'
        existing_csv_path: Path to existing CSV
        output_csv_path: Path to save updated CSV
        
    Returns:
        Number of new products added
    """
    # Load existing CSV
    if existing_csv_path.exists():
        existing_df = pd.read_csv(existing_csv_path)
        existing_urls = set(existing_df['url'].dropna().astype(str).tolist())
        print(f"✅ Loaded existing CSV: {len(existing_df)} products, {len(existing_urls)} unique URLs")
    else:
        existing_df = pd.DataFrame()
        existing_urls = set()
        print(f"⚠️  No existing CSV found, creating new one")
    
    # Scrape category
    print(f"\n🔍 Scraping {gender} {category_name}...")
    print(f"   URL: {category_url}\n")
    
    try:
        new_df = await scrape_category_async(
            category_url=category_url,
            category_name=category_name,
            gender=gender,
            max_products=None  # Get all products
        )
        
        if new_df.empty:
            print(f"❌ No products scraped from {category_url}")
            return 0
        
        print(f"✅ Scraped {len(new_df)} products from {category_name}")
        
        # Filter to only new products (not in existing URLs)
        new_products = []
        for idx, row in new_df.iterrows():
            product_url = str(row.get('url', ''))
            if product_url and product_url not in existing_urls:
                new_products.append(row)
        
        if not new_products:
            print(f"✅ All products already in CSV. No new products to add.")
            return 0
        
        new_products_df = pd.DataFrame(new_products)
        print(f"✅ Found {len(new_products_df)} new products to add")
        
        # Merge with existing
        if existing_df.empty:
            updated_df = new_products_df
        else:
            updated_df = pd.concat([existing_df, new_products_df], ignore_index=True)
        
        # Save updated CSV
        updated_df.to_csv(output_csv_path, index=False)
        print(f"✅ Saved {len(updated_df)} total products to {output_csv_path}")
        
        return len(new_products_df)
        
    except Exception as e:
        print(f"❌ Error scraping {category_name}: {e}")
        import traceback
        traceback.print_exc()
        return 0

async def main():
    """Main function to scrape missing products."""
    data_dir = Path(__file__).parent.parent / "data" / "processed"
    csv_file = data_dir / "cos_all_products.csv"
    
    # Categories to scrape
    categories = [
        {
            'url': 'https://www.cos.com/en-us/men/knitwear',
            'category': 'knitwear',
            'gender': 'men',
            'expected': 163
        },
        {
            'url': 'https://www.cos.com/en-us/women/knitwear',
            'category': 'knitwear',
            'gender': 'women',
            'expected': 154
        },
        {
            'url': 'https://www.cos.com/en-us/men/trousers',
            'category': 'trousers',
            'gender': 'men',
            'expected': None  # Verify count
        }
    ]
    
    # Process categories in parallel (5 at a time)
    batch_size = 5
    total_added = 0
    
    for batch_start in range(0, len(categories), batch_size):
        batch = categories[batch_start:batch_start + batch_size]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(categories) + batch_size - 1) // batch_size
        
        print(f"\n{'='*60}")
        print(f"BATCH {batch_num}/{total_batches}: Processing {len(batch)} categories in parallel")
        print(f"{'='*60}\n")
        
        # Create tasks for parallel execution
        tasks = []
        for cat in batch:
            task = incremental_scrape_category(
                category_url=cat['url'],
                category_name=cat['category'],
                gender=cat['gender'],
                existing_csv_path=csv_file,
                output_csv_path=csv_file
            )
            tasks.append((cat, task))
        
        # Run all tasks in parallel with error handling
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        # Process results
        for i, (cat, result) in enumerate(zip([cat for cat, _ in tasks], results)):
            if isinstance(result, Exception):
                print(f"❌ Error processing {cat['gender']} {cat['category']}: {result}")
            else:
                added = result
                total_added += added
                if cat['expected']:
                    print(f"✅ {cat['gender']} {cat['category']}: Added {added} new products (expected ~{cat['expected']})")
                else:
                    print(f"✅ {cat['gender']} {cat['category']}: Added {added} new products")
        
        # Small delay between batches
        if batch_start + batch_size < len(categories):
            print(f"\n⏸️  Waiting 3 seconds before next batch...\n")
            await asyncio.sleep(3)
    
    print(f"\n{'='*60}")
    print(f"SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Total new products added: {total_added}")
    print(f"✅ Updated CSV: {csv_file}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    asyncio.run(main())

