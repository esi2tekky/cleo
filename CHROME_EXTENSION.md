# Chrome Extension Architecture

## Why Chrome Extension?

✅ **Feasible and Recommended!**

**Advantages:**
- Always accessible via extension icon
- Can work while browsing shopping sites
- Can potentially read product pages (with permissions)
- Native browser integration
- Can use Chrome's new Side Panel API for better UX
- Easy to distribute via Chrome Web Store

**Architecture:**
```
Chrome Extension (Frontend)
    ↓ HTTP/WebSocket
Backend API (Flask/FastAPI)
    ↓
Enriched Data + Embeddings
    ↓
Similarity Search & Query Processing
```

## Project Structure

```
cleo/
├── extension/              # Chrome extension
│   ├── manifest.json      # Extension config
│   ├── popup.html         # Chat UI (or use side panel)
│   ├── popup.js           # Frontend logic
│   ├── styles.css         # Styling
│   └── icons/             # Extension icons
├── backend/               # API server
│   ├── app.py            # Flask/FastAPI server
│   ├── query_handler.py  # Query processing
│   └── search.py         # Similarity search
└── data/                  # Your enriched data
```

## Implementation Options

### Option 1: Side Panel (Recommended)
- Chrome's new Side Panel API (Chrome 114+)
- Persistent chat interface
- Better UX than popup

### Option 2: Popup
- Traditional extension popup
- Opens on icon click
- Simpler but less persistent

### Option 3: Content Script + Modal
- Injects chat into web pages
- Works on shopping sites
- More complex but integrated

## Backend Requirements

1. **API Server** (Flask/FastAPI)
   - Serve enriched product data
   - Handle similarity search queries
   - Process style-related queries

2. **Vector Search**
   - Load embeddings from `embeddings.pkl`
   - Cosine similarity search
   - Filter by style attributes

3. **Query Processing**
   - Parse user queries
   - Extract style intent
   - Return matching products

## Next Steps

1. Create backend API server
2. Create Chrome extension structure
3. Connect extension to API
4. Implement chat UI
5. Add similarity search

