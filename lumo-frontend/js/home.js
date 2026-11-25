/**
 * LUMO Homepage Controller
 * Manages greeting, local date, central search experience, mode selection,
 * live suggestions, and deterministic Daily Discovery content.
 */

import { initShell } from './ui-shell.js';
import { getPreferences } from './preferences.js';
import { getDailyContent, getGreetingForHour } from './daily-content.js';
import {
  SEARCH_MODES,
  getSearchSuggestions,
  escapeHtml,
} from './search-data.js';

initShell({ activeModule: '', borderedHeader: false });

const prefs = getPreferences();
let selectedMode = prefs.defaultSearchMode || 'hybrid';
let activeSuggestionIndex = -1;
let currentSuggestions = [];

const greetingEl = document.getElementById('home-greeting');
const dateEl = document.getElementById('home-date');
const searchForm = document.getElementById('home-search-form');
const searchInput = document.getElementById('home-search-input');
const clearBtn = document.getElementById('home-search-clear');
const feedbackEl = document.getElementById('home-search-feedback');
const suggestionsPanel = document.getElementById('home-suggestions');
const modeButtons = Array.from(document.querySelectorAll('[data-search-mode]'));
const modeDescEl = document.getElementById('home-mode-description');
const quickPromptsEl = document.getElementById('home-quick-prompts');

function initGreetingAndDaily() {
  const now = new Date();
  const daily = getDailyContent(now);

  if (greetingEl) {
    greetingEl.textContent = getGreetingForHour(now.getHours());
  }
  if (dateEl) {
    dateEl.textContent = daily.formattedDate;
  }

  // Render Today's Special Day
  const specialKindEl = document.getElementById('daily-special-kind');
  const specialDateEl = document.getElementById('daily-special-date');
  const specialTitleEl = document.getElementById('daily-special-title');
  const specialDescEl = document.getElementById('daily-special-desc');
  const specialWhyEl = document.getElementById('daily-special-why');

  if (specialKindEl) specialKindEl.textContent = daily.specialDay.kind;
  if (specialDateEl) specialDateEl.textContent = daily.formattedDate;
  if (specialTitleEl) specialTitleEl.textContent = daily.specialDay.title;
  if (specialDescEl) specialDescEl.textContent = daily.specialDay.description;
  if (specialWhyEl) specialWhyEl.textContent = `Why it matters: ${daily.specialDay.why}`;

  // Render Daily Inspiration
  const quoteTextEl = document.getElementById('daily-quote-text');
  const quoteAuthorEl = document.getElementById('daily-quote-author');
  if (quoteTextEl) quoteTextEl.textContent = `“${daily.quote.text}”`;
  if (quoteAuthorEl) quoteAuthorEl.textContent = `— ${daily.quote.author}`;

  // Render Did You Know?
  const dykCatEl = document.getElementById('daily-dyk-category');
  const dykTitleEl = document.getElementById('daily-dyk-title');
  const dykFactEl = document.getElementById('daily-dyk-fact');
  if (dykCatEl) dykCatEl.textContent = daily.didYouKnow.category;
  if (dykTitleEl) dykTitleEl.textContent = daily.didYouKnow.headline;
  if (dykFactEl) dykFactEl.textContent = daily.didYouKnow.fact;

  // Render Daily Discovery
  const discTitleEl = document.getElementById('daily-discovery-title');
  const discSummaryEl = document.getElementById('daily-discovery-summary');
  const discLinkEl = document.getElementById('daily-discovery-explore');
  if (discTitleEl) discTitleEl.textContent = daily.discovery.topic;
  if (discSummaryEl) discSummaryEl.textContent = daily.discovery.summary;
  if (discLinkEl) {
    discLinkEl.dataset.query = daily.discovery.query;
    updateDiscoveryLinkHref();
  }

  const metaEl = document.getElementById('daily-source-meta');
  if (metaEl) metaEl.textContent = daily.sourceLabel;
}

function updateDiscoveryLinkHref() {
  const discLinkEl = document.getElementById('daily-discovery-explore');
  if (!discLinkEl) return;
  const q = discLinkEl.dataset.query || '';
  discLinkEl.href = `./results.html?q=${encodeURIComponent(q)}&mode=${encodeURIComponent(selectedMode)}`;
}

function setSearchMode(mode) {
  if (!SEARCH_MODES[mode]) return;
  selectedMode = mode;

  modeButtons.forEach((btn) => {
    const isCurrent = btn.getAttribute('data-search-mode') === mode;
    btn.setAttribute('aria-pressed', String(isCurrent));
  });

  if (modeDescEl) {
    modeDescEl.textContent = SEARCH_MODES[mode].description;
  }

  updateDiscoveryLinkHref();
}

