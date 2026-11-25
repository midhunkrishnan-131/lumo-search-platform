/**
 * Centralized user preference store for LUMO.
 * Uses localStorage safely with sensible defaults.
 */

const PREFS_STORAGE_KEY = 'lumo_preferences_v1';

export const DEFAULT_PREFERENCES = Object.freeze({
  defaultSearchMode: 'hybrid',
  showSuggestions: true,
  resultsPerPage: 8,
  language: 'en',
  compactDensity: false,
  reducedMotion: false,
  apiBaseUrl: '',
});

const VALID_MODES = new Set(['classic', 'semantic', 'hybrid']);
const VALID_PAGE_SIZES = new Set([5, 8, 10, 20]);
const VALID_LANGUAGES = new Set(['en', 'en-GB', 'de', 'fr', 'es']);

export function getPreferences() {
  try {
    const raw = window.localStorage.getItem(PREFS_STORAGE_KEY);
    if (!raw) return { ...DEFAULT_PREFERENCES };
    const parsed = JSON.parse(raw);
    return {
      defaultSearchMode: VALID_MODES.has(parsed.defaultSearchMode)
        ? parsed.defaultSearchMode
        : DEFAULT_PREFERENCES.defaultSearchMode,
      showSuggestions:
        typeof parsed.showSuggestions === 'boolean'
          ? parsed.showSuggestions
          : DEFAULT_PREFERENCES.showSuggestions,
      resultsPerPage: VALID_PAGE_SIZES.has(Number(parsed.resultsPerPage))
        ? Number(parsed.resultsPerPage)
        : DEFAULT_PREFERENCES.resultsPerPage,
      language: VALID_LANGUAGES.has(parsed.language)
        ? parsed.language
        : DEFAULT_PREFERENCES.language,
      compactDensity: Boolean(parsed.compactDensity),
      reducedMotion: Boolean(parsed.reducedMotion),
      apiBaseUrl:
        typeof parsed.apiBaseUrl === 'string'
          ? parsed.apiBaseUrl.trim().replace(/\/+$/, '')
          : '',
    };
  } catch {
    return { ...DEFAULT_PREFERENCES };
  }
}

export function savePreferences(partial) {
  const next = {
    ...getPreferences(),
    ...partial,
  };
  if (typeof next.apiBaseUrl === 'string') {
    next.apiBaseUrl = next.apiBaseUrl.trim().replace(/\/+$/, '');
  }
  try {
    window.localStorage.setItem(PREFS_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Ignore storage quota / private mode failures gracefully.
  }
  applyInterfacePreferences(next);
  window.dispatchEvent(new CustomEvent('lumo:preferences-changed', { detail: next }));
  return next;
}

export function resetPreferences() {
  try {
    window.localStorage.removeItem(PREFS_STORAGE_KEY);
  } catch {
    // Ignore storage errors.
  }
  applyInterfacePreferences(DEFAULT_PREFERENCES);
  window.dispatchEvent(
    new CustomEvent('lumo:preferences-changed', { detail: { ...DEFAULT_PREFERENCES } })
  );
  return { ...DEFAULT_PREFERENCES };
}

export function applyInterfacePreferences(prefs = getPreferences()) {
  const root = document.documentElement;
  if (prefs.compactDensity) {
    root.dataset.density = 'compact';
  } else {
    delete root.dataset.density;
  }
  if (prefs.reducedMotion) {
    root.dataset.reducedMotion = 'true';
  } else {
    delete root.dataset.reducedMotion;
  }
  if (prefs.language) {
    root.lang = prefs.language;
  }
}
