#!/usr/bin/env python3
"""
COS Product Scraper - FIXED for Descriptions & Main Images
- Clicks "DETAILS & DESCRIPTION" accordion
- Gets main product gallery images (not thumbnails)
- Handles pagination with "LOAD MORE" button
- Dismisses pop-up modals
- Supports customizable product limits
"""
import os
import re
import asyncio
import pandas as pd
from pathlib import Path
from playwright.async_api import async_playwright
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

async def dismiss_popups(page):
    """Dismiss any pop-up modals that might block interaction - robust version."""
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            # Wait a bit for pop-ups to appear
            await page.wait_for_timeout(1000)
            
            # Strategy 1: Try to remove/hide overlays via JavaScript (most reliable for iframes)
            try:
                # Remove or hide common overlay/iframe pop-ups
                await page.evaluate("""
                    () => {
                        // Remove attentive overlay (common email signup popup)
                        const attentiveOverlay = document.getElementById('attentive_overlay');
                        if (attentiveOverlay) {
                            attentiveOverlay.remove();
                        }
                        
                        // Hide any overlays with iframes
                        const overlays = document.querySelectorAll('[id*="overlay"], [id*="attentive"], [class*="overlay"]');
                        overlays.forEach(el => {
                            if (el.querySelector('iframe')) {
                                el.style.display = 'none';
                                el.remove();
                            }
                        });
                        
                        // Hide modals
                        const modals = document.querySelectorAll('[role="dialog"], [class*="modal"], [class*="popup"]');
                        modals.forEach(el => {
                            if (window.getComputedStyle(el).zIndex > 1000) {
                                el.style.display = 'none';
                            }
                        });
                    }
                """)
                await page.wait_for_timeout(300)
            except:
                pass
            
            # Strategy 2: Press Escape key (works for many modals)
            try:
                await page.keyboard.press('Escape')
                await page.wait_for_timeout(500)
            except:
                pass
            
            # Strategy 3: Find and click close buttons (X buttons)
            try:
                # Look for X buttons by various selectors
                close_selectors = [
                    'button[aria-label*="close" i]',
                    'button[aria-label*="Close" i]',
                    'button[class*="close" i]',
                    'button[class*="dismiss" i]',
                    '[role="dialog"] button:last-child',
                    'div[class*="modal"] button:last-child',
                    'div[class*="popup"] button:last-child',
                    'div[class*="overlay"] button:last-child',
                    'button:has-text("×")',
                    'button:has-text("✕")',
                ]
                
                for selector in close_selectors:
                    try:
                        close_btn = await page.query_selector(selector)
                        if close_btn:
                            is_visible = await close_btn.is_visible()
                            if is_visible:
                                # Try to click with force if needed
                                await close_btn.click(force=True, timeout=2000)
                                await page.wait_for_timeout(500)
                                break
                    except:
                        continue
            except:
                pass
            
            # Strategy 4: Look for buttons with close text
            try:
                all_buttons = await page.query_selector_all('button')
                for button in all_buttons:
                    try:
                        text = await button.inner_text()
                        text_lower = text.strip().lower()
                        # Look for close/dismiss buttons
                        if any(keyword in text_lower for keyword in [
                            'close', 'dismiss', 'no thanks', 'not now', 
                            'skip', 'continue shopping', '×', '✕', 'x'
                        ]):
                            is_visible = await button.is_visible()
                            if is_visible:
                                print(f"      🚫 Dismissing pop-up: {text[:30]}")
                                await button.click(force=True, timeout=2000)
                                await page.wait_for_timeout(500)
                                break
                    except:
                        continue
            except:
                pass
            
            # Strategy 5: Click outside modal (backdrop click)
            try:
                # Check if there's an overlay/backdrop
                overlay = await page.query_selector('div[id*="overlay"], div[class*="backdrop"], div[class*="overlay"]')
                if overlay:
                    # Click in top-left corner (safe area)
                    await page.mouse.click(10, 10)
                    await page.wait_for_timeout(300)
            except:
                pass
            
            # Verify pop-up is actually gone
            await page.wait_for_timeout(500)
            
            # Check if pop-up still exists
            popup_still_exists = await page.evaluate("""
                () => {
                    const attentiveOverlay = document.getElementById('attentive_overlay');
                    if (attentiveOverlay && window.getComputedStyle(attentiveOverlay).display !== 'none') {
                        return true;
                    }
                    
                    const modals = document.querySelectorAll('[role="dialog"], [class*="modal"]');
                    for (const modal of modals) {
                        const style = window.getComputedStyle(modal);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && parseInt(style.zIndex) > 1000) {
                            return true;
                        }
                    }
                    return false;
                }
            """)
            
            if not popup_still_exists:
                # Pop-up is gone, we're done
                return
            
            # If we get here, pop-up still exists, try again
            if attempt < max_attempts - 1:
                print(f"      ⚠️ Pop-up still present, retrying ({attempt + 1}/{max_attempts})...")
                await page.wait_for_timeout(1000)
            
        except Exception as e:
            # Continue to next attempt
            if attempt < max_attempts - 1:
                await page.wait_for_timeout(500)
            continue
    
    # Final fallback: Force remove via JavaScript
    try:
        await page.evaluate("""
            () => {
                // Aggressively remove all overlays
                document.querySelectorAll('[id*="overlay"], [id*="attentive"], [class*="overlay"], [class*="modal"]').forEach(el => {
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.remove();
                });
            }
        """)
        await page.wait_for_timeout(500)
    except:
        pass

