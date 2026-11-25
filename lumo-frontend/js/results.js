/**
 * LUMO Search Results Page Controller
 * Preserves query and mode in URL parameters, executes FastAPI or clearly labelled
 * sample searches, and handles sorting, filtering, pagination, loading, empty, and error states.
 */

import { initShell } from './ui-shell.js';
import { getPreferences } from './preferences.js';
import { executeSearch, isBackendConfigured, logBrowsingEvent, saveToWorkspace } from './api.js';
import {
  SEARCH_MODES,
  RESULT_CATEGORIES,
  runSampleSearch,
  highlightSnippet,
  escapeHtml,
} from './search-data.js';

initShell({ activeModule: 'search', borderedHeader: true });

const prefs = getPreferences();
const params = new URLSearchParams(window.location.search);

const state = {
  query: (params.get('q') || '').trim(),
  mode: SEARCH_MODES[params.get('mode')] ? params.get('mode') : prefs.defaultSearchMode,
  category: RESULT_CATEGORIES.includes(params.get('category')) ? params.get('category') : 'All',
  sort: ['relevance', 'newest', 'title'].includes(params.get('sort'))
    ? params.get('sort')
    : 'relevance',
  page: Math.max(1, Number(params.get('page')) || 1),
  perPage: prefs.resultsPerPage || 8,
  forceSampleFallback: false,
};

const searchForm = document.getElementById('results-search-form');
const searchInput = document.getElementById('results-search-input');
const clearBtn = document.getElementById('results-search-clear');
const modeButtons = Array.from(document.querySelectorAll('[data-search-mode]'));
const modeDescEl = document.getElementById('results-mode-description');
const categoryMount = document.getElementById('results-category-filters');
const sortSelect = document.getElementById('results-sort-select');
const sourceNoticeEl = document.getElementById('results-source-notice');
const summaryEl = document.getElementById('results-summary');
const listMount = document.getElementById('results-list-mount');
const paginationMount = document.getElementById('results-pagination-mount');
const asideMetaEl = document.getElementById('results-aside-meta');

function syncUrl() {
  const next = new URLSearchParams();
  if (state.query) next.set('q', state.query);
  next.set('mode', state.mode);
  if (state.category !== 'All') next.set('category', state.category);
  if (state.sort !== 'relevance') next.set('sort', state.sort);
  if (state.page > 1) next.set('page', String(state.page));

  const qs = next.toString();
  const target = qs ? `./results.html?${qs}` : './results.html';
  window.history.replaceState(null, '', target);

  document.title = state.query ? `${state.query} — LUMO Search` : 'Search — LUMO';
}

function renderModeControls() {
  modeButtons.forEach((btn) => {
    const active = btn.getAttribute('data-search-mode') === state.mode;
    btn.setAttribute('aria-pressed', String(active));
  });
  if (modeDescEl && SEARCH_MODES[state.mode]) {
    modeDescEl.textContent = SEARCH_MODES[state.mode].description;
  }
}

function renderCategoryFilters() {
  if (!categoryMount) return;
  categoryMount.innerHTML = RESULT_CATEGORIES.map(
    (cat) => `
      <button
        type="button"
        class="filter-tab"
        data-category="${escapeHtml(cat)}"
        aria-pressed="${String(cat === state.category)}"
      >
        ${escapeHtml(cat)}
      </button>
    `
  ).join('');
}

function renderLoading() {
  if (!listMount) return;
  if (paginationMount) paginationMount.innerHTML = '';
  listMount.innerHTML = Array.from({ length: 4 })
    .map(
      () => `
      <div class="result-item" aria-hidden="true">
        <div class="skeleton-block" style="width: 240px; height: 12px;"></div>
        <div class="skeleton-block" style="width: 68%; height: 18px; margin-top: 4px;"></div>
        <div class="skeleton-block" style="width: 92%; height: 14px; margin-top: 4px;"></div>
        <div class="skeleton-block" style="width: 78%; height: 14px;"></div>
      </div>
    `
    )
    .join('');
}

