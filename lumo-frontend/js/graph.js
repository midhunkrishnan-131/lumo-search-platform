/**
 * LUMO Knowledge Graph Controller
 * Clean monochrome interactive SVG entity-relationship viewer with
 * live FastAPI integration, search, type filtering, pan/zoom,
 * keyboard accessibility, source citations, and relationship inspection.
 */

import { initShell } from './ui-shell.js';
import { escapeHtml } from './search-data.js';
import {
  fetchKnowledgeGraph,
  fetchEntityDetails,
  fetchGraphStats,
  reprocessKnowledgeGraph,
  saveToWorkspace,
  isBackendConfigured,
} from './api.js';

initShell({ activeModule: 'graph', borderedHeader: true });

const SAMPLE_GRAPH = {
  nodes: [
    {
      id: 'entity-hybrid-search',
      label: 'Hybrid Search',
      type: 'Concept',
      x: 360,
      y: 230,
      description:
        'Retrieval architecture combining lexical keyword matching (BM25) with dense semantic vector search via Reciprocal Rank Fusion.',
      sources: [
        { title: 'Reciprocal Rank Fusion in Hybrid Search Pipelines', query: 'hybrid search reciprocal rank fusion' },
        { title: 'How Modern Search Engines Crawl, Index, and Rank the Web', query: 'how search engines work' },
      ],
    },
    {
      id: 'entity-semantic-retrieval',
      label: 'Semantic Retrieval',
      type: 'Concept',
      x: 195,
      y: 120,
      description:
        'Meaning-based search using sentence transformer embeddings stored in a vector index such as Qdrant.',
      sources: [
        { title: 'Semantic Retrieval and Dense Vector Embeddings Explained', query: 'semantic retrieval vector embeddings' },
      ],
    },
    {
      id: 'entity-fastapi',
      label: 'FastAPI Gateway',
      type: 'Technology',
      x: 535,
      y: 130,
      description:
        'Central Python API boundary routing all browser requests cleanly to OpenSearch, Qdrant, PostgreSQL, Redis, and Ollama.',
      sources: [
        { title: 'Building a Secure FastAPI Gateway for Search Platforms', query: 'FastAPI gateway architecture' },
      ],
    },
    {
      id: 'entity-research-agent',
      label: 'Research Agent',
      type: 'Module',
      x: 180,
      y: 345,
      description:
        'Bounded autonomous investigation workflow that breaks questions into subquestions, evaluates sources, flags contradictions, and cites reports.',
      sources: [
        { title: 'Bounded Autonomous Research Agents and Evidence Verification', query: 'bounded autonomous research agents' },
      ],
    },
    {
      id: 'entity-knowledge-graph',
      label: 'Knowledge Graph',
      type: 'Module',
      x: 365,
      y: 390,
      description:
        'Structured graph connecting entities, typed relationships, and source citations for transparent exploration.',
      sources: [
        { title: 'Knowledge Graphs: Modeling Entities, Relationships, and Provenance', query: 'knowledge graph entity relationships' },
      ],
    },
    {
      id: 'entity-download-guardian',
      label: 'Download Guardian',
      type: 'Module',
      x: 565,
      y: 285,
      description:
        'Security inspection pipeline validating URLs, blocking SSRF targets, analyzing redirect chains, and checking file hashes.',
      sources: [
        { title: 'URL Security Inspection: Redirect Chains, Punycode, and SSRF Defenses', query: 'URL security redirect chain inspection' },
      ],
    },
    {
      id: 'entity-sha256',
      label: 'SHA-256 Digest',
      type: 'Protocol',
      x: 695,
      y: 385,
      description:
        'Cryptographic hash function producing a 256-bit fingerprint for tamper detection and file threat-intelligence lookup.',
      sources: [
        { title: 'Cryptographic File Hashing (SHA-256) and Malware Triage', query: 'SHA-256 file verification' },
      ],
    },
    {
      id: 'entity-ssrf-guard',
      label: 'SSRF Defense',
      type: 'Concept',
      x: 700,
      y: 180,
      description:
        'Defensive network inspection blocking private IPv4/IPv6 ranges, loopback addresses, and cloud metadata endpoints.',
      sources: [
        { title: 'SSRF Prevention in Modern Web Crawlers and Threat Scanners', query: 'SSRF prevention crawler security' },
      ],
    },
  ],
  edges: [
    { id: 'e1', from: 'entity-hybrid-search', to: 'entity-semantic-retrieval', label: 'USES' },
    { id: 'e2', from: 'entity-hybrid-search', to: 'entity-research-agent', label: 'POWERED_BY' },
    { id: 'e3', from: 'entity-fastapi', to: 'entity-hybrid-search', label: 'ROUTES_TO' },
    { id: 'e4', from: 'entity-fastapi', to: 'entity-download-guardian', label: 'ROUTES_TO' },
    { id: 'e5', from: 'entity-download-guardian', to: 'entity-sha256', label: 'CALCULATES' },
    { id: 'e6', from: 'entity-download-guardian', to: 'entity-ssrf-guard', label: 'ENFORCES' },
    { id: 'e7', from: 'entity-research-agent', to: 'entity-knowledge-graph', label: 'DISCOVERS' },
    { id: 'e8', from: 'entity-knowledge-graph', to: 'entity-hybrid-search', label: 'INDEXES' },
  ],
};

