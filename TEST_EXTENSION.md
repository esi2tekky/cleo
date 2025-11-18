# Testing the Chrome Extension - Step by Step

## Step 1: Start the Backend Server

Open Terminal and run:

```bash
cd /Users/chloemurdoch/Desktop/cleo/backend
pip install -r requirements.txt
python app.py
```

You should see:
```
✅ Loaded 19 products
✅ Loaded embeddings
🚀 Starting Shopping Assistant API...
📡 Server will run on http://localhost:5001
 * Running on http://0.0.0.0:5001
```

**Keep this terminal open!** The server needs to keep running.

## Step 2: Verify Backend is Working

Open a **new terminal** and test:

```bash
curl http://localhost:5001/api/health
```

You should get a JSON response with status "healthy".

Or run the test script:
```bash
cd /Users/chloemurdoch/Desktop/cleo/backend
python test_api.py
```

## Step 3: Load the Extension in Chrome

1. **Open Chrome** and go to: `chrome://extensions/`

2. **Enable Developer Mode**
   - Toggle the switch in the top-right corner

3. **Load the Extension**
   - Click **"Load unpacked"** button
   - Navigate to: `/Users/chloemurdoch/Desktop/cleo/extension`
   - Click "Select" or "Open"

4. **Verify it Loaded**
   - You should see "COS Shopping Assistant" in the extensions list
   - The extension icon should appear in your Chrome toolbar

## Step 4: Open the Extension

1. **Click the extension icon** in your Chrome toolbar
2. The **side panel** should open on the right side
3. You should see the chat interface with a welcome message

## Step 5: Test Queries

Try these queries one by one:

1. **"Show me minimalist black sweaters"**
   - Should return products matching this style

2. **"Find wool items under $200"**
   - Should filter by material and price

3. **"What colors go with beige?"**
   - Should show color matching suggestions

4. **"Show me casual oversized sweaters"**
   - Should use style keywords

## Troubleshooting

### Backend won't start?
- Check if port 5000 is already in use
- Make sure you're in the `backend/` directory
- Verify dependencies: `pip install -r requirements.txt`

### Extension won't load?
- Check `chrome://extensions/` for error messages (red text)
- Make sure you selected the `extension/` folder (not a subfolder)
- Check browser console (F12) for JavaScript errors

### "Backend not available" message?
- Make sure backend is running (Step 1)
- Check: `curl http://localhost:5000/api/health`
- Verify CORS is enabled (it should be by default)

### No search results?
- Check backend terminal for errors
- Verify enriched data exists: `ls data/processed/enriched_*.csv`
- Test API directly: `python backend/test_api.py`

## What to Look For

✅ **Working correctly:**
- Backend shows "Running on http://0.0.0.0:5000"
- Extension loads without errors
- Side panel opens when clicking icon
- Queries return product results
- Product cards show images and details

❌ **Issues:**
- Backend errors in terminal
- Extension shows "Backend not available"
- No results for valid queries
- JavaScript errors in console

## Next Steps After Testing

Once it's working:
1. Try more complex queries
2. Test color matching features
3. Customize the styling
4. Add more features (favorites, history, etc.)