async def extract_products_from_page(page) -> List[Dict[str, str]]:
    """Extract product links directly from the DOM."""
    products = []
    
    try:
        # Find all product links - COS uses <a> tags with href containing /product/
        product_links = await page.query_selector_all('a[href*="/product/"]')
        
        seen_urls = set()
        
        for link in product_links:
            try:
                href = await link.get_attribute('href')
                if not href or '/product/' not in href:
                    continue
                
                # Make absolute URL if needed
                if href.startswith('/'):
                    href = f"https://www.cos.com{href}"
                elif not href.startswith('http'):
                    continue
                
                # Skip if we've seen this URL
                if href in seen_urls:
                    continue
                seen_urls.add(href)
                
                # Try to get product name and price from the link or nearby elements
                name = ""
                price = ""
                
                # Strategy 1: Get text from the link itself, but clean it
                link_text = await link.inner_text()
                if link_text:
                    # Clean the text - remove newlines, extract price, get just the name
                    link_text_clean = ' '.join(link_text.split()).strip()  # Remove newlines, normalize whitespace
                    
                    # Extract price first if present
                    price_match = re.search(r'\$(\d+)', link_text_clean)
                    if price_match:
                        price = price_match.group(1)
                        # Remove price from name
                        link_text_clean = re.sub(r'\$\d+.*', '', link_text_clean).strip()
                    
                    # Remove common suffixes like "+1", "+2", etc.
                    link_text_clean = re.sub(r'\s*\+\d+\s*$', '', link_text_clean).strip()
                    
                    # Remove product IDs (long numeric strings at the end, typically 10 digits)
                    link_text_clean = re.sub(r'\s+\d{10,}\s*$', '', link_text_clean).strip()
                    
                    name = link_text_clean
                
                # Strategy 2: Look for price and name in nearby elements
                # Find parent container and look for price
                try:
                    parent_handle = await link.evaluate_handle('el => el.closest("article, div[class*=\"product\"], div[class*=\"item\"]")')
                    if parent_handle and not parent_handle.is_null():
                        parent_element = await parent_handle.as_element()
                        if parent_element:
                            parent_text = await parent_element.inner_text()
                            # ALWAYS try to get price from parent (parent is more reliable than link text)
                            price_match = re.search(r'\$(\d+)', parent_text)
                            if price_match:
                                price = price_match.group(1)
                            
                            # Also try to find price in specific price elements
                            if not price:
                                try:
                                    # Look for price in various selectors
                                    price_selectors = [
                                        '[class*="price"]',
                                        '[data-testid*="price"]',
                                        'span:has-text("$")',
                                        '[class*="Price"]',
                                        '[class*="cost"]',
                                    ]
                                    for selector in price_selectors:
                                        try:
                                            price_elem = await parent_element.query_selector(selector)
                                            if price_elem:
                                                price_text = await price_elem.inner_text()
                                                price_match = re.search(r'\$(\d+)', price_text)
                                                if price_match:
                                                    price = price_match.group(1)
                                                    break
                                        except:
                                            continue
                                except:
                                    pass
                            
                            # If no name or name is too short, try to get it from parent
                            if not name or len(name) < 5:
                                # Look for heading or strong text
                                heading = await parent_element.query_selector('h2, h3, h4, strong, [class*="name"], [class*="title"]')
                                if heading:
                                    heading_text = await heading.inner_text()
                                    # Clean heading text too
                                    name = ' '.join(heading_text.split()).strip()
                                    # Remove price if it got included
                                    name = re.sub(r'\$\d+.*', '', name).strip()
                                    name = re.sub(r'\s*\+\d+\s*$', '', name).strip()
                                    # Remove product IDs
                                    name = re.sub(r'\s+\d{10,}\s*$', '', name).strip()
                except:
                    pass
                
                # Strategy 3: Extract from URL if name is missing
                if not name or len(name) < 5:
                    # Extract from URL slug
                    url_parts = href.split('/')
                    if 'product' in url_parts:
                        product_idx = url_parts.index('product')
                        if product_idx + 1 < len(url_parts):
                            slug = url_parts[product_idx + 1]
                            # Convert slug to readable name
                            name = slug.replace('-', ' ').title()
                            # Remove product ID from slug if present (last part if it's all digits)
                            name_parts = name.split()
                            if name_parts and name_parts[-1].isdigit() and len(name_parts[-1]) >= 10:
                                name = ' '.join(name_parts[:-1])
                
                # Final cleanup: Remove any remaining product IDs from name
                if name:
                    name = re.sub(r'\s+\d{10,}\s*$', '', name).strip()
                
                if name and href:
                    products.append({
                        'name': name,
                        'price': price or "",
                        'url': href
                    })
            except Exception as e:
                continue
        
        # Remove duplicates based on URL
        unique_products = []
        seen = set()
        for p in products:
            if p['url'] not in seen:
                seen.add(p['url'])
                unique_products.append(p)
        
        return unique_products
        
    except Exception as e:
        print(f"      ⚠️ Error extracting products: {e}")
        return []

