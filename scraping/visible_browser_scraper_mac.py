#!/usr/bin/env python3
"""
COS Product Scraper - FIXED for Descriptions & Main Images
- Clicks "DETAILS & DESCRIPTION" accordion
- Gets main product gallery images (not thumbnails)
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

load_dotenv()

def extract_product_links(markdown_text: str) -> List[Dict[str, str]]:
    """Extract product links from Exa markdown."""
    products = []
    
    pattern = r'\[\*\*([^\]]+?)\*\*\s+\\\s+\\\s+\$(\d+)(?:\s+\\\s+\\\s+\+\d+)?\]\((https://www\.cos\.com/[^\)]+?)\)'
    matches = re.finditer(pattern, markdown_text, re.DOTALL)
    
    for match in matches:
        url = match.group(3).strip().rstrip('.')
        products.append({
            'name': match.group(1).strip(),
            'price': match.group(2).strip(),
            'url': url
        })
    
    if not products:
        url_pattern = r'https://www\.cos\.com/en-us/[^/]+/[^/]+/[^/]+/[^/]+/product/[^\s\)\]"]+'
        urls = re.findall(url_pattern, markdown_text)
        
        for url in urls:
            idx = markdown_text.find(url)
            context = markdown_text[max(0, idx-200):idx]
            name_match = re.search(r'\*\*([^\*]+?)\*\*', context)
            price_match = re.search(r'\$(\d+)', context)
            
            if name_match and price_match:
                products.append({
                    'name': name_match.group(1).strip(),
                    'price': price_match.group(1),
                    'url': url
                })
    
    seen = set()
    unique = []
    for p in products:
        if p['url'] not in seen:
            seen.add(p['url'])
            unique.append(p)
    
    return unique

async def scrape_product(page, product_url: str, product_num: int, total: int) -> Dict:
    """
    Scrape one product - FIXED to get descriptions and main images.
    """
    result = {
        'description': "",
        'primary_image': "",
        'all_images': ""
    }
    
    try:
        print(f"  [{product_num}/{total}] {product_url.split('/')[-1][:50]}...")
        
        # Navigate
        await page.goto(product_url, wait_until='domcontentloaded', timeout=45000)
        
        # Wait for network to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            pass
        
        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, 2000)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1500)
        
        # ===== CLICK "DETAILS & DESCRIPTION" ACCORDION =====
        description = ""
        
        try:
            # Find and click the "DETAILS & DESCRIPTION" button
            buttons = await page.query_selector_all('button')
            
            for button in buttons:
                button_text = await button.inner_text()
                button_text_clean = button_text.strip().upper()
                
                # Look for "DETAILS" or "DESCRIPTION" in button text
                if 'DETAILS' in button_text_clean or 'DESCRIPTION' in button_text_clean:
                    # Check if not already expanded
                    aria_expanded = await button.get_attribute('aria-expanded')
                    
                    if aria_expanded == 'false' or aria_expanded is None:
                        print(f"      Clicking: {button_text_clean[:30]}")
                        await button.click()
                        await page.wait_for_timeout(1000)
                    
                    break
            
            # Now extract the description from the expanded accordion
            # Try multiple strategies
            
            # Strategy 1: Look for the expanded region
            expanded_regions = await page.query_selector_all('div[role="region"]')
            for region in expanded_regions:
                text = await region.inner_text()
                text = ' '.join(text.split()).strip()
                
                # Check if this looks like a product description
                if len(text) > 60 and any(kw in text.lower() for kw in [
                    'collection', 'designed', 'crafted', 'made', 'piece', 'offered',
                    'fabric', 'features', 'cut', 'blend', 'merino', 'wool', 'cotton'
                ]):
                    # Make sure it's not size/care instructions
                    if not any(skip in text.lower() for skip in [
                        'machine wash', 'do not bleach', 'iron', 'dry clean', 
                        'size guide', 'model is', 'cm', 'inches'
                    ]):
                        description = text
                        print(f"      ✅ Description: {len(text)} chars")
                        break
            
            # Strategy 2: If not found, look in all visible paragraph text
            if not description:
                all_text = await page.inner_text('body')
                lines = all_text.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if len(line) > 80:
                        if any(kw in line.lower() for kw in [
                            'collection is', 'designed for', 'crafted from', 'made from',
                            'this piece', 'offered in', 'features'
                        ]):
                            if not any(skip in line.lower() for skip in [
                                'menu', 'cart', 'sign in', 'delivery', 'returns', 'email'
                            ]):
                                description = line
                                print(f"      ✅ Description (fallback): {len(line)} chars")
                                break
        
        except Exception as e:
            print(f"      ⚠️ Description error: {e}")
        
        # ===== GET MAIN PRODUCT IMAGES =====
        image_urls = []
        
        try:
            # Strategy: Get images with specific dimensions (main product images are large)
            all_imgs = await page.query_selector_all('img')
            
            print(f"      Found {len(all_imgs)} total images")
            
            # First pass: Get large product images only
            large_images = []
            medium_images = []
            
            for img in all_imgs:
                src = await img.get_attribute('src')
                alt = await img.get_attribute('alt') or ""
                
                if not src or 'media.cos.com' not in src:
                    continue
                
                # Skip obvious non-product images
                alt_lower = alt.lower()
                if any(skip in alt_lower for skip in [
                    'campaign', 'festive', 'banner', 'promo', 'logo',
                    'heels', 'bag', 'shoes', 'accessory'
                ]):
                    continue
                
                # Categorize by size
                if 'imwidth=3408' in src or 'imwidth=2160' in src:
                    # Large hero images
                    if src not in large_images:
                        large_images.append(src)
                elif 'imwidth=1260' in src or 'imwidth=1920' in src:
                    # Medium product images
                    if src not in medium_images:
                        medium_images.append(src)
                # Skip small thumbnails (imwidth=80, 160, etc.)
            
            # Prefer large images, fallback to medium
            if large_images:
                image_urls = large_images[:8]
                print(f"      ✅ Using {len(image_urls)} large images")
            elif medium_images:
                image_urls = medium_images[:8]
                print(f"      ✅ Using {len(image_urls)} medium images")
            
            # If still no images, be less strict
            if not image_urls:
                print(f"      ⚠️ No large images found, using any product images...")
                for img in all_imgs:
                    if len(image_urls) >= 8:
                        break
                    
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt') or ""
                    
                    if src and 'media.cos.com' in src:
                        # Just skip tiny thumbnails
                        if any(size in src for size in ['imwidth=80', 'imwidth=160', 'imwidth=60']):
                            continue
                        
                        if src not in image_urls:
                            image_urls.append(src)
                
                print(f"      ✅ Found {len(image_urls)} images (any size)")
        
        except Exception as e:
            print(f"      ⚠️ Image error: {e}")
        
        result['description'] = description
        result['primary_image'] = image_urls[0] if image_urls else ""
        result['all_images'] = '|'.join(image_urls[:8])
        
        return result
        
    except Exception as e:
        print(f"      ❌ Error: {str(e)[:60]}")
        return result

async def scrape_all_products(products: List[Dict]) -> List[Dict]:
    """Scrape all products with visible browser."""
    
    async with async_playwright() as p:
        print("\n  Launching browser (visible)...\n")
        
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        all_data = []
        
        for i, product in enumerate(products, 1):
            details = await scrape_product(page, product['url'], i, len(products))
            
            all_data.append({
                'name': product['name'],
                'price': product['price'],
                'url': product['url'],
                'description': details['description'],
                'primary_image': details['primary_image'],
                'all_images': details['all_images']
            })
            
            # Delay
            if i < len(products):
                await asyncio.sleep(1.5)
        
        print("\n  Closing browser...")
        await browser.close()
        
        return all_data

def scrape_category(category_url: str, category_name: str, gender: str) -> pd.DataFrame:
    """Scrape category."""
    
    print(f"\n{'='*60}")
    print(f"Scraping: {gender.upper()} - {category_name.upper()}")
    print(f"{'='*60}\n")
    
    # Stage 1: Exa
    print("Stage 1: Getting product URLs with Exa...")
    
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        raise ValueError("EXA_API_KEY not found")
    
    exa = Exa(api_key=api_key)
    
    try:
        result = exa.get_contents(urls=[category_url], text=True)
    except Exception as e:
        print(f"❌ Exa error: {e}")
        return pd.DataFrame()
    
    if not result.results:
        print("❌ No results")
        return pd.DataFrame()
    
    products = extract_product_links(result.results[0].text)
    print(f"✅ Found {len(products)} products\n")
    
    if not products:
        return pd.DataFrame()
    
    print("First 3 products:")
    for i, p in enumerate(products[:3], 1):
        print(f"  {i}. {p['name']} - ${p['price']}")
    print()
    
    # Stage 2: Playwright
    print("Stage 2: Scraping with visible browser...\n")
    
    all_data = asyncio.run(scrape_all_products(products))
    
    # Add metadata
    for item in all_data:
        item['gender'] = gender
        item['category'] = category_name
    
    # Create DataFrame
    df = pd.DataFrame(all_data)
    df = df[['gender', 'category', 'name', 'price', 'url', 'description', 'primary_image', 'all_images']]
    
    return df

def main():
    """Main function."""
    
    # Setup
    data_dir = Path("data")
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("COS SCRAPER - FIXED VERSION")
    print("="*60)
    print("\nFixes:")
    print("  ✅ Clicks 'DETAILS & DESCRIPTION' accordion")
    print("  ✅ Gets main product gallery images (not thumbnails)")
    print("="*60 + "\n")
    
    # Scrape
    df = scrape_category(
        category_url="https://www.cos.com/en-us/men/knitwear",
        category_name="knitwear",
        gender="men"
    )
    
    if df.empty:
        print("\n❌ No data")
        return
    
    # Save
    output_csv = data_dir / "processed" / "cos_mens_knitwear.csv"
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n✅ Saved: {output_csv}")
    
    output_json = data_dir / "raw" / "cos_mens_knitwear.json"
    df.to_json(output_json, orient='records', indent=2)
    print(f"✅ Saved: {output_json}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total: {len(df)} products")
    
    has_desc = df['description'].str.len() > 60
    has_imgs = df['all_images'].str.len() > 0
    
    print(f"\nQuality:")
    print(f"  Descriptions: {has_desc.sum()}/{len(df)} ({has_desc.sum()/len(df)*100:.1f}%)")
    print(f"  Images: {has_imgs.sum()}/{len(df)} ({has_imgs.sum()/len(df)*100:.1f}%)")
    
    # Show detailed stats
    if len(df) > 0:
        img_counts = df['all_images'].str.split('|').str.len()
        print(f"  Avg images per product: {img_counts.mean():.1f}")
        print(f"  Products with 5+ images: {(img_counts >= 5).sum()}/{len(df)}")
    
    # Samples
    complete = df[has_desc & has_imgs]
    if len(complete) > 0:
        print(f"\n✅ Sample products with complete data:")
        for idx, row in complete.head(3).iterrows():
            img_count = row['all_images'].count('|') + 1 if row['all_images'] else 0
            print(f"\n  {row['name']} (${row['price']})")
            print(f"  📝 {row['description'][:100]}...")
            print(f"  🖼️  {img_count} images")
            if row['primary_image']:
                print(f"  📸 {row['primary_image'][:80]}...")
    
    # Show issues
    issues = df[~(has_desc & has_imgs)]
    if len(issues) > 0:
        print(f"\n⚠️  Issues ({len(issues)} products):")
        for idx, row in issues.head(3).iterrows():
            problems = []
            if not has_desc[idx]:
                problems.append("no description")
            if not has_imgs[idx]:
                problems.append("no images")
            print(f"  {row['name']}: {', '.join(problems)}")
    
    print(f"\n{'='*60}")
    success_rate = (has_desc.sum() / len(df)) * 0.5 + (has_imgs.sum() / len(df)) * 0.5
    if success_rate > 0.8:
        print("SUCCESS! ✅")
    else:
        print("PARTIAL ⚠️")
        print("Check the issues above")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()