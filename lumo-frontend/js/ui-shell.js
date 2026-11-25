/**
 * LUMO Shared UI Shell
 * Renders the compact header (LUMO logo, Advanced Menu, Theme switcher, Settings),
 * keyboard-accessible Advanced dropdown, and minimal footer across all pages.
 */

import { initThemeSystem } from './theme.js';
import { applyInterfacePreferences } from './preferences.js';
import { initCommandPalette } from './command-palette.js';

export const LUMO_SYMBOL_SVG = `
  <svg class="brand-symbol" viewBox="0 0 40 40" fill="none" aria-hidden="true">
    <g fill="currentColor">
      <path d="M20 2 L24.6 14.0 L20.4 15.6 L18.6 10.6 L14.8 14.2 L13.2 12.6 Z" />
      <path d="M38 20 L26.0 24.6 L24.4 20.4 L29.4 18.6 L25.8 14.8 L27.4 13.2 Z" />
      <path d="M20 38 L15.4 26.0 L19.6 24.4 L21.4 29.4 L25.2 25.8 L26.8 27.4 Z" />
      <path d="M2 20 L14.0 15.4 L15.6 19.6 L10.6 21.4 L14.2 25.2 L12.6 26.8 Z" />
    </g>
  </svg>
`;

const ICONS = {
  grid: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="5" height="5" rx="1"/><rect x="12" y="3" width="5" height="5" rx="1"/><rect x="3" y="12" width="5" height="5" rx="1"/><rect x="12" y="12" width="5" height="5" rx="1"/></svg>`,
  chevron: `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg>`,
  monitor: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="2.5" y="3.5" width="15" height="10" rx="1.5"/><path d="M7 16.5h6M10 13.5v3"/></svg>`,
  sun: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="10" cy="10" r="3.5"/><path d="M10 2.5v2M10 15.5v2M2.5 10h2M15.5 10h2M4.7 4.7l1.4 1.4M13.9 13.9l1.4 1.4M15.3 4.7l-1.4 1.4M6.1 13.9l-1.4 1.4"/></svg>`,
  moon: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16.2 12.6A6.5 6.5 0 0 1 7.4 3.8a6.5 6.5 0 1 0 8.8 8.8Z"/></svg>`,
  settings: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="10" cy="10" r="2.75"/><path d="M16.2 12.3a1.3 1.3 0 0 0 .26 1.43l.05.05a1.55 1.55 0 1 1-2.2 2.2l-.05-.05a1.3 1.3 0 0 0-1.43-.26 1.3 1.3 0 0 0-.78 1.19v.14a1.55 1.55 0 1 1-3.1 0v-.07a1.3 1.3 0 0 0-.85-1.19 1.3 1.3 0 0 0-1.43.26l-.05.05a1.55 1.55 0 1 1-2.2-2.2l.05-.05a1.3 1.3 0 0 0 .26-1.43 1.3 1.3 0 0 0-1.19-.78H3.4a1.55 1.55 0 1 1 0-3.1h.07a1.3 1.3 0 0 0 1.19-.85 1.3 1.3 0 0 0-.26-1.43l-.05-.05a1.55 1.55 0 1 1 2.2-2.2l.05.05a1.3 1.3 0 0 0 1.43.26h.06a1.3 1.3 0 0 0 .78-1.19V3.4a1.55 1.55 0 1 1 3.1 0v.07a1.3 1.3 0 0 0 .78 1.19 1.3 1.3 0 0 0 1.43-.26l.05-.05a1.55 1.55 0 1 1 2.2 2.2l-.05.05a1.3 1.3 0 0 0-.26 1.43v.06a1.3 1.3 0 0 0 1.19.78h.14a1.55 1.55 0 1 1 0 3.1h-.07a1.3 1.3 0 0 0-1.19.78Z"/></svg>`,
  search: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="9" r="5.75"/><path d="m16.5 16.5-3.4-3.4"/></svg>`,
  research: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 3.5h8.5L16 7v9.5a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-12a1 1 0 0 1 1-1Z"/><path d="M12.5 3.5V7H16M6.5 10.5h7M6.5 13.5h5"/></svg>`,
  shield: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 2.5 16 5v4.8c0 3.7-2.6 6.7-6 7.7-3.4-1-6-4-6-7.7V5l6-2.5Z"/></svg>`,
  link: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8.5 11.5a3.5 3.5 0 0 0 5 0l2.2-2.2a3.5 3.5 0 0 0-5-5L9.4 5.6"/><path d="M11.5 8.5a3.5 3.5 0 0 0-5 0L4.3 10.7a3.5 3.5 0 0 0 5 5l1.3-1.3"/></svg>`,
  file: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 2.5h6.5L15.5 6.5V16.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-13a1 1 0 0 1 1-1Z"/><path d="M11.5 2.5v4h4M7.5 12l1.8 1.8L13 10"/></svg>`,
  graph: `<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="10" cy="4.5" r="2"/><circle cx="4.5" cy="14.5" r="2"/><circle cx="15.5" cy="14.5" r="2"/><path d="M8.9 6.2 5.6 12.8M11.1 6.2l3.3 6.6M6.5 14.5h7"/></svg>`,
};