function renderSourceNotice(source) {
  if (!sourceNoticeEl) return;
  if (source === 'api') {
    sourceNoticeEl.innerHTML = `
      <div>
        <strong>Connected Index</strong> · Results retrieved from the configured LUMO FastAPI backend.
      </div>
      <a href="./settings.html" class="text-link">Settings</a>
    `;
  } else {
    sourceNoticeEl.innerHTML = `
      <div>
        <strong>Sample Demonstration Index</strong> · Live web search requires the LUMO FastAPI backend. Connect your API endpoint in Settings to query live OpenSearch and Qdrant indexes.
      </div>
      <a href="./settings.html" class="text-link">Configure API</a>
    `;
  }
}

function renderEmptyQuery() {
  if (summaryEl) summaryEl.textContent = 'Enter a query to search.';
  if (paginationMount) paginationMount.innerHTML = '';
  renderSourceNotice(isBackendConfigured() && !state.forceSampleFallback ? 'api' : 'sample');
  if (listMount) {
    listMount.innerHTML = `
      <div class="state-panel">
        <h2 class="state-panel__title">Start an intelligent search</h2>
        <p class="state-panel__desc">
          Choose Classic, Semantic, or Hybrid retrieval and enter a question, topic, or technical term above.
        </p>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; justify-content: center; margin-top: 0.5rem;">
          <button type="button" class="btn btn--secondary btn--sm" data-suggested-query="how search engines work">How search engines work</button>
          <button type="button" class="btn btn--secondary btn--sm" data-suggested-query="URL security redirect chain">URL security analysis</button>
          <button type="button" class="btn btn--secondary btn--sm" data-suggested-query="knowledge graph entities">Knowledge graphs</button>
        </div>
      </div>
    `;
  }
  updateAside(null);
}

function renderError(err) {
  if (summaryEl) summaryEl.textContent = 'Search request could not be completed.';
  if (paginationMount) paginationMount.innerHTML = '';
  if (listMount) {
    listMount.innerHTML = `
      <div class="state-panel" role="alert">
        <h2 class="state-panel__title">Unable to reach LUMO FastAPI backend</h2>
        <p class="state-panel__desc">
          ${escapeHtml(err.message || 'An unexpected network error occurred.')}
          Verify that your FastAPI service is running and allows requests from this origin.
        </p>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">
          <button type="button" class="btn btn--primary btn--sm" id="results-retry-btn">Retry request</button>
          <button type="button" class="btn btn--secondary btn--sm" id="results-fallback-sample-btn">View sample index</button>
        </div>
      </div>
    `;
  }
}

