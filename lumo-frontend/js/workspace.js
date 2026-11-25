/**
 * LUMO Personal Knowledge Workspace Controller
 * Dashboard, Personal Hybrid Search, Grounded AI Q&A, Collections,
 * Markdown Notes with Autosave, Document/URL Import, Annotations & Graph links.
 */

import { initShell } from './ui-shell.js';
import { escapeHtml } from './search-data.js';
import {
  isBackendConfigured,
  fetchWorkspaceDashboard,
  listWorkspaceItems,
  fetchWorkspaceItem,
  deleteWorkspaceItem,
  fetchWorkspaceItemConnections,
  importWorkspaceFile,
  importWorkspaceUrl,
  createWorkspaceCollection,
  deleteWorkspaceCollection,
  listWorkspaceNotes,
  createWorkspaceNote,
  updateWorkspaceNote,
  deleteWorkspaceNote,
  listWorkspaceAnnotations,
  createWorkspaceAnnotation,
  deleteWorkspaceAnnotation,
  searchWorkspace,
  askWorkspaceAI,
} from './api.js';

initShell({ activeModule: 'workspace', borderedHeader: true });

const state = {
  activeTab: 'overview',
  dashboard: null,
  selectedCollectionId: null,
  selectedTag: null,
  selectedItemId: null,
  activeNoteId: null,
  notes: [],
  autosaveTimer: null,
};

const statsText = document.getElementById('ws-stats-text');
const tabButtons = Array.from(document.querySelectorAll('[data-ws-tab]'));
const panels = {
  overview: document.getElementById('ws-panel-overview'),
  library: document.getElementById('ws-panel-library'),
  notes: document.getElementById('ws-panel-notes'),
  import: document.getElementById('ws-panel-import'),
};

function switchTab(tabName) {
  state.activeTab = tabName;
  tabButtons.forEach((btn) => {
    const active = btn.getAttribute('data-ws-tab') === tabName;
    btn.setAttribute('aria-selected', String(active));
    btn.setAttribute('aria-pressed', String(active));
  });
  Object.entries(panels).forEach(([k, el]) => {
    if (el) el.style.display = k === tabName ? 'flex' : 'none';
    if (el && k !== 'overview') el.style.display = k === tabName ? 'block' : 'none';
  });
}

tabButtons.forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.getAttribute('data-ws-tab')));
});
document.querySelectorAll('[data-ws-tab-jump]').forEach((btn) => {
  btn.addEventListener('click', () => switchTab(btn.getAttribute('data-ws-tab-jump')));
});

async function loadDashboard() {
  if (!isBackendConfigured()) {
    if (statsText) {
      statsText.innerHTML = '<strong>Backend not configured</strong> · Set FastAPI URL in <a href="./settings.html" class="text-link">Settings</a> to use Personal Workspace.';
    }
    return;
  }
  try {
    const dash = await fetchWorkspaceDashboard();
    state.dashboard = dash;
    const s = dash.stats;
    if (statsText) {
      statsText.innerHTML = `<strong>Personal Workspace</strong> · ${s.total_items} items · ${s.total_collections} collections · ${s.total_notes} notes · ${s.total_annotations} annotations`;
    }
    renderRecentList('ws-recent-items', dash.recent_items, 'No saved items yet.');
    renderRecentList('ws-recent-viewed', dash.recently_viewed, 'No recently viewed items.');
    renderCollections(dash.collections);
    renderTags(dash.tags);
    renderImportCollections(dash.collections);
    await loadLibraryItems();
    await loadNotes();
  } catch (err) {
    if (statsText) statsText.textContent = `Workspace unavailable: ${err.message}`;
  }
}

function renderRecentList(mountId, items, emptyMsg) {
  const el = document.getElementById(mountId);
  if (!el) return;
  if (!items || items.length === 0) {
    el.innerHTML = `<p class="field-hint">${escapeHtml(emptyMsg)}</p>`;
    return;
  }
  el.innerHTML = items
    .map(
      (item) => `
      <button type="button" class="btn btn--secondary btn--sm" style="justify-content: space-between; width: 100%; text-align: left;" data-open-item="${escapeHtml(item.id)}">
        <span style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(item.title)}</span>
        <span class="field-hint">${escapeHtml(item.source_type)}</span>
      </button>
    `
    )
    .join('');
}

