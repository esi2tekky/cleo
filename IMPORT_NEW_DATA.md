# Importing New Scraped Data

This guide explains how to import a new CSV file from your partner's scraping.

## Step 1: Add the CSV File

1. **Place the new CSV file in `data/processed/`**
   - If your partner sent you a file, copy it to: `data/processed/your_new_file.csv`
   - For example: `data/processed/cos_mens_knitwear_expanded.csv`

2. **Check the file structure**
   - The CSV should have columns like: `name`, `price`, `description`, `primary_image`, `url`, `category`, `gender`
   - You can check by opening it in Excel or running:
     ```bash
     head -1 data/processed/your_new_file.csv
     ```

## Step 2: Run Enrichment

The enrichment process adds style attributes, embeddings, and color matching to the products.

### Option A: Automatic (Recommended)
```bash
# This will automatically find and process all CSV files in data/processed/
python utils/enrich.py
```

### Option B: Manual (if you want more control)
```python
from pathlib import Path
import pandas as pd
from utils.enrich import StyleEnricher

# Load your new CSV
data_dir = Path("data/processed")
csv_file = data_dir / "your_new_file.csv"
df = pd.read_csv(csv_file)

# Initialize enricher
enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)

# Enrich the data
enriched_df = enricher.enrich_dataframe(
    df,
    save_embeddings_separately=True,
    output_dir=data_dir
)

# Save enriched data
output_file = data_dir / f"enriched_{csv_file.stem}.csv"
cols_to_save = [c for c in enriched_df.columns if 'embedding' not in c.lower()]
enriched_df[cols_to_save].to_csv(output_file, index=False)
print(f"✅ Saved to: {output_file}")
```

## Step 3: Update Backend to Use New Data

You have two options:

### Option A: Replace Existing Data (if new data includes old data)
If the new CSV includes all the old products plus new ones:

1. **Update `backend/app.py`** to load the new enriched file:
   ```python
   # In load_data() function, change line 54:
   csv_file = data_dir / "enriched_your_new_file.csv"
   ```

2. **Restart the backend**:
   ```bash
   python backend/app.py
   ```

### Option B: Merge Data (if you want to keep both)
If you want to combine the old and new data:

```python
import pandas as pd
from pathlib import Path

# Load both datasets
old_df = pd.read_csv("data/processed/enriched_cos_mens_knitwear.csv")
new_df = pd.read_csv("data/processed/enriched_your_new_file.csv")

# Merge (remove duplicates based on URL or name)
merged_df = pd.concat([old_df, new_df], ignore_index=True)
merged_df = merged_df.drop_duplicates(subset=['url'], keep='last')  # Keep newer version if duplicate

# Save merged data
merged_df.to_csv("data/processed/enriched_cos_mens_knitwear_merged.csv", index=False)
print(f"✅ Merged {len(merged_df)} products")
```

Then update `backend/app.py` to load the merged file.

## Step 4: Update Embeddings

If you merged data or have a new embeddings file:

1. **The enrichment process automatically saves embeddings to `embeddings.pkl`**
2. **If you merged data, you may need to regenerate embeddings**:
   ```python
   from utils.enrich import StyleEnricher
   import pandas as pd
   from pathlib import Path
   import pickle
   
   # Load merged data
   df = pd.read_csv("data/processed/enriched_cos_mens_knitwear_merged.csv")
   
   # Initialize enricher
   enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)
   
   # Generate embeddings for all products
   embeddings_dict = {}
   for idx, row in df.iterrows():
       # Generate text embedding
       text_emb = enricher.get_text_embedding(row.get('name', '') + ' ' + str(row.get('description', '')))
       product_id = f"{row.get('name', idx)}_{idx}"
       embeddings_dict[f"{product_id}_text"] = text_emb
   
   # Save embeddings
   embeddings_file = Path("data/processed/embeddings.pkl")
   with open(embeddings_file, 'wb') as f:
       pickle.dump(embeddings_dict, f)
   print(f"✅ Saved {len(embeddings_dict)} embeddings")
   ```

## Step 5: Verify

1. **Check the health endpoint**:
   ```bash
   curl http://localhost:5001/api/health
   ```
   Should show the new product count.

2. **Test a query** in the Chrome extension to make sure products are loading.

## Troubleshooting

- **"No CSV files found"**: Make sure the CSV is in `data/processed/`
- **"Missing columns"**: Check that the CSV has required columns (name, price, description, etc.)
- **"Embeddings not loading"**: Make sure `embeddings.pkl` exists in `data/processed/`
- **"Backend not updating"**: Restart the backend server after changing files

