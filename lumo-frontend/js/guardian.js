/**
 * LUMO Download Guardian, URL Security Analysis & File Security Analysis Controller
 * Performs genuine client-side URL SSRF pre-validation and Web Crypto SHA-256 hashing.
 * Strictly refuses to fabricate remote security verdicts without a live FastAPI scanner.
 */

import { initShell } from './ui-shell.js';
import { isBackendConfigured, submitUrlSecurityScan, submitFileHashScan } from './api.js';
import { validateAndInspectUrl } from './url-validator.js';
import { escapeHtml } from './search-data.js';

const params = new URLSearchParams(window.location.search);
const initialTab = ['download', 'url', 'file'].includes(params.get('tab'))
  ? params.get('tab')
  : 'download';
const initialUrl = (params.get('url') || '').trim();

const activeModuleMap = {
  download: 'guardian',
  url: 'url-security',
  file: 'file-security',
};

initShell({ activeModule: activeModuleMap[initialTab] || 'guardian', borderedHeader: true });

// Tabs
const tabButtons = Array.from(document.querySelectorAll('[data-guardian-tab]'));
const tabPanels = {
  download: document.getElementById('panel-download'),
  url: document.getElementById('panel-url'),
  file: document.getElementById('panel-file'),
};

function selectTab(tab) {
  tabButtons.forEach((btn) => {
    const active = btn.getAttribute('data-guardian-tab') === tab;
    btn.setAttribute('aria-selected', String(active));
  });
  Object.entries(tabPanels).forEach(([key, panel]) => {
    if (panel) panel.hidden = key !== tab;
  });
  const nextParams = new URLSearchParams(window.location.search);
  nextParams.set('tab', tab);
  window.history.replaceState(null, '', `./guardian.html?${nextParams.toString()}`);
}

tabButtons.forEach((btn) => {
  btn.addEventListener('click', () => selectTab(btn.getAttribute('data-guardian-tab')));
});

// Shared URL Inspection Logic for Download Guardian & URL Security Analysis
async function handleUrlInspection({ inputEl, outputEl, feedbackEl }) {
  const raw = (inputEl?.value || '').trim();
  const localCheck = validateAndInspectUrl(raw);

  if (!localCheck.ok) {
    if (feedbackEl) feedbackEl.textContent = localCheck.error;
    if (outputEl) {
      outputEl.innerHTML = localCheck.blocked
        ? `
        <div class="panel" role="alert">
          <h3 class="section-heading">Request blocked by SSRF protection</h3>
          <p class="section-desc" style="margin-bottom: 0;">${escapeHtml(localCheck.error)}</p>
        </div>
      `
        : '';
    }
    return;
  }

  if (feedbackEl) feedbackEl.textContent = '';

  let remoteScan = null;
  let remoteError = null;

  if (isBackendConfigured()) {
    if (outputEl) {
      outputEl.innerHTML = `<div class="panel"><p class="section-desc" style="margin: 0;">Scanning URL via LUMO FastAPI security service...</p></div>`;
    }
    try {
      remoteScan = await submitUrlSecurityScan(localCheck.normalizedUrl);
    } catch (err) {
      remoteError = err.message;
    }
  }

  const risk = remoteScan?.risk_classification || 'Unknown';
  const riskLevels = [
    { name: 'Low Risk', desc: 'No threats identified by available checks. Not an absolute guarantee.' },
    { name: 'Suspicious', desc: 'Anomalies in redirects, domain reputation, or metadata.' },
    { name: 'Malicious', desc: 'Matched confirmed threat intelligence or harmful payload indicators.' },
    { name: 'Unknown', desc: 'Insufficient backend telemetry or scanner not connected.' },
  ];

  const notesHtml =
    localCheck.syntacticNotes.length > 0
      ? `<ul style="display: flex; flex-direction: column; gap: 0.35rem; margin-top: 0.25rem;">${localCheck.syntacticNotes
          .map((n) => `<li>• ${escapeHtml(n)}</li>`)
          .join('')}</ul>`
      : 'No local URL syntax warnings detected (does not verify remote safety).';

  if (outputEl) {
    outputEl.innerHTML = `
      <div class="panel-stack">
        <div class="notice-banner">
          <div>
            <strong>${
              remoteScan
                ? 'FastAPI Security Scan Completed'
                : 'Local URL Structural Inspection Only'
            }</strong> · ${
              remoteScan
                ? 'Remote telemetry returned from configured FastAPI backend.'
                : remoteError
                  ? `FastAPI scan failed (${escapeHtml(remoteError)}). Showing local URL parsing only; risk remains Unknown.`
                  : 'Remote redirect tracing, domain reputation, and threat intelligence require the LUMO FastAPI backend. No remote verdict has been invented.'
            }
          </div>
        </div>

        <div class="panel">
          <h3 class="section-heading">Risk classification: ${escapeHtml(risk)}</h3>
          <p class="section-desc">
            A Low Risk classification is never an absolute guarantee of safety. Always verify software sources and cryptographic hashes independently.
          </p>
          <div class="risk-grid">
            ${riskLevels
              .map(
                (lvl) => `
              <div class="risk-card${lvl.name === risk ? ' risk-card--active' : ''}">
                <span class="risk-card__name">${lvl.name}</span>
                <span class="risk-card__desc">${lvl.desc}</span>
              </div>
            `
              )
              .join('')}
          </div>
        </div>

        <div class="panel">
          <h3 class="section-heading">URL structural &amp; security report</h3>
          <div class="kv-list">
            <div class="kv-row">
              <span class="kv-key">Normalized URL</span>
              <span class="kv-val mono">${escapeHtml(localCheck.normalizedUrl)}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Protocol / Port</span>
              <span class="kv-val mono">${escapeHtml(localCheck.protocol.replace(':', '').toUpperCase())} · Port ${escapeHtml(localCheck.port)}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Hostname</span>
              <span class="kv-val mono">${escapeHtml(localCheck.hostname)}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Path / Extension</span>
              <span class="kv-val mono">${escapeHtml(localCheck.pathname)}${
                localCheck.fileExtension ? ` (.${escapeHtml(localCheck.fileExtension)})` : ''
              }</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">SSRF Validation</span>
              <span class="kv-val">Passed local public-address check (backend DNS &amp; redirect re-validation required)</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Local Syntax Notes</span>
              <span class="kv-val">${notesHtml}</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Redirect Chain</span>
              <span class="kv-val">${
                remoteScan?.redirects
                  ? escapeHtml(JSON.stringify(remoteScan.redirects))
                  : 'Not scanned — requires FastAPI server-side redirect inspector'
              }</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">Domain Reputation</span>
              <span class="kv-val">${
                remoteScan?.domain_reputation
                  ? escapeHtml(String(remoteScan.domain_reputation))
                  : 'Unknown — requires FastAPI threat intelligence integration'
              }</span>
            </div>
            <div class="kv-row">
              <span class="kv-key">File Hash / Metadata</span>
              <span class="kv-val">${
                remoteScan?.sha256
                  ? `<span class="mono">${escapeHtml(remoteScan.sha256)}</span>`
                  : 'Unavailable until controlled server-side download inspection is active'
              }</span>
            </div>
          </div>
        </div>
      </div>
    `;
  }
}

