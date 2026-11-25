import { initShell } from './ui-shell.js';
import {
  createOpsBackup,
  fetchDashboardActivity,
  fetchDashboardAiStatus,
  fetchDashboardAutomations,
  fetchDashboardGuardian,
  fetchDashboardKnowledge,
  fetchDashboardNotifications,
  fetchDashboardOverview,
  fetchDashboardResearch,
  fetchDashboardSystemHealth,
  fetchIntelligenceImports,
  fetchOpsBackups,
  fetchOpsRelease,
  markDashboardNotificationRead,
  requestFastApi,
  retryIntelligenceImport,
} from './api.js';

initShell({ activeModule: 'command-center', borderedHeader: true });

const $ = (id) => document.getElementById(id);
const LAYOUT_KEY = 'lumo_cc_layout_v1';

const DEFAULT_PANELS = [
  { id: 'activity', title: 'Unified Activity Feed', visible: true },
  { id: 'research', title: 'Research Overview', visible: true },
  { id: 'automations', title: 'Automation Overview', visible: true },
  { id: 'ai', title: 'AI & Local AI Overview', visible: true },
  { id: 'data', title: 'Universal Data Intelligence', visible: true },
  { id: 'knowledge', title: 'Knowledge & Adaptive Overview', visible: true },
  { id: 'guardian', title: 'Download Guardian & Search', visible: true },
  { id: 'health', title: 'System Health & Notifications', visible: true },
];

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function safeHref(url) {
  const s = String(url ?? '').trim();
  if (/^(\.\/|\/|https?:\/\/)/i.test(s)) return escapeHtml(s);
  return '#';
}

function showBanner(msg, isError = false) {
  const el = $('cc-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

function loadLayout() {
  try {
    const raw = localStorage.getItem(LAYOUT_KEY);
    if (!raw) return DEFAULT_PANELS.map((p) => ({ ...p }));
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed) || !parsed.length) return DEFAULT_PANELS.map((p) => ({ ...p }));
    const known = new Map(DEFAULT_PANELS.map((p) => [p.id, p]));
    const merged = parsed.filter((p) => known.has(p.id)).map((p) => ({ ...known.get(p.id), visible: Boolean(p.visible) }));
    DEFAULT_PANELS.forEach((p) => {
      if (!merged.some((m) => m.id === p.id)) merged.push({ ...p });
    });
    return merged;
  } catch {
    return DEFAULT_PANELS.map((p) => ({ ...p }));
  }
}

function saveLayout(layout) {
  localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
}

let panelLayout = loadLayout();
let activityState = { category: 'all', offset: 0, limit: 8 };

function initWelcome() {
  const now = new Date();
  const hr = now.getHours();
  const part = hr < 12 ? 'Good morning' : hr < 18 ? 'Good afternoon' : 'Good evening';
  $('cc-greeting').textContent = `${part} — LUMO Command Center`;
  $('cc-date-sub').textContent = now.toLocaleDateString(undefined, {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  }) + ' · Real-time operational view across all LUMO engines.';
}

function buildPanelShells() {
  const grid = $('cc-panels-grid');
  grid.innerHTML = '';
  panelLayout.forEach((p) => {
    if (!p.visible) return;
    const sec = document.createElement('section');
    sec.className = 'panel-card';
    sec.id = `panel-${p.id}`;
    sec.innerHTML = `<div class="cc-panel-head"><h2>${escapeHtml(p.title)}</h2></div><div id="body-${p.id}" class="cc-empty">Loading...</div>`;
    grid.appendChild(sec);
  });
}

