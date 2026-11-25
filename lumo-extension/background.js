/**
 * LUMO Browser Companion — Manifest V3 Service Worker
 * Registers explicit user-triggered context menu actions and executes
 * minimal, read-only metadata extraction on the active tab.
 */

import {
  getExtensionSettings,
  isValidHttpUrl,
  savePageToLumo,
  saveSelectionToLumo,
} from './lib/api.js';

const MENU_SAVE_PAGE = 'lumo-save-page';
const MENU_SAVE_SELECTION = 'lumo-save-selection';

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({
      id: MENU_SAVE_PAGE,
      title: 'Save page to LUMO',
      contexts: ['page'],
    });
    chrome.contextMenus.create({
      id: MENU_SAVE_SELECTION,
      title: 'Save selection to LUMO',
      contexts: ['selection'],
    });
  });
});

/**
 * Safely extract only public page metadata (never inputs, passwords, cookies, or tokens).
 */
function extractSafePageMetadata() {
  const descEl =
    document.querySelector('meta[name="description"]') ||
    document.querySelector('meta[property="og:description"]');
  const canonicalEl = document.querySelector('link[rel="canonical"]');
  const iconEl =
    document.querySelector('link[rel="icon"]') ||
    document.querySelector('link[rel="shortcut icon"]');
  const selection = window.getSelection ? window.getSelection().toString().trim() : '';

  return {
    title: document.title || location.hostname,
    url: location.href,
    description: descEl ? (descEl.getAttribute('content') || '').trim() : '',
    canonicalUrl: canonicalEl ? canonicalEl.getAttribute('href') || '' : '',
    faviconUrl: iconEl ? iconEl.href || '' : '',
    selectedText: selection.slice(0, 20000),
  };
}

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (!tab || !tab.id || !tab.url || !isValidHttpUrl(tab.url)) {
    return;
  }

  const settings = await getExtensionSettings();

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractSafePageMetadata,
    });
    const meta = (results && results[0] && results[0].result) || {
      title: tab.title || tab.url,
      url: tab.url,
      description: '',
      canonicalUrl: '',
      faviconUrl: '',
      selectedText: info.selectionText || '',
    };

    if (info.menuItemId === MENU_SAVE_SELECTION) {
      const selected = (info.selectionText || meta.selectedText || '').trim();
      if (!selected) return;
      await saveSelectionToLumo({
        url: meta.url,
        title: meta.title,
        selected_text: selected,
        collection_id: settings.defaultCollectionId || null,
        tags: ['extension-clip'],
      });
    } else if (info.menuItemId === MENU_SAVE_PAGE) {
      await savePageToLumo({
        url: meta.url,
        title: meta.title,
        description: settings.captureDescription ? meta.description : null,
        canonical_url: meta.canonicalUrl || null,
        favicon_url: meta.faviconUrl || null,
        selected_text: settings.captureSelection ? meta.selectedText : null,
        collection_id: settings.defaultCollectionId || null,
        tags: ['extension-page'],
      });
    }
  } catch (err) {
    console.warn('LUMO context menu save failed:', err);
  }
});