function submitQuery(rawQuery) {
  const query = String(rawQuery || '').trim();
  if (!query) {
    if (feedbackEl) {
      feedbackEl.textContent = 'Enter a search term or choose a suggestion to begin.';
    }
    if (searchInput) searchInput.focus();
    return;
  }
  if (feedbackEl) feedbackEl.textContent = '';
  const url = `./results.html?q=${encodeURIComponent(query)}&mode=${encodeURIComponent(selectedMode)}`;
  window.location.assign(url);
}

function hideSuggestions() {
  if (!suggestionsPanel) return;
  suggestionsPanel.hidden = true;
  activeSuggestionIndex = -1;
  if (searchInput) {
    searchInput.setAttribute('aria-expanded', 'false');
    searchInput.removeAttribute('aria-activedescendant');
  }
}

function renderSuggestions(query) {
  if (!suggestionsPanel || !getPreferences().showSuggestions) {
    hideSuggestions();
    return;
  }

  currentSuggestions = getSearchSuggestions(query, 6);
  if (currentSuggestions.length === 0) {
    hideSuggestions();
    return;
  }

  activeSuggestionIndex = -1;
  suggestionsPanel.innerHTML = currentSuggestions
    .map(
      (item, index) => `
      <button
        type="button"
        id="home-suggestion-${index}"
        class="suggestion-item"
        role="option"
        aria-selected="false"
        data-suggestion-query="${escapeHtml(item.query)}"
      >
        <span class="suggestion-item__left">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
            <circle cx="9" cy="9" r="5.75"/>
            <path d="m16.5 16.5-3.4-3.4"/>
          </svg>
          <span class="suggestion-item__text">${escapeHtml(item.query)}</span>
        </span>
        <span class="suggestion-item__hint">${escapeHtml(item.hint)}</span>
      </button>
    `
    )
    .join('');

  suggestionsPanel.hidden = false;
  if (searchInput) searchInput.setAttribute('aria-expanded', 'true');
}

function highlightSuggestion(index) {
  if (!suggestionsPanel) return;
  const items = Array.from(suggestionsPanel.querySelectorAll('.suggestion-item'));
  if (items.length === 0) return;

  activeSuggestionIndex = index;
  items.forEach((btn, idx) => {
    const selected = idx === activeSuggestionIndex;
    btn.setAttribute('aria-selected', String(selected));
    if (selected && searchInput) {
      searchInput.setAttribute('aria-activedescendant', btn.id);
    }
  });
}

function syncClearButton() {
  if (!clearBtn || !searchInput) return;
  clearBtn.hidden = searchInput.value.length === 0;
}

// Event Wiring
modeButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    setSearchMode(btn.getAttribute('data-search-mode'));
  });
});

if (searchForm) {
  searchForm.addEventListener('submit', (event) => {
    event.preventDefault();
    if (
      activeSuggestionIndex >= 0 &&
      currentSuggestions[activeSuggestionIndex] &&
      !suggestionsPanel.hidden
    ) {
      submitQuery(currentSuggestions[activeSuggestionIndex].query);
      return;
    }
    submitQuery(searchInput ? searchInput.value : '');
  });
}

if (searchInput) {
  searchInput.addEventListener('input', () => {
    syncClearButton();
    if (feedbackEl) feedbackEl.textContent = '';
    renderSuggestions(searchInput.value);
  });

  searchInput.addEventListener('focus', () => {
    if (searchInput.value.trim().length > 0) {
      renderSuggestions(searchInput.value);
    }
  });

  searchInput.addEventListener('keydown', (event) => {
    if (suggestionsPanel.hidden || currentSuggestions.length === 0) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      const next = (activeSuggestionIndex + 1) % currentSuggestions.length;
      highlightSuggestion(next);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      const prev =
        activeSuggestionIndex <= 0
          ? currentSuggestions.length - 1
          : activeSuggestionIndex - 1;
      highlightSuggestion(prev);
    } else if (event.key === 'Escape') {
      hideSuggestions();
    }
  });
}

if (clearBtn && searchInput) {
  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    syncClearButton();
    hideSuggestions();
    if (feedbackEl) feedbackEl.textContent = '';
    searchInput.focus();
  });
}

if (suggestionsPanel) {
  suggestionsPanel.addEventListener('mousedown', (event) => {
    const item = event.target.closest('[data-suggestion-query]');
    if (!item) return;
    event.preventDefault();
    const q = item.getAttribute('data-suggestion-query');
    if (searchInput) searchInput.value = q;
    syncClearButton();
    hideSuggestions();
    submitQuery(q);
  });
}

document.addEventListener('click', (event) => {
  if (
    suggestionsPanel &&
    !suggestionsPanel.hidden &&
    !suggestionsPanel.contains(event.target) &&
    event.target !== searchInput
  ) {
    hideSuggestions();
  }
});

if (quickPromptsEl) {
  quickPromptsEl.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-quick-query]');
    if (!btn) return;
    const q = btn.getAttribute('data-quick-query');
    if (searchInput) searchInput.value = q;
    syncClearButton();
    submitQuery(q);
  });
}

// Initialize Homepage
initGreetingAndDaily();
setSearchMode(selectedMode);
syncClearButton();
