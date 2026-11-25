/**
 * LUMO Adaptive Intelligence & Personalization Dashboard Controller
 */

import { initShell } from './ui-shell.js';
import { escapeHtml } from './search-data.js';
import {
  isBackendConfigured,
  fetchPersonalizationProfile,
  updatePersonalizationSettings,
  addPersonalizationInterest,
  deletePersonalizationInterest,
  addSourcePreference,
  deleteSourcePreference,
  fetchRecommendations,
  deletePersonalizationFeedback,
  resetPersonalizationData,
} from './api.js';

initShell({ activeModule: 'personalization', borderedHeader: true });

const statusTextEl = document.getElementById('pers-status-text');
const enabledToggle = document.getElementById('pers-enabled-toggle');
const historyToggle = document.getElementById('pers-history-toggle');
const weightRange = document.getElementById('pers-weight-range');
const weightLabel = document.getElementById('pers-weight-label');

async function loadProfile() {
  if (!isBackendConfigured()) {
    if (statusTextEl) {
      statusTextEl.innerHTML = '<strong>Backend not configured</strong> · Set FastAPI URL in <a href="./settings.html" class="text-link">Settings</a>.';
    }
    return;
  }

  try {
    const [profile, recs] = await Promise.all([
      fetchPersonalizationProfile(),
      fetchRecommendations(),
    ]);
    const s = profile.settings;
    if (enabledToggle) enabledToggle.checked = Boolean(s.enabled);
    if (historyToggle) historyToggle.checked = Boolean(s.use_search_history);
    if (weightRange) weightRange.value = String(s.personalization_weight);
    if (weightLabel) weightLabel.textContent = String(s.personalization_weight);

    if (statusTextEl) {
      statusTextEl.innerHTML = s.enabled
        ? `<strong>Personalization Active</strong> · Weight ${s.personalization_weight} · ${profile.interests.length} interests · ${profile.sources.length} source rules`
        : '<strong>Personalization Disabled (Default)</strong> · Search uses standard unpersonalized ranking.';
    }

    renderInterests(profile.interests);
    renderSources(profile.sources);
    renderRecommendations(recs, s.enabled);
    renderTopics(profile.topics);
    renderFeedback(profile.recent_feedback);
  } catch (err) {
    if (statusTextEl) statusTextEl.textContent = `Personalization unavailable: ${err.message}`;
  }
}

function renderInterests(interests) {
  const el = document.getElementById('pers-interests-list');
  if (!el) return;
  if (!interests.length) {
    el.innerHTML = '<span class="field-hint">No explicit interests added yet.</span>';
    return;
  }
  el.innerHTML = interests
    .map(
      (i) => `
      <span class="badge" style="display: inline-flex; align-items: center; gap: 0.35rem;">
        <span>${escapeHtml(i.topic)} (${escapeHtml(i.source)})</span>
        <button type="button" data-del-interest="${escapeHtml(i.id)}" style="background:none; border:none; cursor:pointer; color:inherit;">×</button>
      </span>
    `
    )
    .join('');
}

function renderSources(sources) {
  const el = document.getElementById('pers-sources-list');
  if (!el) return;
  if (!sources.length) {
    el.innerHTML = '<p class="field-hint">No domain preferences configured.</p>';
    return;
  }
  el.innerHTML = sources
    .map(
      (src) => `
      <div class="panel panel--subtle" style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem;">
        <span><strong>${escapeHtml(src.domain)}</strong> · ${escapeHtml(src.preference)}</span>
        <button type="button" class="btn btn--ghost btn--sm" data-del-source="${escapeHtml(src.id)}">Remove</button>
      </div>
    `
    )
    .join('');
}

function renderRecommendations(recs, enabled) {
  const el = document.getElementById('pers-recs-list');
  if (!el) return;
  if (!enabled) {
    el.innerHTML = '<p class="field-hint">Enable personalization to view grounded discovery suggestions.</p>';
    return;
  }
  if (!recs.length) {
    el.innerHTML = '<p class="field-hint">Add interests or index documents to see grounded recommendations.</p>';
    return;
  }
  el.innerHTML = recs
    .map(
      (r) => `
      <div class="panel panel--subtle" style="font-size: 0.8125rem;">
        <div class="field-hint">${escapeHtml(r.kind)} · ${escapeHtml(r.reason)}</div>
        <div style="font-weight: 600;">${escapeHtml(r.title)}</div>
      </div>
    `
    )
    .join('');
}

function renderTopics(topics) {
  const el = document.getElementById('pers-topics-list');
  if (!el) return;
  if (!topics.length) {
    el.innerHTML = '<span class="field-hint">No observed search topics recorded.</span>';
    return;
  }
  el.innerHTML = topics
    .map((t) => `<span class="badge">${escapeHtml(t.topic)} (${t.frequency}x · ${escapeHtml(t.signal_kind)})</span>`)
    .join('');
}

function renderFeedback(items) {
  const el = document.getElementById('pers-feedback-list');
  if (!el) return;
  if (!items.length) {
    el.innerHTML = '<p class="field-hint">No feedback submitted yet.</p>';
    return;
  }
  el.innerHTML = items
    .map(
      (f) => `
      <div class="panel panel--subtle" style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem;">
        <span>${escapeHtml(f.feedback_type)} · ${escapeHtml(f.target_type)} (${escapeHtml(f.topic || f.target_id)})</span>
        <button type="button" class="btn btn--ghost btn--sm" data-del-fb="${escapeHtml(f.id)}">Delete</button>
      </div>
    `
    )
    .join('');
}

enabledToggle?.addEventListener('change', async () => {
  await updatePersonalizationSettings({ enabled: enabledToggle.checked });
  await loadProfile();
});

historyToggle?.addEventListener('change', async () => {
  await updatePersonalizationSettings({ use_search_history: historyToggle.checked });
  await loadProfile();
});

weightRange?.addEventListener('change', async () => {
  const val = Number(weightRange.value);
  if (weightLabel) weightLabel.textContent = String(val);
  await updatePersonalizationSettings({ personalization_weight: val });
  await loadProfile();
});

document.getElementById('pers-interest-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const topic = document.getElementById('pers-interest-topic').value.trim();
  const source = document.getElementById('pers-interest-kind').value;
  if (!topic) return;
  try {
    await addPersonalizationInterest({ topic, source });
    document.getElementById('pers-interest-topic').value = '';
    await loadProfile();
  } catch (err) {
    alert(err.message);
  }
});

document.getElementById('pers-source-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const domain = document.getElementById('pers-source-domain').value.trim();
  const preference = document.getElementById('pers-source-kind').value;
  if (!domain) return;
  await addSourcePreference({ domain, preference });
  document.getElementById('pers-source-domain').value = '';
  await loadProfile();
});

document.getElementById('pers-reset-btn')?.addEventListener('click', async () => {
  await resetPersonalizationData();
  await loadProfile();
});

document.addEventListener('click', async (ev) => {
  const di = ev.target.closest('[data-del-interest]');
  if (di) { await deletePersonalizationInterest(di.getAttribute('data-del-interest')); await loadProfile(); return; }
  const ds = ev.target.closest('[data-del-source]');
  if (ds) { await deleteSourcePreference(ds.getAttribute('data-del-source')); await loadProfile(); return; }
  const df = ev.target.closest('[data-del-fb]');
  if (df) { await deletePersonalizationFeedback(df.getAttribute('data-del-fb')); await loadProfile(); }
});

loadProfile();