async def get_all_products_from_category(page, category_url: str, max_products: Optional[int] = None) -> List[Dict[str, str]]:
    """Navigate category page and extract all products with pagination."""
    print(f"  Navigating to category page...")
    
    await page.goto(category_url, wait_until='domcontentloaded', timeout=45000)
    
    # Dismiss any pop-ups
    await dismiss_popups(page)
    
    # Wait for products to load
    await page.wait_for_timeout(2000)
    
    all_products = []
    previous_count = 0
    max_attempts = 50  # Safety limit
    attempts = 0
    
    while attempts < max_attempts:
        # Extract products currently visible
        current_products = await extract_products_from_page(page)
        
        # Add new products
        seen_urls = {p['url'] for p in all_products}
        new_products = [p for p in current_products if p['url'] not in seen_urls]
        all_products.extend(new_products)
        
        print(f"  Found {len(all_products)} products so far...")
        
        # Check if we have enough products
        if max_products and len(all_products) >= max_products:
            all_products = all_products[:max_products]
            print(f"  ✅ Reached limit of {max_products} products")
            break
        
        # Check if we got new products
        if len(all_products) == previous_count:
            # No new products, try to load more
            load_more_clicked = False
            
            # Look for "LOAD MORE" button
            buttons = await page.query_selector_all('button')
            for button in buttons:
                try:
                    button_text = await button.inner_text()
                    button_text_clean = button_text.strip().upper()
                    
                    if 'LOAD MORE' in button_text_clean or 'MORE PRODUCTS' in button_text_clean:
                        is_visible = await button.is_visible()
                        is_enabled = await button.is_enabled()
                        
                        if is_visible and is_enabled:
                            print(f"  🔄 Clicking 'LOAD MORE' button...")
                            await button.scroll_into_view_if_needed()
                            await page.wait_for_timeout(500)
                            await button.click()
                            load_more_clicked = True
                            
                            # Wait for new products to load
                            await page.wait_for_timeout(3000)
                            break
                except:
                    continue
            
            if not load_more_clicked:
                print(f"  ✅ No more products to load (reached end)")
                break
        
        previous_count = len(all_products)
        attempts += 1
        
        # Scroll down to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
    
    return all_products

