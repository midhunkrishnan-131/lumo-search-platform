import { initShell } from './ui-shell.js';
import {
  createApiKey,
  deleteApiKey,
  fetchApiKeys,
  fetchApiUsage,
  fetchDeveloperInfo,
  getBackendUrl,
  revokeApiKey,
  rotateApiKey,
} from './api.js';

initShell({ activeModule: 'developer', borderedHeader: true });

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('dev-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

function showOneTimeKey(rawKey) {
  $('dev-new-key-val').textContent = rawKey;
  $('dev-new-key-box').hidden = false;
}

async function refreshAll() {
  const [info, keys, usage] = await Promise.all([
    fetchDeveloperInfo().catch(() => null),
    fetchApiKeys().catch(() => []),
    fetchApiUsage(20).catch(() => null),
  ]);

  if (info?.permissions) {
    const grid = $('dev-perms-grid');
    if (!grid.children.length) {
      grid.innerHTML = Object.entries(info.permissions).map(([perm, desc]) => `
        <label title="${escapeHtml(desc)}">
          <input type="checkbox" class="dev-perm-chk" value="${escapeHtml(perm)}" ${perm === 'search:read' ? 'checked' : ''}/>
          <code>${escapeHtml(perm)}</code>
        </label>`).join('');
    }
  }

  if (usage) {
    $('stat-total-req').textContent = String(usage.total_requests);
    $('stat-ok-req').textContent = String(usage.successful_requests);
    $('stat-err-req').textContent = String(usage.failed_requests);
    $('stat-rl-req').textContent = String(usage.rate_limited_requests);

    $('dev-usage-list').innerHTML = (usage.recent || []).length
      ? usage.recent.map((u) => `
        <div class="dev-row">
          <div>
            <code>${escapeHtml(u.method)} ${escapeHtml(u.endpoint)}</code>
            <div style="font-size:0.76rem; color:var(--text-secondary);">Key: ${escapeHtml(u.key_prefix || 'anon')} · ${u.duration_ms}ms</div>
          </div>
          <span class="dev-badge">${u.status_code}${u.rate_limited ? ' (429)' : ''}</span>
        </div>`).join('')
      : '<p style="color:var(--text-secondary); font-size:0.86rem;">No external API key requests recorded yet.</p>';
  }

  $('dev-keys-list').innerHTML = keys.length
    ? keys.map((k) => `
      <div class="dev-row">
        <div>
          <strong>${escapeHtml(k.name)}</strong>
          <code>${escapeHtml(k.key_prefix)}...</code>
          <div style="font-size:0.76rem; color:var(--text-secondary);">
            ${k.is_active ? 'Active' : 'Revoked'} · ${k.rate_limit_rpm} rpm · Perms: ${escapeHtml((k.permissions_json || []).join(', '))}
          </div>
        </div>
        <div style="display:flex; gap:0.35rem; flex-wrap:wrap;">
          ${k.is_active ? `<button type="button" class="btn-secondary dev-rotate-btn" data-id="${escapeHtml(k.id)}">Rotate</button>` : ''}
          ${k.is_active ? `<button type="button" class="btn-secondary dev-revoke-btn" data-id="${escapeHtml(k.id)}">Revoke</button>` : ''}
          <button type="button" class="btn-secondary dev-del-btn" data-id="${escapeHtml(k.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No API keys issued yet.</p>';

  $('dev-keys-list').querySelectorAll('.dev-rotate-btn').forEach((b) => {
    b.onclick = async () => {
      try { const res = await rotateApiKey(b.dataset.id); showOneTimeKey(res.raw_key); showBanner('Key rotated.'); await refreshAll(); }
      catch (err) { showBanner(err.message, true); }
    };
  });
  $('dev-keys-list').querySelectorAll('.dev-revoke-btn').forEach((b) => {
    b.onclick = async () => {
      try { await revokeApiKey(b.dataset.id); showBanner('Key revoked.'); await refreshAll(); }
      catch (err) { showBanner(err.message, true); }
    };
  });
  $('dev-keys-list').querySelectorAll('.dev-del-btn').forEach((b) => {
    b.onclick = async () => {
      try { await deleteApiKey(b.dataset.id); showBanner('Key deleted.'); await refreshAll(); }
      catch (err) { showBanner(err.message, true); }
    };
  });
}

$('dev-key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const perms = Array.from(document.querySelectorAll('.dev-perm-chk:checked')).map((c) => c.value);
  const expRaw = $('dev-key-exp').value.trim();
  try {
    const res = await createApiKey({
      name: $('dev-key-name').value.trim(),
      permissions: perms,
      rate_limit_rpm: Number($('dev-key-rpm').value || 60),
      expires_in_days: expRaw ? Number(expRaw) : null,
    });
    $('dev-key-name').value = '';
    showOneTimeKey(res.raw_key);
    showBanner('API key generated.');
    await refreshAll();
  } catch (err) { showBanner(err.message, true); }
});

$('dev-copy-key-btn').addEventListener('click', () => {
  navigator.clipboard?.writeText($('dev-new-key-val').textContent || '');
  showBanner('Copied API key to clipboard.');
});

$('dev-test-btn').addEventListener('click', async () => {
  const rawKey = $('dev-test-key').value.trim();
  const q = $('dev-test-query').value.trim() || 'LUMO';
  const out = $('dev-test-out');
  out.hidden = false;
  out.textContent = 'Executing request...';
  try {
    const headers = rawKey ? { 'X-API-Key': rawKey } : {};
    const url = `${getBackendUrl().replace(/\/+$/, '')}/api/v1/search?q=${encodeURIComponent(q)}&mode=classic`;
    const resp = await fetch(url, { headers });
    const data = await resp.json();
    out.textContent = `HTTP ${resp.status}\n` + JSON.stringify(data, null, 2);
    await refreshAll();
  } catch (err) {
    out.textContent = err.message;
  }
});

refreshAll();