const state = {
  activeGraph: SAMPLE_GRAPH,
  isLive: false,
  selectedId: 'entity-hybrid-search',
  selectedEdgeId: null,
  selectedEntityDetail: null,
  typeFilter: 'All',
  searchQuery: '',
  zoom: 1,
  panX: 0,
  panY: 0,
};

const svgEl = document.getElementById('graph-svg');
const inspectorMount = document.getElementById('graph-inspector');
const entityListMount = document.getElementById('graph-entity-list');
const searchInput = document.getElementById('graph-search-input');
const typeButtons = Array.from(document.querySelectorAll('[data-graph-type]'));
const zoomInBtn = document.getElementById('graph-zoom-in');
const zoomOutBtn = document.getElementById('graph-zoom-out');
const resetViewBtn = document.getElementById('graph-reset-view');
const statusBanner = document.getElementById('graph-status-banner');
const statusText = document.getElementById('graph-status-text');
const reprocessBtn = document.getElementById('graph-reprocess-btn');

async function loadGraphData() {
  if (isBackendConfigured()) {
    try {
      const resp = await fetchKnowledgeGraph({
        limitNodes: 100,
        limitEdges: 200,
        type: state.typeFilter,
        query: state.searchQuery,
      });

      if (resp && resp.nodes && resp.nodes.length > 0) {
        state.activeGraph = {
          nodes: resp.nodes.map((n) => ({
            id: n.id,
            label: n.label,
            type: n.type,
            x: n.x || 400,
            y: n.y || 235,
            description: n.description || '',
            degree: n.degree || 0,
            sourcesCount: n.sources_count || 0,
          })),
          edges: resp.edges.map((e) => ({
            id: e.id,
            from: e.from,
            to: e.to,
            label: e.label,
            snippet: e.first_snippet || '',
          })),
        };
        state.isLive = true;

        if (statusText) {
          statusText.innerHTML = `
            <strong>Live Knowledge Graph</strong> · ${resp.total_nodes} entities, ${resp.total_edges} connections indexed across documents.
          `;
        }
      } else {
        state.activeGraph = SAMPLE_GRAPH;
        state.isLive = false;
        if (statusText) {
          statusText.innerHTML = `
            <strong>Sample Knowledge Graph</strong> · Index has 0 documents. Demonstrating graph exploration with verified sample nodes.
          `;
        }
      }
    } catch (err) {
      console.warn('FastAPI graph fetch failed, falling back to sample:', err);
      state.activeGraph = SAMPLE_GRAPH;
      state.isLive = false;
      if (statusText) {
        statusText.innerHTML = `
          <strong>Sample Knowledge Graph</strong> · Backend offline or unconfigured. Displaying sample nodes.
        `;
      }
    }
  }

  // Ensure valid selection
  if (state.activeGraph.nodes.length > 0) {
    const exists = state.activeGraph.nodes.some((n) => n.id === state.selectedId);
    if (!exists) {
      state.selectedId = state.activeGraph.nodes[0].id;
    }
  }

  renderGraph();
  if (state.isLive && state.selectedId) {
    loadEntityDetails(state.selectedId);
  }
}

