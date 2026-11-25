/**
 * LUMO Settings Page Controller
 * Syncs Appearance (System/Light/Dark), Search Preferences, General Settings,
 * and optional FastAPI Backend Base URL with localStorage.
 */

import { initShell } from './ui-shell.js';
import { getPreferences, savePreferences, resetPreferences } from './preferences.js';
import { applyTheme } from './theme.js';
import {
  checkBackendHealth,
  fetchPlatformDiagnostics,
  fetchLocalAIStatus,
  fetchLocalAIModels,
  updateLocalAIConfig,
  testLocalAIModel,
} from './api.js';
import { escapeHtml } from './search-data.js';

initShell({ activeModule: 'settings', borderedHeader: true });

const defaultModeSelect = document.getElementById('setting-default-mode');
const suggestionsToggle = document.getElementById('setting-suggestions-toggle');
const resultsPerPageSelect = document.getElementById('setting-results-per-page');
const languageSelect = document.getElementById('setting-language');
const compactToggle = document.getElementById('setting-compact-toggle');
const reducedMotionToggle = document.getElementById('setting-motion-toggle');
const apiForm = document.getElementById('setting-api-form');
const apiInput = document.getElementById('setting-api-url');
const apiTestBtn = document.getElementById('setting-api-test');
const apiClearBtn = document.getElementById('setting-api-clear');
const apiStatusEl = document.getElementById('setting-api-status');
const diagnosticsPanelEl = document.getElementById('setting-diagnostics-panel');
const resetAllBtn = document.getElementById('setting-reset-all');

async function renderDiagnostics() {
  if (!diagnosticsPanelEl) return;
  const prefs = getPreferences();
  if (!prefs.apiBaseUrl) {
    diagnosticsPanelEl.style.display = 'none';
    return;
  }
  try {
    const diag = await fetchPlatformDiagnostics();
    diagnosticsPanelEl.style.display = 'block';
    diagnosticsPanelEl.innerHTML = `
      <div class="kv-list" style="font-size: 0.8125rem;">
        <div class="kv-row">
          <span class="kv-key">Platform Status</span>
          <span class="kv-val">${escapeHtml(diag.status)} (${escapeHtml(diag.environment)})</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Database</span>
          <span class="kv-val">${escapeHtml(diag.database.status)} (${escapeHtml(diag.database.dialect)})</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Search Index</span>
          <span class="kv-val">${diag.search_index.total_documents} docs (${diag.search_index.semantic_indexed_documents} semantic)</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Knowledge Graph</span>
          <span class="kv-val">${diag.knowledge_graph.total_entities} entities, ${diag.knowledge_graph.total_relationships} links</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">AI Providers</span>
          <span class="kv-val">Primary: ${escapeHtml(diag.ai_providers.primary)} · Ollama: ${diag.ai_providers.ollama_reachable ? 'online' : (diag.ai_providers.ollama_enabled ? 'offline' : 'disabled')}</span>
        </div>
        <div class="kv-row">
          <span class="kv-key">Runtime &amp; Storage</span>
          <span class="kv-val">v${escapeHtml(diag.version)} · ${escapeHtml((diag.storage && diag.storage.mode) || 'local')} mode</span>
        </div>
      </div>
    `;
  } catch {
    diagnosticsPanelEl.style.display = 'none';
  }
}
const statusToastEl = document.getElementById('settings-feedback');

function announce(msg) {
  if (statusToastEl) statusToastEl.textContent = msg;
}

function hydrateForm() {
  const prefs = getPreferences();
  if (defaultModeSelect) defaultModeSelect.value = prefs.defaultSearchMode;
  if (suggestionsToggle) suggestionsToggle.setAttribute('aria-checked', String(prefs.showSuggestions));
  if (resultsPerPageSelect) resultsPerPageSelect.value = String(prefs.resultsPerPage);
  if (languageSelect) languageSelect.value = prefs.language;
  if (compactToggle) compactToggle.setAttribute('aria-checked', String(prefs.compactDensity));
  if (reducedMotionToggle) reducedMotionToggle.setAttribute('aria-checked', String(prefs.reducedMotion));
  if (apiInput) apiInput.value = prefs.apiBaseUrl;
  if (apiStatusEl) {
    apiStatusEl.textContent = prefs.apiBaseUrl
      ? `Configured FastAPI gateway: ${prefs.apiBaseUrl}`
      : 'Not configured · Frontend uses clearly labelled sample data.';
  }
}

if (defaultModeSelect) {
  defaultModeSelect.addEventListener('change', () => {
    savePreferences({ defaultSearchMode: defaultModeSelect.value });
    announce(`Default search mode updated to ${defaultModeSelect.value}.`);
  });
}

if (suggestionsToggle) {
  suggestionsToggle.addEventListener('click', () => {
    const next = suggestionsToggle.getAttribute('aria-checked') !== 'true';
    suggestionsToggle.setAttribute('aria-checked', String(next));
    savePreferences({ showSuggestions: next });
    announce(`Search suggestions ${next ? 'enabled' : 'disabled'}.`);
  });
}

if (resultsPerPageSelect) {
  resultsPerPageSelect.addEventListener('change', () => {
    savePreferences({ resultsPerPage: Number(resultsPerPageSelect.value) });
    announce(`Results per page set to ${resultsPerPageSelect.value}.`);
  });
}

if (languageSelect) {
  languageSelect.addEventListener('change', () => {
    savePreferences({ language: languageSelect.value });
    announce('Language preference saved.');
  });
}

if (compactToggle) {
  compactToggle.addEventListener('click', () => {
    const next = compactToggle.getAttribute('aria-checked') !== 'true';
    compactToggle.setAttribute('aria-checked', String(next));
    savePreferences({ compactDensity: next });
    announce(`Compact layout ${next ? 'enabled' : 'disabled'}.`);
  });
}