function extractDirectWebDestination(query) {
  const trimmed = String(query || '').trim();
  if (!trimmed) return null;
  const urlPattern = /^(https?:\/\/)?(www\.)?([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(\/.*)?$/i;
  if (urlPattern.test(trimmed)) {
    const fullUrl = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
    return {
      display: trimmed,
      url: fullUrl,
    };
  }
  return null;
}

function renderResults(response) {
  renderSourceNotice(response.source);

  const modeLabel = SEARCH_MODES[response.mode]?.label || 'Hybrid';
  if (summaryEl) {
    summaryEl.innerHTML = `<span class="tabular-nums">${response.total}</span> ${
      response.total === 1 ? 'result' : 'results'
    } · ${escapeHtml(modeLabel)} mode · ${
      response.source === 'api' ? 'Live index' : 'Sample data'
    }`;
  }

  updateAside(response);

  if (!listMount) return;

  const directDest = extractDirectWebDestination(state.query);
  const directNavHtml = directDest
    ? `
      <div class="direct-nav-panel" style="margin-bottom: 1.25rem; padding: 1rem; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--bg-surface);">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem;">
          <div>
            <div style="font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); font-weight: 600;">Web Address Detected</div>
            <div style="font-size: 1.05rem; font-weight: 600; margin-top: 0.15rem;">
              <a href="${directDest.url}" target="_blank" rel="noopener noreferrer" style="color: var(--color-primary);">${escapeHtml(directDest.display)}</a>
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <a href="${directDest.url}" target="_blank" rel="noopener noreferrer" class="btn btn--primary btn--sm">Visit Website</a>
            <a href="./guardian.html?tab=url&url=${encodeURIComponent(directDest.url)}" class="btn btn--secondary btn--sm">Inspect in Guardian</a>
          </div>
        </div>
      </div>
    `
    : '';

  const aiAnswerHtml = response.aiAnswer
    ? `
      <div class="panel" style="margin-bottom: 1.5rem; border-left: 3px solid var(--color-primary); background: var(--bg-surface);">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="badge" style="background: var(--color-primary); color: #fff; font-weight: 600; font-size: 0.7rem; text-transform: uppercase;">AI Answer</span>
            <span style="font-size: 0.75rem; color: var(--text-muted);">${escapeHtml(response.provider ? `Powered by ${response.provider}` : 'Grounded Generation')}</span>
          </div>
          ${response.fallbackUsed ? '<span class="badge" style="font-size: 0.68rem; background: var(--bg-subtle);">Fallback Engaged</span>' : ''}
        </div>
        <div style="font-size: 0.9375rem; line-height: 1.65; color: var(--text-color); white-space: pre-wrap;">${escapeHtml(response.aiAnswer)}</div>
        ${
          response.citations && response.citations.length > 0
            ? `
          <div style="margin-top: 1rem; padding-top: 0.75rem; border-top: 1px solid var(--border-color);">
            <div style="font-size: 0.75rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 0.5rem;">Verified Sources</div>
            <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
              ${response.citations.map((c) => `<a href="${c.url}" target="_blank" rel="noopener noreferrer" class="btn btn--secondary btn--sm" style="font-size: 0.75rem;"><strong>${escapeHtml(c.citation_id)}</strong> ${escapeHtml(c.title)}</a>`).join('')}
            </div>
          </div>
        `
            : ''
        }
      </div>
    `
    : '';

  if (response.items.length === 0) {
    listMount.innerHTML = `
      ${directNavHtml}
      ${aiAnswerHtml}
      <div class="state-panel">
        <h2 class="state-panel__title">No matching results found in Sample Index</h2>
        <p class="state-panel__desc">
          No entries matched “${escapeHtml(state.query)}” in ${escapeHtml(modeLabel)} mode${
            state.category !== 'All' ? ` under ${escapeHtml(state.category)}` : ''
          }.
          LUMO is currently running in local demonstration mode.
        </p>
        <div style="display: flex; flex-wrap: wrap; gap: 0.5rem; margin-top: 0.5rem;">
          ${
            state.category !== 'All'
              ? '<button type="button" class="btn btn--secondary btn--sm" id="results-clear-filter-btn">Clear category filter</button>'
              : ''
          }
          ${
            state.mode !== 'hybrid'
              ? '<button type="button" class="btn btn--primary btn--sm" id="results-try-hybrid-btn">Try Hybrid mode</button>'
              : ''
          }
        </div>
      </div>
    `;
    if (paginationMount) paginationMount.innerHTML = '';
    return;
  }

  listMount.innerHTML = `
    ${directNavHtml}
    ${aiAnswerHtml}
    <div class="result-list">
      ${response.items
        .map((item) => {
          const guardianHref = `./guardian.html?tab=url&url=${encodeURIComponent(item.url)}`;
          const graphHref = item.graphEntityId
            ? `./graph.html?entity=${encodeURIComponent(item.graphEntityId)}`
            : '';
          const metaParts = [item.domain, item.category, item.publishedAt].filter(Boolean);
          return `
            <article class="result-item">
              <div class="result-meta">
                <span>${metaParts.map(escapeHtml).join(' · ')}</span>
              </div>
              <h2 class="result-title">
                <a href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">
                  ${escapeHtml(item.title)}
                </a>
              </h2>
              <div class="result-url">${escapeHtml(item.url)}</div>
              <p class="result-snippet">${highlightSnippet(item.snippet || item.description, state.query)}</p>
              <div class="result-actions">
                <a href="${guardianHref}">Inspect URL in Download Guardian</a>
                ${graphHref ? `<a href="${graphHref}">Explore in Knowledge Graph</a>` : ''}
                <a href="./research.html?q=${encodeURIComponent(item.title)}">Investigate in Research Agent</a>
                <button
                  type="button"
                  class="text-link"
                  style="background: none; border: none; padding: 0; font: inherit; cursor: pointer;"
                  data-save-ws-url="${escapeHtml(item.url)}"
                  data-save-ws-title="${escapeHtml(item.title)}"
                  data-save-ws-snippet="${escapeHtml(item.snippet || item.description || '')}"
                >Save to Workspace</button>
              </div>
            </article>
          `;
        })
        .join('')}
    </div>
  `;

  renderPagination(response);
}

function renderPagination(response) {
  if (!paginationMount) return;
  if (response.totalPages <= 1) {
    paginationMount.innerHTML = '';
    return;
  }

  const pageButtons = Array.from({ length: response.totalPages }, (_, i) => i + 1)
    .map(
      (num) => `
      <button
        type="button"
        class="pagination-btn tabular-nums"
        data-page="${num}"
        ${num === response.page ? 'aria-current="page"' : ''}
      >
        ${num}
      </button>
    `
    )
    .join('');

  paginationMount.innerHTML = `
    <nav class="pagination" aria-label="Search results pagination">
      <button
        type="button"
        class="btn btn--secondary btn--sm"
        data-page="${response.page - 1}"
        ${response.page <= 1 ? 'disabled' : ''}
      >
        Previous
      </button>
      <div class="pagination-pages">${pageButtons}</div>
      <button
        type="button"
        class="btn btn--secondary btn--sm"
        data-page="${response.page + 1}"
        ${response.page >= response.totalPages ? 'disabled' : ''}
      >
        Next
      </button>
    </nav>
  `;
}

function updateAside(response) {
  if (!asideMetaEl) return;
  const endpointMap = {
    classic: 'GET /api/v1/search?q=...',
    semantic: 'GET /api/v1/search?q=...&mode=semantic',
    hybrid: 'GET /api/v1/search/hybrid?q=...',
    ai: 'POST /api/v1/search/ai',
  };
  const researchHref = state.query
    ? `./research.html?q=${encodeURIComponent(state.query)}`
    : './research.html';
  const graphHref = state.query
    ? `./graph.html?q=${encodeURIComponent(state.query)}`
    : './graph.html';

  asideMetaEl.innerHTML = `
    <div>
      <h2 class="section-heading">Retrieval details</h2>
      <div class="kv-list">
        <div class="kv-row" style="grid-template-columns: 92px 1fr;">
          <span class="kv-key">Mode</span>
          <span class="kv-val">${escapeHtml(SEARCH_MODES[state.mode]?.label || 'Hybrid')}</span>
        </div>
        <div class="kv-row" style="grid-template-columns: 92px 1fr;">
          <span class="kv-key">Source</span>
          <span class="kv-val">${response?.source === 'api' ? 'FastAPI Live' : 'Sample Index'}</span>
        </div>
        <div class="kv-row" style="grid-template-columns: 1fr; gap: 3px;">
          <span class="kv-key">Endpoint</span>
          <span class="kv-val mono" style="font-size: 0.72rem;">${escapeHtml(endpointMap[state.mode])}</span>
        </div>
      </div>
    </div>

    <div>
      <h2 class="section-heading">Continue investigating</h2>
      <p class="field-hint" style="margin-bottom: 0.75rem;">
        Move directly from web discovery to deeper research or link verification.
      </p>
      <div style="display: flex; flex-direction: column; gap: 0.5rem;">
        <a href="${researchHref}" class="btn btn--secondary btn--sm" style="justify-content: flex-start;">Open in Research Agent</a>
        <a href="${graphHref}" class="btn btn--secondary btn--sm" style="justify-content: flex-start;">Explore Knowledge Graph</a>
        <a href="./guardian.html" class="btn btn--secondary btn--sm" style="justify-content: flex-start;">Check links in Guardian</a>
      </div>
    </div>
  `;
}

let activeSearchSeq = 0;

async function performSearch() {
  const reqSeq = ++activeSearchSeq;
  syncUrl();
  renderModeControls();
  renderCategoryFilters();
  if (sortSelect) sortSelect.value = state.sort;
  if (searchInput) searchInput.value = state.query;
  if (clearBtn) clearBtn.hidden = !state.query;

  if (!state.query) {
    renderEmptyQuery();
    return;
  }

  renderLoading();

  try {
    const response = state.forceSampleFallback
      ? runSampleSearch(state.query, state)
      : await executeSearch(state.query, state);
    if (reqSeq !== activeSearchSeq) return; // Discard stale response
    state.page = response.page;
    renderResults(response);
  } catch (err) {
    if (reqSeq !== activeSearchSeq) return;
    renderError(err);
  }
}

// Event Listeners
if (searchForm && searchInput) {
  searchForm.addEventListener('submit', (event) => {
    event.preventDefault();
    state.query = searchInput.value.trim();
    state.page = 1;
    state.forceSampleFallback = false;
    performSearch();
  });

  searchInput.addEventListener('input', () => {
    if (clearBtn) clearBtn.hidden = searchInput.value.length === 0;
  });
}

if (clearBtn && searchInput) {
  clearBtn.addEventListener('click', () => {
    searchInput.value = '';
    clearBtn.hidden = true;
    searchInput.focus();
  });
}

modeButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    const mode = btn.getAttribute('data-search-mode');
    if (mode && SEARCH_MODES[mode] && mode !== state.mode) {
      state.mode = mode;
      state.page = 1;
      performSearch();
    }
  });
});

