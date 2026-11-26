import { initShell } from './ui-shell.js';
import {
  cancelWorkflowRun,
  createWorkflowPlan,
  deleteWorkflowRun,
  executeWorkflowPlan,
  fetchWorkflowDetail,
  fetchWorkflows,
  formatSafeError,
  getBackendUrl,
  retryWorkflowRun,
} from './api.js';

initShell({ activeModule: 'workspace-hub', borderedHeader: true });

const $ = (id) => document.getElementById(id);
let activeWorkflow = null;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('uw-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

function renderWorkflow(wf) {
  activeWorkflow = wf;
  $('uw-plan-panel').hidden = false;
  $('uw-plan-meta').innerHTML = `
    <span class="uw-badge">${escapeHtml(wf.intent)}</span>
    <span class="uw-badge">${escapeHtml(wf.status)}</span>
    <span class="uw-badge">${Math.round((wf.progress || 0) * 100)}%</span>
    <span>Modules: ${escapeHtml((wf.selected_modules_json || []).join(', '))}</span>
  `;

  $('uw-steps-list').innerHTML = (wf.steps || []).map((st) => `
    <div class="uw-row">
      <span><strong>${escapeHtml(st.title)}</strong> <code>${escapeHtml(st.module_name)}</code></span>
      <span class="uw-badge">${escapeHtml(st.status)}${st.duration_ms != null ? ` · ${st.duration_ms}ms` : ''}</span>
    </div>`).join('');

  const baseUrl = getBackendUrl().replace(/\/+$/, '');
  $('uw-exp-md').href = `${baseUrl}/api/v1/workflows/${encodeURIComponent(wf.id)}/export?format=markdown`;
  $('uw-exp-json').href = `${baseUrl}/api/v1/workflows/${encodeURIComponent(wf.id)}/export?format=json`;

  const hasResults = wf.results_json && Object.keys(wf.results_json).length > 0;
  $('uw-results-panel').hidden = !hasResults && !(wf.errors_json || []).length;
  $('uw-summary').textContent = wf.summary || '';

  const sections = [];
  Object.entries(wf.results_json || {}).forEach(([mod, data]) => {
    sections.push(`
      <details open>
        <summary style="cursor:pointer; font-weight:600;">${escapeHtml(mod)}</summary>
        <pre class="uw-pre">${escapeHtml(JSON.stringify(data, null, 2))}</pre>
      </details>`);
  });
  if ((wf.sources_json || []).length) {
    sections.push(`
      <details open>
        <summary style="cursor:pointer; font-weight:600;">Sources (${wf.sources_json.length})</summary>
        <pre class="uw-pre">${escapeHtml(JSON.stringify(wf.sources_json, null, 2))}</pre>
      </details>`);
  }
  if ((wf.disagreements_json || []).length) {
    sections.push(`
      <details open>
        <summary style="cursor:pointer; font-weight:600; color:#d97706;">Disagreements & Gaps (${wf.disagreements_json.length})</summary>
        <pre class="uw-pre">${escapeHtml(JSON.stringify(wf.disagreements_json, null, 2))}</pre>
      </details>`);
  }
  $('uw-sections').innerHTML = sections.join('');
}

async function refreshHistory() {
  const q = $('uw-hist-q').value.trim();
  const rows = await fetchWorkflows({ q: q || undefined }).catch(() => []);
  $('uw-history-list').innerHTML = rows.length
    ? rows.map((w) => `
      <div class="uw-row">
        <div>
          <strong>${escapeHtml(w.title)}</strong>
          <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(w.intent)} · ${escapeHtml(w.status)}</div>
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-secondary uw-open" data-id="${escapeHtml(w.id)}">Open</button>
          <button type="button" class="btn-secondary uw-del" data-id="${escapeHtml(w.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No workflows recorded yet.</p>';

  $('uw-history-list').querySelectorAll('.uw-open').forEach((b) => {
    b.onclick = async () => {
      try { renderWorkflow(await fetchWorkflowDetail(b.dataset.id)); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
  $('uw-history-list').querySelectorAll('.uw-del').forEach((b) => {
    b.onclick = async () => {
      try { await deleteWorkflowRun(b.dataset.id); await refreshHistory(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
}

$('uw-plan-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const inputs = {};
  const urlVal = $('uw-url').value.trim();
  const docVal = $('uw-doc').value.trim();
  const csvVal = $('uw-csv').value.trim();
  if (urlVal) inputs.url = urlVal;
  if (docVal) inputs.document_text = docVal;
  if (csvVal) inputs.csv_content = csvVal;
  try {
    const wf = await createWorkflowPlan({
      user_request: $('uw-request').value.trim(),
      preferred_intent: $('uw-intent').value || null,
      inputs,
    });
    renderWorkflow(wf);
    showBanner(`Planned '${wf.intent}' workflow. Review and click Execute.`);
    await refreshHistory();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('uw-exec-btn').addEventListener('click', async () => {
  if (!activeWorkflow) return;
  $('uw-exec-btn').disabled = true;
  try {
    const wf = await executeWorkflowPlan(activeWorkflow.id, {});
    renderWorkflow(wf);
    showBanner(`Workflow ${wf.status}.`);
    await refreshHistory();
  } catch (err) { showBanner(formatSafeError(err), true); }
  finally { $('uw-exec-btn').disabled = false; }
});

$('uw-cancel-btn').addEventListener('click', async () => {
  if (!activeWorkflow) return;
  try { renderWorkflow(await cancelWorkflowRun(activeWorkflow.id)); await refreshHistory(); }
  catch (err) { showBanner(formatSafeError(err), true); }
});

$('uw-retry-btn').addEventListener('click', async () => {
  if (!activeWorkflow) return;
  try { renderWorkflow(await retryWorkflowRun(activeWorkflow.id)); await refreshHistory(); }
  catch (err) { showBanner(formatSafeError(err), true); }
});

$('uw-copy-btn').addEventListener('click', async () => {
  if (!activeWorkflow?.summary) return;
  await navigator.clipboard?.writeText(activeWorkflow.summary).catch(() => {});
  showBanner('Summary copied.');
});

$('uw-hist-refresh').addEventListener('click', refreshHistory);
refreshHistory();
