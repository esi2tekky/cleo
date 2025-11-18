# Next Steps: Test Your Extension

## ✅ Quick Test Checklist

### 1. Start Backend (Terminal 1)

**Option A: Use the script**
```bash
cd /Users/chloemurdoch/Desktop/cleo
./start_backend.sh
```

**Option B: Manual**
```bash
cd /Users/chloemurdoch/Desktop/cleo/backend
python app.py
```

**Expected output:**
```
✅ Loaded 19 products
✅ Loaded 32 embeddings
✅ Enricher initialized
🚀 Starting Shopping Assistant API...
📡 Server will run on http://localhost:5001
 * Running on http://0.0.0.0:5001
```

**Keep this terminal open!** The server must keep running.

---

### 2. Load Extension in Chrome

1. Open Chrome
2. Go to: `chrome://extensions/`
3. **Enable "Developer mode"** (top-right toggle)
4. Click **"Load unpacked"**
5. Navigate to: `/Users/chloemurdoch/Desktop/cleo/extension`
6. Click "Select"

**You should see:**
- "COS Shopping Assistant" in the extensions list
- Extension icon in Chrome toolbar (purple "C" icon)

---

### 3. Open Extension

1. **Click the extension icon** in Chrome toolbar
2. **Side panel opens** on the right
3. You should see the chat interface

---

### 4. Test Queries

Type these in the chat and press Enter:

**Test 1: Style Query**
```
Show me minimalist black sweaters
```

**Test 2: Material + Price**
```
Find wool items under $200
```

**Test 3: Color Query**
```
Show me beige cardigans
```

**Test 4: Style Keywords**
```
Find casual oversized sweaters
```

---

## 🎯 What Should Happen

✅ **Backend:**
- Terminal shows "Running on http://0.0.0.0:5001"
- No error messages

✅ **Extension:**
- Loads without errors in `chrome://extensions/`
- Side panel opens when clicking icon
- Welcome message appears

✅ **Queries:**
- Results appear in chat
- Product cards show with images
- Colors, materials, prices visible
- "View Product →" links work

---

## 🐛 Troubleshooting

### Backend Issues

**"Port 5000 already in use"**
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9
# Then restart backend
```

**"Module not found"**
```bash
cd backend
pip install -r requirements.txt
```

**"No products loaded"**
- Check: `ls data/processed/enriched_*.csv`
- Make sure enriched data exists

### Extension Issues

**Extension won't load**
- Check `chrome://extensions/` for red error messages
- Make sure you selected the `extension/` folder (not a subfolder)
- Verify `manifest.json` exists

**"Backend not available"**
- Make sure backend is running (Step 1)
- Test: `curl http://localhost:5001/api/health`
- Check browser console (F12) for errors

**No search results**
- Check backend terminal for errors
- Test API: `python backend/test_api.py`
- Verify query makes sense (try "wool" or "black")

---

## 📸 Visual Guide

### Step 1: Backend Running
```
Terminal shows:
✅ Loaded 19 products
✅ Loaded 32 embeddings
🚀 Starting Shopping Assistant API...
 * Running on http://0.0.0.0:5000
```

### Step 2: Extension Loaded
```
chrome://extensions/ shows:
┌─────────────────────────────┐
│ COS Shopping Assistant      │
│ Version 1.0.0               │
│ ✅ Enabled                  │
└─────────────────────────────┘
```

### Step 3: Side Panel Open
```
Right side of Chrome shows:
┌─────────────────────┐
│ 🛍️ COS Shopping     │
│    Assistant        │
│                     │
│ 👋 Hi! I'm your...  │
│                     │
│ [Type query here]   │
│ [Send]              │
└─────────────────────┘
```

---

## 🎉 Success Indicators

You'll know it's working when:

1. ✅ Backend terminal shows "Running"
2. ✅ Extension icon appears in toolbar
3. ✅ Side panel opens with chat UI
4. ✅ Queries return product results
5. ✅ Product cards show images and details
6. ✅ Links to COS website work

---

## 🚀 After Testing

Once everything works:

1. **Try more queries** - Experiment with different styles
2. **Test color matching** - Ask "What colors go with beige?"
3. **Customize styling** - Edit `extension/styles.css`
4. **Add features** - Favorites, history, etc.

---

## 📚 Need Help?

- **Backend errors?** Check `backend/app.py` logs
- **Extension errors?** Check Chrome DevTools (F12) → Console
- **API issues?** Test with: `python backend/test_api.py`
- **Data issues?** Verify: `ls data/processed/enriched_*.csv`

