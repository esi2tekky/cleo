# COS Product Scraper

A Python-based web scraper for COS e-commerce products using the Exa API.

## Problem Statement

This project addresses the need to extract structured product data from COS's website for building a shopping assistant chatbot. The initial approach using Exa's `subpages` parameter had several issues:

1. **Wrong subpages**: Exa was following links to other categories (women's, accessories) instead of individual products
2. **Unstructured data**: JSON output wasn't organized by product
3. **Mismatched images**: Image URLs were in a separate `extras` field, not linked to specific products

## Solution

The improved approach:

1. **Two-stage scraping**:
   - Stage 1: Fetch the category page and extract product links using regex pattern matching
   - Stage 2: For each product link, make individual API calls to get details

2. **Regex-based extraction**:
   - Parse markdown links: `[**Product Name** \ \ $Price](url)`
   - Extract only product URLs (containing `/product/` in path)
   
3. **Structured output**:
   - Each row = one product
   - Columns: gender, category, name, price, url, description, primary_image_url, all_image_urls

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set up your Exa API key:
```bash
cp .env.example .env
# Edit .env and add your API key
```

3. Run the scraper:
```bash
python exa_test_crawl.py
```

## Output

The script generates two files:

- `data/processed/cos_mens_knitwear.csv` - Clean, structured CSV
- `data/raw/cos_mens_knitwear.json` - Raw JSON for debugging

### CSV Structure

| Column | Description |
|--------|-------------|
| gender | 'men' or 'women' |
| category | Product category (e.g., 'knitwear') |
| name | Product name |
| price | Price in USD |
| url | Product page URL |
| description | Product description text |
| primary_image_url | Main product image (high-res) |
| all_image_urls | All images (pipe-separated) |

## Current Status

✅ **Working**: Men's knitwear scraping
🔄 **In Progress**: Description extraction refinement
📋 **To Do**: 
- Add other categories
- Implement women's products
- Handle pagination if needed
- Add retry logic for failed requests

## Next Steps

1. **Verify output quality**: Check `data/processed/cos_mens_knitwear.csv`
2. **Refine description extraction**: Currently uses heuristics, may need adjustment
3. **Scale to more categories**: Add men's shirts, pants, etc.
4. **Add women's products**: Same structure, different base URL

## Extending to Other Categories

To scrape additional categories, modify the `main()` function:

```python
# Men's shirts
df_shirts = scrape_category(
    category_url="https://www.cos.com/en-us/men/shirts",
    category_name="shirts",
    gender="men"
)

# Women's knitwear
df_women_knitwear = scrape_category(
    category_url="https://www.cos.com/en-us/women/knitwear",
    category_name="knitwear",
    gender="women"
)

# Combine all
df_all = pd.concat([df, df_shirts, df_women_knitwear])
```

## Known Limitations

1. **Description extraction**: Currently uses pattern matching which may not work for all product pages
2. **Image selection**: Filters thumbnails heuristically (by URL parameters)
3. **Rate limiting**: No built-in rate limiting (Exa may have limits)
4. **No pagination**: Assumes all products visible on category page

## Troubleshooting

**No products found**:
- Check if the regex pattern matches the markdown format
- Verify the category URL is correct
- Look at the "Sample text" output to see what Exa returns

**Wrong images**:
- Adjust the thumbnail filtering logic in `fetch_product_details()`
- Check if COS changed their image URL structure

**Missing descriptions**:
- Review the text content of product pages
- Adjust the description extraction regex in `fetch_product_details()`

## Architecture

```
exa_test_crawl.py          # Main script
├── extract_product_links() # Parse category page markdown
├── fetch_product_details() # Get individual product info
├── scrape_category()       # Orchestrate scraping
└── main()                  # Entry point

data/
├── raw/                    # Raw JSON responses
└── processed/              # Clean CSV outputs
```
