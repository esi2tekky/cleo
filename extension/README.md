# Chrome Extension - Shopping Assistant

## Setup

### 1. Start the Backend API

```bash
# From project root
cd backend
pip install -r requirements.txt
python app.py
```

The API will run on `http://localhost:5001`

### 2. Load the Extension

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `extension/` folder
5. The extension icon should appear in your toolbar

### 3. Use the Extension

- Click the extension icon to open the side panel
- Start chatting! Try queries like:
  - "Show me minimalist black sweaters"
  - "What colors go with beige?"
  - "Find wool items under $200"

## Features

- ✅ Natural language queries
- ✅ Style-based product search
- ✅ Color matching suggestions
- ✅ Visual product cards with images
- ✅ Direct links to product pages

## Development

### File Structure

```
extension/
├── manifest.json      # Extension configuration
├── sidepanel.html     # Chat UI
├── sidepanel.js       # Frontend logic
├── background.js      # Service worker
├── styles.css         # Styling
└── icons/            # Extension icons (create these)
```

### Icons

Create simple icons (16x16, 48x48, 128x128) or use placeholder images for now.

## API Endpoints

- `GET /api/health` - Health check
- `GET /api/products` - Get all products (with filters)
- `POST /api/search` - Semantic similarity search
- `POST /api/query` - Natural language query handler
- `GET /api/color-matches` - Get color matching suggestions