async function loadEntityDetails(entityId) {
  if (!state.isLive) return;
  try {
    const detail = await fetchEntityDetails(entityId);
    state.selectedEntityDetail = detail;
    renderInspector();
  } catch (err) {
    console.debug('Failed loading entity details:', err);
  }
}

function getVisibleNodes() {
  const query = state.searchQuery.trim().toLowerCase();
  return state.activeGraph.nodes.filter((node) => {
    const matchesType = state.typeFilter === 'All' || node.type.toLowerCase() === state.typeFilter.toLowerCase();
    const matchesSearch = !query || node.label.toLowerCase().includes(query) || (node.description || '').toLowerCase().includes(query);
    return matchesType && matchesSearch;
  });
}

function getConnections(nodeId) {
  return state.activeGraph.edges
    .filter((e) => e.from === nodeId || e.to === nodeId)
    .map((e) => {
      const otherId = e.from === nodeId ? e.to : e.from;
      const otherNode = state.activeGraph.nodes.find((n) => n.id === otherId);
      return {
        edge: e,
        otherNode,
        direction: e.from === nodeId ? 'outgoing' : 'incoming',
      };
    })
    .filter((conn) => Boolean(conn.otherNode));
}

function renderGraph() {
  const visibleNodes = getVisibleNodes();
  const visibleIds = new Set(visibleNodes.map((n) => n.id));

  if (visibleNodes.length > 0 && !visibleIds.has(state.selectedId)) {
    state.selectedId = visibleNodes[0].id;
    if (state.isLive) loadEntityDetails(state.selectedId);
  }

  const visibleEdges = state.activeGraph.edges.filter(
    (e) => visibleIds.has(e.from) && visibleIds.has(e.to)
  );

  if (svgEl) {
    const edgesHtml = visibleEdges
      .map((edge) => {
        const from = state.activeGraph.nodes.find((n) => n.id === edge.from);
        const to = state.activeGraph.nodes.find((n) => n.id === edge.to);
        if (!from || !to) return '';
        const isSelectedEdge = edge.id === state.selectedEdgeId;
        const isActive = isSelectedEdge || edge.from === state.selectedId || edge.to === state.selectedId;
        const midX = (from.x + to.x) / 2;
        const midY = (from.y + to.y) / 2 - 5;
        return `
          <g class="graph-edge-group" data-edge-id="${escapeHtml(edge.id)}" tabindex="0" role="button" aria-label="${escapeHtml(edge.label)}">
            <line
              x1="${from.x}"
              y1="${from.y}"
              x2="${to.x}"
              y2="${to.y}"
              class="graph-edge${isActive ? ' graph-edge--active' : ''}${isSelectedEdge ? ' graph-edge--selected' : ''}"
            />
            <text x="${midX}" y="${midY}" class="graph-edge-label">${escapeHtml(edge.label)}</text>
          </g>
        `;
      })
      .join('');

    const nodesHtml = visibleNodes
      .map((node) => {
        const isSelected = node.id === state.selectedId;
        return `
          <g
            class="graph-node${isSelected ? ' graph-node--selected' : ''}"
            data-node-id="${escapeHtml(node.id)}"
            tabindex="0"
            role="button"
            aria-label="${escapeHtml(node.label)} (${escapeHtml(node.type)})"
            aria-pressed="${String(isSelected)}"
            transform="translate(${node.x}, ${node.y})"
          >
            <circle r="12" class="graph-node__circle" />
            <text y="26" class="graph-node__label">${escapeHtml(node.label)}</text>
            <text y="38" class="graph-node__type">${escapeHtml(node.type)}</text>
          </g>
        `;
      })
      .join('');

    svgEl.innerHTML = `
      <g id="graph-viewport" transform="translate(${state.panX}, ${state.panY}) scale(${state.zoom})">
        ${edgesHtml}
        ${nodesHtml}
      </g>
    `;
  }

  renderEntityList(visibleNodes);
  renderInspector();
}

