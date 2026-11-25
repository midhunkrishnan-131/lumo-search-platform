/**
 * LUMO Theme Controller
 * Manages System, Light, and Dark modes with live OS media-query sync
 * and localStorage persistence.
 */

import {
  THEME_STORAGE_KEY,
  normalizeThemePreference,
  resolveAppliedTheme,
} from './theme-logic.js';

let mediaQuery = null;
let currentPreference = 'system';

export function getThemePreference() {
  try {
    return normalizeThemePreference(window.localStorage.getItem(THEME_STORAGE_KEY));
  } catch {
    return 'system';
  }
}

export function getAppliedTheme(preference = currentPreference) {
  const prefersDark =
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches;
  return resolveAppliedTheme(preference, prefersDark);
}

export function applyTheme(preference, { persist = false } = {}) {
  currentPreference = normalizeThemePreference(preference);

  if (persist) {
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, currentPreference);
    } catch {
      // Ignore storage failures in restricted contexts.
    }
  }

  const applied = getAppliedTheme(currentPreference);
  document.documentElement.setAttribute('data-theme', applied);
  document.documentElement.setAttribute('data-theme-preference', currentPreference);

  syncThemeControls();

  window.dispatchEvent(
    new CustomEvent('lumo:theme-changed', {
      detail: { preference: currentPreference, applied },
    })
  );

  return applied;
}

export function syncThemeControls() {
  const buttons = document.querySelectorAll('[data-theme-option]');
  buttons.forEach((button) => {
    const opt = button.getAttribute('data-theme-option');
    const isSelected = opt === currentPreference;
    button.setAttribute('aria-pressed', String(isSelected));
    button.classList.toggle('is-active', isSelected);
  });

  const statusEls = document.querySelectorAll('[data-theme-status]');
  const applied = getAppliedTheme(currentPreference);
  const labelMap = {
    system: `System (${applied === 'dark' ? 'Dark' : 'Light'})`,
    light: 'Light',
    dark: 'Dark',
  };
  statusEls.forEach((el) => {
    el.textContent = labelMap[currentPreference];
  });
}

export function initThemeSystem() {
  currentPreference = getThemePreference();
  applyTheme(currentPreference, { persist: false });

  if (typeof window.matchMedia === 'function') {
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleOsThemeChange = () => {
      if (currentPreference === 'system') {
        applyTheme('system', { persist: false });
      }
    };
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleOsThemeChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleOsThemeChange);
    }
  }

  document.addEventListener('click', (event) => {
    const trigger = event.target.closest('[data-theme-option]');
    if (!trigger) return;
    const option = trigger.getAttribute('data-theme-option');
    applyTheme(option, { persist: true });
  });

  window.addEventListener('storage', (event) => {
    if (event.key === THEME_STORAGE_KEY) {
      applyTheme(getThemePreference(), { persist: false });
    }
  });
}
