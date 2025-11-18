# Troubleshooting Connection Issues

## Backend is Running but Extension Can't Connect

### Step 1: Check Browser Console

1. Open the extension side panel
2. Press **F12** (or right-click → Inspect)
3. Go to **Console** tab
4. Look for error messages

Common errors:
- `Failed to fetch` - Network/CORS issue
- `CORS policy` - CORS configuration issue
- `ERR_CONNECTION_REFUSED` - Backend not running
- `ERR_BLOCKED_BY_CLIENT` - Extension permission issue

### Step 2: Verify Backend is Accessible

In terminal, test:
```bash
curl http://localhost:5001/api/health
```

Should return:
```json
{"status":"healthy","products_loaded":19,"embeddings_loaded":32}
```

### Step 3: Check Extension Permissions

1. Go to `chrome://extensions/`
2. Find "COS Shopping Assistant"
3. Click "Details"
4. Check "Host permissions" includes:
   - `http://localhost:5001/*`
   - `http://127.0.0.1:5001/*`

### Step 4: Reload Extension

After any changes to `manifest.json`:
1. Go to `chrome://extensions/`
2. Click **Reload** on your extension
3. Try again

### Step 5: Try 127.0.0.1 Instead

If `localhost` doesn't work, try using `127.0.0.1`:

Edit `extension/sidepanel.js`:
```javascript
const API_BASE_URL = 'http://127.0.0.1:5001/api';
```

Then reload the extension.

### Step 6: Check Firewall/Antivirus

Some security software blocks localhost connections. Try:
- Temporarily disabling firewall
- Adding exception for port 5001
- Checking antivirus settings

### Step 7: Test in Different Browser

Try loading as a regular web page to isolate extension issues:
1. Open `http://localhost:5001/api/health` in Chrome
2. Should show JSON response
3. If this works, it's an extension permission issue

## Common Solutions

### Solution 1: Update Manifest Permissions

Make sure `manifest.json` has:
```json
"host_permissions": [
  "http://localhost:5001/*",
  "http://127.0.0.1:5001/*"
]
```

### Solution 2: Use 127.0.0.1

Some systems have issues with `localhost`. Use `127.0.0.1` instead.

### Solution 3: Check CORS

Backend should have:
```python
from flask_cors import CORS
CORS(app)
```

### Solution 4: Verify Port

Make sure backend is actually on port 5001:
```bash
lsof -i :5001
```

Should show Python process.

## Still Not Working?

1. **Check backend logs** - Look at terminal running `python app.py`
2. **Check browser console** - F12 → Console tab
3. **Test API directly** - `curl http://localhost:5001/api/health`
4. **Try different port** - Change to 5002 or 8000

