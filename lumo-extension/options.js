/**
 * LUMO Browser Companion — Options Page Controller
 */

import {
  checkExtensionBackendHealth,
  escapeHtml,
  getExtensionSettings,
  getPageStatus,
  isValidHttpUrl,
  saveExtensionSettings,
} from './lib/api.js';

const form = document.getElementById('options-form');
const backendInput = document.getElementById('opt-backend-url');
const frontendInput = document.getElementById('opt-frontend-url');
const themeSelect = document.getElementById('opt-theme');
const collectionSelect = document.getElementById('opt-default-collection');
const captureDescCheck = document.getElementById('opt-capture-desc');
const captureSelCheck = document.getElementById('opt-capture-sel');
const testBtn = document.getElementById('opt-test-btn');
const statusPill = document.getElementById('opt-status');
const feedbackEl = document.getElementById('opt-feedback');

async function loadOptions() {
  const s = await getExtensionSettings();
  document.documentElement.setAttribute('data-theme', s.theme || 'system');
  backendInput.value = s.backendUrl;
  frontendInput.value = s.frontendUrl;
  themeSelect.value = s.theme;
  captureDescCheck.checked = Boolean(s.captureDescription);
  captureSelCheck.checked = Boolean(s.captureSelection);

  try {
    await checkExtensionBackendHealth();
    statusPill.textContent = 'Connected';
    statusPill.className = 'status-pill status-pill--ok';
    const pageStatus = await getPageStatus('');
    collectionSelect.innerHTML =
      '<option value="">No default collection</option>' +
      (pageStatus.collections || [])
        .map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`)
        .join('');
    collectionSelect.value = s.defaultCollectionId || '';
  } catch {
    statusPill.textContent = 'Offline';
    statusPill.className = 'status-pill status-pill--err';
  }
}

form.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const backendUrl = backendInput.value.trim();
  const frontendUrl = frontendInput.value.trim();
  if (!isValidHttpUrl(backendUrl) || !isValidHttpUrl(frontendUrl)) {
    feedbackEl.textContent = 'Both URLs must start with http:// or https://.';
    return;
  }
  await saveExtensionSettings({
    backendUrl,
    frontendUrl,
    theme: themeSelect.value,
    defaultCollectionId: collectionSelect.value,
    captureDescription: captureDescCheck.checked,
    captureSelection: captureSelCheck.checked,
  });
  document.documentElement.setAttribute('data-theme', themeSelect.value);
  feedbackEl.textContent = 'Extension settings saved.';
});

testBtn.addEventListener('click', async () => {
  feedbackEl.textContent = 'Testing connection...';
  try {
    const res = await checkExtensionBackendHealth();
    statusPill.textContent = 'Connected';
    statusPill.className = 'status-pill status-pill--ok';
    feedbackEl.textContent = `Connected to ${res.application} (${res.extension_api}).`;
  } catch (err) {
    statusPill.textContent = 'Offline';
    statusPill.className = 'status-pill status-pill--err';
    feedbackEl.textContent = `Connection failed: ${err.message}`;
  }
});

loadOptions();
