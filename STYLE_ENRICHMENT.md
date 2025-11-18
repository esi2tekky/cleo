# Style Enrichment Guide

This guide explains how to enrich scraped product data with visual embeddings and style attributes to enable style-related queries.

## Overview

The enrichment process adds three types of features to your product data:

1. **Visual Embeddings** - Deep learning embeddings from product images
2. **Text Embeddings** - Semantic embeddings from product descriptions  
3. **Style Attributes** - Extracted style keywords (colors, materials, patterns, fit, etc.)

## Methods

### 1. Visual Embeddings (Fashion CLIP)

**What it is:**
- Uses **Fashion CLIP** from Hugging Face (`Marqo/marqo-fashionCLIP`) - **default and recommended**
- Fine-tuned specifically for fashion products using Generalised Contrastive Learning (GCL)
- Generates embeddings that capture fashion-specific features: categories, styles, colors, materials, and fine details
- Better performance than general CLIP for fashion-related tasks

**Why Fashion CLIP?**
- **Fashion-optimized**: Fine-tuned on fashion data, understands style nuances better
- **Better accuracy**: Outperforms general CLIP models on fashion tasks
- **Multimodal**: Understands both images and text, so you can query with text descriptions
- **Style-aware**: Captures aesthetic and stylistic features specific to fashion
- **Open source**: Available on Hugging Face, no API keys needed

**Fallback option:**
- OpenAI CLIP (`ViT-B/32`, `ViT-L/14`, etc.) - Available as fallback if Fashion CLIP fails to load

### 2. Text Embeddings

**What it is:**
- Uses sentence transformers (default: `all-MiniLM-L6-v2`)
- Generates semantic embeddings from product descriptions
- Enables semantic search for style-related queries

**Why sentence transformers?**
- **Fast**: Optimized for production use
- **Semantic**: Understands meaning, not just keywords
- **Small**: Efficient models that run on CPU
- **Compatible**: Works well with CLIP for hybrid search

### 3. Style Attributes Extraction

**What it is:**
- Pattern-based extraction of style keywords from text
- Extracts: colors, materials, patterns, fit, style keywords, occasion

**Why pattern matching?**
- **Explicit**: Provides structured, queryable attributes
- **Fast**: No model inference needed
- **Interpretable**: Easy to understand and debug
- **Complements embeddings**: Works alongside visual/text embeddings

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Note: Fashion CLIP requires PyTorch and transformers
# For CPU-only: pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
# For GPU: Follow PyTorch installation guide for your system

# The Fashion CLIP model will be downloaded automatically from Hugging Face on first use
```

## Usage

### Basic Usage

```python
from utils.enrich import StyleEnricher
import pandas as pd

# Load your scraped data
df = pd.read_csv("data/processed/cos_mens_knitwear.csv")

# Initialize enricher (uses Fashion CLIP by default)
enricher = StyleEnricher(use_clip=True, use_fashion_clip=True)

# Enrich the data
enriched_df = enricher.enrich_dataframe(
    df,
    save_embeddings_separately=True,
    output_dir=Path("data/processed")
)

# Save enriched data
enriched_df.to_csv("data/processed/enriched_cos_mens_knitwear.csv", index=False)
```

### Command Line

```bash
# Run enrichment on all CSV files in data/processed/
python utils/enrich.py
```

### Custom Configuration

```python
# Use Fashion CLIP (default - recommended for fashion products)
enricher = StyleEnricher(
    use_clip=True,
    use_fashion_clip=True,  # Use Fashion CLIP
    fashion_clip_model="Marqo/marqo-fashionCLIP",  # Default model
    text_model="all-mpnet-base-v2",  # Better text model
    device="cuda"  # Use GPU if available
)

# Or use OpenAI CLIP (fallback)
enricher = StyleEnricher(
    use_clip=True,
    use_fashion_clip=False,  # Use OpenAI CLIP instead
    clip_model="ViT-L/14",  # Larger OpenAI CLIP model
    text_model="all-mpnet-base-v2",
    device="cuda"
)
```

## Output Structure

### Enriched CSV Columns

- All original columns (name, price, description, etc.)
- `colors` - Extracted colors (comma-separated)
- `materials` - Extracted materials (comma-separated)
- `patterns` - Extracted patterns (comma-separated)
- `fit` - Fit type (relaxed, fitted, slim, etc.)
- `style_keywords` - Style descriptors (comma-separated)
- `has_visual_embedding` - Boolean flag
- `has_text_embedding` - Boolean flag
- `style_attributes` - Full JSON object with all attributes

### Embeddings File

Embeddings are saved separately in `embeddings.pkl`:
- Dictionary mapping `{product_id}_{type}` → embedding array
- Types: `_visual` or `_text`
- Load with: `pickle.load(open("embeddings.pkl", "rb"))`

## Query Examples

### 1. Visual Similarity Search

```python
from utils.enrich import StyleEnricher, find_similar_products, load_embeddings
import pandas as pd

