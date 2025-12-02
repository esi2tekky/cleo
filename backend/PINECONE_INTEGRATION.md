# Pinecone Integration Guide

## Overview

CLEO now supports using **Pinecone** for vector search instead of local similarity calculations. This provides:
- **Faster queries**: Pinecone's optimized vector search
- **Scalability**: Can handle millions of vectors
- **Metadata filtering**: Filter by product attributes in Pinecone
- **Fallback**: Automatically falls back to local embeddings if Pinecone isn't available

## Setup

### 1. Set Environment Variables

```bash
export PINECONE_API_KEY="your-pinecone-api-key"
export PINECONE_INDEX_NAME="cos-products"  # Optional, defaults to "cos-products"
```

Or add to `.env` file:
```
PINECONE_API_KEY=your-pinecone-api-key
PINECONE_INDEX_NAME=cos-products
```

### 2. Create and Populate Pinecone Index

Run the embedding generation script to create and populate the Pinecone index:

```bash
python scripts/regenerate_openai_embeddings.py
```

This will:
- Create the Pinecone index if it doesn't exist
- Generate embeddings for all products
- Upload vectors to Pinecone
- Save a local backup to `embeddings.pkl`

### 3. Verify Index

The backend will automatically connect to Pinecone on startup. You should see:
```
✅ Pinecone index 'cos-products' connected
```

If Pinecone isn't available, you'll see:
```
⚠️  Pinecone not available, using local embeddings
```

## How It Works

### Vector Storage Format

Each product vector in Pinecone has:
- **ID**: `"{product_name}_{index}_text"` (e.g., `"Fair Isle Jumper_0_text"`)
- **Vector**: 384-dimensional embedding (sentence-transformers) or 1536-dimensional (OpenAI)
- **Metadata**: Product attributes (optional, for filtering)

### Query Flow

1. **Attribute Filtering** (pandas DataFrame)
   - Filters products by type, color, material, price, etc.
   - Results in a filtered DataFrame

2. **Vector Search** (Pinecone or local)
   - **If Pinecone available**: 
     - Queries Pinecone with filtered product indices
     - Returns top-k most similar products
   - **If Pinecone not available**:
     - Falls back to local cosine similarity calculations
     - Uses pre-computed embeddings from `embeddings.pkl`

### Code Structure

**`backend/pinecone_client.py`**:
- `PineconeClient` class for querying Pinecone
- `query_with_product_indices()`: Query Pinecone but only return results matching specific product indices
- Automatic fallback if Pinecone isn't available

**`backend/app.py`**:
- Initializes Pinecone client on startup
- Uses Pinecone for vector search when available
- Falls back to local embeddings automatically

## Benefits

### Performance
- **Faster queries**: Pinecone's optimized vector search is faster than local calculations for large datasets
- **Scalability**: Can handle millions of products without performance degradation

### Features
- **Metadata filtering**: Can filter by product attributes directly in Pinecone (future enhancement)
- **Hybrid search**: Combines attribute filtering (pandas) with vector search (Pinecone)

### Reliability
- **Automatic fallback**: If Pinecone fails or isn't available, automatically uses local embeddings
- **No breaking changes**: Existing code continues to work with or without Pinecone

## Current Implementation

### What's Implemented
✅ Pinecone client initialization
✅ Vector search on filtered products
✅ Automatic fallback to local embeddings
✅ Integration with existing query flow

### Future Enhancements
- [ ] Metadata filtering in Pinecone (filter by product_type, color, etc. in Pinecone query)
- [ ] Hybrid search (combine Pinecone metadata filters with vector search)
- [ ] Batch querying for multiple queries
- [ ] Pinecone index management utilities

## Troubleshooting

### "Pinecone index does not exist"
**Solution**: Run `python scripts/regenerate_openai_embeddings.py` to create and populate the index

### "Pinecone not available, using local embeddings"
**Possible causes**:
- `PINECONE_API_KEY` not set
- Index name doesn't match
- Network issues

**Solution**: Check environment variables and network connection. System will automatically fall back to local embeddings.

### Dimension Mismatch
**Issue**: Embedding dimensions don't match between query and index

**Solution**: 
- Ensure query embeddings use the same model as product embeddings
- Check index dimension matches embedding dimension (384 for sentence-transformers, 1536 for OpenAI)

## Cost Considerations

### Pinecone Pricing
- **Free tier**: 1 index, 100K vectors, 1M queries/month
- **Paid plans**: Based on usage

### Current Usage
- **Vectors**: One per product (~100-1000 products)
- **Queries**: One per user query
- **Storage**: Minimal (vectors are small)

For most use cases, the free tier is sufficient.

## Migration Notes

### From Local to Pinecone
1. Set `PINECONE_API_KEY`
2. Run embedding generation script
3. Restart backend
4. System automatically uses Pinecone if available

### From Pinecone to Local
1. Remove or unset `PINECONE_API_KEY`
2. Restart backend
3. System automatically falls back to local embeddings

No code changes needed - the system handles both automatically!

