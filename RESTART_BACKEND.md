# How to Restart Backend with New Data

## Quick Start

1. **Stop the current backend** (if running):
   - Press `Ctrl+C` in the terminal where it's running
   - Or find and kill the process:
     ```bash
     pkill -f "python.*app.py"
     ```

2. **Start the backend**:
   ```bash
   cd /Users/chloemurdoch/Desktop/cleo
   python3.13 backend/app.py
   ```

3. **Verify it loaded the new data**:
   You should see:
   ```
   ✅ Loaded 1018 products from enriched_cos_all_products.csv
   ✅ Pinecone index 'cos-products' connected
   ✅ Pinecone client initialized
   ```

4. **Test in Chrome Extension**:
   - Open the Chrome extension
   - Try a query like "show me minimalist black sweaters"
   - The results should now include all 1,018 products with style attributes!

## What Changed

- **Before**: 20 products (knitwear only)
- **After**: 1,018 products (all categories)
- **Enrichment**: Products now have style attributes (colors, materials, patterns, style_keywords)

## Troubleshooting

- **"No products loaded"**: Check that `enriched_cos_all_products.csv` exists in `data/processed/`
- **"Pinecone not available"**: Check your `.env` file has `PINECONE_API_KEY` set
- **Port already in use**: Kill the old process or use a different port