function renderCustomizer() {
  const list = $('cc-customizer-list');
  list.innerHTML = '';
  panelLayout.forEach((p, idx) => {
    const row = document.createElement('div');
    row.className = 'cc-custom-row';
    row.innerHTML = `
      <label><input type="checkbox" data-idx="${idx}" class="cc-vis-chk" ${p.visible ? 'checked' : ''}/> ${escapeHtml(p.title)}</label>
      <div style="display:flex; gap:0.35rem;">
        <button type="button" class="btn-secondary cc-up-btn" data-idx="${idx}" ${idx === 0 ? 'disabled' : ''}>Up</button>
        <button type="button" class="btn-secondary cc-dn-btn" data-idx="${idx}" ${idx === panelLayout.length - 1 ? 'disabled' : ''}>Down</button>
      </div>`;
    list.appendChild(row);
  });

  list.querySelectorAll('.cc-vis-chk').forEach((chk) => {
    chk.onchange = () => {
      panelLayout[Number(chk.dataset.idx)].visible = chk.checked;
      saveLayout(panelLayout);
      loadAllData();
    };
  });
  list.querySelectorAll('.cc-up-btn').forEach((btn) => {
    btn.onclick = () => {
      const i = Number(btn.dataset.idx);
      if (i > 0) {
        [panelLayout[i - 1], panelLayout[i]] = [panelLayout[i], panelLayout[i - 1]];
        saveLayout(panelLayout);
        renderCustomizer();
        loadAllData();
      }
    };
  });
  list.querySelectorAll('.cc-dn-btn').forEach((btn) => {
    btn.onclick = () => {
      const i = Number(btn.dataset.idx);
      if (i < panelLayout.length - 1) {
        [panelLayout[i + 1], panelLayout[i]] = [panelLayout[i], panelLayout[i + 1]];
        saveLayout(panelLayout);
        renderCustomizer();
        loadAllData();
      }
    };
  });
}

async function renderActivityPanel() {
  const el = $('body-activity');
  if (!el) return;
  try {
    const data = await fetchDashboardActivity(activityState);
    const cats = ['all', 'search', 'research', 'intelligence', 'automation', 'guardian'];
    el.innerHTML = `
      <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.65rem;">
        ${cats.map((c) => `<button type="button" class="${c === activityState.category ? 'btn-primary' : 'btn-secondary'} cc-act-cat" data-cat="${c}" style="font-size:0.76rem;">${c.toUpperCase()}</button>`).join('')}
      </div>
      <div>
        ${data.items.length ? data.items.map((it) => `
          <div class="cc-list-row">
            <div>
              <a href="${safeHref(it.href)}" style="font-weight:600;">${escapeHtml(it.title)}</a>
              <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(it.detail)}</div>
            </div>
            <span class="cc-badge">${escapeHtml(it.status)}</span>
          </div>`).join('') : '<p class="cc-empty">No recent activity for this filter.</p>'}
      </div>
      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.6rem; font-size:0.8rem;">
        <span>Total: ${data.total}</span>
        <div style="display:flex; gap:0.4rem;">
          <button type="button" class="btn-secondary" id="cc-act-prev" ${activityState.offset === 0 ? 'disabled' : ''}>Prev</button>
          <button type="button" class="btn-secondary" id="cc-act-next" ${activityState.offset + activityState.limit >= data.total ? 'disabled' : ''}>Next</button>
        </div>
      </div>`;

    el.querySelectorAll('.cc-act-cat').forEach((b) => {
      b.onclick = () => {
        activityState.category = b.dataset.cat;
        activityState.offset = 0;
        renderActivityPanel();
      };
    });
    const prev = $('cc-act-prev');
    const next = $('cc-act-next');
    if (prev) prev.onclick = () => { activityState.offset = Math.max(0, activityState.offset - activityState.limit); renderActivityPanel(); };
    if (next) next.onclick = () => { activityState.offset += activityState.limit; renderActivityPanel(); };
  } catch (err) {
    el.textContent = `Unavailable: ${err.message}`;
  }
}

