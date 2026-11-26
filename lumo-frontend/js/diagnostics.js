import { initShell } from './ui-shell.js';
import { fetchHealthReady, fetchSystemDiagnostics, fetchSystemInfo, formatSafeError } from './api.js';

initShell({ activeModule: 'diagnostics', borderedHeader: true });

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function fmtUptime(sec) {
  const s = Math.max(0, Math.floor(Number(sec || 0)));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m ${s % 60}s`;
}

async function loadDiagnostics() {
  const btn = $('diag-refresh-btn');
  const errEl = $('diag-error');
  const pill = $('diag-status-pill');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';
  errEl.hidden = true;

  try {
    const [diag, info, ready] = await Promise.all([
      fetchSystemDiagnostics(),
      fetchSystemInfo().catch(() => null),
      fetchHealthReady().catch(() => null),
    ]);

    const healthy = diag.status === 'healthy';
    pill.textContent = diag.status.toUpperCase();
    pill.className = `diag-pill ${healthy ? 'ok' : 'warn'}`;

    $('d-version').textContent = `${diag.application} v${diag.version} (${diag.environment})`;
    const dbMs = diag.database?.latency_ms ?? ready?.db_latency_ms;
    $('d-db').textContent = `${diag.database?.status || 'unknown'}${dbMs != null ? ` · ${dbMs} ms` : ''}`;
    $('d-uptime').textContent = fmtUptime(diag.uptime_seconds ?? info?.uptime_seconds);
    $('d-schema').textContent = `v${diag.schema_version ?? info?.database_migration_version ?? 0}`;

    const jobs = diag.background_jobs || {};
    $('d-jobs').textContent = `${jobs.active_total ?? 0} active / ${jobs.failed_total ?? 0} failed`;

    const obs = diag.observability || {};
    $('d-reqs').textContent = `${obs.total_requests ?? 0} reqs / ${obs.total_errors ?? 0} err`;

    const cb = diag.ai_providers?.circuit_breakers || {};
    const cbEntries = Object.entries(cb);
    $('d-providers').innerHTML = cbEntries.length
      ? cbEntries.map(([name, st]) => `
        <div class="diag-row">
          <span><strong>${escapeHtml(name)}</strong> · ${st.configured ? 'configured' : 'not configured'}${st.blocked_by_privacy_mode ? ' (privacy-blocked)' : ''}</span>
          <span class="diag-pill ${st.circuit_state === 'open' ? 'err' : 'ok'}">${escapeHtml(st.circuit_state || 'closed')}</span>
        </div>`).join('')
      : '<p style="color:var(--text-secondary);">No provider status available.</p>';

    $('d-storage').innerHTML = `
      <div class="diag-row"><span>Mode</span><span>${escapeHtml(diag.storage?.mode || 'local')}</span></div>
      <div class="diag-row"><span>Database Dialect</span><span>${escapeHtml(diag.database?.dialect || 'unknown')}</span></div>
      <div class="diag-row"><span>Qdrant Collection</span><span>${escapeHtml(diag.vector_store?.collection_name || 'none')}</span></div>
      <div class="diag-row"><span>Indexed Docs</span><span>${diag.search_index?.total_documents ?? 0} (${diag.search_index?.semantic_indexed_documents ?? 0} semantic)</span></div>
    `;

    $('d-obs').textContent = JSON.stringify({
      status_distribution: obs.status_distribution || {},
      top_endpoints: obs.top_endpoints || [],
      slow_requests: obs.slow_requests || [],
    }, null, 2);

    const errs = obs.recent_errors || [];
    $('d-errors').textContent = errs.length ? JSON.stringify(errs, null, 2) : 'No recent server errors recorded.';
  } catch (err) {
    pill.textContent = 'UNAVAILABLE';
    pill.className = 'diag-pill err';
    errEl.textContent = formatSafeError(err);
    errEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh';
  }
}

$('diag-refresh-btn').addEventListener('click', loadDiagnostics);
loadDiagnostics();
