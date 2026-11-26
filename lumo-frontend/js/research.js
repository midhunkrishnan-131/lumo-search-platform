/**
 * LUMO Autonomous Research Agent Controller
 * Prepares the bounded research workflow (question -> plan -> live steps -> sources
 * -> evidence & contradictions -> cited report) with Pause / Resume / Cancel controls.
 * Supports live FastAPI session execution via polling as well as preview walkthrough mode.
 */

import { initShell } from './ui-shell.js';
import {
  isBackendConfigured,
  createResearchSession,
  getResearchSession,
  getResearchReport,
  cancelResearchSession,
  saveToWorkspace,
} from './api.js';
import { escapeHtml } from './search-data.js';

initShell({ activeModule: 'research', borderedHeader: true });

const params = new URLSearchParams(window.location.search);
const initialQuery = (params.get('q') || '').trim();

const formEl = document.getElementById('research-form');
const questionInput = document.getElementById('research-question-input');
const maxStepsSelect = document.getElementById('research-max-steps');
const maxSourcesSelect = document.getElementById('research-max-sources');
const startBtn = document.getElementById('research-start-btn');
const sampleBtn = document.getElementById('research-sample-btn');
const pauseBtn = document.getElementById('research-pause-btn');
const resumeBtn = document.getElementById('research-resume-btn');
const cancelBtn = document.getElementById('research-cancel-btn');
const copyReportBtn = document.getElementById('research-copy-report');
const saveReportWsBtn = document.getElementById('research-save-workspace');
const feedbackEl = document.getElementById('research-feedback');
const statusLabelEl = document.getElementById('research-status-label');
const planMount = document.getElementById('research-plan-mount');
const progressMount = document.getElementById('research-progress-mount');
const sourcesMount = document.getElementById('research-sources-mount');
const evidenceMount = document.getElementById('research-evidence-mount');
const reportMount = document.getElementById('research-report-mount');

if (questionInput && initialQuery) {
  questionInput.value = initialQuery;
}

const SAMPLE_BLUEPRINT = {
  subquestions: [
    'How do lexical (BM25) and dense vector retrieval systems differ in precision and recall?',
    'What fusion methods (such as Reciprocal Rank Fusion) combine ranked lists reliably?',
    'What latency, memory, and indexing trade-offs arise at scale?',
    'Where do benchmark studies disagree on semantic-only versus hybrid retrieval?',
  ],
  steps: [
    { label: 'Decompose research question into bounded subquestions', detail: '4 verifiable subquestions generated' },
    { label: 'Query indexed literature and documentation sources', detail: 'Bounded to configured source cap' },
    { label: 'Extract claims and cross-check source provenance', detail: 'Evaluating citations and publication dates' },
    { label: 'Identify contradictions and missing evidence', detail: 'Comparing domain-specific benchmarks' },
    { label: 'Assemble cited research brief with audit trail', detail: 'Drafting structured report' },
  ],
  sources: [
    {
      id: 'S1',
      title: 'Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods',
      venue: 'SIGIR Reference Summary (Sample Record)',
      url: 'https://engineering.lumo-sample.org/retrieval/reciprocal-rank-fusion',
    },
    {
      id: 'S2',
      title: 'Semantic Retrieval and Dense Vector Embeddings Explained',
      venue: 'LUMO Sample Research Archive',
      url: 'https://research.lumo-sample.org/retrieval/dense-vector-embeddings',
    },
    {
      id: 'S3',
      title: 'How Modern Search Engines Crawl, Index, and Rank the Web',
      venue: 'LUMO Sample Reference',
      url: 'https://reference.lumo-sample.org/search/architecture-overview',
    },
  ],
  evidence: [
    {
      kind: 'Supported Finding',
      text: 'Hybrid retrieval improves recall on paraphrased natural-language queries while preserving exact match accuracy for identifiers, error codes, and proper nouns [S1, S2].',
    },
    {
      kind: 'Contradiction Noted',
      text: 'Some domain benchmarks favor pure dense retrieval on conversational FAQs, whereas technical documentation corpora show clear regressions without lexical BM25 signals [S1, S3].',
    },
    {
      kind: 'Missing Information',
      text: 'Live cost-per-query measurements for this specific deployment cannot be verified until the LUMO FastAPI backend is connected.',
    },
  ],
  reportMarkdown: (question) =>
    `# Sample Research Report (Workspace Preview)\n\n` +
    `**Question:** ${question}\n` +
    `**Execution Mode:** Sample Walkthrough (not live autonomous retrieval)\n\n` +
    `## Executive Summary\n` +
    `Combining lexical search with dense semantic retrieval via Reciprocal Rank Fusion consistently balances exact-term recall and conceptual relevance [S1, S2].\n\n` +
    `## Evidence & Contradictions\n` +
    `- Lexical indexes excel at exact technical terms and sub-second latency [S3].\n` +
    `- Semantic embeddings capture intent across synonyms but require careful evaluation on specialized jargon [S2].\n` +
    `- Contradictions across studies primarily reflect differences in query type and corpus structure.\n\n` +
    `## Information Gaps\n` +
    `Live external source verification requires connecting the LUMO Python FastAPI research endpoint (POST /api/v1/research).`,
};

