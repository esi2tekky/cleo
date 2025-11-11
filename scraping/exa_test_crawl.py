#!/usr/bin/env python3
"""
COS Product Scraper using Exa API
Scrapes product listings from category pages and individual product details.
"""
import os
import json
import re
import pandas as pd
from pathlib import Path
from exa_py import Exa
from dotenv import load_dotenv
from typing import List, Dict
from utils import strip_all_markdown, clean_description_text

# Load environment variables
load_dotenv()

def extract_product_links(markdown_text: str) -> List[Dict[str, str]]:
    """
    Extract product links from markdown text.
    Format: [**Product Name** \\ \\ $Price](url)
    """
    products = []
    
    # Pattern to match: [**text** \\ \\ $price](url)
    # The product links have this format in the markdown
    pattern = r'\[\*\*([^\]]+?)\*\*\s+\\\s+\\\s+\$(\d+)(?:\\\s+\\\s+\+\d+)?\]\((https://www\.cos\.com/[^\)]+?/product/[^\)]+?)\)'
    
    matches = re.finditer(pattern, markdown_text)
    
    for match in matches:
        products.append({
            'name': match.group(1).strip(),
            'price': match.group(2).strip(),
            'url': match.group(3).strip()
        })
    
    return products

def fetch_product_details(exa: Exa, product_url: str) -> Dict:
    """Fetch detailed information for a single product."""
    try:
        result = exa.get_contents(
            urls=[product_url],
            text=True
        )
        
        if result.results and len(result.results) > 0:
            item = result.results[0]
            
            # Extract description from text
            description = ""
            if item.text:
                # Clean markdown and navigation from the text
                text_clean = clean_description_text(item.text)
                
                # Now look for product description patterns
                # Descriptions usually start with "The [category] collection" or similar
                desc_patterns = [
                    # Pattern 1: Starts with "The menswear/womenswear collection"
                    r'(The (?:menswear|womenswear|men\'s|women\'s) collection[^\.!?]+[\.!?](?:\s+[^\.!?]+[\.!?]){0,4})',
                    
                    # Pattern 2: Starts with "Offered in" or similar product description
                    r'((?:Offered|Designed|Rendered|Crafted|Made)[^\.!?]+[\.!?](?:\s+[^\.!?]+[\.!?]){0,4})',
                    
                    # Pattern 3: First substantial paragraph (3+ sentences)
                    r'([A-Z][^\.!?]{20,}[\.!?]\s+[A-Z][^\.!?]{20,}[\.!?]\s+[A-Z][^\.!?]{20,}[\.!?])',
                ]
                
                for pattern in desc_patterns:
                    desc_match = re.search(pattern, text_clean, re.DOTALL)
                    if desc_match:
                        description = desc_match.group(1).strip()
                        # Clean up extra whitespace
                        description = ' '.join(description.split())
                        break
                
                # Fallback: Get first paragraph with multiple sentences
                if not description:
                    paragraphs = [p.strip() for p in text_clean.split('\n\n') if len(p.strip()) > 50]
                    if paragraphs:
                        # Find the first paragraph that looks like a description
                        for para in paragraphs[:5]:  # Check first 5 paragraphs
                            # Should have at least 2 sentences and not be a list
                            if para.count('.') >= 1 and not para.startswith(('-', '•', '*')):
                                description = para[:500]  # Limit length
                                break
            
            # Extract image URLs
            image_urls = []
            if item.extras and 'image_links' in item.extras:
                # Clean any markdown from image URLs
                for img in item.extras['image_links']:
                    # Remove markdown link syntax if present: Text](url) → url
                    img_clean = strip_all_markdown(img) if '](' in img else img
                    if img_clean and img_clean.startswith('http'):
                        image_urls.append(img_clean)
            
            # Get the primary product image (usually the first one that's not tiny)
            primary_image = ""
            if image_urls:
                # Filter out small thumbnails (typically contain 'imwidth=80' or similar)
                # Also prioritize product images (usually larger imwidth values)
                large_images = [img for img in image_urls 
                               if 'imwidth=80' not in img 
                               and 'imwidth=160' not in img
                               and '.jpg' in img.lower()]
                
                if large_images:
                    # Try to find the main product image (usually has larger imwidth)
                    main_images = [img for img in large_images if 'imwidth=1260' in img or 'imwidth=2160' in img]
                    primary_image = main_images[0] if main_images else large_images[0]
                else:
                    primary_image = image_urls[0] if image_urls else ""
            
            return {
                'description': description,
                'primary_image': primary_image,
                'all_images': '|'.join(image_urls),  # Join with pipe for CSV
                'text_content': item.text[:1000] if item.text else ''  # More text for debugging
            }
    except Exception as e:
        print(f"  Error fetching {product_url}: {e}")
    
    return {
        'description': '',
        'primary_image': '',
        'all_images': '',
        'text_content': ''
    }

