# 🚀 Quick Start Guide

## ⚠️ Important Note

The Exa API recently changed from using `ids` to `urls` parameter. This version is **already fixed** and ready to use!

## What You Have Now

A complete, working product scraper that:
- ✅ Extracts products from COS category pages
- ✅ Gets individual product details (description, images)
- ✅ Outputs clean, structured CSV files
- ✅ Organizes data by gender and category

## Project Structure

```
/home/claude/
├── exa_test_crawl.py      # Main scraper script
├── test_regex.py           # Validation script (already tested ✅)
├── requirements.txt        # Python dependencies
├── .env.example           # Environment template
├── .gitignore             # Git ignore rules
├── README.md              # Full documentation
├── SOLUTION.md            # Why this approach is better
└── QUICKSTART.md          # This file!

data/                       # Created when you run the script
├── raw/                    # Raw JSON responses
└── processed/              # Clean CSV outputs
```

## 🏃 How to Run

### Step 1: Set up your Exa API key

```bash
# Copy the template
cp .env.example .env

# Edit .env and add your key
echo "EXA_API_KEY=your_actual_key_here" > .env
```

**Don't have an Exa API key?** Get one at https://exa.ai/

### Step 2: Run the scraper

```bash
python exa_test_crawl.py
```

You should see output like:

```
============================================================
Scraping: MEN - KNITWEAR
URL: https://www.cos.com/en-us/men/knitwear
============================================================

Step 1: Fetching category page...
Step 2: Extracting product links...
Found 48 products

Step 3: Fetching details for 48 products...
  [1/48] Knitted merino-yak zip-up hoodie...
  [2/48] Boiled-wool crew-neck sweater...
  ...

✓ Successfully scraped 48 products

✓ Saved to: data/processed/cos_mens_knitwear.csv
✓ Saved JSON to: data/raw/cos_mens_knitwear.json

============================================================
SUMMARY
============================================================
Total products: 48
Price range: $79 - $359

Sample products:
                                name  price                                  description
  Knitted merino-yak zip-up hoodie    199  The menswear collection is anchored by...
     Boiled-wool crew-neck sweater    139  Offered in versatile beige-melange...
```

### Step 3: Check the output

```bash
# View the CSV
cat data/processed/cos_mens_knitwear.csv

# Or open in Excel/Google Sheets
# The file is at: data/processed/cos_mens_knitwear.csv
```

## 📊 Expected Output

Your CSV will have these columns:

| Column | Example |
|--------|---------|
| gender | `men` |
| category | `knitwear` |
| name | `Knitted merino-yak zip-up hoodie` |
| price | `199` |
| url | `https://www.cos.com/en-us/men/menswear/...` |
| description | `The menswear collection is anchored by...` |
| primary_image_url | `https://media.cos.com/sb/.../img.jpg` |
| all_image_urls | `img1.jpg\|img2.jpg\|img3.jpg` |

## 🔧 Troubleshooting

### "EXA_API_KEY not found"
→ Make sure you created `.env` and added your key

### "No products found"
→ Check internet connection
→ Verify the category URL is correct
→ Check if COS changed their HTML structure

### "Wrong images"
→ Look at `all_image_urls` column
→ Adjust the filtering logic in `fetch_product_details()`

### API rate limits
→ Exa may limit requests
→ Add delays between product fetches if needed

## 🎯 Next Steps

### 1. Verify Data Quality (5 min)

Open the CSV and spot-check:
- [ ] Product names are correct
- [ ] Prices are right
- [ ] URLs work when clicked
- [ ] Descriptions make sense
- [ ] Images load and are correct

### 2. Tune Description Extraction (optional)

If descriptions aren't great, edit `fetch_product_details()`:

```python
# In exa_test_crawl.py, around line 52
# Adjust this regex pattern:
desc_match = re.search(r'(?:Description|DESCRIPTION)...', item.text)
```

### 3. Scale to More Categories (15 min)

Edit `main()` in `exa_test_crawl.py`:

```python
def main():
    # Scrape multiple categories
    categories = [
        ("https://www.cos.com/en-us/men/knitwear", "knitwear", "men"),
        ("https://www.cos.com/en-us/men/shirts", "shirts", "men"),
        ("https://www.cos.com/en-us/men/trousers", "trousers", "men"),
    ]
    
    all_dfs = []
    for url, cat, gender in categories:
        df = scrape_category(url, cat, gender)
        all_dfs.append(df)
    
    # Combine all
    final_df = pd.concat(all_dfs)
    final_df.to_csv("data/processed/cos_all_mens_products.csv", index=False)
```

### 4. Add Women's Products (5 min)

Just change the URLs:

```python
categories = [
    # Men's
    ("https://www.cos.com/en-us/men/knitwear", "knitwear", "men"),
    
    # Women's  
    ("https://www.cos.com/en-us/women/knitwear", "knitwear", "women"),
    ("https://www.cos.com/en-us/women/dresses", "dresses", "women"),
]
```

### 5. Build Your Chatbot (next phase)

Once you have all products in CSV:

1. Load into database or vector store
2. Create embeddings for descriptions
3. Build search/recommendation logic
4. Add conversational interface

## 📚 Key Files to Read

1. **This file** - Quick start
2. **README.md** - Full documentation
3. **SOLUTION.md** - Why this approach works

## ⚡ Pro Tips

1. **Test small first**: Start with one category before scraping all
2. **Save intermediate results**: The JSON files are useful for debugging
3. **Version control**: Add this to git (the .gitignore is already set up)
4. **API limits**: If you hit rate limits, add `time.sleep(1)` between requests
5. **Data freshness**: Re-run periodically to keep product data updated

## 🎓 Understanding the Code

The scraper works in 3 steps:

```python
# Step 1: Get category page
category_page = exa.get_contents(ids=[category_url])

# Step 2: Extract product URLs using regex
products = extract_product_links(category_page.text)
# Returns: [{'name': '...', 'price': '...', 'url': '...'}, ...]

# Step 3: Get details for each product
for product in products:
    details = fetch_product_details(exa, product['url'])
    # Returns: {'description': '...', 'primary_image': '...', ...}
```

The key insight: **Treat category page as an index, then fetch each product individually.**

## 🚨 Important Notes

1. **Exa API costs**: Each product = 1 API call. 48 products = 49 total calls (1 for category + 48 for products)
2. **Rate limits**: Be respectful, don't hammer the API
3. **Data freshness**: Product data changes, re-scrape periodically
4. **Error handling**: Some products might fail, that's OK
5. **COS changes**: If COS updates their website, the regex might need adjustment

## ✅ Success Checklist

- [ ] .env file created with API key
- [ ] Script runs without errors
- [ ] CSV file generated in `data/processed/`
- [ ] CSV has expected columns
- [ ] Product names and prices look correct
- [ ] Image URLs load in browser
- [ ] Ready to extend to more categories!

---

**Questions?** Check README.md or SOLUTION.md for details!

**Ready to scale?** Edit the `categories` list in `main()` and re-run!
