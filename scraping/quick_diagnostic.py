#!/usr/bin/env python3
"""
Quick diagnostic - saves HTML and checks what's on the page
"""
import asyncio
from playwright.async_api import async_playwright

TEST_URL = "https://www.cos.com/en-us/men/knitwear/product.knitted-merino-yak-zip-up-hoodie-beige.1237169001.html"

async def quick_check():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        print(f"Loading {TEST_URL}...")
        await page.goto(TEST_URL, wait_until='networkidle', timeout=30000)
        
        # Scroll to trigger lazy loading
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(2000)
        await page.evaluate("window.scrollTo(0, 0)")
        await page.wait_for_timeout(2000)
        
        # Save HTML
        html = await page.content()
        with open("/home/claude/quick_check.html", "w", encoding="utf-8") as f:
            f.write(html)
        
        # Check elements
        title = await page.title()
        all_imgs = await page.query_selector_all('img')
        
        print(f"\nPage Title: {title}")
        print(f"Total images: {len(all_imgs)}")
        
        # Sample images
        if all_imgs:
            print("\nFirst 3 images:")
            for i, img in enumerate(all_imgs[:3]):
                src = await img.get_attribute('src')
                print(f"  {i+1}. {src}")
        
        # Check for text content
        body_text = await page.inner_text('body')
        print(f"\nBody text length: {len(body_text)} chars")
        print(f"Contains 'collection': {'collection' in body_text.lower()}")
        print(f"Contains 'merino': {'merino' in body_text.lower()}")
        
        # Look for specific elements
        accordions = await page.query_selector_all('button[aria-expanded]')
        print(f"\nAccordion buttons: {len(accordions)}")
        
        # Check specific selectors
        print("\nTrying description selectors:")
        selectors = [
            'div[id^="disclosure-"]',
            'div[role="region"]',
            '[class*="accordion"]',
        ]
        
        for sel in selectors:
            els = await page.query_selector_all(sel)
            print(f"  {sel}: {len(els)} found")
        
        print(f"\n✅ HTML saved to: quick_check.html")
        
        await browser.close()

asyncio.run(quick_check())