def scrape_category(category_url: str, category_name: str, gender: str) -> pd.DataFrame:
    """
    Scrape all products from a category page.
    
    Args:
        category_url: URL of the category page
        category_name: Name of the category (e.g., 'knitwear')
        gender: Gender category ('men' or 'women')
    """
    # Initialize Exa
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        raise ValueError("EXA_API_KEY not found in environment")
    
    exa = Exa(api_key=api_key)
    
    print(f"\n{'='*60}")
    print(f"Scraping: {gender.upper()} - {category_name.upper()}")
    print(f"URL: {category_url}")
    print(f"{'='*60}\n")
    
    # Step 1: Get the category page
    print("Step 1: Fetching category page...")
    result = exa.get_contents(
        urls=[category_url],
        text=True
    )
    
    if not result.results:
        print("❌ No results returned from category page")
        return pd.DataFrame()
    
    category_page = result.results[0]
    
    # Step 2: Extract product links from the markdown
    print("Step 2: Extracting product links...")
    products = extract_product_links(category_page.text)
    print(f"Found {len(products)} products")
    
    if not products:
        print("❌ No products found in category page")
        print("Sample text:", category_page.text[:500])
        return pd.DataFrame()
    
    # Step 3: Fetch details for each product
    print(f"\nStep 3: Fetching details for {len(products)} products...")
    
    all_product_data = []
    for i, product in enumerate(products, 1):
        print(f"  [{i}/{len(products)}] {product['name'][:50]}...")
        
        details = fetch_product_details(exa, product['url'])
        
        # Combine basic info with details
        product_data = {
            'gender': gender,
            'category': category_name,
            'name': product['name'],
            'price': product['price'],
            'url': product['url'],
            'description': details['description'],
            'primary_image_url': details['primary_image'],
            'all_image_urls': details['all_images']
        }
        
        all_product_data.append(product_data)
    
    # Create DataFrame
    df = pd.DataFrame(all_product_data)
    
    print(f"\n✓ Successfully scraped {len(df)} products")
    return df

def main():
    """Main execution function."""
    
    # Create output directories
    data_dir = Path("data")
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    
    # Scrape men's knitwear as test case
    df = scrape_category(
        category_url="https://www.cos.com/en-us/men/knitwear",
        category_name="knitwear",
        gender="men"
    )
    
    if df.empty:
        print("\n❌ No data collected. Please check the scraping logic.")
        return
    
    # Save results
    output_csv = data_dir / "processed" / "cos_mens_knitwear.csv"
    df.to_csv(output_csv, index=False)
    print(f"\n✓ Saved to: {output_csv}")
    
    # Also save as JSON for debugging
    output_json = data_dir / "raw" / "cos_mens_knitwear.json"
    df.to_json(output_json, orient='records', indent=2)
    print(f"✓ Saved JSON to: {output_json}")
    
    # Display summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total products: {len(df)}")
    print(f"Price range: ${df['price'].astype(int).min()} - ${df['price'].astype(int).max()}")
    print(f"\nSample products:")
    print(df[['name', 'price', 'description']].head(3).to_string(index=False))
    
    print(f"\n{'='*60}")
    print("NEXT STEPS")
    print(f"{'='*60}")
    print("1. Review the output CSV to verify data quality")
    print("2. Check if descriptions are being captured correctly")
    print("3. Verify image URLs are correct")
    print("4. If satisfied, extend to scrape other categories")

if __name__ == "__main__":
    main()
