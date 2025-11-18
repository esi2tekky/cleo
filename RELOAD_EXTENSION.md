# How to Reload the Extension After Changes

After updating the extension code, you need to reload it in Chrome:

## Quick Steps

1. **Go to Chrome Extensions**
   - Open: `chrome://extensions/`
   - Or: Chrome menu → Extensions → Manage Extensions

2. **Find Your Extension**
   - Look for "COS Shopping Assistant"

3. **Click the Reload Icon** 🔄
   - Click the circular arrow icon under your extension
   - This reloads the extension with the latest code

4. **Test Again**
   - Click the extension icon to open side panel
   - Try a query

## Alternative: Remove and Re-add

If reload doesn't work:

1. Click "Remove" on the extension
2. Click "Load unpacked" again
3. Select the `extension/` folder

## Why This Happens

Chrome caches extension files. When you update:
- `sidepanel.js`
- `sidepanel.html`
- `styles.css`
- `manifest.json`

You need to reload the extension for changes to take effect.

## Pro Tip

Enable "Developer mode" and keep the extensions page open while developing. Then you can quickly reload after each change.

