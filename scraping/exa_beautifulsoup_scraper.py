#!/usr/bin/env python3
"""
COS Product Scraper - Hybrid Approach
Uses Exa API for finding products, BeautifulSoup for extracting details.

This approach:
1. Exa: Get product URLs from category pages (fast, reliable)
2. BeautifulSoup: Scrape each product page HTML (gets hidden accordion content)
"""
import os
import re
import time
import requests
import pandas as pd
from pathlib import Path
from exa_py import Exa
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from typing import List, Dict

# Load environment variables
load_dotenv()

def extract_product_links(markdown_text: str) -> List[Dict[str, str]]:
    """
    Extract product links from Exa markdown text.
    Format: [**Product Name** \\ \\ $Price](url)
    """
    products = []
    pattern = r'\[\*\*([^\]]+?)\*\*\s+\\\s+\\\s+\$(\d+)(?:\\\s+\\\s+\+\d+)?\]\((https://www\.cos\.com/[^\)]+?/product/[^\)]+?)\)'
    
    matches = re.finditer(pattern, markdown_text)
    
    for match in matches:
        products.append({
            'name': match.group(1).strip(),
            'price': match.group(2).strip(),
            'url': match.group(3).strip()
        })
    
    return products

def scrape_product_with_beautifulsoup(product_url: str) -> Dict:
    """
    Scrape product details using BeautifulSoup.
    This captures the accordion content that Exa misses.
    """
    try:
        # Add headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        response = requests.get(product_url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Extract description from the accordion/disclosure div
        # Based on your HTML: <div class="w-full overflow-y-auto..." id="disclosure-:r8m:">
        description = ""
        
        # Try multiple selectors to find the description
        desc_selectors = [
            'div[id^="disclosure-"]',  # Starts with "disclosure-"
            'div.overflow-y-auto',     # Class pattern
            'div[data-testid="accordion-item-0"]',  # Test ID
        ]
        
        for selector in desc_selectors:
            desc_div = soup.select_one(selector)
            if desc_div:
                # Get all text from paragraphs and lists
                text_parts = []
                for elem in desc_div.find_all(['p', 'li']):
                    text = elem.get_text(strip=True)
                    if text and len(text) > 10:  # Ignore empty or very short text
                        text_parts.append(text)
                
                if text_parts:
                    description = ' '.join(text_parts)
                    break
        
        # Fallback: Look for any div with product description keywords
        if not description:
            for div in soup.find_all('div'):
                text = div.get_text(strip=True)
                if 'menswear collection' in text.lower() or 'womenswear collection' in text.lower():
                    description = text[:500]
                    break
        
        # Extract images from <img> tags
        image_urls = []
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src')
            if src and 'media.cos.com' in src and src.startswith('http'):
                # Filter out tiny thumbnails
                if 'imwidth=80' not in src and 'imwidth=160' not in src:
                    image_urls.append(src)
        
        # Get primary image (first large one)
        primary_image = ""
        if image_urls:
            # Prefer larger images
            large_images = [img for img in image_urls if 'imwidth=1260' in img or 'imwidth=2160' in img]
            primary_image = large_images[0] if large_images else image_urls[0]
        
        return {
            'description': description.strip() if description else "",
            'primary_image': primary_image,
            'all_images': '|'.join(image_urls) if image_urls else ""
        }
        
    except Exception as e:
        print(f"  Error scraping {product_url}: {e}")
        return {
            'description': "",
            'primary_image': "",
            'all_images': ""
        }

def scrape_category(category_url: str, category_name: str, gender: str) -> pd.DataFrame:
    """
    Scrape all products from a category.
    
    Stage 1: Use Exa to get product URLs
    Stage 2: Use BeautifulSoup to get details from each product page
    """
    print(f"\n{'='*60}")
    print(f"Scraping: {gender.upper()} - {category_name.upper()}")
    print(f"URL: {category_url}")
    print(f"{'='*60}\n")
    
    # Stage 1: Get product URLs with Exa
    print("Stage 1: Getting product URLs with Exa...")
    
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        raise ValueError("EXA_API_KEY not found in environment")
    
    exa = Exa(api_key=api_key)
    
    result = exa.get_contents(
        urls=[category_url],
        text=True
    )
    
    if not result.results:
        print("❌ No results from Exa")
        return pd.DataFrame()
    
    category_page = result.results[0]
    products = extract_product_links(category_page.text)
    
    print(f"✓ Found {len(products)} products\n")
    
    if not products:
        print("❌ No products found")
        return pd.DataFrame()
    
    # Stage 2: Scrape details with BeautifulSoup
    print(f"Stage 2: Scraping details with BeautifulSoup...")
    print("(This will take a few minutes...)\n")
    
    all_product_data = []
    
    for i, product in enumerate(products, 1):
        print(f"  [{i}/{len(products)}] {product['name'][:50]}...")
        
        # Get details with BeautifulSoup
        details = scrape_product_with_beautifulsoup(product['url'])
        
        # Combine all data
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
        
        # Be nice to the server - add small delay
        if i < len(products):
            time.sleep(0.5)  # 500ms delay between requests
    
    df = pd.DataFrame(all_product_data)
    
    print(f"\n✓ Successfully scraped {len(df)} products")
    return df

def main():
    """Main execution function."""
    
    # Create output directories
    data_dir = Path("data")
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    
    # Scrape men's knitwear
    df = scrape_category(
        category_url="https://www.cos.com/en-us/men/knitwear",
        category_name="knitwear",
        gender="men"
    )
    
    if df.empty:
        print("\n❌ No data collected")
        return
    
    # Save results
    output_csv = data_dir / "processed" / "cos_mens_knitwear.csv"
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n✓ Saved to: {output_csv}")
    
    # Save JSON
    output_json = data_dir / "raw" / "cos_mens_knitwear.json"
    df.to_json(output_json, orient='records', indent=2)
    print(f"✓ Saved JSON to: {output_json}")
    
    # Display summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total products: {len(df)}")
    
    # Check data quality
    has_description = df['description'].notna() & (df['description'].str.len() > 50)
    has_images = df['primary_image_url'].notna() & (df['primary_image_url'].str.len() > 0)
    
    print(f"Products with descriptions: {has_description.sum()} ({has_description.sum()/len(df)*100:.1f}%)")
    print(f"Products with images: {has_images.sum()} ({has_images.sum()/len(df)*100:.1f}%)")
    
    if df['price'].notna().any():
        print(f"Price range: ${df['price'].astype(int).min()} - ${df['price'].astype(int).max()}")
    
    print(f"\nSample products:")
    print(df[['name', 'price', 'description']].head(3).to_string(index=False, max_colwidth=50))
    
    print(f"\n{'='*60}")
    print("SUCCESS! ✅")
    print(f"{'='*60}")
    print("Your data is ready for the chatbot!")

if __name__ == "__main__":
    main()
