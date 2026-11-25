/**
 * LUMO Global Command Palette (Ctrl+K / Cmd+K)
 * Pure Vanilla JS, keyboard-accessible, ARIA-compliant, zero dependencies.
 */

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

export function buildCommandItems(modules = [], query = '') {
  const q = String(query || '').trim();
  const base = modules.map((m) => ({
    id: `nav:${m.id}`,
    label: m.label,
    category: m.group || 'Navigate',
    action: () => { window.location.href = m.href; },
  }));

  if (q.length >= 2) {
    base.unshift(
      {
        id: 'search:hybrid',
        label: `Search Web Index (Hybrid) for "${q}"`,
        category: 'Discover',
        action: () => { window.location.href = `./results.html?q=${encodeURIComponent(q)}&mode=hybrid`; },
      },
      {
        id: 'search:ai',
        label: `Ask AI Search about "${q}"`,
        category: 'Discover',
        action: () => { window.location.href = `./results.html?q=${encodeURIComponent(q)}&mode=ai`; },
      },
      {
        id: 'search:workspace',
        label: `Search Personal Workspace for "${q}"`,
        category: 'Workspace',
        action: () => { window.location.href = `./workspace.html?q=${encodeURIComponent(q)}`; },
      }
    );
  }

  if (!q) return base;
  const ql = q.toLowerCase();
  return base.filter((it) => it.label.toLowerCase().includes(ql) || it.category.toLowerCase().includes(ql));
}

export function initCommandPalette({ modules = [] } = {}) {
  if (typeof document === 'undefined' || document.getElementById('lumo-cmd-backdrop')) return;

  const backdrop = document.createElement('div');
  backdrop.id = 'lumo-cmd-backdrop';
  backdrop.className = 'cmd-backdrop';
  backdrop.hidden = true;
  backdrop.innerHTML = `
    <div class="cmd-dialog" role="dialog" aria-modal="true" aria-label="LUMO Command Palette">
      <div class="cmd-input-wrap">
        <input id="lumo-cmd-input" class="cmd-input" type="search" placeholder="Type a module, command, or search query..." aria-label="Command palette filter" />
      </div>
      <div id="lumo-cmd-list" class="cmd-list" role="listbox" aria-label="Available commands"></div>
    </div>
  `;
  document.body.appendChild(backdrop);

  const input = document.getElementById('lumo-cmd-input');
  const listEl = document.getElementById('lumo-cmd-list');
  let activeIdx = 0;
  let currentItems = [];
  let lastFocus = null;

  function render() {
    currentItems = buildCommandItems(modules, input.value);
    if (activeIdx >= currentItems.length) activeIdx = 0;
    listEl.innerHTML = currentItems.length
      ? currentItems.map((it, idx) => `
        <button type="button" class="cmd-item${idx === activeIdx ? ' is-active' : ''}" role="option" aria-selected="${idx === activeIdx}" data-idx="${idx}">
          <span>${escapeHtml(it.label)}</span>
          <span class="cmd-item__cat">${escapeHtml(it.category)}</span>
        </button>`).join('')
      : '<div style="padding:0.75rem;font-size:0.86rem;color:var(--text-secondary);">No matching commands.</div>';

    listEl.querySelectorAll('.cmd-item').forEach((btn) => {
      btn.onclick = () => {
        const chosen = currentItems[Number(btn.dataset.idx)];
        close();
        chosen?.action();
      };
    });
  }

  function open() {
    lastFocus = document.activeElement;
    backdrop.hidden = false;
    input.value = '';
    activeIdx = 0;
    render();
    input.focus();
  }

  function close() {
    backdrop.hidden = true;
    if (lastFocus && typeof lastFocus.focus === 'function') lastFocus.focus();
  }

  const trigger = document.getElementById('lumo-cmd-trigger');
  if (trigger) trigger.addEventListener('click', open);

  backdrop.addEventListener('click', (e) => {
    if (e.target === backdrop) close();
  });

  input.addEventListener('input', () => {
    activeIdx = 0;
    render();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      close();
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (currentItems.length) { activeIdx = (activeIdx + 1) % currentItems.length; render(); }
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (currentItems.length) { activeIdx = (activeIdx - 1 + currentItems.length) % currentItems.length; render(); }
    } else if (e.key === 'Enter' && currentItems[activeIdx]) {
      e.preventDefault();
      const chosen = currentItems[activeIdx];
      close();
      chosen.action();
    }
  });

  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      if (backdrop.hidden) open();
      else close();
    }
  });
}
