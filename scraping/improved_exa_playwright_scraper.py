#!/usr/bin/env python3
"""
COS Product Scraper - Improved Playwright Version
Uses Exa API for finding products, Playwright for extracting details.
Now with better debugging and more robust selectors!
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
import json

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

async def scrape_product_with_playwright(page, product_url: str, debug: bool = False) -> Dict:
    """
    Scrape product details using Playwright with improved selectors.
    """
    try:
        # Navigate to product page
        await page.goto(product_url, wait_until='domcontentloaded', timeout=30000)
        
        # Wait for page to fully load
        await page.wait_for_timeout(2000)
        
        if debug:
            print(f"\n      Debug: Page loaded, extracting data...")
        
        # ===== Extract Description =====
        description = ""
        
        # Strategy 1: Try to click the accordion to expand it
        try:
            # Look for accordion buttons or headers
            accordion_selectors = [
                'button[aria-expanded="false"]',
                '[data-testid*="accordion"]',
                'button:has-text("Details")',
                'button:has-text("Product details")',
            ]
            
            for selector in accordion_selectors:
                button = await page.query_selector(selector)
                if button:
                    # Check if this is the product details accordion
                    button_text = await button.inner_text()
                    if any(word in button_text.lower() for word in ['detail', 'description', 'product']):
                        await button.click()
                        await page.wait_for_timeout(500)
                        if debug:
                            print(f"      Debug: Clicked accordion button")
                        break
        except Exception as e:
            if debug:
                print(f"      Debug: Could not click accordion: {e}")
        
        # Strategy 2: Extract description from multiple possible locations
        desc_selectors = [
            'div[id^="disclosure-"] p',  # Inside disclosure div
            'div[data-testid*="accordion"] p',
            '[class*="ProductDescription"] p',
            '[class*="product-description"] p',
            'div[role="region"] p',  # Expanded accordion content
        ]
        
        for selector in desc_selectors:
            try:
                elements = await page.query_selector_all(selector)
                if elements:
                    for elem in elements:
                        text = await elem.inner_text()
                        text = ' '.join(text.split())
                        if len(text) > 50 and any(word in text.lower() for word in ['collection', 'piece', 'crafted', 'designed']):
                            description = text
                            if debug:
                                print(f"      Debug: Found description via selector: {selector}")
                            break
                if description:
                    break
            except:
                continue
        
        # Strategy 3: Fallback - search all paragraphs
        if not description:
            try:
                all_paragraphs = await page.query_selector_all('p')
                for p in all_paragraphs:
                    text = await p.inner_text()
                    text = ' '.join(text.split())
                    if len(text) > 50 and any(word in text.lower() for word in ['collection', 'piece', 'crafted', 'designed', 'offered']):
                        description = text
                        if debug:
                            print(f"      Debug: Found description in paragraph fallback")
                        break
            except:
                pass
        
        # ===== Extract Images =====
        image_urls = []
        primary_image = ""
        
        try:
            # Wait for images to load
            await page.wait_for_selector('img[src*="media.cos.com"]', timeout=5000)
            
            # Get all images
            img_elements = await page.query_selector_all('img')
            
            for img in img_elements:
                src = await img.get_attribute('src')
                if src and 'media.cos.com' in src:
                    # Filter out very small thumbnails
                    if 'imwidth=80' not in src and 'imwidth=160' not in src:
                        # Clean up the URL (remove query params except important ones)
                        if src not in image_urls:
                            image_urls.append(src)
            
            if debug:
                print(f"      Debug: Found {len(image_urls)} images")
            
            # Get primary image (prefer high-res)
            if image_urls:
                # Prefer images with larger widths
                large_images = [img for img in image_urls if any(size in img for size in ['imwidth=1260', 'imwidth=2160', 'imwidth=3408'])]
                primary_image = large_images[0] if large_images else image_urls[0]
                
        except Exception as e:
            if debug:
                print(f"      Debug: Error getting images: {e}")
        
        # ===== Debug Output =====
        if debug:
            print(f"      Description length: {len(description)} chars")
            print(f"      Description preview: {description[:100]}...")
            print(f"      Images found: {len(image_urls)}")
            print(f"      Primary image: {primary_image[:80]}..." if primary_image else "      No primary image")
        
        return {
            'description': description.strip() if description else "",
            'primary_image': primary_image,
            'all_images': '|'.join(image_urls) if image_urls else ""
        }
        
    except Exception as e:
        print(f"      ❌ Error scraping {product_url}: {e}")
        return {
            'description': "",
            'primary_image': "",
            'all_images': ""
        }

async def scrape_all_products_async(products: List[Dict], debug: bool = False) -> List[Dict]:
    """Scrape all products using Playwright."""
    
    async with async_playwright() as p:
        # Launch browser with better settings
        print("  Launching browser...")
        browser = await p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled']  # Helps avoid detection
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US'
        )
        
        page = await context.new_page()
        
        all_product_data = []
        
        for i, product in enumerate(products, 1):
            print(f"  [{i}/{len(products)}] {product['name'][:50]}...")
            
            # Get details with Playwright (debug first 3 products)
            details = await scrape_product_with_playwright(page, product['url'], debug=(i <= 3))
            
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
                await asyncio.sleep(1)
        
        await browser.close()
        
        return all_product_data

def scrape_category(category_url: str, category_name: str, gender: str, debug: bool = False) -> pd.DataFrame:
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
    
    print(f"✅ Found {len(products)} products\n")
    
    if not products:
        print("❌ No products found")
        return pd.DataFrame()
    
    # Stage 2: Scrape details with Playwright
    print(f"Stage 2: Scraping details with Playwright...")
    print("(This will take a few minutes...)\n")
    
    # Run async scraping
    all_product_data = asyncio.run(scrape_all_products_async(products, debug=debug))
    
    # Add gender and category
    for item in all_product_data:
        item['gender'] = gender
        item['category'] = category_name
    
    # Reorder columns
    df = pd.DataFrame(all_product_data)
    df = df[['gender', 'category', 'name', 'price', 'url', 'description', 'primary_image', 'all_images']]
    
    print(f"\n✅ Successfully scraped {len(df)} products")
    return df

def main():
    """Main execution function."""
    
    # Create output directories
    data_dir = Path("data")
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    
    # Scrape men's knitwear (with debug for first 3 products)
    df = scrape_category(
        category_url="https://www.cos.com/en-us/men/knitwear",
        category_name="knitwear",
        gender="men",
        debug=True  # Enable debug mode
    )
    
    if df.empty:
        print("\n❌ No data collected")
        return
    
    # Save results
    output_csv = data_dir / "processed" / "cos_mens_knitwear.csv"
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n✅ Saved to: {output_csv}")
    
    # Save JSON
    output_json = data_dir / "raw" / "cos_mens_knitwear.json"
    df.to_json(output_json, orient='records', indent=2)
    print(f"✅ Saved JSON to: {output_json}")
    
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
    
    # Show samples
    print(f"\nSample products:")
    sample_df = df[['name', 'price', 'description']].head(3)
    for idx, row in sample_df.iterrows():
        print(f"\n  {row['name']}")
        print(f"  ${row['price']}")
        print(f"  {row['description'][:100]}..." if row['description'] else "  (no description)")
    
    # Show issues if any
    no_desc = df[~has_description]
    if len(no_desc) > 0:
        print(f"\n⚠️ Products missing descriptions ({len(no_desc)}):")
        for idx, row in no_desc[['name', 'url']].head(5).iterrows():
            print(f"  - {row['name']}")
            print(f"    {row['url']}")
    
    print(f"\n{'='*60}")
    print("SUCCESS! ✅")
    print(f"{'='*60}")
    print("Your data is ready for the chatbot!")

if __name__ == "__main__":
    main()