const runState = {
  mode: 'idle', // idle | running | paused | completed | cancelled | error
  isSampleWalkthrough: false,
  sessionId: null,
  pollTimerId: null,
  question: '',
  completedSteps: 0,
  timerId: null,
  reportText: '',
};

function clearAllTimers() {
  if (runState.timerId) {
    window.clearTimeout(runState.timerId);
    runState.timerId = null;
  }
  if (runState.pollTimerId) {
    window.clearTimeout(runState.pollTimerId);
    runState.pollTimerId = null;
  }
}

function updateControls() {
  const active = runState.mode === 'running' || runState.mode === 'paused';
  if (startBtn) startBtn.disabled = active;
  if (sampleBtn) sampleBtn.disabled = active;
  if (pauseBtn) pauseBtn.disabled = runState.mode !== 'running';
  if (resumeBtn) resumeBtn.disabled = runState.mode !== 'paused';
  if (cancelBtn) cancelBtn.disabled = !active;
  if (copyReportBtn) copyReportBtn.disabled = !runState.reportText;
  if (saveReportWsBtn) saveReportWsBtn.disabled = !runState.reportText;

  const labels = {
    idle: 'Idle · Ready for research question',
    running: runState.isSampleWalkthrough
      ? 'Running sample walkthrough (not live execution)'
      : 'Running via FastAPI backend',
    paused: 'Paused by user',
    completed: runState.isSampleWalkthrough
      ? 'Sample walkthrough complete'
      : 'Investigation complete',
    cancelled: 'Cancelled by user',
    error: 'Backend request failed',
  };
  if (statusLabelEl) statusLabelEl.textContent = labels[runState.mode] || 'Idle';
}

function renderWalkthroughState() {
  const maxSteps = Number(maxStepsSelect?.value || 5);
  const steps = SAMPLE_BLUEPRINT.steps.slice(0, Math.min(SAMPLE_BLUEPRINT.steps.length, maxSteps));

  if (planMount) {
    planMount.innerHTML = `
      <ol class="step-list">
        ${SAMPLE_BLUEPRINT.subquestions
          .map(
            (sub, idx) => `
          <li class="step-row">
            <span class="step-index tabular-nums">0${idx + 1}</span>
            <span>${escapeHtml(sub)}</span>
            <span class="step-status">Planned</span>
          </li>
        `
          )
          .join('')}
      </ol>
    `;
  }

  if (progressMount) {
    progressMount.innerHTML = `
      <ol class="step-list">
        ${steps
          .map((step, idx) => {
            let status = 'Pending';
            if (idx < runState.completedSteps) status = 'Done';
            else if (idx === runState.completedSteps && runState.mode === 'running') status = 'In progress';
            else if (idx === runState.completedSteps && runState.mode === 'paused') status = 'Paused';
            else if (runState.mode === 'cancelled') status = 'Cancelled';
            return `
              <li class="step-row">
                <span class="step-index tabular-nums">0${idx + 1}</span>
                <div>
                  <div>${escapeHtml(step.label)}</div>
                  <div class="field-hint">${escapeHtml(step.detail)}</div>
                </div>
                <span class="step-status">${status}</span>
              </li>
            `;
          })
          .join('')}
      </ol>
    `;
  }

  const showSources = runState.completedSteps >= 2;
  if (sourcesMount) {
    sourcesMount.innerHTML = showSources
      ? `
      <ul class="step-list">
        ${SAMPLE_BLUEPRINT.sources
          .map(
            (src) => `
          <li class="step-row">
            <span class="step-index">${escapeHtml(src.id)}</span>
            <div>
              <div>${escapeHtml(src.title)}</div>
              <div class="field-hint">${escapeHtml(src.venue)}</div>
            </div>
            <span class="step-status">Sample</span>
          </li>
        `
          )
          .join('')}
      </ul>
    `
      : '<p class="field-hint">Sources appear here once retrieval steps run.</p>';
  }

  const showEvidence = runState.completedSteps >= 4;
  if (evidenceMount) {
    evidenceMount.innerHTML = showEvidence
      ? `
      <div class="kv-list">
        ${SAMPLE_BLUEPRINT.evidence
          .map(
            (ev) => `
          <div class="kv-row">
            <span class="kv-key">${escapeHtml(ev.kind)}</span>
            <span class="kv-val">${escapeHtml(ev.text)}</span>
          </div>
        `
          )
          .join('')}
      </div>
    `
      : '<p class="field-hint">Evidence comparisons, contradictions, and information gaps appear after source evaluation.</p>';
  }

  const showReport = runState.mode === 'completed';
  if (reportMount) {
    if (showReport) {
      runState.reportText = SAMPLE_BLUEPRINT.reportMarkdown(runState.question);
      reportMount.innerHTML = `
        <div class="notice-banner" style="margin-bottom: 1rem;">
          <div><strong>Sample Output</strong> · This preview demonstrates LUMO's citation and report layout. Connect FastAPI to generate live evidence-based reports.</div>
        </div>
        <pre class="mono" style="white-space: pre-wrap; font-size: 0.8125rem; line-height: 1.6; color: var(--text-primary); margin: 0;">${escapeHtml(runState.reportText)}</pre>
      `;
    } else {
      runState.reportText = '';
      reportMount.innerHTML =
        '<p class="field-hint">The cited research report will appear once bounded investigation steps finish.</p>';
    }
  }

  updateControls();
}

