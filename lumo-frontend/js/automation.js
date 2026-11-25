/**
 * LUMO Intelligence Automation Engine Controller
 * Dashboard, 6 Reusable Templates, Visual Workflow Builder (add/remove/reorder steps),
 * Execution History & Logs, and Internal Notifications.
 */

import { initShell } from './ui-shell.js';
import { escapeHtml } from './search-data.js';
import {
  isBackendConfigured,
  fetchAutomationTemplates,
  listAutomations,
  createAutomation,
  deleteAutomation,
  runAutomationNow,
  pauseAutomation,
  resumeAutomation,
  duplicateAutomation,
  listAutomationExecutions,
  cancelAutomationExecution,
  listNotifications,
  markNotificationRead,
  deleteNotification,
} from './api.js';

initShell({ activeModule: 'automation', borderedHeader: true });

const state = {
  templates: [],
  automations: [],
  executions: [],
  notifications: [],
  builderSteps: [
    { id: 'step-1', type: 'hybrid_search', config: { query: 'Hybrid Search', limit: 6 } },
    { id: 'step-2', type: 'ai_summarize', config: { instruction: 'Summarize key findings.' } },
    { id: 'step-3', type: 'workspace_save', config: { source_type: 'research_report', tags: ['automation'] } },
  ],
};

const statusTextEl = document.getElementById('auto-status-text');
const tabButtons = Array.from(document.querySelectorAll('[data-auto-tab]'));
const panels = {
  dashboard: document.getElementById('auto-panel-dashboard'),
  builder: document.getElementById('auto-panel-builder'),
  executions: document.getElementById('auto-panel-executions'),
  notifications: document.getElementById('auto-panel-notifications'),
};

function switchTab(name) {
  tabButtons.forEach((b) => b.setAttribute('aria-pressed', String(b.getAttribute('data-auto-tab') === name)));
  Object.entries(panels).forEach(([k, el]) => {
    if (!el) return;
    el.style.display = k === name ? (k === 'dashboard' ? 'flex' : 'block') : 'none';
  });
}

tabButtons.forEach((btn) => btn.addEventListener('click', () => switchTab(btn.getAttribute('data-auto-tab'))));

async function loadAll() {
  if (!isBackendConfigured()) {
    if (statusTextEl) {
      statusTextEl.innerHTML = '<strong>Backend not configured</strong> · Set FastAPI URL in <a href="./settings.html" class="text-link">Settings</a>.';
    }
    return;
  }

  try {
    const [templates, automations, executions, notifications] = await Promise.all([
      fetchAutomationTemplates(),
      listAutomations(),
      listAutomationExecutions(),
      listNotifications(),
    ]);
    state.templates = templates || [];
    state.automations = automations || [];
    state.executions = executions || [];
    state.notifications = notifications || [];

    const activeCnt = state.automations.filter((a) => a.enabled).length;
    const unreadCnt = state.notifications.filter((n) => !n.is_read).length;
    if (statusTextEl) {
      statusTextEl.innerHTML = `<strong>Automation Engine</strong> · ${activeCnt} active / ${state.automations.length} total · ${state.executions.length} recent runs · ${unreadCnt} unread notifications`;
    }

    renderTemplates();
    renderAutomations();
    renderBuilderSteps();
    renderExecutions();
    renderNotifications();
  } catch (err) {
    if (statusTextEl) statusTextEl.textContent = `Automation Engine unavailable: ${err.message}`;
  }
}

function renderTemplates() {
  const mount = document.getElementById('auto-templates-grid');
  if (!mount) return;
  mount.innerHTML = state.templates
    .map(
      (t) => `
      <div class="panel panel--subtle" style="display: flex; flex-direction: column; justify-content: space-between; gap: 0.5rem;">
        <div>
          <div class="field-hint">${escapeHtml(t.trigger_type)} · ${t.steps.length} steps</div>
          <div style="font-weight: 600; margin-top: 0.15rem;">${escapeHtml(t.name)}</div>
          <p style="font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.25rem;">${escapeHtml(t.description)}</p>
        </div>
        <button type="button" class="btn btn--secondary btn--sm" data-use-template="${escapeHtml(t.id)}">Use Template</button>
      </div>
    `
    )
    .join('');
}

