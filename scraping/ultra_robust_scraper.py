#!/usr/bin/env python3
"""
COS Product Scraper - Ultra-Robust Mac Version
Uses correct COS URL format and saves to ./data/ directory
"""
import os
import re
import asyncio
import pandas as pd
from pathlib import Path
from exa_py import Exa
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
from dotenv import load_dotenv
from typing import List, Dict
import traceback

load_dotenv()

def extract_product_links(markdown_text: str) -> List[Dict[str, str]]:
    """
    Extract product links from Exa markdown text.
    Updated pattern to match new URL format.
    """
    products = []
    
    # Try multiple patterns to catch different URL formats
    patterns = [
        # New format: [**Name** \\ \\ $Price](url)
        r'\[\*\*([^\]]+?)\*\*\s+\\\s+\\\s+\$(\d+)(?:\\\s+\\\s+\+\d+)?\]\((https://www\.cos\.com/[^\)]+?)\)',
        # Simpler pattern: [Name](url) with price nearby
        r'\[([^\]]+?)\]\((https://www\.cos\.com/[^\)]+?product[^\)]+?)\)'
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, markdown_text)
        for match in matches:
            if len(match.groups()) == 3:
                products.append({
                    'name': match.group(1).strip().replace('**', ''),
                    'price': match.group(2).strip(),
                    'url': match.group(3).strip()
                })
            elif len(match.groups()) == 2:
                # Extract price from nearby text if possible
                name = match.group(1).strip().replace('**', '')
                url = match.group(2).strip()
                
                # Try to find price near this match
                price_match = re.search(r'\$(\d+)', markdown_text[max(0, match.start()-50):match.end()+50])
                price = price_match.group(1) if price_match else "0"
                
                products.append({
                    'name': name,
                    'price': price,
                    'url': url
                })
    
    # Remove duplicates
    seen_urls = set()
    unique_products = []
    for p in products:
        if p['url'] not in seen_urls:
            seen_urls.add(p['url'])
            unique_products.append(p)
    
    return unique_products

