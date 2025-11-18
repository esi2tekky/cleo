# Chrome Extension Setup Guide

## ✅ Yes, Chrome Extension is Feasible!

I've created a complete Chrome extension setup for your shopping assistant chatbot.

## What's Been Created

### Backend API (`backend/`)
- **`app.py`** - Flask API server with endpoints for:
  - Product search
  - Semantic similarity search
  - Natural language queries
  - Color matching suggestions
- **`requirements.txt`** - Backend dependencies
- **`test_api.py`** - Test script to verify API works

### Chrome Extension (`extension/`)
- **`manifest.json`** - Extension configuration (Manifest V3)
- **`sidepanel.html`** - Chat UI interface
- **`sidepanel.js`** - Frontend JavaScript logic
- **`background.js`** - Service worker
- **`styles.css`** - Modern, clean styling
- **`icons/`** - Extension icons (created)

## Quick Start

### 1. Start Backend (Terminal 1)

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

### 2. Load Extension (Chrome)

1. Open Chrome → Go to `chrome://extensions/`
2. Enable **"Developer mode"** (toggle in top right)
3. Click **"Load unpacked"**
4. Navigate to and select the `extension/` folder
5. Extension should appear in your toolbar ✅

### 3. Test It!

1. Click the extension icon in Chrome toolbar
2. Side panel opens with chat interface
3. Try these queries:
   - "Show me minimalist black sweaters"
   - "What colors go with beige?"
   - "Find wool items under $200"
   - "Show me casual oversized sweaters"

## Features

### ✅ What Works Now

- **Natural Language Queries** - Ask in plain English
- **Semantic Search** - Uses text embeddings for style queries
- **Attribute Filtering** - Filters by color, material, price, style
- **Color Matching** - Shows complementary, neutral, and monochrome colors
- **Product Cards** - Beautiful cards with images and details
- **Direct Links** - Click to view products on COS website

### 🎨 UI Features

- Modern gradient header
- Chat-style message bubbles
- Product cards with images
- Loading indicators
- Smooth animations
- Responsive design

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/products` | GET | Get all products (with filters) |
| `/api/search` | POST | Semantic similarity search |
| `/api/query` | POST | Natural language query handler |
| `/api/color-matches` | GET | Color compatibility suggestions |

## Example Queries

- **Style queries**: "minimalist black sweater", "casual oversized"
- **Material queries**: "wool items", "cashmere sweaters"
- **Color queries**: "beige cardigans", "navy blue items"
- **Price queries**: "items under $200", "sweaters under $150"
- **Combined**: "minimalist black wool sweater under $200"

## Architecture

```
┌─────────────────┐
│ Chrome Extension│
│  (Side Panel)   │
└────────┬────────┘
         │ HTTP Requests
         ↓
┌─────────────────┐
│  Flask API      │
│  (localhost:   │
│   5000)         │
└────────┬────────┘
         │
         ↓
┌─────────────────┐
│ Enriched Data   │
│ + Embeddings    │
└─────────────────┘
```

## File Structure

```
cleo/
├── backend/
│   ├── app.py              # Flask API server
│   ├── requirements.txt    # Backend deps
│   └── test_api.py         # API test script
├── extension/
│   ├── manifest.json       # Extension config
│   ├── sidepanel.html      # Chat UI
│   ├── sidepanel.js        # Frontend logic
│   ├── background.js       # Service worker
│   ├── styles.css          # Styling
│   └── icons/              # Extension icons
└── data/processed/
    ├── enriched_*.csv      # Enriched product data
    └── embeddings.pkl      # Visual & text embeddings
```

## Testing

### Test Backend API

```bash
cd backend
python test_api.py
```

### Test in Browser

1. Open Chrome DevTools (F12)
2. Go to Console tab
3. Check for any JavaScript errors
4. Check Network tab for API requests

## Customization

### Change API URL

Edit `extension/sidepanel.js`:
```javascript
const API_BASE_URL = 'http://localhost:5001/api';
```

### Change Styling

Edit `extension/styles.css` - colors, fonts, layout, etc.

### Add Features

- Save favorite products
- Query history
- Product comparisons
- Style recommendations

## Troubleshooting

### Extension won't load
- Check `chrome://extensions/` for errors
- Verify all files are in `extension/` folder
- Make sure `manifest.json` is valid JSON

### Backend not connecting
- Verify backend is running: `curl http://localhost:5000/api/health`
- Check CORS is enabled (it is by default)
- Check browser console for errors

### No search results
- Verify enriched data exists: `ls data/processed/enriched_*.csv`
- Check backend logs for errors
- Test API directly: `python backend/test_api.py`

## Next Steps

1. ✅ **Test the extension** - Make sure everything works
2. 🎨 **Customize design** - Adjust colors, fonts, layout
3. 🚀 **Deploy backend** - Host on Heroku, Railway, or similar
4. 📦 **Publish extension** - Submit to Chrome Web Store (optional)
5. 🔧 **Add features** - Favorites, history, comparisons

## Production Considerations

### Backend Deployment
- Use production WSGI server (gunicorn, uvicorn)
- Add authentication if needed
- Use environment variables for config
- Set up proper CORS for your domain

### Extension Distribution
- Create proper icons (replace placeholders)
- Add extension description
- Prepare screenshots for Chrome Web Store
- Set up auto-updates

## Support

- Backend API: `backend/app.py`
- Extension: `extension/` folder
- Documentation: `CHROME_EXTENSION.md`, `QUICK_START_EXTENSION.md`

