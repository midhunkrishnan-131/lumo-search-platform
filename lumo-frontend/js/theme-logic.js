/**
 * Pure theme resolution logic for LUMO.
 * Decoupled from DOM so it can be unit-tested deterministically.
 */

export const THEME_STORAGE_KEY = 'lumo_theme_preference';
export const VALID_THEMES = Object.freeze(['system', 'light', 'dark']);

/**
 * Normalizes a persisted or user-supplied theme value.
 * Defaults to 'system' for first-time visitors or invalid values.
 *
 * @param {string | null | undefined} value
 * @returns {'system' | 'light' | 'dark'}
 */
export function normalizeThemePreference(value) {
  if (value === 'light' || value === 'dark' || value === 'system') {
    return value;
  }
  return 'system';
}

/**
 * Resolves the effective visual palette ('light' | 'dark') from a user preference
 * and the current operating system color-scheme preference.
 *
 * @param {'system' | 'light' | 'dark'} preference
 * @param {boolean} systemPrefersDark
 * @returns {'light' | 'dark'}
 */
export function resolveAppliedTheme(preference, systemPrefersDark) {
  const normalized = normalizeThemePreference(preference);
  if (normalized === 'light') return 'light';
  if (normalized === 'dark') return 'dark';
  return systemPrefersDark ? 'dark' : 'light';
}