function advanceWalkthrough() {
  clearAllTimers();
  const maxSteps = Math.min(
    SAMPLE_BLUEPRINT.steps.length,
    Number(maxStepsSelect?.value || 5)
  );
  if (runState.mode !== 'running') return;

  if (runState.completedSteps >= maxSteps) {
    runState.mode = 'completed';
    renderWalkthroughState();
    return;
  }

  runState.timerId = window.setTimeout(() => {
    if (runState.mode !== 'running') return;
    runState.completedSteps += 1;
    if (runState.completedSteps >= maxSteps) {
      runState.mode = 'completed';
      renderWalkthroughState();
    } else {
      renderWalkthroughState();
      advanceWalkthrough();
    }
  }, 550);
}

function startSampleWalkthrough() {
  const question =
    (questionInput?.value || '').trim() ||
    'How does hybrid search balance lexical precision and semantic recall?';
  if (questionInput && !questionInput.value.trim()) {
    questionInput.value = question;
  }
  if (feedbackEl) {
    feedbackEl.textContent =
      'Running clearly labelled sample walkthrough. Connect FastAPI in Settings for live autonomous research.';
  }
  clearAllTimers();
  runState.mode = 'running';
  runState.isSampleWalkthrough = true;
  runState.sessionId = null;
  runState.question = question;
  runState.completedSteps = 0;
  runState.reportText = '';
  renderWalkthroughState();
  advanceWalkthrough();
}

