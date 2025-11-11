"""
Utility functions for cleaning and parsing Exa markdown output.
"""
import re

def strip_markdown_links(text: str) -> str:
    """
    Remove markdown link syntax from text.
    
    Converts: [Link Text](https://url) → Link Text
    """
    # Pattern: [text](url)
    cleaned = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return cleaned

def strip_all_markdown(text: str) -> str:
    """
    Remove various markdown formatting from text.
    """
    if not text:
        return ""
    
    # Remove markdown links [text](url)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    
    # Remove bold/italic markers
    text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
    text = re.sub(r'\*([^\*]+)\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    
    # Remove inline code markers
    text = re.sub(r'`([^`]+)`', r'\1', text)
    
    # Remove escape characters
    text = text.replace('\\', '')
    
    # Clean up multiple spaces
    text = ' '.join(text.split())
    
    return text

def extract_markdown_images(text: str) -> list:
    """
    Extract image URLs from markdown image syntax.
    
    Finds: ![alt](image_url)
    """
    pattern = r'!\[([^\]]*)\]\(([^\)]+)\)'
    matches = re.findall(pattern, text)
    return [url for alt, url in matches]

def clean_description_text(text: str) -> str:
    """
    Clean description text by removing navigation and markdown.
    """
    if not text:
        return ""
    
    # First strip markdown
    text = strip_all_markdown(text)
    
    # Remove common navigation patterns
    nav_patterns = [
        r'Home\s+Men\s+',
        r'Home\s+Women\s+',
        r'Filter & sort',
        r'DESCRIPTION',
        r'SIZE & FIT',
        r'SHIPPING & RETURNS',
        r'MATERIAL & CARE',
        r'Add to bag',
        r'Size guide',
    ]
    
    for pattern in nav_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    
    # Clean up extra whitespace
    text = ' '.join(text.split())
    
    return text.strip()

# Test the functions
if __name__ == "__main__":
    # Test data
    test_text = "[**Product Name**](https://example.com) Home](https://cos.com) Men](https://cos.com/men)"
    
    print("Original:", test_text)
    print("Stripped:", strip_markdown_links(test_text))
    print("Fully cleaned:", strip_all_markdown(test_text))
    
    # Test image extraction
    test_images = "Some text ![Product Image](https://example.com/img1.jpg) more text ![Another](https://example.com/img2.jpg)"
    print("\nImage URLs:", extract_markdown_images(test_images))
