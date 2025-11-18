// Background service worker for Chrome extension

// Open side panel when extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ windowId: tab.windowId });
});

// Optional: Auto-open side panel on shopping websites
chrome.tabs.onUpdated.addListener((tabId, info, tab) => {
    if (info.status === 'complete' && tab.url && tab.url.includes('cos.com')) {
        // Could auto-open side panel here if desired
        // chrome.sidePanel.open({ windowId: tab.windowId });
    }
});

