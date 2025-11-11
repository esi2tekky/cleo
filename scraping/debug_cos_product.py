#!/usr/bin/env python3
"""
Debug script to test scraping a single COS product page.
This will help us see what's actually in the HTML.
"""
import requests
from bs4 import BeautifulSoup

# Test URL - a product from COS men's knitwear
TEST_URL = "https://www.cos.com/en-us/men/knitwear/product.knitted-merino-yak-zip-up-hoodie-beige.1237169001.html"

print(f"Testing URL: {TEST_URL}\n")
print("="*60)

# Headers to mimic a real browser
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1'
}

try:
    print("Fetching page...")
    response = requests.get(TEST_URL, headers=headers, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Content Length: {len(response.text)} characters\n")
    
    if response.status_code != 200:
        print(f"❌ Got status {response.status_code}")
        print(f"Response text: {response.text[:500]}")
        exit(1)
    
    print("="*60)
    print("PARSING HTML")
    print("="*60)
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # ===== Test 1: Find description =====
    print("\n1. Looking for description...")
    
    # Try multiple selectors
    desc_selectors = [
        ('div[id^="disclosure-"]', 'Accordion div with id starting with "disclosure-"'),
        ('div[data-testid="accordion-item-0"]', 'Accordion with data-testid'),
        ('div[class*="ProductDescription"]', 'Div with ProductDescription in class'),
        ('div[class*="accordion"]', 'Div with accordion in class'),
    ]
    
    description_found = False
    for selector, desc in desc_selectors:
        print(f"\n   Trying: {desc}")
        print(f"   Selector: {selector}")
        
        elements = soup.select(selector)
        print(f"   Found {len(elements)} elements")
        
        if elements:
            for i, elem in enumerate(elements[:3]):  # Show first 3
                text = elem.get_text(strip=True)
                print(f"   Element {i+1} text: {text[:150]}...")
                if len(text) > 50 and 'collection' in text.lower():
                    description_found = True
                    print(f"   ✅ Found good description!")
    
    if not description_found:
        print("\n   ⚠️ No good description found with standard selectors")
        print("   Let's search the entire HTML for description text...")
        
        # Search for common description patterns
        all_text = soup.get_text()
        if 'menswear collection' in all_text.lower() or 'product is' in all_text.lower():
            print("   ✅ Description text exists somewhere in the HTML!")
            # Find the containing element
            for elem in soup.find_all(['p', 'div', 'span']):
                text = elem.get_text(strip=True)
                if 'collection' in text.lower() and len(text) > 50:
                    print(f"   Found in <{elem.name}> tag:")
                    print(f"   Classes: {elem.get('class')}")
                    print(f"   ID: {elem.get('id')}")
                    print(f"   Text: {text[:150]}...")
                    break
        else:
            print("   ❌ Description text not found anywhere")
    
    # ===== Test 2: Find images =====
    print("\n" + "="*60)
    print("2. Looking for images...")
    
    all_imgs = soup.find_all('img')
    print(f"\n   Total <img> tags found: {len(all_imgs)}")
    
    cos_images = [img for img in all_imgs if img.get('src') and 'media.cos.com' in img.get('src', '')]
    print(f"   Images from media.cos.com: {len(cos_images)}")
    
    if cos_images:
        print("\n   Sample images:")
        for i, img in enumerate(cos_images[:5]):
            src = img.get('src', '')
            alt = img.get('alt', 'No alt')
            print(f"\n   Image {i+1}:")
            print(f"      src: {src}")
            print(f"      alt: {alt}")
            
            # Check if it's a thumbnail
            if 'imwidth=' in src:
                width = src.split('imwidth=')[1].split('&')[0] if '&' in src.split('imwidth=')[1] else src.split('imwidth=')[1]
                print(f"      width: {width}px")
    else:
        print("   ❌ No images from media.cos.com found")
        print("\n   Let's check what image domains are present:")
        unique_domains = set()
        for img in all_imgs:
            src = img.get('src', '')
            if src and src.startswith('http'):
                domain = src.split('/')[2]
                unique_domains.add(domain)
        print(f"   Image domains found: {list(unique_domains)}")
    
    # ===== Test 3: Check for bot detection =====
    print("\n" + "="*60)
    print("3. Checking for bot detection...")
    
    # Check for common bot detection indicators
    bot_indicators = [
        ('Cloudflare', 'Checking your browser'),
        ('PerimeterX', 'Please verify you are a human'),
        ('Access Denied', 'Access Denied'),
        ('captcha', 'CAPTCHA'),
    ]
    
    page_text = soup.get_text().lower()
    detected = False
    for indicator, message in bot_indicators:
        if indicator.lower() in page_text or message.lower() in page_text:
            print(f"   ⚠️ Possible bot detection: Found '{indicator}'")
            detected = True
    
    if not detected:
        print("   ✅ No obvious bot detection found")
    
    # ===== Test 4: Save HTML for inspection =====
    print("\n" + "="*60)
    print("4. Saving HTML for manual inspection...")
    
    output_file = "/home/claude/debug_page.html"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(response.text)
    print(f"   ✅ Saved to: {output_file}")
    print(f"   You can inspect this file to see the exact HTML structure")
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"✅ Successfully fetched page (status 200)")
    print(f"✅ Page contains {len(response.text)} characters")
    print(f"✅ Found {len(all_imgs)} total images")
    print(f"{'✅' if cos_images else '❌'} Found {len(cos_images)} COS product images")
    print(f"{'✅' if description_found else '❌'} Found product description")
    print(f"{'⚠️' if detected else '✅'} {'Bot detection detected' if detected else 'No bot detection'}")
    
except requests.exceptions.Timeout:
    print("❌ Request timeout - site might be slow or blocking requests")
except requests.exceptions.RequestException as e:
    print(f"❌ Request error: {e}")
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