async function loadAllData() {
  buildPanelShells();

  const tasks = await Promise.allSettled([
    fetchDashboardOverview(),
    fetchDashboardResearch(5),
    fetchDashboardAutomations(5),
    fetchDashboardAiStatus(),
    fetchIntelligenceImports(5),
    fetchDashboardKnowledge(5),
    fetchDashboardGuardian(5),
    fetchDashboardSystemHealth(false),
    fetchDashboardNotifications(6, false),
    fetchOpsRelease(),
    fetchOpsBackups(),
  ]);

  if (tasks[0].status === 'fulfilled') {
    const m = tasks[0].value.metrics || {};
    $('kpi-web-docs').textContent = String(m.indexed_web_documents ?? 0);
    $('kpi-ws-docs').textContent = String(m.personal_documents ?? 0);
    $('kpi-research').textContent = String(m.research_reports ?? 0);
    $('kpi-kg').textContent = String(m.knowledge_graph_entities ?? 0);
    $('kpi-autos').textContent = String(m.active_automations ?? 0);
    $('kpi-datasets').textContent = String((m.datasets ?? 0) + (m.ai_reports ?? 0));
    $('kpi-notifs').textContent = String(m.unread_notifications ?? 0);
  }

  renderActivityPanel();

  if ($('body-research')) {
    if (tasks[1].status === 'fulfilled') {
      const r = tasks[1].value;
      $('body-research').innerHTML = `
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.6rem;">
          <span class="cc-badge">Active: ${r.counts.active}</span>
          <span class="cc-badge">Completed: ${r.counts.completed}</span>
          <span class="cc-badge">Failed: ${r.counts.failed}</span>
          <a href="./research.html" style="margin-left:auto; font-size:0.82rem;">Open Research →</a>
        </div>
        ${r.recent.length ? r.recent.map((s) => `
          <div class="cc-list-row">
            <span>${escapeHtml(s.topic)}</span>
            <span class="cc-badge">${escapeHtml(s.status)}</span>
          </div>`).join('') : '<p class="cc-empty">No research sessions yet.</p>'}`;
    } else {
      $('body-research').textContent = 'Research overview unavailable.';
    }
  }

  if ($('body-automations')) {
    if (tasks[2].status === 'fulfilled') {
      const a = tasks[2].value;
      $('body-automations').innerHTML = `
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.6rem;">
          <span class="cc-badge">Active: ${a.counts.active}</span>
          <span class="cc-badge">Paused: ${a.counts.paused}</span>
          <span class="cc-badge">Failed Runs: ${a.counts.failed_executions}</span>
          <a href="./automation.html" style="margin-left:auto; font-size:0.82rem;">Manage →</a>
        </div>
        ${a.automations.length ? a.automations.map((au) => `
          <div class="cc-list-row">
            <div>
              <strong>${escapeHtml(au.name)}</strong>
              <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(au.trigger_type)} · ${escapeHtml(au.workflow_type)}</div>
            </div>
            <div style="display:flex; gap:0.35rem;">
              <button type="button" class="btn-secondary cc-run-auto" data-id="${escapeHtml(au.id)}">Run</button>
              <button type="button" class="btn-secondary cc-toggle-auto" data-id="${escapeHtml(au.id)}" data-enabled="${au.enabled}">${au.enabled ? 'Pause' : 'Resume'}</button>
            </div>
          </div>`).join('') : '<p class="cc-empty">No automations configured yet.</p>'}`;

      $('body-automations').querySelectorAll('.cc-run-auto').forEach((b) => {
        b.onclick = async () => {
          try { await requestFastApi(`/api/v1/automations/${encodeURIComponent(b.dataset.id)}/run`, { method: 'POST' }); showBanner('Automation triggered.'); loadAllData(); }
          catch (err) { showBanner(err.message, true); }
        };
      });
      $('body-automations').querySelectorAll('.cc-toggle-auto').forEach((b) => {
        b.onclick = async () => {
          const act = b.dataset.enabled === 'true' ? 'pause' : 'resume';
          try { await requestFastApi(`/api/v1/automations/${encodeURIComponent(b.dataset.id)}/${act}`, { method: 'POST' }); showBanner(`Automation ${act}d.`); loadAllData(); }
          catch (err) { showBanner(err.message, true); }
        };
      });
    } else {
      $('body-automations').textContent = 'Automation overview unavailable.';
    }
  }

  if ($('body-ai')) {
    if (tasks[3].status === 'fulfilled') {
      const ai = tasks[3].value;
      const provs = Object.entries(ai.router?.providers || {}).map(([name, info]) =>
        `<span class="cc-badge">${escapeHtml(name)}: ${info.blocked_by_privacy_mode ? 'blocked (local-only)' : info.configured ? 'configured' : 'not configured'}</span>`
      ).join(' ');
      $('body-ai').innerHTML = `
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.6rem;">${provs}</div>
        ${(ai.recent_tasks || []).length ? ai.recent_tasks.map((t) => `
          <div class="cc-list-row">
            <span>${escapeHtml(t.title)}</span>
            <span class="cc-badge">${escapeHtml(t.provider || 'deterministic')}</span>
          </div>`).join('') : '<p class="cc-empty">No recent AI analysis reports.</p>'}`;
    } else {
      $('body-ai').textContent = 'AI status unavailable.';
    }
  }

  if ($('body-data')) {
    if (tasks[4].status === 'fulfilled') {
      const imps = tasks[4].value || [];
      $('body-data').innerHTML = `
        <div style="display:flex; justify-content:space-between; margin-bottom:0.5rem;">
          <span class="cc-badge">Recent Imports: ${imps.length}</span>
          <a href="./intelligence.html" style="font-size:0.82rem;">Open Data Engine →</a>
        </div>
        ${imps.length ? imps.map((j) => `
          <div class="cc-list-row">
            <div>
              <strong>${escapeHtml(j.file_name || j.source_url || j.id)}</strong>
              <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(j.format_type)} · ${escapeHtml(j.content_category)}</div>
            </div>
            <div style="display:flex; gap:0.35rem; align-items:center;">
              <span class="cc-badge">${escapeHtml(j.status)}</span>
              ${j.status === 'failed' ? `<button type="button" class="btn-secondary cc-retry-imp" data-id="${escapeHtml(j.id)}">Retry</button>` : ''}
            </div>
          </div>`).join('') : '<p class="cc-empty">No files or datasets imported yet.</p>'}`;

      $('body-data').querySelectorAll('.cc-retry-imp').forEach((b) => {
        b.onclick = async () => {
          try { await retryIntelligenceImport(b.dataset.id); showBanner('Import retried.'); loadAllData(); }
          catch (err) { showBanner(err.message, true); }
        };
      });
    } else {
      $('body-data').textContent = 'Universal Data overview unavailable.';
    }
  }

  if ($('body-knowledge')) {
    if (tasks[5].status === 'fulfilled') {
      const k = tasks[5].value;
      $('body-knowledge').innerHTML = `
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.6rem;">
          <span class="cc-badge">Entities: ${k.graph.entities}</span>
          <span class="cc-badge">Relationships: ${k.graph.relationships}</span>
          <span class="cc-badge">Personalization: ${k.personalization_enabled ? 'On' : 'Opt-Out'}</span>
          <a href="./workspace.html" style="margin-left:auto; font-size:0.82rem;">Workspace →</a>
        </div>
        ${(k.recent_items || []).length ? k.recent_items.map((it) => `
          <div class="cc-list-row">
            <span>${escapeHtml(it.title)}</span>
            <span class="cc-badge">${escapeHtml(it.source_type)}</span>
          </div>`).join('') : '<p class="cc-empty">No workspace items yet.</p>'}`;
    } else {
      $('body-knowledge').textContent = 'Knowledge overview unavailable.';
    }
  }

  if ($('body-guardian')) {
    if (tasks[6].status === 'fulfilled') {
      const g = tasks[6].value;
      $('body-guardian').innerHTML = `
        <div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.5rem;">
          <span class="cc-badge">Analyses: ${g.total}</span>
          <span class="cc-badge">High/Critical: ${g.high_risk_warnings}</span>
          <a href="./guardian.html" style="margin-left:auto; font-size:0.82rem;">Open Guardian →</a>
        </div>
        <p style="font-size:0.76rem; color:var(--text-secondary); margin:0.25rem 0 0.5rem;">${escapeHtml(g.disclaimer)}</p>
        ${(g.recent || []).length ? g.recent.map((x) => `
          <div class="cc-list-row">
            <span>${escapeHtml(x.target)}</span>
            <span class="cc-badge">${escapeHtml(x.risk_level)} (${x.risk_score})</span>
          </div>`).join('') : '<p class="cc-empty">No Guardian analyses yet.</p>'}`;
    } else {
      $('body-guardian').textContent = 'Guardian overview unavailable.';
    }
  }

  if ($('body-health')) {
    const hOk = tasks[7].status === 'fulfilled' ? tasks[7].value : null;
    const nOk = tasks[8].status === 'fulfilled' ? tasks[8].value : null;
    const relOk = tasks[9]?.status === 'fulfilled' ? tasks[9].value : null;
    const bkpOk = tasks[10]?.status === 'fulfilled' ? tasks[10].value : [];
    let html = '';
    if (hOk) {
      html += `<div style="display:flex; gap:0.4rem; flex-wrap:wrap; margin-bottom:0.65rem;">
        <span class="cc-badge">Backend: ${escapeHtml(hOk.status)}</span>
        <span class="cc-badge">DB: ${escapeHtml(hOk.database?.status || 'unknown')}</span>
        <span class="cc-badge">Qdrant: ${hOk.vector_store?.qdrant_configured ? 'configured' : 'none'}</span>
        <span class="cc-badge">Ollama: ${hOk.ai_providers?.ollama_reachable ? 'reachable' : 'offline'}</span>
        ${relOk ? `<span class="cc-badge">v${escapeHtml(relOk.version)} · Schema v${relOk.schema_version}</span>` : ''}
        <span class="cc-badge">Backups: ${bkpOk.length}</span>
        <button type="button" class="btn-secondary" id="cc-create-backup-btn" style="font-size:0.74rem;">Create Backup</button>
      </div>`;
    } else {
      html += '<p class="cc-empty">System health unavailable.</p>';
    }
    if (nOk && nOk.items?.length) {
      html += `<div><strong>Recent Notifications</strong></div>`;
      html += nOk.items.map((n) => `
        <div class="cc-list-row">
          <div>
            <strong>${escapeHtml(n.title)}</strong>
            <div style="font-size:0.78rem; color:var(--text-secondary);">${escapeHtml(n.message)}</div>
          </div>
          ${n.is_read ? '<span class="cc-badge">Read</span>' : `<button type="button" class="btn-secondary cc-read-notif" data-id="${escapeHtml(n.id)}">Mark Read</button>`}
        </div>`).join('');
    } else {
      html += '<p class="cc-empty">No notifications.</p>';
    }
    $('body-health').innerHTML = html;
    $('body-health').querySelectorAll('.cc-read-notif').forEach((b) => {
      b.onclick = async () => {
        await markDashboardNotificationRead(b.dataset.id).catch(() => {});
        loadAllData();
      };
    });
    const bkpBtn = $('cc-create-backup-btn');
    if (bkpBtn) {
      bkpBtn.onclick = async () => {
        try {
          const res = await createOpsBackup('command_center');
          showBanner(`Backup created: ${res.backup_id}`);
          loadAllData();
        } catch (err) {
          showBanner(err.message, true);
        }
      };
    }
  }
}

$('cc-search-form').addEventListener('submit', (e) => {
  e.preventDefault();
  const q = $('cc-search-input').value.trim();
  const mode = $('cc-search-mode').value;
  if (!q) return;
  if (mode === 'workspace') {
    window.location.href = `./workspace.html?q=${encodeURIComponent(q)}`;
  } else {
    window.location.href = `./results.html?q=${encodeURIComponent(q)}&mode=${encodeURIComponent(mode)}`;
  }
});

$('cc-refresh-btn').addEventListener('click', loadAllData);
$('cc-customize-btn').addEventListener('click', () => {
  const box = $('cc-customizer');
  box.hidden = !box.hidden;
  if (!box.hidden) renderCustomizer();
});
$('cc-reset-layout-btn').addEventListener('click', () => {
  panelLayout = DEFAULT_PANELS.map((p) => ({ ...p }));
  saveLayout(panelLayout);
  renderCustomizer();
  loadAllData();
  showBanner('Dashboard layout reset to default.');
});

initWelcome();
loadAllData();