export const ADVANCED_MODULES = Object.freeze([
  {
    id: 'command-center',
    group: 'Platform',
    label: 'Intelligence Command Center',
    description: 'Unified operational dashboard across Search, Research, AI, Automations, Data, and Health.',
    href: './command-center.html',
    icon: ICONS.grid,
  },
  {
    id: 'search',
    group: 'Discover',
    label: 'Intelligent Search',
    description: 'Advanced search options and search preferences.',
    href: './results.html',
    icon: ICONS.search,
  },
  {
    id: 'research',
    group: 'Research',
    label: 'Autonomous Research Agent',
    description: 'Investigate complex questions and create evidence-based research reports.',
    href: './research.html',
    icon: ICONS.research,
  },
  {
    id: 'guardian',
    group: 'Intelligence',
    label: 'Download Guardian',
    description: 'Inspect URLs, redirects and downloads for potential security risks.',
    href: './guardian.html?tab=download',
    icon: ICONS.shield,
  },
  {
    id: 'url-security',
    group: 'Intelligence',
    label: 'URL Security Analysis',
    description: 'Analyse suspicious links, domain reputation and redirect behaviour.',
    href: './guardian.html?tab=url',
    icon: ICONS.link,
  },
  {
    id: 'file-security',
    group: 'Intelligence',
    label: 'File Security Analysis',
    description: 'Inspect uploaded files and display security findings.',
    href: './guardian.html?tab=file',
    icon: ICONS.file,
  },
  {
    id: 'graph',
    group: 'Intelligence',
    label: 'Knowledge Graph',
    description: 'Explore connected entities, concepts and relationships.',
    href: './graph.html',
    icon: ICONS.graph,
  },
  {
    id: 'workspace',
    group: 'Workspace',
    label: 'Personal Workspace',
    description: 'Save documents, organize collections, write notes, and search your knowledge.',
    href: './workspace.html',
    icon: ICONS.file,
  },
  {
    id: 'local-ai',
    group: 'Platform',
    label: 'Offline Local AI',
    description: 'Private local AI chat, document tasks, and grounded RAG via Ollama.',
    href: './local-ai.html',
    icon: ICONS.research,
  },
  {
    id: 'automation',
    group: 'Automation',
    label: 'Intelligence Automations',
    description: 'Create scheduled, event-driven, and manual intelligence workflows.',
    href: './automation.html',
    icon: ICONS.grid,
  },
  {
    id: 'personalization',
    group: 'Workspace',
    label: 'Adaptive Personalization',
    description: 'Manage explicit interests, source preferences, discovery, and privacy.',
    href: './personalization.html',
    icon: ICONS.search,
  },
  {
    id: 'intelligence',
    group: 'Intelligence',
    label: 'Universal Data Intelligence',
    description: 'Ingest PDFs, spreadsheets, datasets, and images with AI analysis and charts.',
    href: './intelligence.html',
    icon: ICONS.research,
  },
  {
    id: 'integrations',
    group: 'Platform',
    label: 'External Integrations',
    description: 'Connect RSS/Atom feeds, GitHub repos, documentation sites, and open data APIs.',
    href: './integrations.html',
    icon: ICONS.link,
  },
  {
    id: 'developer',
    group: 'Platform',
    label: 'Developer Portal & API',
    description: 'Generate API keys, inspect permissions, monitor usage, and explore OpenAPI docs.',
    href: './developer.html',
    icon: ICONS.settings,
  },
  {
    id: 'evaluations',
    group: 'Platform',
    label: 'Evaluation & Benchmarks',
    description: 'Benchmark Search, AI, Research, Graph, Data, and Guardian with regression tracking.',
    href: './evaluations.html',
    icon: ICONS.research,
  },
  {
    id: 'settings',
    group: 'Platform',
    label: 'Settings',
    description: 'Manage themes, preferences and application settings.',
    href: './settings.html',
    icon: ICONS.settings,
  },
]);