async def scrape_product(page, product_url: str, product_num: int, total: int, initial_price: str = "") -> Dict:
    """
    Scrape one product - FIXED to get descriptions and main images.
    Also extracts price from product page if not already found.
    """
    result = {
        'description': "",
        'primary_image': "",
        'all_images': "",
        'price': initial_price  # Use price from category page if available
    }
    
    try:
        print(f"  [{product_num}/{total}] {product_url.split('/')[-1][:50]}...")
        
        # Navigate
        await page.goto(product_url, wait_until='domcontentloaded', timeout=45000)
        
        # Dismiss any pop-ups
        await dismiss_popups(page)
        
        # Wait for network to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=10000)
        except:
            pass
        
        # Extract price from product page if not already found
        if not result['price']:
            try:
                # Look for price on product page
                page_text = await page.inner_text('body')
                price_match = re.search(r'\$(\d+)', page_text)
                if price_match:
                    result['price'] = price_match.group(1)
                    print(f"      💰 Found price: ${result['price']}")
                
                # Also try specific price selectors
                if not result['price']:
                    price_selectors = [
                        '[class*="price"]',
                        '[data-testid*="price"]',
                        '[class*="Price"]',
                        'span:has-text("$")',
                    ]
                    for selector in price_selectors:
                        try:
                            price_elem = await page.query_selector(selector)
                            if price_elem:
                                price_text = await price_elem.inner_text()
                                price_match = re.search(r'\$(\d+)', price_text)
                                if price_match:
                                    result['price'] = price_match.group(1)
                                    print(f"      💰 Found price: ${result['price']}")
                                    break
                        except:
                            continue
            except:
                pass
        
        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, 2000)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(1500)
        
        # Make sure pop-up is dismissed before proceeding
        await dismiss_popups(page)
        
        # Wait a bit more to ensure page is ready
        await page.wait_for_timeout(500)
        
        # ===== CLICK "DETAILS & DESCRIPTION" ACCORDION =====
        description = ""
        
        try:
            # Find and click the "DETAILS & DESCRIPTION" button
            buttons = await page.query_selector_all('button')
            
            for button in buttons:
                try:
                    button_text = await button.inner_text()
                    button_text_clean = button_text.strip().upper()
                    
                    # Look for "DETAILS" or "DESCRIPTION" in button text
                    if 'DETAILS' in button_text_clean or 'DESCRIPTION' in button_text_clean:
                        # Check if not already expanded
                        aria_expanded = await button.get_attribute('aria-expanded')
                        
                        if aria_expanded == 'false' or aria_expanded is None:
                            # Verify pop-up is not blocking before clicking
                            is_blocked = await page.evaluate("""
                                () => {
                                    const overlay = document.getElementById('attentive_overlay');
                                    if (overlay && window.getComputedStyle(overlay).display !== 'none') {
                                        return true;
                                    }
                                    return false;
                                }
                            """)
                            
                            if is_blocked:
                                print(f"      ⚠️ Pop-up blocking, dismissing again...")
                                await dismiss_popups(page)
                                await page.wait_for_timeout(500)
                            
                            print(f"      Clicking: {button_text_clean[:30]}")
                            # Use force click if needed to bypass any remaining overlays
                            await button.click(force=True, timeout=5000)
                            await page.wait_for_timeout(1000)
                        
                        break
                except Exception as e:
                    # If click fails, try to dismiss pop-ups and retry once
                    if 'intercepts pointer events' in str(e).lower() or 'timeout' in str(e).lower():
                        print(f"      ⚠️ Click blocked, dismissing pop-ups and retrying...")
                        await dismiss_popups(page)
                        await page.wait_for_timeout(500)
                        try:
                            await button.click(force=True, timeout=5000)
                            await page.wait_for_timeout(1000)
                            break
                        except:
                            continue
                    continue
            
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
                            'this piece', 'offered in', 'features', 'designed with',
                            'menswear', 'collection', 'crafted', 'made with', 'cut in',
                            'offered', 'features', 'designed', 'knitted', 'woven'
                        ]):
                            if not any(skip in line.lower() for skip in [
                                'menu', 'cart', 'sign in', 'delivery', 'returns', 'email',
                                'cookie', 'privacy', 'terms', 'subscribe', 'newsletter'
                            ]):
                                description = line
                                print(f"      ✅ Description (fallback): {len(line)} chars")
                                break
            
            # Strategy 3: Try to find description in specific product description containers
            if not description:
                try:
                    # Look for common description selectors
                    desc_selectors = [
                        '[class*="description"]',
                        '[class*="product-description"]',
                        '[class*="details"]',
                        '[id*="description"]',
                        'p[class*="description"]',
                    ]
                    
                    for selector in desc_selectors:
                        desc_elements = await page.query_selector_all(selector)
                        for elem in desc_elements:
                            text = await elem.inner_text()
                            text = ' '.join(text.split()).strip()
                            if len(text) > 80 and any(kw in text.lower() for kw in [
                                'designed', 'crafted', 'made', 'collection', 'offered', 'features'
                            ]):
                                if not any(skip in text.lower() for skip in [
                                    'machine wash', 'size guide', 'model is', 'cm', 'inches'
                                ]):
                                    description = text
                                    print(f"      ✅ Description (selector): {len(text)} chars")
                                    break
                        if description:
                            break
                except:
                    pass
        
        except Exception as e:
            print(f"      ⚠️ Description error: {e}")
        
        # ===== GET MAIN PRODUCT IMAGES =====
        image_urls = []
        
        try:
            # Strategy: Get images with specific dimensions (main product images are large)
            all_imgs = await page.query_selector_all('img')
            
            print(f"      Found {len(all_imgs)} total images")
            
            def get_base_image_url(url):
                """Extract base image URL without size parameters to detect duplicates."""
                if '?' in url:
                    base = url.split('?')[0]
                else:
                    base = url
                return base
            
            # First pass: Get large product images only
            large_images = []
            medium_images = []
            seen_bases = set()  # Track base URLs to avoid duplicates
            
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
                
                # Get base URL to check for duplicates
                base_url = get_base_image_url(src)
                if base_url in seen_bases:
                    continue  # Skip duplicate
                seen_bases.add(base_url)
                
                # Categorize by size - prefer large images
                if 'imwidth=3408' in src or 'imwidth=2160' in src:
                    # Large hero images
                        large_images.append(src)
                elif 'imwidth=1260' in src or 'imwidth=1920' in src:
                    # Medium product images
                        medium_images.append(src)
                # Skip small thumbnails (imwidth=80, 160, etc.)
            
            # Prefer large images, fallback to medium
            if large_images:
                image_urls = large_images[:2]  # Limit to top 2
                print(f"      ✅ Using {len(image_urls)} large images")
            elif medium_images:
                image_urls = medium_images[:2]  # Limit to top 2
                print(f"      ✅ Using {len(image_urls)} medium images")
            
            # If still no images, be less strict
            if not image_urls:
                print(f"      ⚠️ No large images found, using any product images...")
                seen_bases_fallback = set()
                for img in all_imgs:
                    if len(image_urls) >= 2:  # Limit to 2
                        break
                    
                    src = await img.get_attribute('src')
                    alt = await img.get_attribute('alt') or ""
                    
                    if src and 'media.cos.com' in src:
                        # Just skip tiny thumbnails
                        if any(size in src for size in ['imwidth=80', 'imwidth=160', 'imwidth=60']):
                            continue
                        
                        # Check for duplicates
                        base_url = get_base_image_url(src)
                        if base_url not in seen_bases_fallback:
                            seen_bases_fallback.add(base_url)
                            image_urls.append(src)
                
                print(f"      ✅ Found {len(image_urls)} images (any size)")
        
        except Exception as e:
            print(f"      ⚠️ Image error: {e}")
        
        result['description'] = description
        result['primary_image'] = image_urls[0] if image_urls else ""
        result['all_images'] = '|'.join(image_urls[:2])  # Limit to top 2
        
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
            details = await scrape_product(page, product['url'], i, len(products), initial_price=product.get('price', ''))
            
            # Use price from product page if found, otherwise use from category page
            final_price = details.get('price', '') or product.get('price', '')
            
            all_data.append({
                'name': product['name'],
                'price': final_price,
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

async def scrape_category_async(category_url: str, category_name: str, gender: str, max_products: Optional[int] = None) -> pd.DataFrame:
    """Scrape category with pagination support."""
    
    print(f"\n{'='*60}")
    print(f"Scraping: {gender.upper()} - {category_name.upper()}")
    if max_products:
        print(f"Limit: {max_products} products")
    else:
        print(f"Limit: ALL products")
    print(f"{'='*60}\n")
    
    async with async_playwright() as p:
        print("Stage 1: Getting product URLs with pagination...\n")
        
        browser = await p.chromium.launch(
            headless=False,
            slow_mo=100
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Get all products from category page with pagination
        products = await get_all_products_from_category(page, category_url, max_products)
    
        if not products:
            print("❌ No products found")
            await browser.close()
            return pd.DataFrame()
    
        print(f"\n✅ Found {len(products)} products\n")
        
        print("First 3 products:")
        for i, p in enumerate(products[:3], 1):
            print(f"  {i}. {p['name']} - ${p['price'] if p['price'] else 'N/A'}")
        print()
        
        # Stage 2: Scrape individual product details
        print("Stage 2: Scraping product details...\n")
        
        all_data = []
        
        for i, product in enumerate(products, 1):
            details = await scrape_product(page, product['url'], i, len(products), initial_price=product.get('price', ''))
            
            # Use price from product page if found, otherwise use from category page
            final_price = details.get('price', '') or product.get('price', '')
            
            all_data.append({
                'name': product['name'],
                'price': final_price,
                'url': product['url'],
                'description': details['description'],
                'primary_image': details['primary_image'],
                'all_images': details['all_images']
            })
            
            # Delay between products
            if i < len(products):
                await asyncio.sleep(1.5)
        
        await browser.close()
        
        # Add metadata
        for item in all_data:
            item['gender'] = gender
            item['category'] = category_name
        
        # Create DataFrame
        df = pd.DataFrame(all_data)
        df = df[['gender', 'category', 'name', 'price', 'url', 'description', 'primary_image', 'all_images']]
        
        return df

def scrape_category(category_url: str, category_name: str, gender: str, max_products: Optional[int] = None) -> pd.DataFrame:
    """Synchronous wrapper for scrape_category_async."""
    return asyncio.run(scrape_category_async(category_url, category_name, gender, max_products))

async def scrape_multiple_categories_parallel(categories: List[Dict]) -> pd.DataFrame:
    """Scrape multiple categories in parallel."""
    tasks = []
    for cat in categories:
        task = scrape_category_async(
            category_url=cat['url'],
            category_name=cat['category'],
            gender=cat['gender'],
            max_products=cat.get('max_products', None)
        )
        tasks.append(task)
    
    # Run all tasks in parallel
    results = await asyncio.gather(*tasks)
    
    # Combine all DataFrames
    all_dfs = [df for df in results if not df.empty]
    if not all_dfs:
        return pd.DataFrame()
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    return combined_df

def scrape_multiple_categories(categories: List[Dict]) -> pd.DataFrame:
    """Synchronous wrapper for parallel category scraping."""
    return asyncio.run(scrape_multiple_categories_parallel(categories))

def main():
    """Main function."""
    
    # Setup
    data_dir = Path("data")
    (data_dir / "processed").mkdir(parents=True, exist_ok=True)
    (data_dir / "raw").mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*60)
    print("COS SCRAPER - ENHANCED VERSION (PARALLEL)")
    print("="*60)
    print("\nFeatures:")
    print("  ✅ Clicks 'DETAILS & DESCRIPTION' accordion")
    print("  ✅ Gets main product gallery images (not thumbnails)")
    print("  ✅ Handles pagination with 'LOAD MORE' button")
    print("  ✅ Dismisses pop-up modals")
    print("  ✅ Customizable product limits")
    print("  ✅ Parallel scraping for multiple categories")
    print("="*60 + "\n")
    
    # Define categories to scrape in parallel
    categories = [
        {
            'url': "https://www.cos.com/en-us/men/trousers",
            'category': "trousers",
            'gender': "men",
            'max_products': 4  # Testing with 4 products
        },
        {
            'url': "https://www.cos.com/en-us/men/t-shirts/polo-shirts",
            'category': "polo-shirts",
            'gender': "men",
            'max_products': 4  # Testing with 4 products
        },
        {
            'url': "https://www.cos.com/en-us/men/knitwear",
            'category': "knitwear",
            'gender': "men",
            'max_products': 4  # Testing with 4 products
        },
    ]
    
    print(f"Scraping {len(categories)} categories in parallel...\n")
    
    # Scrape all categories in parallel
    df = scrape_multiple_categories(categories)
    
    if df.empty:
        print("\n❌ No data")
        return
    
    # Save combined results
    output_csv = data_dir / "processed" / "cos_all_products.csv"
    df.to_csv(output_csv, index=False, encoding='utf-8-sig')
    print(f"\n✅ Saved: {output_csv}")
    
    output_json = data_dir / "raw" / "cos_all_products.json"
    df.to_json(output_json, orient='records', indent=2)
    print(f"✅ Saved: {output_json}")
    
    # Also save by gender/category
    for gender in df['gender'].unique():
        for category in df[df['gender'] == gender]['category'].unique():
            subset = df[(df['gender'] == gender) & (df['category'] == category)]
            if not subset.empty:
                filename = f"cos_{gender}_{category}.csv"
                filepath = data_dir / "processed" / filename
                subset.to_csv(filepath, index=False, encoding='utf-8-sig')
                print(f"✅ Saved: {filepath}")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    print(f"Total: {len(df)} products")
    
    # Summary by category
    print(f"\nBy Category:")
    for gender in df['gender'].unique():
        for category in df[df['gender'] == gender]['category'].unique():
            count = len(df[(df['gender'] == gender) & (df['category'] == category)])
            print(f"  {gender.upper()} {category}: {count} products")
    
    has_desc = df['description'].str.len() > 60
    has_imgs = df['all_images'].str.len() > 0
    
    print(f"\nQuality:")
    print(f"  Descriptions: {has_desc.sum()}/{len(df)} ({has_desc.sum()/len(df)*100:.1f}%)")
    print(f"  Images: {has_imgs.sum()}/{len(df)} ({has_imgs.sum()/len(df)*100:.1f}%)")
    
    # Show detailed stats
    if len(df) > 0:
        img_counts = df['all_images'].str.split('|').str.len()
        print(f"  Avg images per product: {img_counts.mean():.1f}")
    
    print(f"\n{'='*60}")
    print("SUCCESS! ✅")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()