# Load data
df = pd.read_csv("data/processed/enriched_cos_mens_knitwear.csv")
embeddings = load_embeddings(Path("data/processed/embeddings.pkl"))

# Initialize enricher
enricher = StyleEnricher()

# Find similar products
results = find_similar_products(
    query_text="minimalist black sweater",
    enricher=enricher,
    products_df=df,
    embeddings_dict=embeddings,
    top_k=5
)

print(results[['name', 'price', 'colors', 'style_keywords']])
```

### 2. Style Attribute Filtering

```python
# Filter by extracted attributes
black_items = df[df['colors'].str.contains('black', na=False)]
minimalist_items = df[df['style_keywords'].str.contains('minimalist', na=False)]
wool_items = df[df['materials'].str.contains('wool', na=False)]
```

### 3. Hybrid Search (Visual + Text)

```python
# Combine visual and text embeddings for better results
# (Implementation depends on your search backend)
```

## Performance Considerations

### Visual Embedding Models

| Model | Type | Embedding Size | Speed | Quality | Use Case |
|-------|------|---------------|-------|---------|----------|
| Fashion CLIP | Fashion-optimized | 512 | Fast | Excellent (for fashion) | **Default, recommended** |
| OpenAI ViT-B/32 | General | 512 | Fast | Good | Fallback option |
| OpenAI ViT-L/14 | General | 768 | Slow | Excellent | When Fashion CLIP unavailable |

### Processing Time

- **Visual embeddings**: ~1-2 seconds per product (depends on image download + Fashion CLIP)
- **Text embeddings**: ~0.01 seconds per product
- **Style extraction**: ~0.001 seconds per product

For 100 products:
- With Fashion CLIP: ~2-3 minutes
- Text-only: ~1-2 seconds

**Note**: First run will download the Fashion CLIP model (~500MB) from Hugging Face, which may take a few minutes.

### Memory

- Fashion CLIP: ~800MB RAM (model + cache)
- OpenAI CLIP ViT-B/32: ~600MB RAM
- Sentence transformer: ~100MB RAM
- Embeddings: ~0.5KB per product (visual) + ~0.2KB (text)

## Alternative Approaches

### If Fashion CLIP is too slow/heavy:

1. **Use text-only embeddings** - Still enables semantic style queries
2. **Use OpenAI CLIP** - Slightly faster, but less fashion-specific
3. **Batch processing** - Process images in batches
4. **Cache embeddings** - Save and reuse for unchanged products
5. **Use CPU** - Slower but less memory intensive

### If you need better style extraction:

1. **Use LLM-based extraction** - GPT-4/Claude for better attribute extraction
2. **Fine-tune CLIP** - Train on fashion/style datasets
3. **Use fashion-specific models** - Models trained on fashion data

### For production:

1. **Vector database** - Use Pinecone, Weaviate, or Qdrant for similarity search
2. **API service** - Deploy enrichment as a microservice
3. **Caching** - Cache embeddings to avoid recomputation
4. **Async processing** - Process products in parallel

## Troubleshooting

### Fashion CLIP installation issues

```bash
# Make sure transformers is installed
pip install transformers>=4.30.0

# The model will download automatically on first use
# If download fails, check your internet connection
# Model is cached in ~/.cache/huggingface/ after first download
```

### OpenAI CLIP installation (fallback)

```bash
# Only needed if Fashion CLIP fails
pip install git+https://github.com/openai/CLIP.git
```

### Out of memory errors

- Use smaller CLIP model (ViT-B/32 instead of ViT-L/14)
- Process fewer products at once
- Use CPU instead of GPU (slower but less memory)

### Image download failures

- Check network connectivity
- Some images may be behind authentication
- Increase timeout in `download_image()`

## Next Steps

1. **Run enrichment** on your scraped data
2. **Test queries** to see what works best for your use case
3. **Fine-tune** style attribute extraction patterns
4. **Integrate** with your chatbot/query system
5. **Consider vector database** for production similarity search

## References

- [Fashion CLIP on Hugging Face](https://huggingface.co/Marqo/marqo-fashionCLIP)
- [CLIP Paper](https://arxiv.org/abs/2103.00020)
- [Sentence Transformers](https://www.sbert.net/)
- [Fashion Similarity Search](https://github.com/openai/CLIP#zero-shot-image-classification)