export function initShell({ activeModule = '', borderedHeader = false } = {}) {
  applyInterfacePreferences();

  const headerMount = document.getElementById('lumo-header');
  if (headerMount) {
    headerMount.className = `site-header${borderedHeader ? ' site-header--bordered' : ''}`;
    headerMount.innerHTML = buildHeaderMarkup(activeModule);
    wireAdvancedMenu(headerMount);

    if (!borderedHeader) {
      const onScroll = () => {
        headerMount.classList.toggle('is-scrolled', window.scrollY > 8);
      };
      window.addEventListener('scroll', onScroll, { passive: true });
      onScroll();
    }
  }

  const footerMount = document.getElementById('lumo-footer');
  if (footerMount) {
    footerMount.className = 'site-footer';
    footerMount.innerHTML = buildFooterMarkup();
  }

  initThemeSystem();
  initCommandPalette({ modules: ADVANCED_MODULES });
}

function buildHeaderMarkup(activeModule) {
  const groupOrder = ['Discover', 'Research', 'Intelligence', 'Workspace', 'Automation', 'Platform'];
  const grouped = new Map(groupOrder.map((g) => [g, []]));
  ADVANCED_MODULES.forEach((mod) => {
    const g = grouped.has(mod.group) ? mod.group : 'Platform';
    grouped.get(g).push(mod);
  });

  const menuItemsHtml = groupOrder
    .filter((g) => grouped.get(g).length > 0)
    .map((g) => {
      const items = grouped.get(g).map((mod) => {
        const isCurrent = mod.id === activeModule;
        return `
          <li role="none">
            <a
              href="${mod.href}"
              class="advanced-menu__item"
              role="menuitem"
              ${isCurrent ? 'aria-current="page"' : ''}
            >
              <span class="advanced-menu__icon">${mod.icon}</span>
              <span class="advanced-menu__body">
                <span class="advanced-menu__label">${mod.label}</span>
                <span class="advanced-menu__desc">${mod.description}</span>
              </span>
            </a>
          </li>
        `;
      }).join('');
      return `<li role="presentation" class="advanced-menu__group-label">${g}</li>${items}`;
    }).join('');

  return `
    <div class="header-inner">
      <a href="./index.html" class="brand-link" aria-label="LUMO Home">
        ${LUMO_SYMBOL_SVG}
        <span class="brand-wordmark">LUMO</span>
      </a>

      <div class="header-controls">
        <button
          type="button"
          id="lumo-cmd-trigger"
          class="cmd-trigger"
          aria-label="Open Command Palette (Ctrl+K)"
          title="Command Palette (Ctrl+K)"
        >
          ${ICONS.search}
          <span>Jump</span>
          <kbd class="cmd-kbd">Ctrl+K</kbd>
        </button>

        <button
          type="button"
          id="lumo-advanced-trigger"
          class="advanced-trigger"
          aria-haspopup="menu"
          aria-expanded="false"
          aria-controls="lumo-advanced-menu"
        >
          ${ICONS.grid}
          <span class="advanced-trigger__label">Advanced</span>
          ${ICONS.chevron}
        </button>

        <div class="theme-switcher" role="group" aria-label="Appearance theme">
          <button
            type="button"
            class="theme-switcher__btn"
            data-theme-option="system"
            aria-label="System theme"
            aria-pressed="false"
            title="System theme"
          >
            ${ICONS.monitor}
          </button>
          <button
            type="button"
            class="theme-switcher__btn"
            data-theme-option="light"
            aria-label="Light theme"
            aria-pressed="false"
            title="Light theme"
          >
            ${ICONS.sun}
          </button>
          <button
            type="button"
            class="theme-switcher__btn"
            data-theme-option="dark"
            aria-label="Dark theme"
            aria-pressed="false"
            title="Dark theme"
          >
            ${ICONS.moon}
          </button>
        </div>

        <a
          href="./settings.html"
          class="icon-btn${activeModule === 'settings' ? ' icon-btn--active' : ''}"
          aria-label="Settings"
          title="Settings"
          ${activeModule === 'settings' ? 'aria-current="page"' : ''}
        >
          ${ICONS.settings}
        </a>

        <div
          id="lumo-advanced-menu"
          class="advanced-menu"
          role="menu"
          aria-labelledby="lumo-advanced-trigger"
          hidden
        >
          <div class="advanced-menu__header">
            <span class="advanced-menu__title">LUMO Modules</span>
          </div>
          <ul class="advanced-menu__list" role="none">
            ${menuItemsHtml}
          </ul>
        </div>
      </div>
    </div>
  `;
}

