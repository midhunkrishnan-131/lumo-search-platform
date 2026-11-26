import { initShell } from './ui-shell.js';
import {
  createStudioProject,
  deleteStudioProject,
  fetchStudioProject,
  fetchStudioProjects,
  formatSafeError,
  getBackendUrl,
  studioAIAssist,
  studioPresentationOutline,
  studioSaveToKnowledge,
  updateStudioProject,
} from './api.js';

initShell({ activeModule: 'studio', borderedHeader: true });

const $ = (id) => document.getElementById(id);
let activeProject = null;
let pendingAiText = '';

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('st-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

function renderProject(p) {
  activeProject = p;
  $('st-editor').hidden = false;
  $('st-ed-title').textContent = `${p.title} (v${p.version_number})`;
  $('st-ed-status').textContent = 'Saved';
  $('st-exec-sum').value = p.executive_summary || '';

  const baseUrl = getBackendUrl().replace(/\/+$/, '');
  $('st-prev-link').href = `${baseUrl}/api/v1/studio/projects/${encodeURIComponent(p.id)}/preview`;
  $('st-exp-md').href = `${baseUrl}/api/v1/studio/projects/${encodeURIComponent(p.id)}/export?format=markdown`;
  $('st-exp-html').href = `${baseUrl}/api/v1/studio/projects/${encodeURIComponent(p.id)}/export?format=html`;

  $('st-sections').innerHTML = (p.sections || []).map((sec, idx) => `
    <div style="border:1px solid var(--border); border-radius:8px; padding:0.75rem;">
      <strong>${escapeHtml(sec.title)}</strong>
      <textarea class="st-input st-sec-body" data-idx="${idx}" rows="3" style="margin-top:0.4rem;">${escapeHtml((sec.paragraphs || []).join('\n\n'))}</textarea>
    </div>`).join('');
}

async function refreshProjects() {
  const rows = await fetchStudioProjects().catch(() => []);
  $('st-proj-list').innerHTML = rows.length
    ? rows.map((p) => `
      <div class="st-row">
        <span><strong>${escapeHtml(p.title)}</strong> <span class="st-badge">${escapeHtml(p.document_type)}</span></span>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-secondary st-open" data-id="${escapeHtml(p.id)}">Open</button>
          <button type="button" class="btn-secondary st-del" data-id="${escapeHtml(p.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No Studio projects yet.</p>';

  $('st-proj-list').querySelectorAll('.st-open').forEach((b) => {
    b.onclick = async () => {
      try { renderProject(await fetchStudioProject(b.dataset.id)); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
  $('st-proj-list').querySelectorAll('.st-del').forEach((b) => {
    b.onclick = async () => {
      try { await deleteStudioProject(b.dataset.id); await refreshProjects(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
}

$('st-create-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const p = await createStudioProject({
      title: $('st-title').value.trim(),
      document_type: $('st-type').value,
    });
    $('st-title').value = '';
    renderProject(p);
    await refreshProjects();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('st-save-btn').addEventListener('click', async () => {
  if (!activeProject) return;
  const updatedSecs = (activeProject.sections || []).map((sec, idx) => {
    const ta = document.querySelector(`.st-sec-body[data-idx="${idx}"]`);
    const paras = ta ? ta.value.split('\n\n').map((s) => s.trim()).filter(Boolean) : [];
    return { ...sec, paragraphs: paras };
  });
  try {
    const p = await updateStudioProject(activeProject.id, {
      executive_summary: $('st-exec-sum').value,
      sections: updatedSecs,
      save_version: true,
      change_summary: 'Manual editor save',
    });
    renderProject(p);
    showBanner(`Saved v${p.version_number}.`);
    await refreshProjects();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('st-ai-btn').addEventListener('click', async () => {
  if (!activeProject) return;
  try {
    const res = await studioAIAssist(activeProject.id, {
      action: 'generate_executive_summary',
      input_text: $('st-exec-sum').value || activeProject.title,
    });
    if (res.status === 'preview_ready') {
      pendingAiText = res.preview_text;
      $('st-ai-text').textContent = pendingAiText;
      $('st-ai-preview').hidden = false;
    } else {
      showBanner(res.error || 'AI provider unavailable.', true);
    }
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('st-ai-accept').addEventListener('click', () => {
  $('st-exec-sum').value = pendingAiText;
  $('st-ai-preview').hidden = true;
});
$('st-ai-reject').addEventListener('click', () => {
  pendingAiText = '';
  $('st-ai-preview').hidden = true;
});

$('st-slides-btn').addEventListener('click', async () => {
  if (!activeProject) return;
  try {
    const res = await studioPresentationOutline(activeProject.id);
    showBanner(`Generated presentation outline with ${res.slide_count} slides.`);
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('st-kh-btn').addEventListener('click', async () => {
  if (!activeProject) return;
  try {
    await studioSaveToKnowledge(activeProject.id, {});
    showBanner('Saved deliverable to Knowledge Hub.');
  } catch (err) { showBanner(formatSafeError(err), true); }
});

refreshProjects();