function renderAutomations() {
  const mount = document.getElementById('auto-list-mount');
  if (!mount) return;
  if (state.automations.length === 0) {
    mount.innerHTML = '<p class="field-hint">No automations created yet. Pick a template above or open the Workflow Builder.</p>';
    return;
  }
  mount.innerHTML = state.automations
    .map(
      (a) => `
      <div class="panel panel--subtle" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.75rem;">
        <div>
          <div style="font-weight: 600;">${escapeHtml(a.name)} <span class="badge" style="font-size: 0.7rem;">${a.enabled ? 'Active' : 'Paused'}</span></div>
          <div class="field-hint">${escapeHtml(a.trigger_type)} · ${a.steps.length} steps · Last run: ${a.last_run_at ? new Date(a.last_run_at).toLocaleString() : 'Never'}</div>
        </div>
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
          <button type="button" class="btn btn--primary btn--sm" data-run-auto="${escapeHtml(a.id)}">Run Now</button>
          ${
            a.enabled
              ? `<button type="button" class="btn btn--secondary btn--sm" data-pause-auto="${escapeHtml(a.id)}">Pause</button>`
              : `<button type="button" class="btn btn--secondary btn--sm" data-resume-auto="${escapeHtml(a.id)}">Resume</button>`
          }
          <button type="button" class="btn btn--secondary btn--sm" data-dup-auto="${escapeHtml(a.id)}">Duplicate</button>
          <button type="button" class="btn btn--ghost btn--sm" data-del-auto="${escapeHtml(a.id)}">Delete</button>
        </div>
      </div>
    `
    )
    .join('');
}

function renderBuilderSteps() {
  const mount = document.getElementById('builder-steps-list');
  if (!mount) return;
  mount.innerHTML = state.builderSteps
    .map(
      (s, idx) => `
      <div class="panel panel--subtle" style="display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
          <span class="mono" style="font-size: 0.75rem;">#${idx + 1}</span>
          <strong>${escapeHtml(s.type)}</strong>
          <input
            type="text"
            class="text-input"
            style="flex: 1; font-size: 0.8125rem;"
            value="${escapeHtml(s.config.query || s.config.instruction || s.config.condition_type || '')}"
            placeholder="Step query / instruction / condition..."
            data-step-param="${idx}"
          />
        </div>
        <div style="display: flex; gap: 0.25rem;">
          <button type="button" class="btn btn--ghost btn--sm" data-move-up="${idx}" ${idx === 0 ? 'disabled' : ''}>↑</button>
          <button type="button" class="btn btn--ghost btn--sm" data-move-down="${idx}" ${idx === state.builderSteps.length - 1 ? 'disabled' : ''}>↓</button>
          <button type="button" class="btn btn--ghost btn--sm" data-remove-step="${idx}">×</button>
        </div>
      </div>
    `
    )
    .join('');
}

function renderExecutions() {
  const mount = document.getElementById('auto-executions-mount');
  if (!mount) return;
  if (state.executions.length === 0) {
    mount.innerHTML = '<p class="field-hint">No executions recorded yet.</p>';
    return;
  }
  mount.innerHTML = state.executions
    .map(
      (ex) => `
      <div class="panel panel--subtle" style="display: flex; flex-direction: column; gap: 0.4rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <strong>${escapeHtml(ex.automation_name || ex.automation_id)} · ${escapeHtml(ex.status.toUpperCase())}</strong>
          <span class="field-hint">${escapeHtml(ex.trigger_source)} · Step ${ex.current_step_index}/${ex.total_steps}</span>
        </div>
        ${ex.output_summary ? `<div style="font-size: 0.8125rem;">${escapeHtml(ex.output_summary)}</div>` : ''}
        ${ex.error_message ? `<div style="font-size: 0.8125rem; color: #dc2626;">Error: ${escapeHtml(ex.error_message)}</div>` : ''}
        <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
          ${(ex.step_logs || []).map((l) => `<span class="badge" style="font-size: 0.7rem;">${escapeHtml(l.step_type)}: ${escapeHtml(l.status)} (${l.duration_ms}ms)</span>`).join('')}
        </div>
        ${['pending', 'queued', 'running'].includes(ex.status) ? `<button type="button" class="btn btn--secondary btn--sm" style="align-self: flex-start;" data-cancel-exec="${escapeHtml(ex.id)}">Cancel</button>` : ''}
      </div>
    `
    )
    .join('');
}

function renderNotifications() {
  const mount = document.getElementById('auto-notifications-mount');
  if (!mount) return;
  if (state.notifications.length === 0) {
    mount.innerHTML = '<p class="field-hint">No notifications yet.</p>';
    return;
  }
  mount.innerHTML = state.notifications
    .map(
      (n) => `
      <div class="panel panel--subtle" style="display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; opacity: ${n.is_read ? '0.65' : '1'};">
        <div>
          <div style="font-weight: 600; font-size: 0.875rem;">${escapeHtml(n.title)}</div>
          <div style="font-size: 0.8125rem;">${escapeHtml(n.message)}</div>
        </div>
        <div style="display: flex; gap: 0.25rem;">
          ${!n.is_read ? `<button type="button" class="btn btn--secondary btn--sm" data-read-notif="${escapeHtml(n.id)}">Read</button>` : ''}
          <button type="button" class="btn btn--ghost btn--sm" data-del-notif="${escapeHtml(n.id)}">×</button>
        </div>
      </div>
    `
    )
    .join('');
}

// Builder Events
document.getElementById('builder-add-step-btn')?.addEventListener('click', () => {
  const type = document.getElementById('builder-add-step-type').value;
  state.builderSteps.push({ id: `step-${state.builderSteps.length + 1}`, type, config: {} });
  renderBuilderSteps();
});