function buildFooterMarkup() {
  const year = new Date().getFullYear();
  return `
    <div class="footer-inner">
      <span>LUMO · Independent Search &amp; Intelligence · ${year}</span>
      <nav class="footer-links" aria-label="Footer links">
        <a href="./results.html">Search</a>
        <a href="./research.html">Research Agent</a>
        <a href="./guardian.html">Download Guardian</a>
        <a href="./graph.html">Knowledge Graph</a>
        <a href="./settings.html">Settings</a>
      </nav>
    </div>
  `;
}

function wireAdvancedMenu(headerEl) {
  const trigger = headerEl.querySelector('#lumo-advanced-trigger');
  const menu = headerEl.querySelector('#lumo-advanced-menu');
  if (!trigger || !menu) return;

  const getItems = () => Array.from(menu.querySelectorAll('[role="menuitem"]'));

  const openMenu = ({ focusFirst = false } = {}) => {
    menu.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    if (focusFirst) {
      const items = getItems();
      if (items[0]) items[0].focus();
    }
  };

  const closeMenu = ({ restoreFocus = false } = {}) => {
    if (menu.hidden) return;
    menu.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
    if (restoreFocus) {
      trigger.focus();
    }
  };

  trigger.addEventListener('click', (event) => {
    event.stopPropagation();
    if (menu.hidden) {
      openMenu();
    } else {
      closeMenu();
    }
  });

  trigger.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        openMenu({ focusFirst: true });
      }
    }
  });

  menu.addEventListener('keydown', (event) => {
    const items = getItems();
    const currentIndex = items.indexOf(document.activeElement);

    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu({ restoreFocus: true });
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      const next = items[(currentIndex + 1) % items.length];
      if (next) next.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      const prev = items[(currentIndex - 1 + items.length) % items.length];
      if (prev) prev.focus();
    } else if (event.key === 'Home') {
      event.preventDefault();
      if (items[0]) items[0].focus();
    } else if (event.key === 'End') {
      event.preventDefault();
      if (items[items.length - 1]) items[items.length - 1].focus();
    } else if (event.key === 'Tab') {
      closeMenu();
    }
  });

  document.addEventListener('click', (event) => {
    if (!menu.hidden && !menu.contains(event.target) && !trigger.contains(event.target)) {
      closeMenu();
    }
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !menu.hidden) {
      closeMenu({ restoreFocus: true });
    }
  });
}
