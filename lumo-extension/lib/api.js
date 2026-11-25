/**
 * LUMO Browser Companion — Local Backend API Client & Settings Store
 * Communicates strictly with the user's configured local LUMO FastAPI backend.
 */

export const DEFAULT_SETTINGS = Object.freeze({
  backendUrl: 'http://127.0.0.1:8000',
  frontendUrl: 'http://127.0.0.1:3000',
  theme: 'system',
  defaultCollectionId: '',
  captureDescription: true,
  captureSelection: true,
});

const REQUEST_TIMEOUT_MS = 8000;

export function isValidHttpUrl(rawUrl) {
  try {
    const parsed = new URL(rawUrl);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export async function getExtensionSettings() {
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.get(DEFAULT_SETTINGS, (items) => {
        resolve({ ...DEFAULT_SETTINGS, ...items });
      });
    });
  }
  return { ...DEFAULT_SETTINGS };
}

export async function saveExtensionSettings(partial) {
  const clean = { ...partial };
  if (clean.backendUrl) {
    clean.backendUrl = clean.backendUrl.trim().replace(/\/+$/, '');
  }
  if (clean.frontendUrl) {
    clean.frontendUrl = clean.frontendUrl.trim().replace(/\/+$/, '');
  }
  if (typeof chrome !== 'undefined' && chrome.storage && chrome.storage.local) {
    return new Promise((resolve) => {
      chrome.storage.local.set(clean, () => resolve(clean));
    });
  }
  return clean;
}

async function requestBackend(path, options = {}) {
  const settings = await getExtensionSettings();
  const baseUrl = (settings.backendUrl || DEFAULT_SETTINGS.backendUrl).replace(/\/+$/, '');
  if (!isValidHttpUrl(baseUrl)) {
    throw new Error('Invalid LUMO backend URL in extension settings.');
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs || REQUEST_TIMEOUT_MS);

  try {
    const resp = await fetch(`${baseUrl}${path}`, {
      method: options.method || 'GET',
      headers: {
        Accept: 'application/json',
        ...(options.body ? { 'Content-Type': 'application/json' } : {}),
      },
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });

    if (!resp.ok) {
      let detail = `HTTP ${resp.status}`;
      try {
        const err = await resp.json();
        if (err && err.detail) detail = err.detail;
      } catch {}
      throw new Error(detail);
    }

    if (resp.status === 204) return null;
    return await resp.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new Error('Connection to local LUMO backend timed out.');
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

export async function checkExtensionBackendHealth() {
  return await requestBackend('/api/v1/extension/health', { timeoutMs: 4000 });
}

export async function getPageStatus(pageUrl) {
  const qs = pageUrl ? `?url=${encodeURIComponent(pageUrl)}` : '';
  return await requestBackend(`/api/v1/extension/status${qs}`);
}

export async function savePageToLumo(payload) {
  return await requestBackend('/api/v1/extension/save-page', {
    method: 'POST',
    body: payload,
  });
}

export async function saveSelectionToLumo(payload) {
  return await requestBackend('/api/v1/extension/save-selection', {
    method: 'POST',
    body: payload,
  });
}

export async function searchWorkspaceFromExtension(query, mode = 'hybrid', limit = 8) {
  const qs = new URLSearchParams({
    q: query,
    mode,
    limit: String(limit),
  });
  return await requestBackend(`/api/v1/extension/search?${qs.toString()}`);
}
