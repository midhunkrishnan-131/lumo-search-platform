/**
 * LUMO Browser Companion — Popup Controller
 */

import {
  checkExtensionBackendHealth,
  escapeHtml,
  getExtensionSettings,
  getPageStatus,
  isValidHttpUrl,
  savePageToLumo,
  saveSelectionToLumo,
  searchWorkspaceFromExtension,
} from './lib/api.js';

const connStatusEl = document.getElementById('conn-status');
const pageTitleEl = document.getElementById('page-title');
const pageUrlEl = document.getElementById('page-url');
const savedBadgeEl = document.getElementById('saved-badge');
const collectionSelect = document.getElementById('collection-select');
const tagsInput = document.getElementById('tags-input');
const noteInput = document.getElementById('note-input');
const savePageBtn = document.getElementById('save-page-btn');
const saveSelectionBtn = document.getElementById('save-selection-btn');
const openLumoBtn = document.getElementById('open-lumo-btn');
const saveFeedbackEl = document.getElementById('save-feedback');
const searchForm = document.getElementById('search-form');
const searchInput = document.getElementById('search-input');
const searchResultsEl = document.getElementById('search-results');
const openOptionsBtn = document.getElementById('open-options-btn');

const state = {
  settings: null,
  tabMeta: {
    title: '',
    url: '',
    description: '',
    canonicalUrl: '',
    faviconUrl: '',
    selectedText: '',
  },
  savedItemId: null,
};

