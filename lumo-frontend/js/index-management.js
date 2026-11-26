import { initShell } from './ui-shell.js';
import {
  deleteRetrievalItem,
  fetchRetrievalIndexItems,
  fetchRetrievalIndexStats,
  formatSafeError,
  indexRetrievalContent,
  reindexRetrievalItem,
} from './api.js';

initShell({ activeModule: 'index-management', borderedHeader: true });

const $ = (id) => document.getElementById(id);

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showBanner(msg, isError = false) {
  const el = $('im-banner');
  el.textContent = msg;
  el.className = `status-banner ${isError ? 'is-error' : 'is-success'}`;
  el.hidden = false;
  setTimeout(() => { el.hidden = true; }, 4500);
}

async function refreshIndex() {
  const [stats, items] = await Promise.all([
    fetchRetrievalIndexStats().catch(() => null),
    fetchRetrievalIndexItems().catch(() => []),
  ]);
  if (stats) {
    $('im-total').textContent = String(stats.total_records ?? 0);
    $('im-chunks').textContent = String(stats.total_chunks ?? 0);
    $('im-hits').textContent = `${stats.embedding_cache?.cache_hits ?? 0} / ${stats.embedding_cache?.cache_misses ?? 0}`;
  }

  $('im-list').innerHTML = items.length
    ? items.map((r) => `
      <div class="im-row">
        <div>
          <span class="im-badge">${escapeHtml(r.status)}</span>
          <strong>${escapeHtml(r.title)}</strong>
          <span style="font-size:0.78rem; color:var(--text-secondary);">(${r.chunk_count} chunks)</span>
        </div>
        <div style="display:flex; gap:0.35rem;">
          <button type="button" class="btn-secondary im-reidx" data-id="${escapeHtml(r.id)}">Reindex</button>
          <button type="button" class="btn-secondary im-del" data-id="${escapeHtml(r.id)}">Delete</button>
        </div>
      </div>`).join('')
    : '<p style="color:var(--text-secondary); font-size:0.86rem;">No indexed records yet.</p>';

  $('im-list').querySelectorAll('.im-reidx').forEach((b) => {
    b.onclick = async () => {
      try { await reindexRetrievalItem(b.dataset.id); showBanner('Reindexed.'); await refreshIndex(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
  $('im-list').querySelectorAll('.im-del').forEach((b) => {
    b.onclick = async () => {
      if (!confirm('Delete this indexed record?')) return;
      try { await deleteRetrievalItem(b.dataset.id); await refreshIndex(); }
      catch (err) { showBanner(formatSafeError(err), true); }
    };
  });
}

$('im-idx-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const res = await indexRetrievalContent({
      title: $('im-title').value.trim(),
      content_type: $('im-ctype').value,
      content: $('im-content').value.trim(),
    });
    $('im-title').value = '';
    $('im-content').value = '';
    showBanner(`Indexed (${res.status}, ${res.chunk_count} chunks).`);
    await refreshIndex();
  } catch (err) { showBanner(formatSafeError(err), true); }
});

refreshIndex();
