import { initShell } from './ui-shell.js';
import {
  cloneEvaluation,
  compareEvaluationRuns,
  createEvaluation,
  createEvaluationDataset,
  deleteEvaluation,
  deleteEvaluationDataset,
  fetchEvaluationDatasets,
  fetchEvaluationRuns,
  fetchEvaluations,
  formatSafeError,
  getBackendUrl,
  runEvaluation,
} from './api.js';

initShell({ activeModule: 'evaluations', borderedHeader: true });

const $ = (id) => document.getElementById(id);

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
    : '<option value="">Create a dataset first</option>';

  $('ev-ds-list').innerHTML = datasets.length
    ? datasets.map((d) => `
      <div class="ev-row">
        <span><strong>${escapeHtml(d.name)}</strong> · ${escapeHtml(d.category)} (${d.case_count} cases)</span>
        <button type="button" class="btn-secondary ev-ds-del" data-id="${escapeHtml(d.id)}">Delete</button>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.86rem;">No evaluation datasets yet.</p>';

  $('ev-ds-list').querySelectorAll('.ev-ds-del').forEach((b) => {
    b.onclick = async () => {
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
      try {
        const r = await runEvaluation(b.dataset.id, { k: 5 });
        showBanner(`Run ${r.status}: ${r.passed_cases}/${r.total_cases} passed.`);
        await refreshAll();
      } catch (err) { showBanner(formatSafeError(err), true); }
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
          <span class="ev-badge">${r.passed_cases}/${r.total_cases} passed</span>
          <div style="font-size:0.76rem; color:var(--text-secondary);">Metrics: ${escapeHtml(JSON.stringify(r.metrics_json).slice(0, 140))}</div>
        </div>
        <div style="display:flex; gap:0.35rem;">
          <a class="btn-secondary" href="${baseUrl}/api/v1/evaluations/runs/${encodeURIComponent(r.id)}/export?format=csv" target="_blank" rel="noopener">CSV</a>
          <a class="btn-secondary" href="${baseUrl}/api/v1/evaluations/runs/${encodeURIComponent(r.id)}/export?format=json" target="_blank" rel="noopener">JSON</a>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);font-size:0.86rem;">No benchmark runs executed yet.</p>';

  const runOpts = runs.map((r) => `<option value="${escapeHtml(r.id)}">${escapeHtml(r.target_module)} (${r.passed_cases}/${r.total_cases})</option>`).join('');
  $('ev-cmp-base').innerHTML = runOpts;
  $('ev-cmp-curr').innerHTML = runOpts;
}

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

refreshAll();