async def scrape_product_robust(page, product_url: str, debug: bool = False) -> Dict:
    """
    Scrape product with maximum robustness.
    Never fails - returns partial data if needed.
    """
    result = {
        'description': "",
        'primary_image': "",
        'all_images': "",
        'error': None
    }
    
    try:
        if debug:
            print(f"      Loading: {product_url[:80]}...")
        
        # Try to navigate with multiple strategies
        try:
            await page.goto(product_url, wait_until='domcontentloaded', timeout=60000)
        except PlaywrightTimeout:
            try:
                await page.goto(product_url, wait_until='load', timeout=60000)
            except PlaywrightTimeout:
                await page.goto(product_url, timeout=60000)
        except Exception as e:
            if debug:
                print(f"      ⚠️ Navigation error: {e}")
            result['error'] = str(e)
            return result
        
        if debug:
            print(f"      Page loaded, extracting content...")
        
        # Wait for page to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            pass
        
        # Scroll to trigger lazy loading
        try:
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(2000)
        except:
            pass
        
        # ===== Extract Description =====
        description = ""
        
        # Try clicking accordion first
        try:
            accordion_buttons = await page.query_selector_all('button[aria-expanded]')
            for btn in accordion_buttons[:5]:
                try:
                    btn_text = await btn.inner_text()
                    if any(word in btn_text.lower() for word in ['detail', 'description', 'product']):
                        expanded = await btn.get_attribute('aria-expanded')
                        if expanded == 'false':
                            await btn.click()
                            await page.wait_for_timeout(500)
                            if debug:
                                print(f"      Clicked accordion: {btn_text}")
                        break
                except:
                    continue
        except:
            pass
        
        # Try multiple description selectors
        desc_selectors = [
            'div[id^="disclosure-"] p',
            'div[role="region"] p', 
            'div[role="region"]',
            'div[data-testid*="accordion"] p',
            '[class*="ProductDescription"] p',
            '[class*="description"] p',
        ]
        
        for selector in desc_selectors:
            try:
                elements = await page.query_selector_all(selector)
                for elem in elements:
                    text = await elem.inner_text()
                    text = ' '.join(text.split()).strip()
                    # Check if it looks like a real description
                    if len(text) > 50 and any(word in text.lower() for word in 
                        ['collection', 'piece', 'crafted', 'designed', 'offered', 'made', 'fabric', 'merino', 'wool']):
                        description = text
                        if debug:
                            print(f"      ✅ Found description ({len(text)} chars)")
                        break
                if description:
                    break
            except:
                continue
        
        # Fallback: Search all paragraphs
        if not description:
            try:
                all_p = await page.query_selector_all('p')
                for p in all_p:
                    text = await p.inner_text()
                    text = ' '.join(text.split()).strip()
                    if len(text) > 50 and any(word in text.lower() for word in 
                        ['collection', 'piece', 'crafted', 'designed', 'offered', 'merino', 'wool']):
                        description = text
                        if debug:
                            print(f"      ✅ Found description in paragraphs ({len(text)} chars)")
                        break
            except:
                pass
        
        # ===== Extract Images =====
        image_urls = []
        
        try:
            all_imgs = await page.query_selector_all('img')
            
            if debug:
                print(f"      Found {len(all_imgs)} total images")
            
            for img in all_imgs:
                try:
                    # Check src
                    src = await img.get_attribute('src')
                    if src and ('media.cos.com' in src or 'cosstores.com' in src or 'lp2.hm.com' in src):
                        if not any(size in src for size in ['imwidth=80', 'imwidth=160', 'imwidth=60']):
                            if src not in image_urls:
                                image_urls.append(src)
                    
                    # Check data-src for lazy loaded
                    data_src = await img.get_attribute('data-src')
                    if data_src and ('media.cos.com' in data_src or 'cosstores.com' in data_src):
                        if data_src not in image_urls:
                            image_urls.append(data_src)
                except:
                    continue
            
            if debug:
                print(f"      ✅ Found {len(image_urls)} product images")
            
        except Exception as e:
            if debug:
                print(f"      ⚠️ Error extracting images: {e}")
        
        # Get primary image
        primary_image = ""
        if image_urls:
            # Prefer high-res images
            large_imgs = [img for img in image_urls if any(size in img for size in 
                ['imwidth=1260', 'imwidth=2160', 'imwidth=3408', 'imwidth=1920'])]
            primary_image = large_imgs[0] if large_imgs else image_urls[0]
        
        result['description'] = description
        result['primary_image'] = primary_image
        result['all_images'] = '|'.join(image_urls)
        
        return result
        
    except Exception as e:
        if debug:
            print(f"      ❌ Unexpected error: {e}")
            traceback.print_exc()
        result['error'] = str(e)
        return result