// Wire Download Guardian form
const dgForm = document.getElementById('dg-url-form');
const dgInput = document.getElementById('dg-url-input');
const dgOutput = document.getElementById('dg-url-output');
const dgFeedback = document.getElementById('dg-url-feedback');

if (dgForm) {
  dgForm.addEventListener('submit', (e) => {
    e.preventDefault();
    handleUrlInspection({ inputEl: dgInput, outputEl: dgOutput, feedbackEl: dgFeedback });
  });
}

// Wire URL Security Analysis form
const urlForm = document.getElementById('urlsec-form');
const urlInput = document.getElementById('urlsec-input');
const urlOutput = document.getElementById('urlsec-output');
const urlFeedback = document.getElementById('urlsec-feedback');

if (urlForm) {
  urlForm.addEventListener('submit', (e) => {
    e.preventDefault();
    handleUrlInspection({ inputEl: urlInput, outputEl: urlOutput, feedbackEl: urlFeedback });
  });
}

// Quick test buttons (demonstrate public URL parsing + SSRF blocking)
document.addEventListener('click', (event) => {
  const sampleTrigger = event.target.closest('[data-test-url]');
  if (!sampleTrigger) return;
  const sampleUrl = sampleTrigger.getAttribute('data-test-url');
  const target = sampleTrigger.getAttribute('data-test-target');
  if (target === 'urlsec' && urlInput) {
    urlInput.value = sampleUrl;
    handleUrlInspection({ inputEl: urlInput, outputEl: urlOutput, feedbackEl: urlFeedback });
  } else if (dgInput) {
    dgInput.value = sampleUrl;
    handleUrlInspection({ inputEl: dgInput, outputEl: dgOutput, feedbackEl: dgFeedback });
  }
});

// File Security Analysis (Real Browser Web Crypto SHA-256 Hashing)
const dropzone = document.getElementById('file-dropzone');
const fileInput = document.getElementById('file-security-input');
const fileSelectBtn = document.getElementById('file-select-btn');
const fileReportMount = document.getElementById('file-report-mount');
const fileDownloadBtn = document.getElementById('file-download-report');
const fileStatusEl = document.getElementById('file-analysis-status');