function renderCollections(collections) {
  const el = document.getElementById('ws-collections-list');
  if (!el) return;
  const allBtn = `
    <button type="button" class="filter-tab" style="justify-content: space-between; width: 100%;" data-filter-collection="" aria-pressed="${String(!state.selectedCollectionId)}">
      <span>All Items</span>
    </button>
  `;
  const rows = (collections || [])
    .map(
      (c) => `
      <div style="display: flex; gap: 0.25rem; align-items: center;">
        <button type="button" class="filter-tab" style="flex: 1; justify-content: space-between; text-align: left;" data-filter-collection="${escapeHtml(c.id)}" aria-pressed="${String(state.selectedCollectionId === c.id)}">
          <span>${escapeHtml(c.name)}</span>
          <span class="field-hint">${c.item_count}</span>
        </button>
        <button type="button" class="btn btn--ghost btn--sm" data-del-collection="${escapeHtml(c.id)}" title="Delete collection">×</button>
      </div>
    `
    )
    .join('');
  el.innerHTML = allBtn + rows;
}

function renderImportCollections(collections) {
  const sel = document.getElementById('ws-import-collection');
  if (!sel) return;
  sel.innerHTML = '<option value="">No collection</option>' +
    (collections || []).map((c) => `<option value="${escapeHtml(c.id)}">${escapeHtml(c.name)}</option>`).join('');
}

function renderTags(tags) {
  const el = document.getElementById('ws-tags-list');
  if (!el) return;
  if (!tags || tags.length === 0) {
    el.innerHTML = '<span class="field-hint">No tags yet.</span>';
    return;
  }
  el.innerHTML = tags
    .map(
      (t) => `<button type="button" class="filter-tab" data-filter-tag="${escapeHtml(t.name)}" aria-pressed="${String(state.selectedTag === t.name)}">#${escapeHtml(t.display_name)}</button>`
    )
    .join('');
}

async function loadLibraryItems() {
  const mount = document.getElementById('ws-library-items');
  if (!mount) return;
  try {
    const res = await listWorkspaceItems({
      collectionId: state.selectedCollectionId,
      tag: state.selectedTag,
      limit: 50,
    });
    if (!res.items || res.items.length === 0) {
      mount.innerHTML = '<p class="field-hint">No items in this view. Save search results or import documents to populate your workspace.</p>';
      return;
    }
    mount.innerHTML = res.items
      .map(
        (item) => `
        <div class="panel panel--subtle" style="display: flex; justify-content: space-between; gap: 0.75rem; align-items: flex-start;">
          <div style="min-width: 0; flex: 1;">
            <button type="button" class="text-link" style="font-weight: 600; text-align: left; background: none; border: none; padding: 0; cursor: pointer;" data-open-item="${escapeHtml(item.id)}">
              ${escapeHtml(item.title)}
            </button>
            <div class="field-hint" style="margin-top: 0.2rem;">
              ${escapeHtml(item.source_type)}${item.collection_name ? ` · ${escapeHtml(item.collection_name)}` : ''} · ${item.annotation_count} annotations
            </div>
            ${item.summary ? `<p style="font-size: 0.8125rem; margin-top: 0.35rem; color: var(--text-secondary);">${escapeHtml(item.summary)}</p>` : ''}
          </div>
          <button type="button" class="btn btn--ghost btn--sm" data-del-item="${escapeHtml(item.id)}">Delete</button>
        </div>
      `
      )
      .join('');
  } catch (err) {
    mount.innerHTML = `<p class="field-hint">Failed to load items: ${escapeHtml(err.message)}</p>`;
  }
}

