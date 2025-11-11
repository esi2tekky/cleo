#!/usr/bin/env python3
"""
COS Product Scraper - Playwright Approach
Uses Exa API for finding products, Playwright for extracting details.

This approach uses a real browser to bypass COS's bot protection.
Slower but more reliable when facing 403 errors.
"""
import os
import re
import asyncio
import pandas as pd
from pathlib import Path
from exa_py import Exa
from playwright.async_api import async_playwright
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

async def scrape_product_with_playwright(page, product_url: str) -> Dict:
    """
    Scrape product details using Playwright.
    Uses a real browser to bypass bot protection.
    """
    try:
        # Navigate to product page
        await page.goto(product_url, wait_until='networkidle', timeout=30000)
        
        # Wait a bit for any dynamic content
        await page.wait_for_timeout(1000)
        
        # Extract description
        description = ""
        
        # Try to find the description div
        desc_selectors = [
            'div[id^="disclosure-"]',
            'div[data-testid="accordion-item-0"]',
        ]
        
        for selector in desc_selectors:
            try:
                desc_element = await page.query_selector(selector)
                if desc_element:
                    description = await desc_element.inner_text()
                    # Clean up the text
                    description = ' '.join(description.split())
                    if len(description) > 50:
                        break
            except:
                continue
        
        # Fallback: get any text containing "collection"
        if not description:
            try:
                page_text = await page.inner_text('body')
                # Look for sentences with "collection"
                sentences = page_text.split('.')
                for sentence in sentences:
                    if 'collection' in sentence.lower() and len(sentence) > 50:
                        description = sentence.strip() + '.'
                        break
            except:
                pass
        
        # Extract images
        image_urls = []
        
        try:
            # Find all img tags
            img_elements = await page.query_selector_all('img')
            
            for img in img_elements:
                src = await img.get_attribute('src')
                if src and 'media.cos.com' in src:
                    # Filter out tiny thumbnails
                    if 'imwidth=80' not in src and 'imwidth=160' not in src:
                        image_urls.append(src)
        except:
            pass
        
        # Get primary image
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

async def scrape_all_products_async(products: List[Dict]) -> List[Dict]:
    """Scrape all products using Playwright."""
    
    async with async_playwright() as p:
        # Launch browser
        print("  Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        all_product_data = []
        
        for i, product in enumerate(products, 1):
            print(f"  [{i}/{len(products)}] {product['name'][:50]}...")
            
            # Get details with Playwright
            details = await scrape_product_with_playwright(page, product['url'])
            
            # Combine all data
            product_data = {
                'name': product['name'],
                'price': product['price'],
                'url': product['url'],
                'description': details['description'],
                'primary_image': details['primary_image'],
                'all_images': details['all_images']
            }
            
            all_product_data.append(product_data)
            
            # Small delay to be respectful
            if i < len(products):
                await asyncio.sleep(0.5)
        
        await browser.close()
        
        return all_product_data

def scrape_category(category_url: str, category_name: str, gender: str) -> pd.DataFrame:
    """
    Scrape all products from a category.
    
    Stage 1: Use Exa to get product URLs
    Stage 2: Use Playwright to get details from each product page
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
    
    # Stage 2: Scrape details with Playwright
    print(f"Stage 2: Scraping details with Playwright (real browser)...")
    print("(This will take longer but avoids bot detection...)\n")
    
    # Run async scraping
    all_product_data = asyncio.run(scrape_all_products_async(products))
    
    # Add gender and category
    for item in all_product_data:
        item['gender'] = gender
        item['category'] = category_name
    
    # Reorder columns
    df = pd.DataFrame(all_product_data)
    df = df[['gender', 'category', 'name', 'price', 'url', 'description', 'primary_image', 'all_images']]
    
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
    has_images = df['primary_image'].notna() & (df['primary_image'].str.len() > 0)
    
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
