import { initShell } from './ui-shell.js';
import {
  addEvaluationReview,
  cancelEvaluationRun,
  cloneEvaluation,
  compareEvaluationRuns,
  createEvaluation,
  createEvaluationDataset,
  deleteEvaluation,
  deleteEvaluationDataset,
  fetchEvaluationDatasets,
  fetchEvaluationReviews,
  fetchEvaluationRunResults,
  fetchEvaluationRuns,
  fetchEvaluations,
  fetchIntelligenceProvidersStatus,
  formatSafeError,
  getBackendUrl,
  importEvaluationDataset,
  runEvaluation,
} from './api.js';

initShell({ activeModule: 'evaluations', borderedHeader: true });

const $ = (id) => document.getElementById(id);
const MAX_IMPORT_BYTES = 5 * 1024 * 1024;
const ALLOWED_EXTS = ['.json', '.jsonl', '.csv'];
let activeReviewRunId = null;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('ev-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

export function validateDatasetFileClient(file) {
  if (!file) return 'Please select a dataset file.';
  const lower = String(file.name || '').toLowerCase();
  if (!ALLOWED_EXTS.some((ext) => lower.endsWith(ext))) {
    return 'Unsupported format. Upload .json, .jsonl, or .csv.';
  }
  if (file.size <= 0) return 'Selected file is empty.';
  if (file.size > MAX_IMPORT_BYTES) return 'File exceeds 5 MB upload limit.';
  return null;
}

async function loadProviderOptions() {
  const sel = $('ev-run-provider');
  const status = await fetchIntelligenceProvidersStatus().catch(() => null);
  if (!status?.providers) return;
  const opts = ['<option value="auto">Auto (Configured)</option>'];
  Object.entries(status.providers).forEach(([name, info]) => {
    const usable = info.configured && !info.blocked_by_privacy_mode;
    const label = usable
      ? `${name} (configured)`
      : `${name} (${info.blocked_by_privacy_mode ? 'blocked by local-only' : 'unavailable'})`;
    opts.push(`<option value="${escapeHtml(name)}" ${usable ? '' : 'disabled'}>${escapeHtml(label)}</option>`);
  });
  sel.innerHTML = opts.join('');
}

async function openRunInspector(runId) {
  activeReviewRunId = runId;
  const panel = $('ev-review-panel');
  panel.hidden = false;
  $('ev-rev-meta').textContent = 'Loading run details...';
  try {
    const [detail, reviews] = await Promise.all([
      fetchEvaluationRunResults(runId),
      fetchEvaluationReviews(runId).catch(() => []),
    ]);
    $('ev-rev-meta').textContent = `Run ${detail.id} · Target: ${detail.target_module} · Provider: ${detail.provider_name || 'auto'} · Model: ${detail.model_name || 'default'} · Status: ${detail.status}`;
    $('ev-rev-results').textContent = JSON.stringify(detail.results_json || [], null, 2);

    $('ev-rev-list').innerHTML = reviews.length
      ? reviews.map((rv) => `
        <div class="ev-row">
          <div>
            <strong>Score ${rv.score}/5</strong> <span class="ev-badge">${escapeHtml(rv.status)}</span>
            ${rv.case_id ? `<code>${escapeHtml(rv.case_id)}</code>` : ''}
            <div style="font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(rv.reviewer_notes)}</div>
          </div>
        </div>`).join('')
      : '<p style="color:var(--text-secondary);font-size:0.85rem;">No human reviews recorded yet.</p>';
  } catch (err) {
    $('ev-rev-meta').textContent = formatSafeError(err);
  }
}

async function refreshAll() {
  const [datasets, benchmarks, runs] = await Promise.all([
    fetchEvaluationDatasets().catch(() => []),
    fetchEvaluations().catch(() => []),
    fetchEvaluationRuns(25).catch(() => []),
  ]);

  $('ev-stat-ds').textContent = String(datasets.length);
  $('ev-stat-bm').textContent = String(benchmarks.length);
  $('ev-stat-runs').textContent = String(runs.length);
  if (runs.length && runs[0].total_cases > 0) {
    $('ev-stat-pass').textContent = `${Math.round((runs[0].passed_cases / runs[0].total_cases) * 100)}%`;
  }

  $('ev-bm-ds').innerHTML = datasets.length
    ? datasets.map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)} (v${escapeHtml(d.version)}, ${d.case_count} cases)</option>`).join('')
    : '<option value="">Create or import a dataset first</option>';

  $('ev-ds-list').innerHTML = datasets.length
    ? datasets.map((d) => `
      <div class="ev-row">
        <span><strong>${escapeHtml(d.name)}</strong> · ${escapeHtml(d.category)} (${escapeHtml(d.format_type)}, ${d.case_count} cases)</span>
        <button type="button" class="btn-secondary ev-ds-del" data-id="${escapeHtml(d.id)}">Delete</button>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.86rem;">No evaluation datasets yet.</p>';

  $('ev-ds-list').querySelectorAll('.ev-ds-del').forEach((b) => {
    b.onclick = async () => {
      if (!confirm('Delete this evaluation dataset?')) return;
      try { await deleteEvaluationDataset(b.dataset.id); await refreshAll(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });

  $('ev-bm-list').innerHTML = benchmarks.length
    ? benchmarks.map((bm) => `
      <div class="ev-row">
        <div>
          <strong>${escapeHtml(bm.name)}</strong>
          <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(bm.target_module)} · ${escapeHtml(bm.status)}</div>
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-primary ev-bm-run" data-id="${escapeHtml(bm.id)}">Run</button>
          <button type="button" class="btn-secondary ev-bm-clone" data-id="${escapeHtml(bm.id)}">Clone</button>
          <button type="button" class="btn-secondary ev-bm-del" data-id="${escapeHtml(bm.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.86rem;">No benchmarks registered yet.</p>';

  $('ev-bm-list').querySelectorAll('.ev-bm-run').forEach((b) => {
    b.onclick = async () => {
      b.disabled = true;
      try {
        const kVal = Math.max(1, Math.min(50, Number($('ev-run-k').value || 5)));
        const prov = $('ev-run-provider').value || 'auto';
        const mod = $('ev-run-model').value.trim() || null;
        const r = await runEvaluation(b.dataset.id, { k: kVal, provider: prov, model_name: mod });
        showBanner(`Run ${r.status}: ${r.passed_cases}/${r.total_cases} passed.`);
        await refreshAll();
        await openRunInspector(r.id);
      } catch (err) { showBanner(formatSafeError(err), true); }
      finally { b.disabled = false; }
    };
  });
  $('ev-bm-list').querySelectorAll('.ev-bm-clone').forEach((b) => {
    b.onclick = async () => {
      try { await cloneEvaluation(b.dataset.id); await refreshAll(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
  $('ev-bm-list').querySelectorAll('.ev-bm-del').forEach((b) => {
    b.onclick = async () => {
      if (!confirm('Delete this benchmark and its run history?')) return;
      try { await deleteEvaluation(b.dataset.id); await refreshAll(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });

  const baseUrl = getBackendUrl().replace(/\/+$/, '');
  $('ev-runs-list').innerHTML = runs.length
    ? runs.map((r) => `
      <div class="ev-row">
        <div>
          <strong>${escapeHtml(r.target_module)}</strong>
          <span class="ev-badge">${r.passed_cases}/${r.total_cases} · ${escapeHtml(r.status)}</span>
          <span class="ev-badge">${escapeHtml(r.provider_name || 'auto')}${r.model_name ? ` / ${escapeHtml(r.model_name)}` : ''}</span>
          <div style="font-size:0.76rem; color:var(--text-secondary);">Metrics: ${escapeHtml(JSON.stringify(r.metrics_json).slice(0, 120))}</div>
        </div>
        <div style="display:flex; gap:0.35rem; flex-wrap:wrap;">
          <button type="button" class="btn-secondary ev-run-inspect" data-id="${escapeHtml(r.id)}">Review</button>
          ${r.status === 'running' ? `<button type="button" class="btn-secondary ev-run-cancel" data-id="${escapeHtml(r.id)}">Cancel</button>` : ''}
          <a class="btn-secondary" href="${baseUrl}/api/v1/evaluations/runs/${encodeURIComponent(r.id)}/export?format=csv" target="_blank" rel="noopener">CSV</a>
          <a class="btn-secondary" href="${baseUrl}/api/v1/evaluations/runs/${encodeURIComponent(r.id)}/export?format=json" target="_blank" rel="noopener">JSON</a>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.86rem;">No benchmark runs executed yet.</p>';

  $('ev-runs-list').querySelectorAll('.ev-run-inspect').forEach((b) => {
    b.onclick = () => openRunInspector(b.dataset.id);
  });
  $('ev-runs-list').querySelectorAll('.ev-run-cancel').forEach((b) => {
    b.onclick = async () => {
      try { await cancelEvaluationRun(b.dataset.id); showBanner('Cancellation requested.'); await refreshAll(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });

  const runOpts = runs.map((r) => `<option value="${escapeHtml(r.id)}">${escapeHtml(r.target_module)} [${escapeHtml(r.provider_name || 'auto')}] (${r.passed_cases}/${r.total_cases})</option>`).join('');
  $('ev-cmp-base').innerHTML = runOpts;
  $('ev-cmp-curr').innerHTML = runOpts;
}

$('ev-import-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = $('ev-imp-file').files?.[0];
  const errMsg = validateDatasetFileClient(file);
  if (errMsg) { showBanner(errMsg, true); return; }

  const btn = $('ev-imp-btn');
  btn.disabled = true;
  btn.textContent = 'Importing...';
  try {
    const ds = await importEvaluationDataset(file, {
      name: $('ev-imp-name').value.trim(),
      category: $('ev-imp-cat').value,
    });
    $('ev-imp-file').value = '';
    $('ev-imp-name').value = '';
    showBanner(`Imported '${ds.name}' (${ds.case_count} cases).`);
    await refreshAll();
  } catch (err) {
    showBanner(formatSafeError(err), true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Import File';
  }
});

$('ev-ds-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const cases = JSON.parse($('ev-ds-cases').value.trim());
    await createEvaluationDataset({
      name: $('ev-ds-name').value.trim(),
      category: $('ev-ds-cat').value,
      version: $('ev-ds-ver').value.trim() || '1.0',
      cases,
    });
    $('ev-ds-name').value = '';
    showBanner('Evaluation dataset created.');
    await refreshAll();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('ev-bm-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const target = $('ev-bm-target').value;
  try {
    await createEvaluation({
      name: $('ev-bm-name').value.trim(),
      category: target,
      dataset_id: $('ev-bm-ds').value || null,
      target_module: target,
    });
    $('ev-bm-name').value = '';
    showBanner('Benchmark registered.');
    await refreshAll();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('ev-cmp-btn').addEventListener('click', async () => {
  const b = $('ev-cmp-base').value;
  const c = $('ev-cmp-curr').value;
  if (!b || !c) return;
  const out = $('ev-cmp-out');
  out.hidden = false;
  try {
    const res = await compareEvaluationRuns(b, c);
    out.textContent = JSON.stringify(res, null, 2);
  } catch (err) { out.textContent = formatSafeError(err); }
});

$('ev-rev-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!activeReviewRunId) return;
  const btn = $('ev-rev-submit');
  btn.disabled = true;
  try {
    await addEvaluationReview(activeReviewRunId, {
      case_id: $('ev-rev-case').value.trim() || null,
      score: Number($('ev-rev-score').value),
      status: $('ev-rev-status').value,
      reviewer_notes: $('ev-rev-notes').value.trim(),
    });
    $('ev-rev-notes').value = '';
    showBanner('Human review saved.');
    await openRunInspector(activeReviewRunId);
  } catch (err) {
    showBanner(formatSafeError(err), true);
  } finally {
    btn.disabled = false;
  }
});

loadProviderOptions();
refreshAll();