if (reducedMotionToggle) {
  reducedMotionToggle.addEventListener('click', () => {
    const next = reducedMotionToggle.getAttribute('aria-checked') !== 'true';
    reducedMotionToggle.setAttribute('aria-checked', String(next));
    savePreferences({ reducedMotion: next });
    announce(`Reduced motion ${next ? 'enabled' : 'disabled'}.`);
  });
}

if (apiForm && apiInput) {
  apiForm.addEventListener('submit', (event) => {
    event.preventDefault();
    const val = apiInput.value.trim();
    if (val && !/^https?:\/\/.+/i.test(val)) {
      if (apiStatusEl) {
        apiStatusEl.textContent = 'Enter a valid HTTP or HTTPS base URL (e.g. http://localhost:8000).';
      }
      return;
    }
    savePreferences({ apiBaseUrl: val });
    hydrateForm();
renderDiagnostics();
renderLocalAIManagement();
    announce('Backend API endpoint saved.');
  });
}

if (apiTestBtn) {
  apiTestBtn.addEventListener('click', async () => {
    const prefs = getPreferences();
    if (!prefs.apiBaseUrl) {
      if (apiStatusEl) apiStatusEl.textContent = 'Save a FastAPI base URL before testing.';
      return;
    }
    if (apiStatusEl) apiStatusEl.textContent = 'Checking FastAPI /health endpoint...';
    try {
      await checkBackendHealth();
      if (apiStatusEl) apiStatusEl.textContent = 'FastAPI backend responded normally.';
      await renderDiagnostics();
    } catch (err) {
      if (apiStatusEl) apiStatusEl.textContent = `Health check failed: ${err.message}`;
      if (diagnosticsPanelEl) diagnosticsPanelEl.style.display = 'none';
    }
  });
}

if (apiClearBtn) {
  apiClearBtn.addEventListener('click', () => {
    savePreferences({ apiBaseUrl: '' });
    hydrateForm();
renderDiagnostics();
renderLocalAIManagement();
    announce('Cleared backend endpoint. Sample demonstration mode active.');
  });
}

if (resetAllBtn) {
  resetAllBtn.addEventListener('click', () => {
    resetPreferences();
    applyTheme('system', { persist: true });
    hydrateForm();
renderDiagnostics();
renderLocalAIManagement();
    announce('All LUMO settings restored to defaults.');
  });
}

hydrateForm();
renderDiagnostics();
renderLocalAIManagement();


async function renderLocalAIManagement() {
  const statusEl = document.getElementById('setting-local-ai-status');
  const localOnlyEl = document.getElementById('setting-local-only-toggle');
  const modelSel = document.getElementById('setting-ollama-model-select');
  const saveBtn = document.getElementById('setting-ollama-save-btn');
  const testBtn = document.getElementById('setting-ollama-test-btn');
  const listEl = document.getElementById('setting-ollama-models-list');
  if (!statusEl) return;

  const prefs = getPreferences();
  if (!prefs.apiBaseUrl) {
    statusEl.textContent = 'Configure FastAPI Base URL above to manage local Ollama models.';
    return;
  }

  try {
    const [st, modelsRes] = await Promise.all([fetchLocalAIStatus(), fetchLocalAIModels()]);
    if (localOnlyEl) localOnlyEl.checked = Boolean(st.local_only_mode);
    statusEl.textContent = st.reachable
      ? `Ollama online · ${st.models_count} local model(s) installed · Active: ${st.default_model}`
      : st.setup_instructions || 'Ollama offline.';

    const models = modelsRes.models || [];
    if (modelSel) {
      modelSel.innerHTML = models.length
        ? models
            .map(
              (m) => `<option value="${escapeHtml(m.name)}" ${m.name === st.default_model ? 'selected' : ''}>${escapeHtml(m.name)} (${m.size_gb} GB)</option>`
            )
            .join('')
        : `<option value="${escapeHtml(st.default_model)}">${escapeHtml(st.default_model)}</option>`;
    }

    if (listEl) {
      listEl.innerHTML = models.length
        ? models
            .map(
              (m) => `
              <div class="panel panel--subtle" style="font-size: 0.8125rem; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.5rem;">
                <strong>${escapeHtml(m.name)}</strong>
                <span class="field-hint">${m.size_gb} GB · ${escapeHtml((m.capabilities || []).join(', '))}</span>
              </div>
            `
            )
            .join('')
        : `<p class="field-hint">${escapeHtml(st.setup_instructions || 'No local models detected. Run ollama pull llama3.2 in PowerShell.')}</p>`;
    }

    if (localOnlyEl && !localOnlyEl.dataset.bound) {
      localOnlyEl.dataset.bound = '1';
      localOnlyEl.addEventListener('change', async () => {
        await updateLocalAIConfig({ local_only_mode: localOnlyEl.checked });
        await renderLocalAIManagement();
      });
    }
    if (saveBtn && !saveBtn.dataset.bound) {
      saveBtn.dataset.bound = '1';
      saveBtn.addEventListener('click', async () => {
        await updateLocalAIConfig({ ollama_model: modelSel.value, ollama_enabled: true });
        statusEl.textContent = `Preferred local model set to ${modelSel.value}.`;
      });
    }
    if (testBtn && !testBtn.dataset.bound) {
      testBtn.dataset.bound = '1';
      testBtn.addEventListener('click', async () => {
        statusEl.textContent = `Testing local model ${modelSel.value}...`;
        const res = await testLocalAIModel(modelSel.value);
        statusEl.textContent = res.message;
      });
    }
  } catch (err) {
    statusEl.textContent = `Local AI check skipped: ${err.message}`;
  }
}