function renderLiveSession(session) {
  // Update status label
  const statusDisplay = {
    pending: 'Queued · Initializing session',
    planning: 'Planning · Formulating research objectives and subquestions',
    researching: `Researching · Iteration ${session.current_iteration}/${session.max_iterations} (Queries: ${session.queries_executed?.length || 0}/${session.max_queries})`,
    analyzing: 'Analyzing · Cross-referencing evidence and finding contradictions',
    generating_report: 'Reporting · Synthesizing structured report with citations',
    completed: 'Completed · Final cited report generated',
    cancelled: 'Cancelled · Research terminated early by user',
    failed: `Failed · ${session.error_message || 'Research session encountered an error'}`,
  };
  if (statusLabelEl) {
    statusLabelEl.textContent = statusDisplay[session.status] || session.status;
  }

  // Render Plan & Subquestions
  if (planMount) {
    const subquestions = session.plan?.subquestions || [];
    if (subquestions.length > 0) {
      planMount.innerHTML = `
        <ol class="step-list">
          ${subquestions
            .map(
              (sub, idx) => `
            <li class="step-row">
              <span class="step-index tabular-nums">0${idx + 1}</span>
              <span>${escapeHtml(sub)}</span>
              <span class="step-status">Investigated</span>
            </li>
          `
            )
            .join('')}
        </ol>
      `;
    } else {
      planMount.innerHTML = '<p class="field-hint">Formulating research subquestions...</p>';
    }
  }

  // Render Progress & Audit Trail (queries executed)
  if (progressMount) {
    const queries = session.queries_executed || [];
    if (queries.length > 0) {
      progressMount.innerHTML = `
        <ol class="step-list">
          ${queries
            .map(
              (q, idx) => `
            <li class="step-row">
              <span class="step-index tabular-nums">Q${idx + 1}</span>
              <div>
                <div><strong>${escapeHtml(q.query)}</strong></div>
                <div class="field-hint">Iteration ${q.iteration} · Found ${q.results_count} candidate results</div>
              </div>
              <span class="step-status">Retrieved</span>
            </li>
          `
            )
            .join('')}
        </ol>
      `;
    } else {
      progressMount.innerHTML = `<p class="field-hint">Status: ${escapeHtml(session.status)} · Retrieval queries will appear here.</p>`;
    }
  }

  // Render Sources
  if (sourcesMount) {
    const sources = session.sources || [];
    if (sources.length > 0) {
      sourcesMount.innerHTML = `
        <ul class="step-list">
          ${sources
            .map(
              (src) => `
            <li class="step-row">
              <span class="step-index">[${escapeHtml(src.source_id)}]</span>
              <div>
                <div><strong>${escapeHtml(src.title)}</strong></div>
                <div class="field-hint">
                  <a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="text-link">${escapeHtml(src.domain || src.url)}</a>
                </div>
              </div>
              <span class="step-status">Verified</span>
            </li>
          `
            )
            .join('')}
        </ul>
      `;
    } else {
      sourcesMount.innerHTML = '<p class="field-hint">Sources will appear once evidence is collected from hybrid search.</p>';
    }
  }

  // Render Findings, Contradictions, and Gaps
  if (evidenceMount) {
    const findings = session.findings || [];
    if (findings.length > 0) {
      evidenceMount.innerHTML = `
        <div class="kv-list">
          ${findings
            .map(
              (f) => `
            <div class="kv-row">
              <span class="kv-key">${escapeHtml(f.kind)}</span>
              <span class="kv-val">
                ${escapeHtml(f.text)}
                ${f.citations?.length ? ` <span class="mono" style="font-size: 0.75rem; color: var(--accent-primary);">[${f.citations.join(', ')}]</span>` : ''}
              </span>
            </div>
          `
            )
            .join('')}
        </div>
      `;
    } else {
      evidenceMount.innerHTML = '<p class="field-hint">Evidence evaluation and contradiction analysis will appear here.</p>';
    }
  }

  // Render Completed Report
  if (reportMount && session.report_markdown) {
    runState.reportText = session.report_markdown;
    reportMount.innerHTML = `
      <pre class="mono" style="white-space: pre-wrap; font-size: 0.8125rem; line-height: 1.6; color: var(--text-primary); margin: 0;">${escapeHtml(session.report_markdown)}</pre>
    `;
  }
}

async function pollResearchSession(sessionId) {
  if (runState.mode !== 'running') return;

  try {
    const session = await getResearchSession(sessionId);
    renderLiveSession(session);

    if (session.status === 'completed') {
      runState.mode = 'completed';
      if (feedbackEl) feedbackEl.textContent = 'Autonomous research completed successfully.';
      updateControls();
      return;
    }

    if (session.status === 'cancelled') {
      runState.mode = 'cancelled';
      if (feedbackEl) feedbackEl.textContent = 'Research session was cancelled.';
      updateControls();
      return;
    }

    if (session.status === 'failed') {
      runState.mode = 'error';
      if (feedbackEl) feedbackEl.textContent = `Research failed: ${session.error_message || 'Unknown error'}`;
      updateControls();
      return;
    }

    // Continue polling every 1200ms while running
    runState.pollTimerId = window.setTimeout(() => {
      pollResearchSession(sessionId);
    }, 1200);
  } catch (err) {
    console.warn('Research polling error:', err);
    // Retry polling in 2 seconds in case of intermittent connection
    runState.pollTimerId = window.setTimeout(() => {
      pollResearchSession(sessionId);
    }, 2000);
  }
}