if (categoryMount) {
  categoryMount.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-category]');
    if (!btn) return;
    state.category = btn.getAttribute('data-category');
    state.page = 1;
    performSearch();
  });
}

if (sortSelect) {
  sortSelect.addEventListener('change', () => {
    state.sort = sortSelect.value;
    state.page = 1;
    performSearch();
  });
}

if (paginationMount) {
  paginationMount.addEventListener('click', (event) => {
    const btn = event.target.closest('[data-page]');
    if (!btn || btn.disabled) return;
    const nextPage = Number(btn.getAttribute('data-page'));
    if (Number.isFinite(nextPage) && nextPage >= 1) {
      state.page = nextPage;
      performSearch();
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  });
}

if (listMount) {
  listMount.addEventListener('click', (event) => {
    const resultLink = event.target.closest('.result-title a');
    if (resultLink && isBackendConfigured()) {
      const articleEl = resultLink.closest('article.result-item');
      logBrowsingEvent({
        url: resultLink.href,
        title: resultLink.textContent.trim(),
        referrer: window.location.href,
      });
    }

    const saveWsBtn = event.target.closest('[data-save-ws-url]');
    if (saveWsBtn) {
      if (!isBackendConfigured()) {
        saveWsBtn.textContent = 'Configure API in Settings';
        return;
      }
      saveWsBtn.disabled = true;
      saveWsBtn.textContent = 'Saving...';
      saveToWorkspace({
        title: saveWsBtn.getAttribute('data-save-ws-title') || 'Saved Result',
        source_url: saveWsBtn.getAttribute('data-save-ws-url') || null,
        content: saveWsBtn.getAttribute('data-save-ws-snippet') || '',
        source_type: 'search_result',
      })
        .then(() => {
          saveWsBtn.textContent = 'Saved to Workspace';
        })
        .catch(() => {
          saveWsBtn.textContent = 'Save failed';
          saveWsBtn.disabled = false;
        });
      return;
    }

    const suggested = event.target.closest('[data-suggested-query]');
    if (suggested) {
      state.query = suggested.getAttribute('data-suggested-query');
      state.page = 1;
      performSearch();
      return;
    }
    if (event.target.id === 'results-retry-btn') {
      state.forceSampleFallback = false;
      performSearch();
      return;
    }
    if (event.target.id === 'results-fallback-sample-btn') {
      state.forceSampleFallback = true;
      performSearch();
      return;
    }
    if (event.target.id === 'results-clear-filter-btn') {
      state.category = 'All';
      state.page = 1;
      performSearch();
      return;
    }
    if (event.target.id === 'results-try-hybrid-btn') {
      state.mode = 'hybrid';
      state.page = 1;
      performSearch();
    }
  });
}

performSearch();
