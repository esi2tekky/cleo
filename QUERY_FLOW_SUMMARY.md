# Query Handling & Result Fetching - Complete Summary

## Overview

CLEO uses a **hybrid approach** combining:
1. **OpenAI API** for query understanding (optional, with fallback)
2. **Sentence Transformers** (local) for text embeddings
3. **Pandas DataFrame filtering** for attribute-based filtering
4. **Cosine similarity** for semantic search ranking

---

## Complete Query Flow

### 1. Frontend (Chrome Extension)

**File**: `extension/sidepanel.js`

**User Action** → Query sent to backend:
```javascript
POST http://localhost:5001/api/query
{
  "query": "show me wool sweaters under $200",
  "top_k": 10,
  "tagged_products": [...],           // Products tagged with '@' button
  "last_displayed_products": [...]    // Previous search results
}
```

**Frontend Logic**:
- Detects if query references products (pronouns: "this", "that", "these", "those")
- Sends tagged products if user clicked '@' button
- Always sends last displayed products for "which of those" queries

---

### 2. Backend Query Processing

**File**: `backend/app.py` → `handle_query()`

#### Step 1: Query Understanding (Optional)

**API Used**: OpenAI GPT-4o-mini (if `OPENAI_API_KEY` is set)

**Module**: `backend/query_understanding.py`

**What it does**:
- Parses natural language query into structured JSON
- Extracts: intent, product_type, attributes, price, filters, reference
- **Fallback**: If OpenAI fails or not available → keyword-based parsing

**Example Output**:
```json
{
  "intent": "search",
  "product_type": "sweater",
  "attributes": {
    "materials": ["wool"],
    "features": ["buttons"]
  },
  "price": {"max": 200},
  "filters": {"strict": false}
}
```

#### Step 2: Special Query Handling

**Priority 1: Filter Previous Results**
- Detects: "which of these/those" + filter
- Filters `last_displayed_products` directly
- Returns filtered results (no new search)

**Priority 2: Tagged Product References**
- Detects: "show me more like this" + tagged products
- Uses tagged product for similarity search
- Handles: similar products, accessories

#### Step 3: Attribute-Based Filtering

**No API calls** - Uses pandas DataFrame operations:

1. **Product Type Filtering**
   - Matches product types (sweater, cardigan, sock, etc.)
   - Includes related types (cardigan → sweater)

2. **Category Filtering**
   - Filters by category (e.g., "knitwear")

3. **Color Filtering**
   - Matches colors in `colors` column

4. **Material Filtering**
   - Matches materials in `materials` column

5. **Price Filtering**
   - Applies min/max price constraints

6. **Style Filtering** (strict mode only)
   - Matches style keywords in `style_keywords` column

7. **Feature Filtering**
   - **Must have**: "with buttons" → includes only products with buttons
   - **Must not have**: "no pattern" → excludes products with patterns

8. **Exclusion Filtering**
   - Handles "without", "no", "don't have" patterns

**Result**: Filtered DataFrame with products matching all criteria

#### Step 4: Semantic Search (Re-ranking)

**Embedding Model**: Sentence Transformers (local, no API)

**Module**: `utils/enrich.py` → `StyleEnricher.get_text_embedding()`