async function submitLiveResearch(event) {
  event.preventDefault();
  const question = (questionInput?.value || '').trim();
  if (!question) {
    if (feedbackEl) feedbackEl.textContent = 'Enter a research question before starting.';
    if (questionInput) questionInput.focus();
    return;
  }

  if (!isBackendConfigured()) {
    if (feedbackEl) {
      feedbackEl.textContent =
        'FastAPI backend is not configured. Configure your backend URL in Settings to run POST /api/v1/research, or use "Preview Sample Walkthrough" to inspect the workspace.';
    }
    return;
  }

  clearAllTimers();
  runState.mode = 'running';
  runState.isSampleWalkthrough = false;
  runState.question = question;
  runState.reportText = '';
  updateControls();
  if (feedbackEl) feedbackEl.textContent = 'Submitting autonomous research session to FastAPI...';

  try {
    const session = await createResearchSession({
      query: question,
      max_iterations: Number(maxStepsSelect?.value || 3),
      max_sources: Number(maxSourcesSelect?.value || 8),
      auto_start: true,
    });

    runState.sessionId = session.id;
    if (feedbackEl) feedbackEl.textContent = `Session ${session.id.substring(0, 8)} started. Planning investigation...`;
    renderLiveSession(session);
    pollResearchSession(session.id);
  } catch (err) {
    runState.mode = 'error';
    if (feedbackEl) {
      feedbackEl.textContent = `FastAPI request failed: ${err.message}`;
    }
    updateControls();
  }
}

if (formEl) formEl.addEventListener('submit', submitLiveResearch);
if (sampleBtn) sampleBtn.addEventListener('click', startSampleWalkthrough);

if (pauseBtn) {
  pauseBtn.addEventListener('click', () => {
    if (runState.mode === 'running') {
      clearAllTimers();
      runState.mode = 'paused';
      renderWalkthroughState();
    }
  });
}

if (resumeBtn) {
  resumeBtn.addEventListener('click', () => {
    if (runState.mode === 'paused') {
      runState.mode = 'running';
      if (runState.isSampleWalkthrough) {
        renderWalkthroughState();
        advanceWalkthrough();
      } else if (runState.sessionId) {
        pollResearchSession(runState.sessionId);
      }
    }
  });
}

if (cancelBtn) {
  cancelBtn.addEventListener('click', async () => {
    clearAllTimers();
    if (runState.isSampleWalkthrough) {
      runState.mode = 'cancelled';
      renderWalkthroughState();
    } else if (runState.sessionId) {
      try {
        if (feedbackEl) feedbackEl.textContent = 'Cancelling research session...';
        await cancelResearchSession(runState.sessionId);
        runState.mode = 'cancelled';
        updateControls();
        if (statusLabelEl) statusLabelEl.textContent = 'Cancelled by user';
      } catch (err) {
        console.error('Failed to cancel session:', err);
        runState.mode = 'cancelled';
        updateControls();
      }
    }
  });
}

if (copyReportBtn) {
  copyReportBtn.addEventListener('click', async () => {
    if (!runState.reportText) return;
    try {
      await navigator.clipboard.writeText(runState.reportText);
      if (feedbackEl) feedbackEl.textContent = 'Report copied to clipboard.';
    } catch {
      if (feedbackEl) feedbackEl.textContent = 'Clipboard access unavailable in this browser context.';
    }
  });
}

if (saveReportWsBtn) {
  saveReportWsBtn.addEventListener('click', async () => {
    if (!runState.reportText) return;
    if (!isBackendConfigured()) {
      if (feedbackEl) feedbackEl.textContent = 'Configure FastAPI URL in Settings before saving.';
      return;
    }
    saveReportWsBtn.disabled = true;
    saveReportWsBtn.textContent = 'Saving...';
    try {
      await saveToWorkspace({
        title: `Research: ${runState.question || 'Untitled Report'}`,
        content: runState.reportText,
        source_type: 'research_report',
        source_ref_id: runState.sessionId || null,
        tags: ['research-report'],
      });
      saveReportWsBtn.textContent = 'Saved';
      if (feedbackEl) feedbackEl.textContent = 'Research report saved to Personal Workspace.';
    } catch (err) {
      saveReportWsBtn.textContent = 'Save failed';
      saveReportWsBtn.disabled = false;
      if (feedbackEl) feedbackEl.textContent = `Save failed: ${err.message}`;
    }
  });
}

updateControls();
