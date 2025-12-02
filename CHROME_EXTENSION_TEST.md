# Chrome Extension Testing Guide

## Quick Start

### 1. Start the Backend Server

Make sure the backend is running:

```bash
cd /Users/esi/Documents/cleo
python3 backend/app.py
```

You should see:
- ✅ Loaded 821 products
- ✅ OpenAI embedder initialized
- ✅ Pinecone index 'cos-products' connected
- 📡 Server will run on http://localhost:5001

### 2. Load Extension in Chrome

1. Open Chrome and go to `chrome://extensions/`
2. Enable **"Developer mode"** (toggle in top right)
3. Click **"Load unpacked"**
4. Navigate to and select: `/Users/esi/Documents/cleo/extension`
5. The extension should appear in your extensions list

### 3. Open the Side Panel

1. Click the extension icon in Chrome toolbar
2. The side panel should open with the chat interface
3. You should see a welcome message

### 4. Test Queries

Try these queries to test different features:

**Simple queries:**
- "black sweater"
- "wool items under $200"

**Situational queries:**
- "sweater for a cool winter day in california"
- "night out in paris"
- "casual day outfit"

**Follow-up queries:**
- First: "black sweater"
- Then: "show me more like that"
- Or: "what goes with that"

**Compatibility queries:**
- "what goes with black sweater"
- "what matches this"

**Image upload (optional):**
- Click "📷 Upload Image"
- Select an image
- Then search with text + image

## Troubleshooting

### Backend not connecting
- Check backend is running: `curl http://localhost:5001/api/health`
- Check console for errors (F12 in Chrome)

### Extension not loading
- Check manifest.json is valid
- Check all files exist in extension/ directory
- Look for errors in chrome://extensions/ page

### No results
- Check backend logs for errors
- Verify Pinecone has embeddings: Check health endpoint
- Try a simpler query first

## Features to Test

✅ Text queries with OpenAI embeddings
✅ Situational queries (weather, location, occasion)
✅ Conversation memory (follow-up queries)
✅ Compatibility matching
✅ Image upload (optional)
✅ Pinecone vector search