document.getElementById('builder-steps-list')?.addEventListener('input', (ev) => {
  const inp = ev.target.closest('[data-step-param]');
  if (!inp) return;
  const idx = Number(inp.getAttribute('data-step-param'));
  const step = state.builderSteps[idx];
  if (!step) return;
  if (step.type.includes('search')) step.config.query = inp.value;
  else if (step.type === 'condition') step.config.condition_type = inp.value || 'results_exist';
  else step.config.instruction = inp.value;
});

document.getElementById('auto-builder-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const feedbackEl = document.getElementById('builder-feedback');
  const trigType = document.getElementById('builder-trigger-type').value;
  const trigParam = document.getElementById('builder-trigger-param').value.trim();
  const triggerConfig = {};
  if (trigType === 'scheduled') triggerConfig.interval = trigParam || 'daily';
  else if (trigType === 'event') triggerConfig.event_name = trigParam || 'document_indexed';
  else if (trigParam) triggerConfig.topic = trigParam;

  try {
    await createAutomation({
      name: document.getElementById('builder-name').value.trim(),
      description: document.getElementById('builder-desc').value.trim() || null,
      trigger_type: trigType,
      trigger_config: triggerConfig,
      steps: state.builderSteps,
    });
    feedbackEl.textContent = 'Automation saved!';
    switchTab('dashboard');
    await loadAll();
  } catch (err) {
    feedbackEl.textContent = `Save failed: ${err.message}`;
  }
});

// Delegated clicks
document.addEventListener('click', async (ev) => {
  const tplBtn = ev.target.closest('[data-use-template]');
  if (tplBtn) {
    const tpl = state.templates.find((t) => t.id === tplBtn.getAttribute('data-use-template'));
    if (tpl) {
      document.getElementById('builder-name').value = tpl.name;
      document.getElementById('builder-desc').value = tpl.description;
      document.getElementById('builder-trigger-type').value = tpl.trigger_type;
      state.builderSteps = JSON.parse(JSON.stringify(tpl.steps));
      renderBuilderSteps();
      switchTab('builder');
    }
    return;
  }

  const runBtn = ev.target.closest('[data-run-auto]');
  if (runBtn) {
    runBtn.disabled = true;
    runBtn.textContent = 'Running...';
    await runAutomationNow(runBtn.getAttribute('data-run-auto'), true);
    await loadAll();
    switchTab('executions');
    return;
  }

  const pauseBtn = ev.target.closest('[data-pause-auto]');
  if (pauseBtn) { await pauseAutomation(pauseBtn.getAttribute('data-pause-auto')); await loadAll(); return; }
  const resumeBtn = ev.target.closest('[data-resume-auto]');
  if (resumeBtn) { await resumeAutomation(resumeBtn.getAttribute('data-resume-auto')); await loadAll(); return; }
  const dupBtn = ev.target.closest('[data-dup-auto]');
  if (dupBtn) { await duplicateAutomation(dupBtn.getAttribute('data-dup-auto')); await loadAll(); return; }
  const delBtn = ev.target.closest('[data-del-auto]');
  if (delBtn) { await deleteAutomation(delBtn.getAttribute('data-del-auto')); await loadAll(); return; }
  const cancelBtn = ev.target.closest('[data-cancel-exec]');
  if (cancelBtn) { await cancelAutomationExecution(cancelBtn.getAttribute('data-cancel-exec')); await loadAll(); return; }
  const readNotif = ev.target.closest('[data-read-notif]');
  if (readNotif) { await markNotificationRead(readNotif.getAttribute('data-read-notif')); await loadAll(); return; }
  const delNotif = ev.target.closest('[data-del-notif]');
  if (delNotif) { await deleteNotification(delNotif.getAttribute('data-del-notif')); await loadAll(); return; }

  const upBtn = ev.target.closest('[data-move-up]');
  if (upBtn) {
    const idx = Number(upBtn.getAttribute('data-move-up'));
    if (idx > 0) {
      [state.builderSteps[idx - 1], state.builderSteps[idx]] = [state.builderSteps[idx], state.builderSteps[idx - 1]];
      renderBuilderSteps();
    }
    return;
  }
  const downBtn = ev.target.closest('[data-move-down]');
  if (downBtn) {
    const idx = Number(downBtn.getAttribute('data-move-down'));
    if (idx < state.builderSteps.length - 1) {
      [state.builderSteps[idx + 1], state.builderSteps[idx]] = [state.builderSteps[idx], state.builderSteps[idx + 1]];
      renderBuilderSteps();
    }
    return;
  }
  const remBtn = ev.target.closest('[data-remove-step]');
  if (remBtn) {
    const idx = Number(remBtn.getAttribute('data-remove-step'));
    if (state.builderSteps.length > 1) {
      state.builderSteps.splice(idx, 1);
      renderBuilderSteps();
    }
  }
});

document.getElementById('auto-refresh-btn')?.addEventListener('click', loadAll);

loadAll();