function extractTabMetadataInPage() {
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

async function initPopup() {
  state.settings = await getExtensionSettings();
  document.documentElement.setAttribute('data-theme', state.settings.theme || 'system');

  // 1. Inspect active browser tab
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (tab && tab.url && isValidHttpUrl(tab.url)) {
    state.tabMeta.title = tab.title || tab.url;
    state.tabMeta.url = tab.url;
    try {
      const res = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: extractTabMetadataInPage,
      });
      if (res && res[0] && res[0].result) {
        state.tabMeta = res[0].result;
      }
    } catch {
      // Fallback to tab.title / tab.url on restricted pages
    }
    pageTitleEl.textContent = state.tabMeta.title;
    pageUrlEl.textContent = state.tabMeta.url;
    if (state.tabMeta.selectedText) {
      saveSelectionBtn.disabled = false;
      saveSelectionBtn.title = `Save ${state.tabMeta.selectedText.length} selected chars`;
    }
  } else {
    pageTitleEl.textContent = 'Unsupported page';
    pageUrlEl.textContent = 'Only http:// and https:// pages can be saved.';
    savePageBtn.disabled = true;
    saveSelectionBtn.disabled = true;
  }

  // 2. Check backend health & page saved status
  try {
    await checkExtensionBackendHealth();
    connStatusEl.textContent = 'Connected';
    connStatusEl.className = 'status-pill status-pill--ok';

    const status = await getPageStatus(state.tabMeta.url);
    collectionSelect.innerHTML =
      '<option value="">No collection</option>' +
      (status.collections || [])
        .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`)
        .join('');

    if (status.already_saved) {
      state.savedItemId = status.item_id;
      savedBadgeEl.textContent = 'Already in Workspace';
      savedBadgeEl.className = 'badge badge--saved';
      if (status.collection_id) collectionSelect.value = status.collection_id;
    } else {
      savedBadgeEl.textContent = 'Not saved yet';
      savedBadgeEl.className = 'badge';
      if (state.settings.defaultCollectionId) {
        collectionSelect.value = state.settings.defaultCollectionId;
      }
    }
  } catch (err) {
    connStatusEl.textContent = 'Offline';
    connStatusEl.className = 'status-pill status-pill--err';
    savedBadgeEl.textContent = 'Backend unreachable';
    saveFeedbackEl.textContent = `Cannot reach ${state.settings.backendUrl}: ${err.message}`;
  }
}

function parseTags() {
  return (tagsInput.value || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean);
}

savePageBtn.addEventListener('click', async () => {
  savePageBtn.disabled = true;
  saveFeedbackEl.textContent = 'Saving page to LUMO...';
  try {
    const res = await savePageToLumo({
      url: state.tabMeta.url,
      title: state.tabMeta.title,
      description: state.settings.captureDescription ? state.tabMeta.description : null,
      canonical_url: state.tabMeta.canonicalUrl || null,
      favicon_url: state.tabMeta.faviconUrl || null,
      selected_text: state.settings.captureSelection ? state.tabMeta.selectedText : null,
      note: noteInput.value.trim() || null,
      collection_id: collectionSelect.value || null,
      tags: parseTags(),
    });
    state.savedItemId = res.item.id;
    savedBadgeEl.textContent = res.is_duplicate ? 'Already in Workspace (updated)' : 'Saved to Workspace';
    savedBadgeEl.className = 'badge badge--saved';
    saveFeedbackEl.textContent = res.is_duplicate
      ? 'Page already exists in workspace; tags/notes updated.'
      : 'Page saved successfully.';
  } catch (err) {
    saveFeedbackEl.textContent = `Save failed: ${err.message}`;
  } finally {
    savePageBtn.disabled = false;
  }
});

saveSelectionBtn.addEventListener('click', async () => {
  if (!state.tabMeta.selectedText) return;
  saveSelectionBtn.disabled = true;
  saveFeedbackEl.textContent = 'Saving selection to LUMO...';
  try {
    const res = await saveSelectionToLumo({
      url: state.tabMeta.url,
      title: state.tabMeta.title,
      selected_text: state.tabMeta.selectedText,
      note: noteInput.value.trim() || null,
      collection_id: collectionSelect.value || null,
      tags: parseTags(),
    });
    state.savedItemId = res.item.id;
    saveFeedbackEl.textContent = 'Selected text saved to Workspace.';
  } catch (err) {
    saveFeedbackEl.textContent = `Selection save failed: ${err.message}`;
  } finally {
    saveSelectionBtn.disabled = false;
  }
});

openLumoBtn.addEventListener('click', () => {
  const base = (state.settings?.frontendUrl || 'http://127.0.0.1:3000').replace(/\/+$/, '');
  const url = state.savedItemId
    ? `${base}/workspace.html?item=${encodeURIComponent(state.savedItemId)}`
    : `${base}/workspace.html`;
  chrome.tabs.create({ url });
});

openOptionsBtn.addEventListener('click', () => {
  chrome.runtime.openOptionsPage();
});

searchForm.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const q = searchInput.value.trim();
  if (!q) return;
  searchResultsEl.innerHTML = '<div class="feedback">Searching workspace...</div>';
  try {
    const res = await searchWorkspaceFromExtension(q, 'hybrid', 8);
    if (!res.hits || res.hits.length === 0) {
      searchResultsEl.innerHTML = '<div class="feedback">No matching workspace items found.</div>';
      return;
    }
    searchResultsEl.innerHTML = res.hits
      .map(
        (h) => `
        <button type="button" class="result-item" data-open-ws-id="${escapeHtml(h.id)}" data-open-ws-kind="${escapeHtml(h.kind)}">
          <div class="result-item__title">${escapeHtml(h.title)}</div>
          <div class="result-item__snippet">${escapeHtml(h.kind)} · ${escapeHtml(h.snippet)}</div>
        </button>
      `
      )
      .join('');
  } catch (err) {
    searchResultsEl.innerHTML = `<div class="feedback">Search failed: ${escapeHtml(err.message)}</div>`;
  }
});

searchResultsEl.addEventListener('click', (ev) => {
  const btn = ev.target.closest('[data-open-ws-id]');
  if (!btn) return;
  const id = btn.getAttribute('data-open-ws-id');
  const kind = btn.getAttribute('data-open-ws-kind');
  const base = (state.settings?.frontendUrl || 'http://127.0.0.1:3000').replace(/\/+$/, '');
  const targetUrl = kind === 'item' ? `${base}/workspace.html?item=${encodeURIComponent(id)}` : `${base}/workspace.html`;
  chrome.tabs.create({ url: targetUrl });
});

initPopup();