async function openItemViewer(itemId) {
  state.selectedItemId = itemId;
  switchTab('library');
  const viewer = document.getElementById('ws-item-viewer');
  if (!viewer) return;
  viewer.style.display = 'block';
  viewer.innerHTML = '<p class="field-hint">Loading item details...</p>';

  try {
    const [item, annotations, connections] = await Promise.all([
      fetchWorkspaceItem(itemId),
      listWorkspaceAnnotations(itemId),
      fetchWorkspaceItemConnections(itemId),
    ]);

    viewer.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
          <div>
            <div class="field-hint">${escapeHtml(item.source_type)} ${item.file_name ? `· ${escapeHtml(item.file_name)}` : ''}</div>
            <h2 class="section-heading">${escapeHtml(item.title)}</h2>
            ${item.source_url ? `<a href="${escapeHtml(item.source_url)}" target="_blank" rel="noopener" class="text-link" style="font-size: 0.8125rem;">${escapeHtml(item.source_url)}</a>` : ''}
          </div>
          <button type="button" id="ws-close-viewer" class="btn btn--ghost btn--sm">Close</button>
        </div>

        <div style="max-height: 280px; overflow-y: auto; padding: 0.75rem; background: var(--bg-secondary); border: 1px solid var(--border-color); border-radius: 6px; font-size: 0.875rem; white-space: pre-wrap;">${escapeHtml(item.content || item.summary || '')}</div>

        <div>
          <h3 class="field-label" style="margin-bottom: 0.5rem;">Annotations (${annotations.length})</h3>
          <form id="ws-ann-form" style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.75rem;">
            <input id="ws-ann-quote" type="text" class="text-input" placeholder="Selected text / highlight..." style="flex: 1 1 180px; font-size: 0.8125rem;" required />
            <input id="ws-ann-comment" type="text" class="text-input" placeholder="Your note/comment..." style="flex: 1 1 180px; font-size: 0.8125rem;" />
            <button type="submit" class="btn btn--secondary btn--sm">Add Annotation</button>
          </form>
          <div style="display: flex; flex-direction: column; gap: 0.4rem;">
            ${annotations.map((a) => `
              <div class="panel panel--subtle" style="display: flex; justify-content: space-between; gap: 0.5rem; font-size: 0.8125rem;">
                <div>
                  <div style="font-style: italic;">“${escapeHtml(a.selected_text)}”</div>
                  ${a.comment ? `<div style="margin-top: 0.2rem;">${escapeHtml(a.comment)}</div>` : ''}
                </div>
                <button type="button" class="btn btn--ghost btn--sm" data-del-ann="${escapeHtml(a.id)}">×</button>
              </div>
            `).join('') || '<p class="field-hint">No annotations yet.</p>'}
          </div>
        </div>

        <div>
          <h3 class="field-label" style="margin-bottom: 0.4rem;">Knowledge Graph Entities (${connections.entities.length})</h3>
          <div style="display: flex; flex-wrap: wrap; gap: 0.35rem;">
            ${connections.entities.map((e) => `<a href="./graph.html" class="badge" style="font-size: 0.75rem; text-decoration: none;">${escapeHtml(e.name)} (${escapeHtml(e.type)})</a>`).join('') || '<span class="field-hint">No entities detected.</span>'}
          </div>
        </div>
      </div>
    `;

    document.getElementById('ws-close-viewer')?.addEventListener('click', () => {
      viewer.style.display = 'none';
    });

    document.getElementById('ws-ann-form')?.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const quote = document.getElementById('ws-ann-quote').value.trim();
      const comment = document.getElementById('ws-ann-comment').value.trim();
      if (!quote) return;
      await createWorkspaceAnnotation(itemId, { selected_text: quote, comment });
      await openItemViewer(itemId);
    });
  } catch (err) {
    viewer.innerHTML = `<p class="field-hint">Failed to load item: ${escapeHtml(err.message)}</p>`;
  }
}

// --- Notes & Autosave ---
async function loadNotes() {
  const listEl = document.getElementById('ws-notes-list');
  if (!listEl) return;
  try {
    state.notes = await listWorkspaceNotes();
    if (state.notes.length === 0) {
      listEl.innerHTML = '<p class="field-hint">No notes yet.</p>';
      return;
    }
    listEl.innerHTML = state.notes
      .map(
        (n) => `
        <button type="button" class="filter-tab" style="justify-content: flex-start; text-align: left; width: 100%;" data-select-note="${escapeHtml(n.id)}" aria-pressed="${String(state.activeNoteId === n.id)}">
          ${escapeHtml(n.title)}
        </button>
      `
      )
      .join('');
  } catch {}
}

function selectNote(noteId) {
  if (state.autosaveTimer) {
    window.clearTimeout(state.autosaveTimer);
    state.autosaveTimer = null;
  }
  const note = state.notes.find((n) => n.id === noteId);
  if (!note) return;
  state.activeNoteId = note.id;
  document.getElementById('ws-note-title').value = note.title;
  document.getElementById('ws-note-tags').value = (note.tags || []).join(', ');
  document.getElementById('ws-note-content').value = note.content;
  document.getElementById('ws-note-status').textContent = 'Loaded · Autosave ready';
  document.getElementById('ws-delete-note-btn').style.display = 'inline-flex';
  loadNotes();
}

function scheduleNoteAutosave() {
  const statusEl = document.getElementById('ws-note-status');
  const targetNoteId = state.activeNoteId;
  if (statusEl) statusEl.textContent = 'Unsaved changes...';
  if (state.autosaveTimer) window.clearTimeout(state.autosaveTimer);
  state.autosaveTimer = window.setTimeout(async () => {
    state.autosaveTimer = null;
    const title = document.getElementById('ws-note-title').value.trim() || 'Untitled Note';
    const content = document.getElementById('ws-note-content').value;
    const tags = document.getElementById('ws-note-tags').value.split(',').map((t) => t.trim()).filter(Boolean);
    try {
      if (targetNoteId) {
        if (state.activeNoteId !== targetNoteId) return;
        await updateWorkspaceNote(targetNoteId, { title, content, tags });
      } else {
        const created = await createWorkspaceNote({ title, content, tags });
        if (state.activeNoteId === null) {
          state.activeNoteId = created.id;
          document.getElementById('ws-delete-note-btn').style.display = 'inline-flex';
        }
      }
      if (statusEl) statusEl.textContent = 'Saved';
      await loadNotes();
    } catch (err) {
      if (statusEl) statusEl.textContent = `Save failed: ${err.message}`;
    }
  }, 600);
}

['ws-note-title', 'ws-note-tags', 'ws-note-content'].forEach((id) => {
  document.getElementById(id)?.addEventListener('input', scheduleNoteAutosave);
});

document.getElementById('ws-new-note-btn')?.addEventListener('click', () => {
  state.activeNoteId = null;
  document.getElementById('ws-note-title').value = '';
  document.getElementById('ws-note-tags').value = '';
  document.getElementById('ws-note-content').value = '';
  document.getElementById('ws-note-status').textContent = 'New note · Start typing to autosave';
  document.getElementById('ws-delete-note-btn').style.display = 'none';
});

document.getElementById('ws-delete-note-btn')?.addEventListener('click', async () => {
  if (!state.activeNoteId) return;
  await deleteWorkspaceNote(state.activeNoteId);
  state.activeNoteId = null;
  document.getElementById('ws-note-title').value = '';
  document.getElementById('ws-note-content').value = '';
  document.getElementById('ws-delete-note-btn').style.display = 'none';
  await loadDashboard();
});

// --- Search & AI Ask ---
document.getElementById('ws-search-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const query = document.getElementById('ws-search-input').value.trim();
  const mode = document.getElementById('ws-search-mode').value;
  const mount = document.getElementById('ws-search-results');
  if (!mount) return;
  mount.innerHTML = '<p class="field-hint">Searching personal workspace...</p>';
  try {
    const res = await searchWorkspace({ query, mode, limit: 15 });
    if (!res.hits || res.hits.length === 0) {
      mount.innerHTML = '<p class="field-hint">No matching personal items, notes, or annotations found.</p>';
      return;
    }
    mount.innerHTML = res.hits
      .map(
        (h) => `
        <div class="panel panel--subtle" style="margin-bottom: 0.5rem;">
          <div class="field-hint">${escapeHtml(h.kind.toUpperCase())} · Score ${h.score}</div>
          <div style="font-weight: 600;">${escapeHtml(h.title)}</div>
          <p style="font-size: 0.8125rem; margin-top: 0.25rem;">${escapeHtml(h.snippet)}</p>
        </div>
      `
      )
      .join('');
  } catch (err) {
    mount.innerHTML = `<p class="field-hint">Search failed: ${escapeHtml(err.message)}</p>`;
  }
});

document.getElementById('ws-ask-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const question = document.getElementById('ws-ask-input').value.trim();
  const mount = document.getElementById('ws-ask-output');
  if (!question || !mount) return;
  mount.innerHTML = '<p class="field-hint">Retrieving workspace context and querying AI...</p>';
  try {
    const res = await askWorkspaceAI({ question });
    mount.innerHTML = `
      <div class="panel panel--subtle" style="font-size: 0.875rem; line-height: 1.55;">
        <div class="field-hint" style="margin-bottom: 0.4rem;">Status: ${escapeHtml(res.status)}${res.provider ? ` · Provider: ${escapeHtml(res.provider)}` : ''}</div>
        <div style="white-space: pre-wrap;">${escapeHtml(res.answer)}</div>
        ${res.citations.length ? `<div style="margin-top: 0.75rem; border-top: 1px solid var(--border-color); padding-top: 0.5rem;"><strong>Citations:</strong><ul style="margin-top: 0.25rem;">${res.citations.map((c) => `<li style="font-size: 0.8125rem;">[${escapeHtml(c.key)}] ${escapeHtml(c.title)}</li>`).join('')}</ul></div>` : ''}
      </div>
    `;
  } catch (err) {
    mount.innerHTML = `<p class="field-hint">AI query failed: ${escapeHtml(err.message)}</p>`;
  }
});

// --- Collection & Import Forms ---
document.getElementById('ws-collection-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const input = document.getElementById('ws-collection-name');
  const name = input.value.trim();
  if (!name) return;
  await createWorkspaceCollection(name);
  input.value = '';
  await loadDashboard();
});

document.getElementById('ws-file-import-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const fileInput = document.getElementById('ws-import-file');
  const colId = document.getElementById('ws-import-collection').value;
  const tags = document.getElementById('ws-import-tags').value;
  const statusEl = document.getElementById('ws-file-import-status');
  if (!fileInput.files || !fileInput.files[0]) return;
  statusEl.textContent = 'Importing and extracting text locally...';
  try {
    const item = await importWorkspaceFile(fileInput.files[0], colId, tags);
    statusEl.textContent = item.is_duplicate
      ? `Already in workspace (deduplicated): ${item.title}`
      : `Imported "${item.title}" successfully.`;
    fileInput.value = '';
    await loadDashboard();
  } catch (err) {
    statusEl.textContent = `Import error: ${err.message}`;
  }
});

document.getElementById('ws-url-import-form')?.addEventListener('submit', async (ev) => {
  ev.preventDefault();
  const urlInput = document.getElementById('ws-import-url');
  const tags = document.getElementById('ws-url-tags').value.split(',').map((t) => t.trim()).filter(Boolean);
  const statusEl = document.getElementById('ws-url-import-status');
  statusEl.textContent = 'Validating SSRF policy and importing URL...';
  try {
    const item = await importWorkspaceUrl(urlInput.value.trim(), null, tags);
    statusEl.textContent = `Saved "${item.title}".`;
    urlInput.value = '';
    await loadDashboard();
  } catch (err) {
    statusEl.textContent = `URL import error: ${err.message}`;
  }
});

// Delegated clicks
document.addEventListener('click', async (ev) => {
  const openBtn = ev.target.closest('[data-open-item]');
  if (openBtn) {
    await openItemViewer(openBtn.getAttribute('data-open-item'));
    return;
  }
  const delItemBtn = ev.target.closest('[data-del-item]');
  if (delItemBtn) {
    await deleteWorkspaceItem(delItemBtn.getAttribute('data-del-item'));
    await loadDashboard();
    return;
  }
  const colBtn = ev.target.closest('[data-filter-collection]');
  if (colBtn) {
    state.selectedCollectionId = colBtn.getAttribute('data-filter-collection') || null;
    await loadDashboard();
    return;
  }
  const delColBtn = ev.target.closest('[data-del-collection]');
  if (delColBtn) {
    await deleteWorkspaceCollection(delColBtn.getAttribute('data-del-collection'));
    if (state.selectedCollectionId === delColBtn.getAttribute('data-del-collection')) {
      state.selectedCollectionId = null;
    }
    await loadDashboard();
    return;
  }
  const tagBtn = ev.target.closest('[data-filter-tag]');
  if (tagBtn) {
    const t = tagBtn.getAttribute('data-filter-tag');
    state.selectedTag = state.selectedTag === t ? null : t;
    await loadDashboard();
    return;
  }
  const noteBtn = ev.target.closest('[data-select-note]');
  if (noteBtn) {
    selectNote(noteBtn.getAttribute('data-select-note'));
    return;
  }
  const delAnnBtn = ev.target.closest('[data-del-ann]');
  if (delAnnBtn && state.selectedItemId) {
    await deleteWorkspaceAnnotation(delAnnBtn.getAttribute('data-del-ann'));
    await openItemViewer(state.selectedItemId);
  }
});

loadDashboard().then(() => {
  const params = new URLSearchParams(window.location.search);
  const targetItem = params.get('item');
  if (targetItem) {
    openItemViewer(targetItem);
  }
});