function renderEntityList(visibleNodes) {
  if (!entityListMount) return;
  if (visibleNodes.length === 0) {
    entityListMount.innerHTML = '<p class="field-hint">No entities match the current filter.</p>';
    return;
  }
  entityListMount.innerHTML = visibleNodes
    .map(
      (node) => `
      <button
        type="button"
        class="filter-tab"
        data-select-entity="${escapeHtml(node.id)}"
        aria-pressed="${String(node.id === state.selectedId)}"
      >
        ${escapeHtml(node.label)}
      </button>
    `
    )
    .join('');
}

function renderInspector() {
  if (!inspectorMount) return;

  // If an edge was specifically selected, display relationship evidence
  if (state.selectedEdgeId) {
    const edge = state.activeGraph.edges.find((e) => e.id === state.selectedEdgeId);
    if (edge) {
      const from = state.activeGraph.nodes.find((n) => n.id === edge.from);
      const to = state.activeGraph.nodes.find((n) => n.id === edge.to);
      inspectorMount.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 1rem;">
          <div>
            <div class="field-hint">Relationship Evidence</div>
            <h2 class="section-heading" style="margin-top: 0.25rem;">${escapeHtml(edge.label)}</h2>
            <p style="font-size: 0.875rem; margin-top: 0.5rem;">
              <strong>${escapeHtml(from ? from.label : edge.from)}</strong>
              <span class="mono" style="margin: 0 0.25rem;">—[${escapeHtml(edge.label)}]→</span>
              <strong>${escapeHtml(to ? to.label : edge.to)}</strong>
            </p>
          </div>

          ${
            edge.snippet
              ? `
            <div>
              <h3 class="field-label" style="margin-bottom: 0.5rem;">Supporting Text Evidence</h3>
              <div class="panel" style="background-color: var(--bg-secondary); padding: 0.75rem; font-size: 0.8125rem; font-style: italic; border-left: 3px solid var(--accent-primary);">
                “${escapeHtml(edge.snippet)}”
              </div>
            </div>
          `
              : ''
          }

          <div style="padding-top: 0.5rem; border-top: 1px solid var(--border-color); display: flex; gap: 0.5rem;">
            <button type="button" id="graph-deselect-edge" class="btn btn--secondary btn--sm">Back to Entity</button>
          </div>
        </div>
      `;
      const deselectBtn = document.getElementById('graph-deselect-edge');
      if (deselectBtn) {
        deselectBtn.addEventListener('click', () => {
          state.selectedEdgeId = null;
          renderGraph();
        });
      }
      return;
    }
  }

  const node = state.activeGraph.nodes.find((n) => n.id === state.selectedId);
  if (!node) {
    inspectorMount.innerHTML = '<p class="field-hint">Select an entity to inspect relationships and sources.</p>';
    return;
  }

  const detail = state.selectedEntityDetail && state.selectedEntityDetail.id === node.id ? state.selectedEntityDetail : null;
  const connections = getConnections(node.id);
  const aliases = detail && detail.aliases ? detail.aliases : [];
  const sources = detail && detail.documents ? detail.documents : (node.sources || []);

  inspectorMount.innerHTML = `
    <div style="display: flex; flex-direction: column; gap: 1rem;">
      <div>
        <div class="field-hint">${escapeHtml(node.type)} · ${state.isLive ? 'Indexed Entity' : 'Sample Entity'}</div>
        <h2 class="section-heading" style="margin-top: 0.25rem;">${escapeHtml(node.label)}</h2>
        <p class="daily-cell__body">${escapeHtml(node.description || 'Grounded entity discovered from indexed document content.')}</p>
      </div>

      ${
        aliases.length > 0
          ? `
        <div>
          <h3 class="field-label" style="margin-bottom: 0.25rem;">Aliases & Alternate Names</h3>
          <div style="display: flex; gap: 0.35rem; flex-wrap: wrap;">
            ${aliases.map((a) => `<span class="badge" style="font-size: 0.75rem;">${escapeHtml(a)}</span>`).join('')}
          </div>
        </div>
      `
          : ''
      }

      <div>
        <h3 class="field-label" style="margin-bottom: 0.5rem;">Connected entities (${connections.length})</h3>
        <div style="display: flex; flex-direction: column; gap: 0.375rem;">
          ${
            connections.length === 0
              ? '<p class="field-hint">No direct connections discovered.</p>'
              : connections
                  .map(
                    (conn) => `
              <button
                type="button"
                class="btn btn--secondary btn--sm"
                style="justify-content: space-between; width: 100%;"
                data-select-entity="${escapeHtml(conn.otherNode.id)}"
              >
                <span>${escapeHtml(conn.otherNode.label)}</span>
                <span class="field-hint">${escapeHtml(conn.edge.label)}</span>
              </button>
            `
                  )
                  .join('')
          }
        </div>
      </div>

      <div>
        <h3 class="field-label" style="margin-bottom: 0.5rem;">Source references (${sources.length})</h3>
        <ul style="display: flex; flex-direction: column; gap: 0.5rem;">
          ${
            sources.length === 0
              ? '<li class="field-hint">No source references registered.</li>'
              : sources
                  .map((src) => {
                    const title = src.document_title || src.title || src.document_url || 'Indexed Source Document';
                    const linkUrl = src.document_url
                      ? src.document_url
                      : `./results.html?q=${encodeURIComponent(src.query || node.label)}&mode=hybrid`;
                    return `
              <li>
                <a
                  href="${escapeHtml(linkUrl)}"
                  target="_blank"
                  rel="noopener"
                  class="text-link"
                  style="font-size: 0.8125rem;"
                >
                  ${escapeHtml(title)}
                </a>
                ${src.mention_count ? `<span class="field-hint" style="margin-left: 0.25rem;">(${src.mention_count} mentions)</span>` : ''}
              </li>
            `;
                  })
                  .join('')
          }
        </ul>
      </div>

      <div style="padding-top: 0.5rem; border-top: 1px solid var(--border-color); display: flex; gap: 0.5rem; flex-wrap: wrap;">
        <a href="./results.html?q=${encodeURIComponent(node.label)}&mode=hybrid" class="btn btn--primary btn--sm">
          Search in LUMO
        </a>
        <a href="./research.html?q=${encodeURIComponent(`How does ${node.label} connect to modern search and security systems?`)}" class="btn btn--secondary btn--sm">
          Research topic
        </a>
        <button type="button" id="graph-save-workspace-btn" class="btn btn--secondary btn--sm">
          Save to Workspace
        </button>
      </div>
    </div>
  `;

  const saveWsBtn = document.getElementById('graph-save-workspace-btn');
  if (saveWsBtn) {
    saveWsBtn.addEventListener('click', async () => {
      if (!isBackendConfigured()) {
        saveWsBtn.textContent = 'Configure API first';
        return;
      }
      saveWsBtn.disabled = true;
      try {
        await saveToWorkspace({
          title: `${node.label} (${node.type})`,
          content: node.description || `Knowledge Graph entity: ${node.label} (${node.type})`,
          source_type: 'graph_entity',
          source_ref_id: node.id,
          tags: [node.type],
        });
        saveWsBtn.textContent = 'Saved';
      } catch {
        saveWsBtn.textContent = 'Save failed';
        saveWsBtn.disabled = false;
      }
    });
  }
}

// Event Listeners
if (svgEl) {
  svgEl.addEventListener('click', (event) => {
    const edgeGroup = event.target.closest('[data-edge-id]');
    if (edgeGroup) {
      state.selectedEdgeId = edgeGroup.getAttribute('data-edge-id');
      renderGraph();
      return;
    }

    const nodeEl = event.target.closest('[data-node-id]');
    if (nodeEl) {
      state.selectedEdgeId = null;
      state.selectedId = nodeEl.getAttribute('data-node-id');
      if (state.isLive) loadEntityDetails(state.selectedId);
      renderGraph();
      return;
    }
  });

  svgEl.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const nodeEl = event.target.closest('[data-node-id]');
    if (!nodeEl) return;
    event.preventDefault();
    state.selectedEdgeId = null;
    state.selectedId = nodeEl.getAttribute('data-node-id');
    if (state.isLive) loadEntityDetails(state.selectedId);
    renderGraph();
  });

  // Pan dragging
  let isDragging = false;
  let startX = 0;
  let startY = 0;

  svgEl.addEventListener('pointerdown', (event) => {
    if (event.target.closest('[data-node-id]') || event.target.closest('[data-edge-id]')) return;
    isDragging = true;
    startX = event.clientX - state.panX;
    startY = event.clientY - state.panY;
    svgEl.setPointerCapture(event.pointerId);
  });

  svgEl.addEventListener('pointermove', (event) => {
    if (!isDragging) return;
    state.panX = event.clientX - startX;
    state.panY = event.clientY - startY;
    const viewport = svgEl.querySelector('#graph-viewport');
    if (viewport) {
      viewport.setAttribute('transform', `translate(${state.panX}, ${state.panY}) scale(${state.zoom})`);
    }
  });

  const endDrag = () => {
    isDragging = false;
  };
  svgEl.addEventListener('pointerup', endDrag);
  svgEl.addEventListener('pointercancel', endDrag);
}

document.addEventListener('click', (event) => {
  const trigger = event.target.closest('[data-select-entity]');
  if (!trigger) return;
  state.selectedEdgeId = null;
  state.selectedId = trigger.getAttribute('data-select-entity');
  if (state.isLive) loadEntityDetails(state.selectedId);
  renderGraph();
});

let graphSearchDebounce = null;
if (searchInput) {
  searchInput.addEventListener('input', () => {
    state.searchQuery = searchInput.value;
    if (graphSearchDebounce) window.clearTimeout(graphSearchDebounce);
    graphSearchDebounce = window.setTimeout(() => {
      renderGraph();
    }, 150);
  });
}

typeButtons.forEach((btn) => {
  btn.addEventListener('click', () => {
    state.typeFilter = btn.getAttribute('data-graph-type');
    typeButtons.forEach((b) =>
      b.setAttribute('aria-pressed', String(b.getAttribute('data-graph-type') === state.typeFilter))
    );
    renderGraph();
  });
});

if (zoomInBtn) {
  zoomInBtn.addEventListener('click', () => {
    state.zoom = Math.min(2.0, Number((state.zoom + 0.15).toFixed(2)));
    renderGraph();
  });
}

if (zoomOutBtn) {
  zoomOutBtn.addEventListener('click', () => {
    state.zoom = Math.max(0.5, Number((state.zoom - 0.15).toFixed(2)));
    renderGraph();
  });
}

if (resetViewBtn) {
  resetViewBtn.addEventListener('click', () => {
    state.zoom = 1;
    state.panX = 0;
    state.panY = 0;
    renderGraph();
  });
}

if (reprocessBtn) {
  reprocessBtn.addEventListener('click', async () => {
    reprocessBtn.disabled = true;
    const origText = reprocessBtn.textContent;
    reprocessBtn.textContent = 'Reprocessing...';
    try {
      const res = await reprocessKnowledgeGraph({ batchSize: 50 });
      alert(`Knowledge Graph reprocessed: ${res.entities_extracted} entities and ${res.relationships_extracted} relationships extracted from ${res.documents_processed} documents.`);
      await loadGraphData();
    } catch (err) {
      alert(`Reprocessing failed: ${err.message || 'FastAPI unavailable'}`);
    } finally {
      reprocessBtn.disabled = false;
      reprocessBtn.textContent = origText;
    }
  });
}

// Initial Graph Load
loadGraphData();