async def scrape_all_products_async(products: List[Dict], debug: bool = False) -> List[Dict]:
    """Scrape all products with maximum robustness."""
    
    async with async_playwright() as p:
        print("  Launching browser with stealth settings...")
        
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            locale='en-US',
            timezone_id='America/New_York'
        )
        
        # Add stealth script
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            })
        """)
        
        page = await context.new_page()
        
        all_product_data = []
        errors = []
        
        for i, product in enumerate(products, 1):
            print(f"  [{i}/{len(products)}] {product['name'][:50]}...")
            
            # Scrape with robust error handling
            details = await scrape_product_robust(page, product['url'], debug=(i <= 3 and debug))
            
            # Combine data
            product_data = {
                'name': product['name'],
                'price': product['price'],
                'url': product['url'],
                'description': details['description'],
                'primary_image': details['primary_image'],
                'all_images': details['all_images']
            }
            
            if details['error']:
                errors.append({
                    'name': product['name'],
                    'url': product['url'],
                    'error': details['error']
                })
            
            all_product_data.append(product_data)
            
            # Be respectful with delays
            if i < len(products):
                await asyncio.sleep(2)
        
        await browser.close()
        
        # Report errors
        if errors:
            print(f"\n  ⚠️ Encountered {len(errors)} errors:")
            for err in errors[:5]:
                print(f"     - {err['name']}: {err['error'][:50]}")
        
        return all_product_data

def scrape_category(category_url: str, category_name: str, gender: str, debug: bool = True) -> pd.DataFrame:
    """Scrape all products from a category."""
    
    print(f"\n{'='*60}")
    print(f"Scraping: {gender.upper()} - {category_name.upper()}")
    print(f"URL: {category_url}")
    print(f"{'='*60}\n")
    
    # Stage 1: Get product URLs with Exa
    print("Stage 1: Getting product URLs with Exa...")
    
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        raise ValueError("EXA_API_KEY not found. Create a .env file with: EXA_API_KEY=your_key")
    
    exa = Exa(api_key=api_key)
    
    try:
        result = exa.get_contents(
            urls=[category_url],
            text=True
        )
    except Exception as e:
        print(f"❌ Exa API error: {e}")
        return pd.DataFrame()
    
    if not result.results:
        print("❌ No results from Exa")
        return pd.DataFrame()
    
    category_page = result.results[0]
    products = extract_product_links(category_page.text)
    
    print(f"✅ Found {len(products)} products\n")
    
    if not products:
        print("❌ No products found")
        print("Here's a sample of the Exa response:")
        print(category_page.text[:500])
        return pd.DataFrame()
    
    # Show sample products
    print("Sample products found:")
    for i, p in enumerate(products[:3], 1):
        print(f"  {i}. {p['name']} - ${p['price']}")
        print(f"     {p['url'][:80]}...")
    print()
    
    # Stage 2: Scrape details with Playwright
    print(f"Stage 2: Scraping details with Playwright...")
    print("(Using robust error handling - this may take a while...)\n")
    
    # Run async scraping
    all_product_data = asyncio.run(scrape_all_products_async(products, debug=debug))
    
    # Add gender and category
    for item in all_product_data:
        item['gender'] = gender
        item['category'] = category_name
    
    # Reorder columns
    df = pd.DataFrame(all_product_data)
    df = df[['gender', 'category', 'name', 'price', 'url', 'description', 'primary_image', 'all_images']]
    
    print(f"\n✅ Successfully processed {len(df)} products")
    return df

def main():
    """Main execution function."""
    
    # Create output directories
    data_dir = Path("data")
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    (data_dir / "debug").mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("COS PRODUCT SCRAPER - MAC VERSION")
    print("="*60)
    print(f"Output directory: {data_dir.absolute()}")
    print("="*60 + "\n")
    
    # Scrape
    df = scrape_category(
        category_url="https://www.cos.com/en-us/men/knitwear",
        category_name="knitwear",
        gender="men",
        debug=True
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
    
    # Display detailed summary
    print(f"\n{'='*60}")
    print("DETAILED SUMMARY")
    print(f"{'='*60}")
    print(f"Total products: {len(df)}")
    
    # Data quality analysis
    has_description = df['description'].notna() & (df['description'].str.len() > 50)
    has_images = df['primary_image'].notna() & (df['primary_image'].str.len() > 0)
    has_multiple_images = df['all_images'].str.contains('\|', na=False)
    
    print(f"\n📊 Data Quality:")
    print(f"  Products with descriptions: {has_description.sum()}/{len(df)} ({has_description.sum()/len(df)*100:.1f}%)")
    print(f"  Products with images: {has_images.sum()}/{len(df)} ({has_images.sum()/len(df)*100:.1f}%)")
    print(f"  Products with multiple images: {has_multiple_images.sum()}/{len(df)} ({has_multiple_images.sum()/len(df)*100:.1f}%)")
    
    if df['price'].notna().any():
        try:
            prices = df['price'].astype(int)
            print(f"\n💰 Price range: ${prices.min()} - ${prices.max()}")
        except:
            pass
    
    # Show sample with complete data
    complete = df[has_description & has_images]
    if len(complete) > 0:
        print(f"\n✅ Sample products with complete data:")
        for idx, row in complete.head(3).iterrows():
            print(f"\n  📦 {row['name']}")
            print(f"     ${row['price']}")
            print(f"     📝 {row['description'][:80]}...")
            print(f"     🖼️  {row['primary_image'][:60]}...")
    
    # Show products missing data
    incomplete = df[~(has_description & has_images)]
    if len(incomplete) > 0:
        print(f"\n⚠️  Products with incomplete data ({len(incomplete)}):")
        for idx, row in incomplete.head(5).iterrows():
            missing = []
            if not (row['description'] and len(row['description']) > 50):
                missing.append("description")
            if not row['primary_image']:
                missing.append("image")
            print(f"  - {row['name']}: missing {', '.join(missing)}")
            print(f"    URL: {row['url'][:80]}...")
    
    print(f"\n{'='*60}")
    success_rate = (has_description.sum() + has_images.sum()) / (len(df) * 2)
    if success_rate > 0.8:
        print("SUCCESS! ✅")
        print("Data quality is good enough for production use!")
    else:
        print("PARTIAL SUCCESS ⚠️")
        print("Some data is missing. Check the debug output above.")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()