**What it does**:
1. **Query Embedding**: Converts query text to vector using sentence-transformers
   - Model: `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)
   - Runs locally, no API call

2. **Product Embeddings**: Loaded from `data/processed/embeddings.pkl`
   - Pre-computed during enrichment phase
   - One embedding per product (text-based)

3. **Similarity Calculation**:
   ```python
   similarity = cosine_similarity(query_emb, product_emb)
   ```
   - Computed for all filtered products
   - Sorts by similarity score

4. **Re-ranking**: Returns top-k products by similarity

**Note**: Semantic search only runs on **already filtered** products, not all products

---

## APIs Used

### 1. OpenAI API (Optional)

**Used For**:
- **Query Understanding**: `gpt-4o-mini` for parsing queries
  - Cost: ~$0.001-0.002 per query
  - Endpoint: `beta.chat.completions.parse()` with JSON schema

**Configuration**:
- Set `OPENAI_API_KEY` environment variable
- Falls back to keyword-based parsing if not set

**Files**:
- `backend/query_understanding.py` - Query parsing
- `backend/openai_client.py` - Embedding client (not currently used for queries)

### 2. Sentence Transformers (Local)

**Used For**:
- **Text Embeddings**: Converting query and product text to vectors
- **Model**: `sentence-transformers/all-MiniLM-L6-v2`
- **Dimensions**: 384
- **No API calls** - Runs locally

**Files**:
- `utils/enrich.py` - `StyleEnricher.get_text_embedding()`

### 3. No Pinecone (Currently)

**Note**: Pinecone integration exists in codebase but is **not actively used** for query processing. All embeddings are stored locally in `embeddings.pkl`.

---

## Data Flow Diagram

```
User Query
    ↓
Frontend (sidepanel.js)
    ↓
POST /api/query
    ↓
Backend (app.py)
    ↓
┌─────────────────────────────────────┐
│ 1. Query Understanding              │
│    - OpenAI GPT-4o-mini (optional)  │
│    - OR keyword-based (fallback)    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 2. Special Query Handling           │
│    - Filter previous results?       │
│    - Tagged product reference?     │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 3. Attribute Filtering              │
│    - Product type                   │
│    - Colors, materials, styles      │
│    - Price, features, exclusions    │
│    (Pandas DataFrame operations)    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│ 4. Semantic Search (Re-ranking)    │
│    - Query embedding (local)        │
│    - Product embeddings (pre-computed)│
│    - Cosine similarity              │
│    - Sort by similarity             │
└─────────────────────────────────────┘
    ↓
Return Top-K Results
```

---

## Key Design Decisions

### 1. Filter-First Approach
- **Attribute filters applied FIRST** (product type, color, price, etc.)
- **Semantic search runs ONLY on filtered set**
- Ensures strict adherence to explicit filters

### 2. Local Embeddings
- Uses sentence-transformers (local) instead of OpenAI embeddings
- Faster, no API costs, works offline
- Pre-computed product embeddings stored in pickle file

### 3. Hybrid Query Understanding
- OpenAI for accurate parsing (optional)
- Keyword-based fallback for reliability
- Best of both worlds: accuracy + reliability

### 4. Conversational Context
- Tracks `last_displayed_products` for "which of those" queries
- Tracks `tagged_products` for "show me more like this"
- Enables natural follow-up queries

---

## Performance Characteristics

### Query Processing Time
- **OpenAI parsing**: ~200-500ms (if used)
- **Attribute filtering**: ~10-50ms (pandas operations)
- **Semantic search**: ~50-200ms (depends on filtered set size)
- **Total**: ~100-750ms per query

### Cost per Query
- **OpenAI query understanding**: ~$0.001-0.002 (if used)
- **Sentence transformers**: $0 (local)
- **Total**: ~$0.001-0.002 per query (if OpenAI enabled)

---

## Files Involved

### Frontend
- `extension/sidepanel.js` - Query sending, result display

### Backend
- `backend/app.py` - Main query handler
- `backend/query_understanding.py` - OpenAI query parsing
- `backend/openai_client.py` - OpenAI embedding client (unused for queries)
- `utils/enrich.py` - Sentence transformers embeddings

### Data
- `data/processed/enriched_cos_mens_knitwear.csv` - Product data
- `data/processed/embeddings.pkl` - Pre-computed embeddings

---

## Example Query Breakdown

**Query**: "only show me sweaters with buttons"

1. **OpenAI Parsing** (if available):
   ```json
   {
     "product_type": "sweater",
     "filters": {
       "must_have": ["buttons"],
       "strict": true
     }
   }
   ```

2. **Attribute Filtering**:
   - Filter to products with "sweater" in name/category
   - Filter to products with "button" in name/description
   - Result: Only sweaters with buttons

3. **Semantic Search**:
   - Re-rank by semantic similarity to query
   - Return top-k results

**Result**: Only sweaters with buttons, ranked by relevance

