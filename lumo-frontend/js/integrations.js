import { initShell } from './ui-shell.js';
import {
  addIntegrationSource,
  configureIntegration,
  deleteIntegrationSource,
  disableIntegration,
  enableIntegration,
  fetchIntegrationHistory,
  fetchIntegrationRecords,
  fetchIntegrationSources,
  fetchIntegrations,
  pauseIntegrationSource,
  resumeIntegrationSource,
  syncIntegration,
  testIntegration,
} from './api.js';

initShell({ activeModule: 'integrations', borderedHeader: true });

const $ = (id) => document.getElementById(id);
const ALL_PERMS = ['read_external', 'import_data', 'write_workspace', 'create_notifications', 'sync_sources', 'access_config'];
let selectedId = 'rss_atom';
let integrationsCache = [];

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('int-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

async function loadSelectedDetails() {
  const rec = integrationsCache.find((i) => i.id === selectedId) || integrationsCache[0];
  if (!rec) return;
  selectedId = rec.id;

  $('int-selected-header').innerHTML = `
    <strong>${escapeHtml(rec.name)}</strong>
    <span class="int-badge">${escapeHtml(rec.category)}</span>
    <span class="int-badge">${rec.enabled ? 'Enabled' : 'Disabled'}</span>
    <span class="int-badge">Conn: ${escapeHtml(rec.connection_status)}</span>
    ${rec.has_secret ? '<span class="int-badge">Token Configured</span>' : ''}
  `;
  $('int-cfg-freq').value = rec.sync_frequency_minutes || 60;
  $('int-cfg-secret').value = '';

  const granted = new Set(rec.permissions_json || []);
  $('int-perms-box').innerHTML = ALL_PERMS.map((p) => `
    <label><input type="checkbox" class="int-perm-chk" value="${p}" ${granted.has(p) ? 'checked' : ''}/> ${p}</label>
  `).join('');

  const [sources, history, records] = await Promise.all([
    fetchIntegrationSources(selectedId).catch(() => []),
    fetchIntegrationHistory(selectedId, 10).catch(() => []),
    fetchIntegrationRecords(selectedId, 10).catch(() => []),
  ]);

  $('int-sources-list').innerHTML = sources.length
    ? sources.map((s) => `
      <div class="int-row">
        <div>
          <strong>${escapeHtml(s.name)}</strong>
          <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(s.source_url)} · ${s.paused ? 'Paused' : 'Active'}</div>
          ${s.last_error ? `<div style="font-size:0.76rem; color:#dc2626;">${escapeHtml(s.last_error)}</div>` : ''}
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-secondary int-src-toggle" data-id="${escapeHtml(s.id)}" data-paused="${s.paused}">${s.paused ? 'Resume' : 'Pause'}</button>
          <button type="button" class="btn-secondary int-src-del" data-id="${escapeHtml(s.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No monitored sources added yet.</p>';

  $('int-sources-list').querySelectorAll('.int-src-toggle').forEach((b) => {
    b.onclick = async () => {
      try {
        if (b.dataset.paused === 'true') await resumeIntegrationSource(b.dataset.id);
        else await pauseIntegrationSource(b.dataset.id);
        await loadSelectedDetails();
      } catch (err) { showBanner(err.message, true); }
    };
  });
  $('int-sources-list').querySelectorAll('.int-src-del').forEach((b) => {
    b.onclick = async () => {
      try { await deleteIntegrationSource(b.dataset.id); showBanner('Source removed.'); await loadSelectedDetails(); }
      catch (err) { showBanner(err.message, true); }
    };
  });

  $('int-history-list').innerHTML = history.length
    ? history.map((h) => `
      <div class="int-row">
        <span>${escapeHtml(h.trigger_mode)} · ${h.imported_count} imported, ${h.skipped_count} skipped</span>
        <span class="int-badge">${escapeHtml(h.status)} (${h.duration_ms}ms)</span>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No sync runs yet.</p>';

  $('int-records-list').innerHTML = records.length
    ? records.map((r) => `
      <div class="int-row">
        <span>${escapeHtml(r.title)}</span>
        <span class="int-badge">${escapeHtml(r.content_hash.slice(0, 8))}</span>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No imported items yet.</p>';
}

async function refreshAll() {
  integrationsCache = await fetchIntegrations().catch(() => []);
  $('int-stat-total').textContent = String(integrationsCache.length);
  $('int-stat-enabled').textContent = String(integrationsCache.filter((i) => i.enabled).length);
  $('int-stat-disabled').textContent = String(integrationsCache.filter((i) => !i.enabled).length);
  $('int-stat-connected').textContent = String(integrationsCache.filter((i) => i.connection_status === 'connected').length);

  $('int-registry-list').innerHTML = integrationsCache.map((i) => `
    <div class="int-row">
      <div>
        <button type="button" class="btn-secondary int-select-btn" data-id="${escapeHtml(i.id)}" style="font-weight:600;">${escapeHtml(i.name)}</button>
        <div style="font-size:0.78rem; color:var(--text-secondary); margin-top:0.2rem;">${escapeHtml(i.description)}</div>
      </div>
      <div style="display:flex; gap:0.35rem; align-items:center;">
        <span class="int-badge">${i.enabled ? 'Enabled' : 'Disabled'}</span>
        <button type="button" class="btn-secondary int-toggle-btn" data-id="${escapeHtml(i.id)}" data-enabled="${i.enabled}">${i.enabled ? 'Disable' : 'Enable'}</button>
      </div>
    </div>`).join('');

  $('int-registry-list').querySelectorAll('.int-select-btn').forEach((b) => {
    b.onclick = () => { selectedId = b.dataset.id; loadSelectedDetails(); };
  });
  $('int-registry-list').querySelectorAll('.int-toggle-btn').forEach((b) => {
    b.onclick = async () => {
      try {
        if (b.dataset.enabled === 'true') await disableIntegration(b.dataset.id);
        else await enableIntegration(b.dataset.id);
        await refreshAll();
      } catch (err) { showBanner(err.message, true); }
    };
  });

  await loadSelectedDetails();
}

$('int-config-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const perms = Array.from(document.querySelectorAll('.int-perm-chk:checked')).map((c) => c.value);
  const token = $('int-cfg-secret').value.trim();
  try {
    await configureIntegration(selectedId, {
      permissions: perms,
      sync_frequency_minutes: Number($('int-cfg-freq').value || 60),
      secret_token: token || null,
    });
    showBanner('Integration configuration saved.');
    await refreshAll();
  } catch (err) { showBanner(err.message, true); }
});

$('int-test-btn').addEventListener('click', async () => {
  try {
    const res = await testIntegration(selectedId);
    showBanner(`Test: ${res.detail || (res.ok ? 'Connected' : 'Failed')}`, !res.ok);
    await refreshAll();
  } catch (err) { showBanner(err.message, true); }
});

$('int-sync-btn').addEventListener('click', async () => {
  try {
    const run = await syncIntegration(selectedId, {});
    showBanner(`Sync ${run.status}: ${run.imported_count} imported, ${run.skipped_count} skipped.`);
    await refreshAll();
  } catch (err) { showBanner(err.message, true); }
});

$('int-source-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await addIntegrationSource(selectedId, {
      name: $('int-src-name').value.trim(),
      source_url: $('int-src-url').value.trim(),
      source_type: selectedId,
      monitored: true,
    });
    $('int-src-name').value = '';
    $('int-src-url').value = '';
    showBanner('Monitored source added.');
    await loadSelectedDetails();
  } catch (err) { showBanner(err.message, true); }
});

refreshAll();
