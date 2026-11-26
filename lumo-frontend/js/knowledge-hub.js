import { initShell } from './ui-shell.js';
import {
  createKnowledgeCollection,
  createKnowledgeNote,
  deleteKnowledgeCollection,
  deleteKnowledgeItem,
  fetchKnowledgeDashboard,
  fetchKnowledgeRecommendations,
  formatSafeError,
  getBackendUrl,
  saveKnowledgeItem,
  searchKnowledgeHub,
  updateKnowledgeNote,
} from './api.js';

initShell({ activeModule: 'knowledge-hub', borderedHeader: true });

const $ = (id) => document.getElementById(id);
let activeNoteId = null;
let noteTimer = null;

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('kh-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

function renderItems(items) {
  $('kh-items-list').innerHTML = items.length
    ? items.map((it) => `
      <div class="kh-row">
        <div>
          <span class="kh-badge">${escapeHtml(it.item_type)}</span>
          <strong>${escapeHtml(it.title)}</strong>
          <div style="font-size:0.78rem; color:var(--text-secondary);">
            ${it.tags?.length ? `Tags: ${escapeHtml(it.tags.join(', '))} · ` : ''}${escapeHtml((it.description || it.content || '').slice(0, 120))}
          </div>
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-secondary kh-rec" data-id="${escapeHtml(it.id)}">Connections</button>
          <button type="button" class="btn-secondary kh-del-item" data-id="${escapeHtml(it.id)}">Remove</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No knowledge items match your filter.</p>';

  $('kh-items-list').querySelectorAll('.kh-del-item').forEach((b) => {
    b.onclick = async () => {
      try { await deleteKnowledgeItem(b.dataset.id); await loadDashboard(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
  $('kh-items-list').querySelectorAll('.kh-rec').forEach((b) => {
    b.onclick = async () => {
      try {
        const rec = await fetchKnowledgeRecommendations(b.dataset.id);
        showBanner(`Verified links: ${rec.verified_relationships.length}, Suggested: ${rec.suggested_connections.length}`);
      } catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
}

async function loadDashboard() {
  const baseUrl = getBackendUrl().replace(/\/+$/, '');
  $('kh-exp-md').href = `${baseUrl}/api/v1/knowledge/export?format=markdown`;
  $('kh-exp-json').href = `${baseUrl}/api/v1/knowledge/export?format=json`;

  const dash = await fetchKnowledgeDashboard().catch(() => null);
  if (!dash) return;

  const cols = dash.collections || [];
  $('kh-item-col').innerHTML = '<option value="">No collection</option>' +
    cols.map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)} (${c.item_count})</option>`).join('');

  $('kh-col-list').innerHTML = cols.length
    ? cols.map((c) => `
      <div class="kh-row">
        <span><strong>${escapeHtml(c.name)}</strong> (${c.item_count} items)</span>
        <button type="button" class="btn-secondary kh-del-col" data-id="${escapeHtml(c.id)}">Delete</button>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No collections yet.</p>';

  $('kh-col-list').querySelectorAll('.kh-del-col').forEach((b) => {
    b.onclick = async () => {
      try { await deleteKnowledgeCollection(b.dataset.id); await loadDashboard(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });

  renderItems(dash.recent_items || []);

  const notes = dash.notes || [];
  $('kh-notes-list').innerHTML = notes.length
    ? notes.map((n) => `
      <div class="kh-row">
        <span><strong>${escapeHtml(n.title)}</strong></span>
        <button type="button" class="btn-secondary kh-edit-note" data-id="${escapeHtml(n.id)}" data-title="${escapeHtml(n.title)}" data-content="${escapeHtml(n.content)}">Edit</button>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No notes yet.</p>';

  $('kh-notes-list').querySelectorAll('.kh-edit-note').forEach((b) => {
    b.onclick = () => {
      activeNoteId = b.dataset.id;
      $('kh-note-title').value = b.dataset.title || '';
      $('kh-note-body').value = b.dataset.content || '';
      $('kh-note-status').textContent = 'Editing';
    };
  });

  const tl = dash.timeline || [];
  $('kh-timeline-list').innerHTML = tl.length
    ? tl.map((t) => `
      <div class="kh-row">
        <span><span class="kh-badge">${escapeHtml(t.category)}</span> ${escapeHtml(t.title)}</span>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No activity yet.</p>';
}

$('kh-col-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await createKnowledgeCollection({ name: $('kh-col-name').value.trim() });
    $('kh-col-name').value = '';
    await loadDashboard();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('kh-save-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const tags = $('kh-item-tags').value.split(',').map((t) => t.trim()).filter(Boolean);
    const res = await saveKnowledgeItem({
      item_type: $('kh-item-type').value,
      collection_id: $('kh-item-col').value || null,
      title: $('kh-item-title').value.trim(),
      source_url: $('kh-item-url').value.trim() || null,
      tags,
      content: $('kh-item-content').value.trim(),
    });
    $('kh-item-title').value = '';
    $('kh-item-content').value = '';
    showBanner(res.deduplicated ? 'Item already saved (deduplicated).' : 'Saved to Knowledge Hub.');
    await loadDashboard();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('kh-search-btn').addEventListener('click', async () => {
  try {
    const items = await searchKnowledgeHub({
      query: $('kh-q').value.trim(),
      item_type: $('kh-filter-type').value || null,
    });
    renderItems(items);
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('kh-note-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    if (activeNoteId) {
      await updateKnowledgeNote(activeNoteId, {
        title: $('kh-note-title').value.trim(),
        content: $('kh-note-body').value,
      });
    } else {
      const created = await createKnowledgeNote({
        title: $('kh-note-title').value.trim(),
        content: $('kh-note-body').value,
      });
      activeNoteId = created.id;
    }
    $('kh-note-status').textContent = 'Saved';
    await loadDashboard();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

$('kh-note-body').addEventListener('input', () => {
  if (!activeNoteId) return;
  $('kh-note-status').textContent = 'Unsaved...';
  clearTimeout(noteTimer);
  noteTimer = setTimeout(async () => {
    $('kh-note-status').textContent = 'Saving...';
    try {
      await updateKnowledgeNote(activeNoteId, { content: $('kh-note-body').value });
      $('kh-note-status').textContent = 'Saved';
    } catch {
      $('kh-note-status').textContent = 'Save failed';
    }
  }, 800);
});

loadDashboard();
