import { initShell } from './ui-shell.js';
import {
  analyzeIntelligenceDataset,
  analyzeIntelligenceDocument,
  deleteIntelligenceImport,
  fetchIntelligenceDatasetProfile,
  fetchIntelligenceDatasets,
  fetchIntelligenceDocuments,
  fetchIntelligenceImports,
  fetchIntelligenceProvidersStatus,
  fetchIntelligenceReports,
  importIntelligenceUrl,
  retryIntelligenceImport,
  runCrossDocumentAnalysis,
  uploadIntelligenceFile,
  visualizeIntelligenceDataset,
} from './api.js';

initShell({ activeModule: 'intelligence', borderedHeader: true });

const $ = (id) => document.getElementById(id);

function showBanner(msg, isError = false) {
  const el = $('uni-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 5000);
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

let cachedDatasets = [];
let currentSvgMarkup = '';

function renderSvgChart(viz) {
  const container = $('uni-chart-container');
  container.hidden = false;
  const W = 580;
  const H = 290;
  const padL = 54;
  const padR = 20;
  const padT = 36;
  const padB = 54;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const palette = ['#2563eb', '#0ea5e9', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#14b8a6', '#ec4899'];

  let body = `<text x="${W / 2}" y="20" text-anchor="middle" font-size="13" font-weight="600" fill="currentColor">${escapeHtml(viz.title)}</text>`;

  if (viz.chart_type === 'pie') {
    const total = viz.values.reduce((a, b) => a + Math.max(0, b), 0) || 1;
    const cx = 175;
    const cy = 155;
    const r = 95;
    let angle = -Math.PI / 2;
    viz.labels.forEach((lbl, i) => {
      const val = Math.max(0, viz.values[i] || 0);
      const slice = (val / total) * Math.PI * 2;
      const x1 = cx + r * Math.cos(angle);
      const y1 = cy + r * Math.sin(angle);
      const x2 = cx + r * Math.cos(angle + slice);
      const y2 = cy + r * Math.sin(angle + slice);
      const large = slice > Math.PI ? 1 : 0;
      const color = palette[i % palette.length];
      body += `<path d="M ${cx} ${cy} L ${x1.toFixed(1)} ${y1.toFixed(1)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z" fill="${color}" stroke="#fff" stroke-width="1"/>`;
      if (i < 8) {
        const ly = 56 + i * 24;
        body += `<rect x="310" y="${ly - 10}" width="12" height="12" rx="2" fill="${color}"/><text x="328" y="${ly}" font-size="11" fill="currentColor">${escapeHtml(lbl.slice(0, 22))} (${val})</text>`;
      }
      angle += slice;
    });
  } else if (viz.chart_type === 'scatter') {
    const pts = viz.points || [];
    if (!pts.length) {
      body += `<text x="${W / 2}" y="${H / 2}" text-anchor="middle" fill="currentColor">No numeric point pairs available.</text>`;
    } else {
      const xs = pts.map((p) => p.x);
      const ys = pts.map((p) => p.y);
      const minX = Math.min(...xs), maxX = Math.max(...xs) || minX + 1;
      const minY = Math.min(...ys), maxY = Math.max(...ys) || minY + 1;
      body += `<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.35"/>`;
      body += `<line x1="${padL}" y1="${padT + plotH}" x2="${padL + plotW}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.35"/>`;
      pts.forEach((p) => {
        const cx = padL + ((p.x - minX) / (maxX - minX || 1)) * plotW;
        const cy = padT + plotH - ((p.y - minY) / (maxY - minY || 1)) * plotH;
        body += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="4" fill="#2563eb" fill-opacity="0.75"/>`;
      });
      body += `<text x="${W / 2}" y="${H - 10}" text-anchor="middle" font-size="11" fill="currentColor">${escapeHtml(viz.x_label)}</text>`;
      body += `<text x="14" y="${H / 2}" text-anchor="middle" font-size="11" fill="currentColor" transform="rotate(-90 14 ${H / 2})">${escapeHtml(viz.y_label)}</text>`;
    }
  } else {
    const vals = viz.values || [];
    const lbls = viz.labels || [];
    const maxV = Math.max(...vals, 1);
    body += `<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.35"/>`;
    body += `<line x1="${padL}" y1="${padT + plotH}" x2="${padL + plotW}" y2="${padT + plotH}" stroke="currentColor" stroke-opacity="0.35"/>`;
    if (viz.chart_type === 'line' && vals.length > 0) {
      const stepX = vals.length > 1 ? plotW / (vals.length - 1) : plotW;
      const polyPts = vals.map((v, i) => `${(padL + i * stepX).toFixed(1)},${(padT + plotH - (v / maxV) * plotH).toFixed(1)}`).join(' ');
      body += `<polyline fill="none" stroke="#2563eb" stroke-width="2.5" points="${polyPts}"/>`;
      vals.forEach((v, i) => {
        const cx = padL + i * stepX;
        const cy = padT + plotH - (v / maxV) * plotH;
        body += `<circle cx="${cx.toFixed(1)}" cy="${cy.toFixed(1)}" r="3.5" fill="#2563eb"/>`;
      });
    } else {
      const n = Math.max(vals.length, 1);
      const bw = Math.max(8, (plotW / n) * 0.7);
      const gap = plotW / n;
      vals.forEach((v, i) => {
        const bh = Math.max(1, (v / maxV) * plotH);
        const x = padL + i * gap + (gap - bw) / 2;
        const y = padT + plotH - bh;
        body += `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="3" fill="${palette[i % palette.length]}"/>`;
        if (i < 12) {
          body += `<text x="${(x + bw / 2).toFixed(1)}" y="${padT + plotH + 14}" text-anchor="middle" font-size="9" fill="currentColor">${escapeHtml((lbls[i] || '').slice(0, 10))}</text>`;
        }
      });
    }
    body += `<text x="${W / 2}" y="${H - 10}" text-anchor="middle" font-size="11" fill="currentColor">${escapeHtml(viz.x_label)}</text>`;
    body += `<text x="14" y="${H / 2}" text-anchor="middle" font-size="11" fill="currentColor" transform="rotate(-90 14 ${H / 2})">${escapeHtml(viz.y_label)}</text>`;
  }

  currentSvgMarkup = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" width="100%" style="max-width:${W}px;height:auto;">${body}</svg>`;
  container.innerHTML = currentSvgMarkup;
  $('uni-chart-export-btn').hidden = false;

  const sugWrap = $('uni-chart-suggestions');
  sugWrap.innerHTML = '';
  (viz.suggestions || []).forEach((s) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn-secondary';
    btn.style.fontSize = '0.78rem';
    btn.textContent = `${s.chart_type.toUpperCase()}: ${s.title}`;
    btn.onclick = () => {
      $('uni-chart-type').value = s.chart_type;
      if (s.x_column) $('uni-chart-x').value = s.x_column;
      if (s.y_column) $('uni-chart-y').value = s.y_column;
      renderSelectedChart();
    };
    sugWrap.appendChild(btn);
  });
}

async function renderSelectedChart() {
  const dsId = $('uni-ds-select').value;
  if (!dsId) return;
  try {
    const viz = await visualizeIntelligenceDataset(dsId, {
      chart_type: $('uni-chart-type').value,
      x_column: $('uni-chart-x').value || null,
      y_column: $('uni-chart-y').value || null,
      limit: 15,
    });
    renderSvgChart(viz);
  } catch (err) {
    showBanner(err.message, true);
  }
}

async function loadDatasetDetails(dsId, sheet = '') {
  if (!dsId) return;
  const ds = await fetchIntelligenceDatasetProfile(dsId, sheet);
  $('uni-ds-summary').textContent = ds.summary || `${ds.row_count} rows, ${ds.column_count} cols`;

  const sheetSel = $('uni-ds-sheet');
  if (ds.sheet_names && ds.sheet_names.length > 1) {
    sheetSel.hidden = false;
    sheetSel.innerHTML = ds.sheet_names.map((s) => `<option value="${escapeHtml(s)}" ${s === ds.active_sheet ? 'selected' : ''}>Sheet: ${escapeHtml(s)}</option>`).join('');
  } else {
    sheetSel.hidden = true;
  }

  const cols = ds.columns_json || [];
  const xSel = $('uni-chart-x');
  const ySel = $('uni-chart-y');
  xSel.innerHTML = cols.map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${c.inferred_type})</option>`).join('');
  ySel.innerHTML = `<option value="">(Count)</option>` + cols.map((c) => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)} (${c.inferred_type})</option>`).join('');

  const profEl = $('uni-ds-profile');
  profEl.hidden = false;
  const obs = (ds.profile_json?.quality_observations || []).join('\n- ');
  const colLines = cols.map((c) => `• ${c.name} [${c.inferred_type}] — missing: ${c.missing_count} (${c.missing_pct}%), unique: ${c.unique_count}${c.numeric_stats ? `, mean=${c.numeric_stats.mean}, min=${c.numeric_stats.min}, max=${c.numeric_stats.max}` : ''}`).join('\n');
  profEl.textContent = `Data Quality Observations:\n- ${obs}\n\nColumn Profiles:\n${colLines}`;
}

async function refreshAll() {
  const [providers, imports, docs, datasets, reports] = await Promise.all([
    fetchIntelligenceProvidersStatus().catch(() => null),
    fetchIntelligenceImports().catch(() => []),
    fetchIntelligenceDocuments().catch(() => []),
    fetchIntelligenceDatasets().catch(() => []),
    fetchIntelligenceReports().catch(() => []),
  ]);

  $('stat-imports').textContent = String(imports.length);
  $('stat-docs').textContent = String(docs.length);
  $('stat-datasets').textContent = String(datasets.length);
  $('stat-reports').textContent = String(reports.length);

  if (providers) {
    const activeList = Object.entries(providers.providers || {})
      .filter(([, v]) => v.configured && !v.blocked_by_privacy_mode)
      .map(([k]) => k);
    $('stat-providers').textContent = activeList.length ? activeList.join(', ') : 'Deterministic / Local';
  }

  const docSel = $('uni-doc-select');
  docSel.innerHTML = docs.length
    ? docs.map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.title)} [${escapeHtml(d.content_category)}]</option>`).join('')
    : '<option value="">No documents ingested yet</option>';

  const crossList = $('uni-cross-list');
  crossList.innerHTML = docs.length
    ? docs.map((d) => `<label><input type="checkbox" class="uni-cross-chk" value="${escapeHtml(d.id)}"/> ${escapeHtml(d.title)} (${escapeHtml(d.file_type || d.source_type)})</label>`).join('')
    : '<span style="color:var(--text-secondary);font-size:0.85rem;">Ingest 2+ documents or datasets to compare.</span>';

  cachedDatasets = datasets;
  const dsSel = $('uni-ds-select');
  dsSel.innerHTML = datasets.length
    ? datasets.map((d) => `<option value="${escapeHtml(d.id)}">${escapeHtml(d.title)} (${d.row_count}×${d.column_count})</option>`).join('')
    : '<option value="">No datasets ingested yet</option>';
  if (datasets.length) {
    await loadDatasetDetails(datasets[0].id);
  }

  const impEl = $('uni-imports-list');
  impEl.innerHTML = imports.length
    ? imports.map((j) => `
      <div style="padding:0.65rem 0; border-bottom:1px solid var(--border-subtle); display:flex; justify-content:space-between; gap:0.5rem; align-items:center;">
        <div>
          <strong>${escapeHtml(j.file_name || j.source_url || j.id)}</strong>
          <div style="font-size:0.8rem; color:var(--text-secondary);">${escapeHtml(j.format_type)} · ${escapeHtml(j.content_category)} · ${escapeHtml(j.status)} (${j.progress_pct}%)</div>
          ${j.error_message ? `<div style="font-size:0.78rem; color:#dc2626;">${escapeHtml(j.error_message)}</div>` : ''}
        </div>
        <div class="uni-row-actions">
          ${j.status === 'failed' ? `<button type="button" class="btn-secondary uni-retry-btn" data-id="${escapeHtml(j.id)}">Retry</button>` : ''}
          <button type="button" class="btn-secondary uni-del-btn" data-id="${escapeHtml(j.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);">No import jobs yet.</p>';

  impEl.querySelectorAll('.uni-retry-btn').forEach((b) => {
    b.onclick = async () => {
      try { await retryIntelligenceImport(b.dataset.id); showBanner('Import retried.'); await refreshAll(); }
      catch (err) { showBanner(err.message, true); }
    };
  });
  impEl.querySelectorAll('.uni-del-btn').forEach((b) => {
    b.onclick = async () => {
      try { await deleteIntelligenceImport(b.dataset.id); showBanner('Import and linked records deleted.'); await refreshAll(); }
      catch (err) { showBanner(err.message, true); }
    };
  });

  const repEl = $('uni-reports-list');
  repEl.innerHTML = reports.length
    ? reports.map((r) => `
      <div style="padding:0.65rem 0; border-bottom:1px solid var(--border-subtle);">
        <strong>${escapeHtml(r.title)}</strong>
        <span class="uni-chip">${escapeHtml(r.report_type)} · ${escapeHtml(r.provider || 'deterministic')}</span>
        <div style="font-size:0.84rem; color:var(--text-secondary); margin-top:0.25rem;">${escapeHtml((r.summary || '').slice(0, 220))}${(r.summary || '').length > 220 ? '...' : ''}</div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary);">No intelligence reports generated yet.</p>';
}

$('uni-file-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = $('uni-file-input').files?.[0];
  if (!file) return;
  try {
    await uploadIntelligenceFile(file, {
      classifyWithAi: $('uni-classify-ai').checked,
      provider: $('uni-provider-select').value,
    });
    $('uni-file-input').value = '';
    showBanner(`Processed '${file.name}' successfully.`);
    await refreshAll();
  } catch (err) {
    showBanner(err.message, true);
  }
});

$('uni-url-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await importIntelligenceUrl({
      url: $('uni-url-input').value.trim(),
      title: $('uni-url-title').value.trim() || null,
      classify_with_ai: $('uni-classify-ai').checked,
      provider: $('uni-provider-select').value,
    });
    $('uni-url-input').value = '';
    $('uni-url-title').value = '';
    showBanner('Web URL imported and indexed.');
    await refreshAll();
  } catch (err) {
    showBanner(err.message, true);
  }
});

$('uni-doc-analyze-btn').addEventListener('click', async () => {
  const docId = $('uni-doc-select').value;
  if (!docId) return;
  const out = $('uni-doc-output');
  out.hidden = false;
  out.textContent = 'Analyzing document...';
  try {
    const rep = await analyzeIntelligenceDocument(docId, {
      mode: $('uni-doc-mode').value,
      question: $('uni-doc-question').value.trim() || null,
      provider: $('uni-provider-select').value,
    });
    out.textContent = `[Provider: ${rep.provider}]\n\n${rep.summary}`;
    await refreshAll();
  } catch (err) {
    out.textContent = err.message;
  }
});

$('uni-cross-btn').addEventListener('click', async () => {
  const ids = Array.from(document.querySelectorAll('.uni-cross-chk:checked')).map((c) => c.value);
  if (ids.length < 2) {
    showBanner('Select at least 2 documents or datasets to compare.', true);
    return;
  }
  const out = $('uni-cross-output');
  out.hidden = false;
  out.textContent = 'Running cross-document intelligence...';
  try {
    const rep = await runCrossDocumentAnalysis({
      source_ids: ids,
      question: $('uni-cross-question').value.trim() || null,
      provider: $('uni-provider-select').value,
    });
    out.textContent = `[Provider: ${rep.provider}]\n\n${rep.summary}`;
    await refreshAll();
  } catch (err) {
    out.textContent = err.message;
  }
});

$('uni-ds-select').addEventListener('change', async () => {
  await loadDatasetDetails($('uni-ds-select').value);
});

$('uni-ds-sheet').addEventListener('change', async () => {
  await loadDatasetDetails($('uni-ds-select').value, $('uni-ds-sheet').value);
});

$('uni-ds-ask-btn').addEventListener('click', async () => {
  const dsId = $('uni-ds-select').value;
  const q = $('uni-ds-question').value.trim();
  if (!dsId || !q) return;
  const out = $('uni-ds-answer');
  out.hidden = false;
  out.textContent = 'Computing deterministic metrics & analyzing...';
  try {
    const rep = await analyzeIntelligenceDataset(dsId, {
      question: q,
      provider: $('uni-provider-select').value,
    });
    out.textContent = `[Provider: ${rep.provider}]\n\n${rep.summary}`;
    await refreshAll();
  } catch (err) {
    out.textContent = err.message;
  }
});

$('uni-chart-btn').addEventListener('click', renderSelectedChart);
$('uni-chart-export-btn').addEventListener('click', () => {
  if (!currentSvgMarkup) return;
  const blob = new Blob([currentSvgMarkup], { type: 'image/svg+xml' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'lumo-chart.svg';
  a.click();
});

refreshAll();
