# Quick Start: Chrome Extension

## ✅ Yes, Chrome Extension is Feasible!

I've created a complete Chrome extension setup for your shopping assistant.

## Architecture

```
Chrome Extension (Frontend)
    ↓ HTTP Requests
Flask API (Backend)
    ↓
Enriched Data + Embeddings
    ↓
Similarity Search
```

## Setup (3 Steps)

### Step 1: Start Backend API

```bash
cd backend
pip install -r requirements.txt
python app.py
```

You should see:
```
✅ Loaded 19 products
✅ Loaded embeddings
🚀 Starting Shopping Assistant API...
 * Running on http://0.0.0.0:5000
```

### Step 2: Load Chrome Extension

1. Open Chrome → `chrome://extensions/`
2. Enable **"Developer mode"** (top right toggle)
3. Click **"Load unpacked"**
4. Select the `extension/` folder
5. Extension icon appears in toolbar ✅

### Step 3: Test It!

1. Click the extension icon
2. Side panel opens with chat interface
3. Try queries:
   - "Show me minimalist black sweaters"
   - "What colors go with beige?"
   - "Find wool items under $200"

## What's Included

### Backend (`backend/app.py`)
- ✅ Flask API server
- ✅ Product search endpoints
- ✅ Semantic similarity search
- ✅ Natural language query handling
- ✅ Color matching suggestions

### Extension (`extension/`)
- ✅ Side panel chat UI
- ✅ Product cards with images
- ✅ Real-time search
- ✅ Modern, clean design

## API Endpoints

- `GET /api/health` - Check if backend is running
- `GET /api/products` - Get all products (with filters)
- `POST /api/search` - Semantic similarity search
- `POST /api/query` - Natural language queries
- `GET /api/color-matches` - Color compatibility

## Example Queries

- "minimalist black sweater"
- "wool items under $200"
- "show me beige cardigans"
- "what colors match with navy?"
- "find casual oversized sweaters"

## Next Steps

1. **Test the extension** - Make sure backend is running first
2. **Add icons** - Create extension icons (or use placeholders)
3. **Customize styling** - Adjust colors/fonts in `styles.css`
4. **Enhance queries** - Add more sophisticated NLP processing
5. **Add features** - Save favorites, history, etc.

## Troubleshooting

**Extension not loading?**
- Check `chrome://extensions/` for errors
- Make sure all files are in `extension/` folder

**Backend not connecting?**
- Verify backend is running: `curl http://localhost:5001/api/health`
- Check CORS is enabled in `app.py`

**No results?**
- Check backend logs for errors
- Verify enriched data exists in `data/processed/`

