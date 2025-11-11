#!/usr/bin/env python3
"""
Debug script to see what Exa returns for a COS product page.
This helps us understand what text/HTML we're working with.
"""
import os
import json
from pathlib import Path
from exa_py import Exa
from dotenv import load_dotenv

load_dotenv()

def debug_product_page(save_to_file=True):
    """Fetch and display what Exa sees on a product page."""
    
    # Example product URL (the merino-yak sweatpants you mentioned)
    product_url = "https://www.cos.com/en-us/men/menswear/trousers/wool/product/knitted-merino-yak-joggers-beige-mlange-1311860001"
    
    print("=" * 80)
    print("DEBUG: Exa Product Page Content")
    print("=" * 80)
    print(f"\nFetching: {product_url}\n")
    
    api_key = os.getenv('EXA_API_KEY')
    if not api_key:
        print("❌ EXA_API_KEY not found in .env file")
        return
    
    exa = Exa(api_key=api_key)
    
    # Fetch the product page
    result = exa.get_contents(
        urls=[product_url],
        text=True  # This should return rendered text
    )
    
    if not result.results:
        print("❌ No results returned")
        return
    
    item = result.results[0]
    
    # Save to file if requested
    if save_to_file:
        debug_dir = Path("data/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        
        debug_data = {
            'url': product_url,
            'title': item.title,
            'text': item.text,
            'extras': item.extras if item.extras else {}
        }
        
        output_file = debug_dir / "product_page_debug.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(debug_data, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Saved full debug output to: {output_file}\n")
    
    print("=" * 80)
    print("TITLE:")
    print("=" * 80)
    print(item.title)
    
    print("\n" + "=" * 80)
    print("TEXT CONTENT (first 2000 chars):")
    print("=" * 80)
    print(item.text[:2000] if item.text else "No text content")
    
    print("\n" + "=" * 80)
    print("IMAGE LINKS:")
    print("=" * 80)
    if item.extras and 'image_links' in item.extras:
        for i, img in enumerate(item.extras['image_links'][:10], 1):
            print(f"{i}. {img}")
        if len(item.extras['image_links']) > 10:
            print(f"... and {len(item.extras['image_links']) - 10} more images")
    else:
        print("No image links found")
    
    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)
    
    if item.text:
        # Check for description keywords
        has_description = "menswear collection" in item.text.lower()
        has_joggers = "joggers" in item.text.lower()
        has_material = "wool" in item.text.lower() or "merino" in item.text.lower()
        has_fit = "relaxed fit" in item.text.lower()
        has_beige = "beige" in item.text.lower() or "mélange" in item.text.lower()
        
        print(f"Contains 'menswear collection': {has_description}")
        print(f"Contains 'joggers': {has_joggers}")
        print(f"Contains material info (wool/merino): {has_material}")
        print(f"Contains 'relaxed fit': {has_fit}")
        print(f"Contains 'beige/mélange': {has_beige}")
        print(f"Total text length: {len(item.text)} characters")
        print(f"Number of sentences (.): {item.text.count('.')}")
    
    print("\n" + "=" * 80)
    print("EXPECTED DESCRIPTION:")
    print("=" * 80)
    expected = "The menswear collection is anchored by foundational staples like these joggers"
    print(expected + "...")
    
    if item.text and expected in item.text:
        print("\n✅ Description IS in the text!")
        # Find and print the full paragraph
        start_idx = item.text.find(expected)
        end_idx = item.text.find(".", start_idx + 200) + 1  # Find sentence end
        if end_idx > start_idx:
            print("\nFull description found:")
            print(item.text[start_idx:end_idx])
    else:
        print("\n❌ Description NOT found in text")
        print("\nPossible reasons:")
        print("1. Exa isn't capturing accordion/disclosure content")
        print("2. Content is loaded by JavaScript after initial render")
        print("3. We need to look for different text patterns")
        
        if save_to_file:
            print(f"\n💡 Check the full text in: data/debug/product_page_debug.json")
    
    print("\n" + "=" * 80)
    print("RECOMMENDATION:")
    print("=" * 80)
    
    if item.text and expected in item.text:
        print("✅ Exa CAN capture the description! The regex just needs tuning.")
        print("   Action: Run the main scraper - it should work now.")
    else:
        print("⚠️  Exa might not capture accordion content.")
        print("   Options:")
        print("   1. Check if description is elsewhere in the text")
        print("   2. Use BeautifulSoup to parse the HTML directly")
        print("   3. Use a headless browser (Playwright/Selenium)")
        print("   4. Extract from product metadata/JSON-LD if available")

if __name__ == "__main__":
    debug_product_page(save_to_file=True)
