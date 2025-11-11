#!/usr/bin/env python3
"""
Advanced COS Product Page Debugger - Mac Compatible
Takes screenshots and saves HTML to help diagnose scraping issues.
Saves to: ./data/debug/ folder
"""
import asyncio
from playwright.async_api import async_playwright
from pathlib import Path

# Test URL - Updated to correct format
TEST_URL = "https://www.cos.com/en-us/men/menswear/knitwear/merino/product/knitted-merino-yak-zip-up-hoodie-beige-mlange-1311859001"

# Create output directory
OUTPUT_DIR = Path("data/debug")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

async def debug_product_page():
    """Debug a single product page in detail."""
    
    print(f"Testing URL: {TEST_URL}\n")
    print("="*60)
    print(f"Output directory: {OUTPUT_DIR.absolute()}")
    print("="*60 + "\n")
    
    async with async_playwright() as p:
        # Launch browser
        print("Launching browser...")
        browser = await p.chromium.launch(
            headless=False,  # Run with visible browser to see what happens
            slow_mo=500  # Slow down actions to see them
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        try:
            # Navigate
            print("Navigating to page...")
            await page.goto(TEST_URL, wait_until='domcontentloaded', timeout=30000)
            
            print("✅ Page loaded\n")
            
            # Wait for network to settle
            try:
                await page.wait_for_load_state('networkidle', timeout=10000)
            except:
                pass
            
            # Wait and scroll to load lazy images
            print("Scrolling page to trigger lazy loading...")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000)
            await page.evaluate("window.scrollTo(0, 0)")
            await page.wait_for_timeout(2000)
            
            # Take initial screenshot
            screenshot_path = OUTPUT_DIR / "screenshot_1_initial.png"
            print(f"Taking screenshot...")
            await page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"✅ Saved: {screenshot_path}\n")
            
            # Save initial HTML
            html_path = OUTPUT_DIR / "page_html_1_initial.html"
            print("Saving HTML...")
            html = await page.content()
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"✅ Saved: {html_path} ({len(html)} chars)\n")
            
            # Check for common elements
            print("="*60)
            print("CHECKING PAGE ELEMENTS")
            print("="*60)
            
            # 1. Check page title
            title = await page.title()
            print(f"\n1. Page Title: {title}")
            
            # 2. Count images
            all_imgs = await page.query_selector_all('img')
            print(f"\n2. Total <img> tags: {len(all_imgs)}")
            
            if all_imgs:
                print("   Sample image sources:")
                for i, img in enumerate(all_imgs[:5]):
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt')
                    print(f"   [{i+1}] src: {src[:80] if src else 'None'}...")
                    print(f"       alt: {alt[:50] if alt else 'None'}...")
            
            # 3. Check for media.cos.com images
            cos_images = []
            for img in all_imgs:
                src = await img.get_attribute('src')
                if src and 'media.cos.com' in src:
                    cos_images.append(src)
            
            print(f"\n3. Images from media.cos.com: {len(cos_images)}")
            if cos_images:
                print(f"   First image: {cos_images[0]}")
            
            # 4. Check for lazy-loaded images
            print("\n4. Checking for lazy-loaded images...")
            lazy_imgs = await page.query_selector_all('img[loading="lazy"]')
            print(f"   Found {len(lazy_imgs)} lazy-loaded images")
            
            # Also check data-src
            data_src_imgs = await page.query_selector_all('img[data-src]')
            print(f"   Found {len(data_src_imgs)} images with data-src attribute")
            
            # 5. Check for picture/source elements
            pictures = await page.query_selector_all('picture')
            print(f"\n5. <picture> elements: {len(pictures)}")
            
            # 6. Look for description text
            print("\n6. Searching for product description...")
            
            # Try to find accordion
            accordion_buttons = await page.query_selector_all('button[aria-expanded]')
            print(f"   Found {len(accordion_buttons)} accordion buttons")
            
            if accordion_buttons:
                print("   Accordion button details:")
                for i, btn in enumerate(accordion_buttons[:3]):
                    text = await btn.inner_text()
                    expanded = await btn.get_attribute('aria-expanded')
                    aria_controls = await btn.get_attribute('aria-controls')
                    print(f"   [{i+1}] Text: '{text}' | Expanded: {expanded} | Controls: {aria_controls}")
                
                # Try clicking first accordion that looks like details
                print("\n   Attempting to click product details accordion...")
                for btn in accordion_buttons:
                    text = await btn.inner_text()
                    if any(word in text.lower() for word in ['detail', 'product', 'description']):
                        print(f"   Clicking: '{text}'")
                        await btn.click()
                        await page.wait_for_timeout(1000)
                        break
                
                # Take screenshot after click
                screenshot_path2 = OUTPUT_DIR / "screenshot_2_after_click.png"
                await page.screenshot(path=str(screenshot_path2), full_page=True)
                print(f"   ✅ Saved: {screenshot_path2}")
                
                # Save HTML after click
                html_path2 = OUTPUT_DIR / "page_html_2_after_click.html"
                html_after = await page.content()
                with open(html_path2, "w", encoding="utf-8") as f:
                    f.write(html_after)
                print(f"   ✅ Saved: {html_path2}")
            
            # 7. Search for description in various places
            print("\n7. Looking for description text patterns...")
            
            desc_patterns = [
                ('div[id^="disclosure-"]', 'Disclosure div'),
                ('div[role="region"]', 'Region div'),
                ('[data-testid*="accordion"]', 'Accordion testid'),
                ('[class*="ProductDescription"]', 'ProductDescription class'),
            ]
            
            found_description = False
            for selector, name in desc_patterns:
                elements = await page.query_selector_all(selector)
                if elements:
                    print(f"\n   {name} ({selector}): {len(elements)} found")
                    for i, elem in enumerate(elements[:2]):
                        text = await elem.inner_text()
                        text = ' '.join(text.split())
                        if len(text) > 30:
                            print(f"      [{i+1}] {text[:150]}...")
                            if 'collection' in text.lower() or 'piece' in text.lower():
                                found_description = True
                                print(f"      ✅ This looks like the product description!")
            
            # 8. Check page text content
            print("\n8. Checking if description keywords exist in page...")
            page_text = await page.inner_text('body')
            keywords = ['collection', 'crafted', 'designed', 'piece', 'offered', 'fabric', 'merino', 'wool']
            found_keywords = [k for k in keywords if k in page_text.lower()]
            print(f"   Found keywords: {', '.join(found_keywords)}")
            
            # Look for the actual description text
            if 'merino' in page_text.lower():
                print("\n   Searching for description text containing 'merino'...")
                lines = page_text.split('\n')
                for line in lines:
                    if 'merino' in line.lower() and len(line) > 50:
                        print(f"   Found: {line.strip()[:200]}...")
                        break
            
            # 9. Check for bot detection
            print("\n9. Checking for bot detection...")
            bot_keywords = ['cloudflare', 'captcha', 'verify you are human', 'access denied']
            detected = [k for k in bot_keywords if k in page_text.lower()]
            if detected:
                print(f"   ⚠️ Possible bot detection: {detected}")
            else:
                print("   ✅ No obvious bot detection")
            
            # 10. Export selectors that work
            print("\n10. Testing specific selectors...")
            
            test_selectors = [
                'img[src*="media.cos.com"]',
                'div[id^="disclosure-"] p',
                'button[aria-expanded]',
                '[data-testid*="product"]',
            ]
            
            for sel in test_selectors:
                count = len(await page.query_selector_all(sel))
                print(f"   {sel}: {count} elements")
            
            print("\n" + "="*60)
            print("SUMMARY")
            print("="*60)
            print(f"✅ Page loaded successfully")
            print(f"✅ Title: {title}")
            print(f"✅ Total images: {len(all_imgs)}")
            print(f"✅ COS product images: {len(cos_images)}")
            print(f"✅ Accordion buttons: {len(accordion_buttons)}")
            print(f"{'✅' if found_description else '⚠️'} Description found: {found_description}")
            print(f"✅ Keywords present: {len(found_keywords)}/{len(keywords)}")
            
            print(f"\n📁 Files saved to: {OUTPUT_DIR.absolute()}")
            print(f"   - screenshot_1_initial.png")
            print(f"   - screenshot_2_after_click.png")
            print(f"   - page_html_1_initial.html")
            print(f"   - page_html_2_after_click.html")
            
            # Keep browser open for manual inspection
            print("\n" + "="*60)
            print("Browser will stay open for 30 seconds for manual inspection...")
            print("Press Ctrl+C to close early")
            print("="*60)
            await page.wait_for_timeout(30000)
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
            
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_product_page())