let latestFileReport = null;

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

async function computeSha256Hex(file) {
  const buffer = await file.arrayBuffer();
  const digest = await window.crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

function setFileStatus(statusText) {
  if (fileStatusEl) fileStatusEl.textContent = statusText;
}

async function inspectSelectedFile(file) {
  if (!file) return;
  latestFileReport = null;
  if (fileDownloadBtn) fileDownloadBtn.disabled = true;

  setFileStatus('Scanning · Computing local SHA-256 digest...');

  try {
    const sha256 = await computeSha256Hex(file);
    let backendThreatResult = null;
    let status = 'Unknown';
    let findingsNote =
      'Local cryptographic SHA-256 hash computed in browser. Threat intelligence lookup requires the LUMO FastAPI backend.';

    if (isBackendConfigured()) {
      try {
        backendThreatResult = await submitFileHashScan({
          filename: file.name,
          size_bytes: file.size,
          mime_type: file.type || 'application/octet-stream',
          sha256,
        });
        status = 'Completed';
        findingsNote =
          backendThreatResult?.summary || 'Threat intelligence response received from FastAPI.';
      } catch (err) {
        status = 'Failed';
        findingsNote = `FastAPI threat lookup failed (${err.message}). Local SHA-256 digest remains valid.`;
      }
    }

    setFileStatus(status);

    latestFileReport = {
      platform: 'LUMO File Security Analysis',
      generatedAt: new Date().toISOString(),
      status,
      disclaimer:
        'Selecting or hashing a file locally does not verify that it is safe. Always confirm file authenticity and scan via trusted security engines.',
      file: {
        name: file.name,
        sizeBytes: file.size,
        sizeFormatted: formatBytes(file.size),
        mimeType: file.type || 'Unknown / application/octet-stream',
        sha256,
      },
      threatIntelligence: backendThreatResult || {
        classification: 'Unknown',
        note: findingsNote,
      },
    };

    if (fileDownloadBtn) fileDownloadBtn.disabled = false;

    if (fileReportMount) {
      fileReportMount.innerHTML = `
        <div class="kv-list">
          <div class="kv-row">
            <span class="kv-key">Analysis Status</span>
            <span class="kv-val"><strong>${escapeHtml(status)}</strong></span>
          </div>
          <div class="kv-row">
            <span class="kv-key">File Name</span>
            <span class="kv-val mono">${escapeHtml(file.name)}</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">File Size</span>
            <span class="kv-val tabular-nums">${escapeHtml(formatBytes(file.size))} (${file.size} bytes)</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">File Type</span>
            <span class="kv-val mono">${escapeHtml(file.type || 'Unknown / binary')}</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">SHA-256 Hash</span>
            <span class="kv-val mono" style="font-size: 0.78rem;">${escapeHtml(sha256)}</span>
          </div>
          <div class="kv-row">
            <span class="kv-key">Threat Intelligence</span>
            <span class="kv-val">${escapeHtml(findingsNote)}</span>
          </div>
        </div>
      `;
    }
  } catch (err) {
    setFileStatus('Failed');
    if (fileReportMount) {
      fileReportMount.innerHTML = `<p class="field-hint">Unable to read or hash the selected file: ${escapeHtml(err.message)}</p>`;
    }
  }
}

if (fileSelectBtn && fileInput) {
  fileSelectBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => {
    if (fileInput.files && fileInput.files[0]) {
      inspectSelectedFile(fileInput.files[0]);
    }
  });
}

if (dropzone) {
  ['dragenter', 'dragover'].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.add('is-dragover');
    });
  });
  ['dragleave', 'drop'].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      dropzone.classList.remove('is-dragover');
    });
  });
  dropzone.addEventListener('drop', (e) => {
    const file = e.dataTransfer?.files?.[0];
    if (file) inspectSelectedFile(file);
  });
}

if (fileDownloadBtn) {
  fileDownloadBtn.addEventListener('click', () => {
    if (!latestFileReport) return;
    const blob = new Blob([JSON.stringify(latestFileReport, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `lumo-file-report-${latestFileReport.file.sha256.slice(0, 12)}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
}

// Initialize tab and optional pre-filled URL from Search Results
selectTab(initialTab);
if (initialUrl) {
  if (initialTab === 'url' && urlInput) {
    urlInput.value = initialUrl;
    handleUrlInspection({ inputEl: urlInput, outputEl: urlOutput, feedbackEl: urlFeedback });
  } else if (dgInput) {
    dgInput.value = initialUrl;
    handleUrlInspection({ inputEl: dgInput, outputEl: dgOutput, feedbackEl: dgFeedback });
  }
}
