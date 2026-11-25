/**
 * LUMO Offline AI Intelligence Engine Controller
 * Streaming local chat, Stop generation, Local-Only Privacy Mode,
 * model selection, grounded RAG citations, and Offline Task Engine.
 */

import { initShell } from './ui-shell.js';
import { escapeHtml } from './search-data.js';
import {
  isBackendConfigured,
  fetchLocalAIStatus,
  fetchLocalAIModels,
  updateLocalAIConfig,
  streamLocalAIChat,
  runLocalAITask,
} from './api.js';

initShell({ activeModule: 'local-ai', borderedHeader: true });

const statusTextEl = document.getElementById('local-ai-status-text');
const localOnlyToggle = document.getElementById('local-only-toggle');
const modelSelect = document.getElementById('local-ai-model-select');
const ragSelect = document.getElementById('local-ai-rag-select');
const clearBtn = document.getElementById('local-ai-clear-btn');
const messagesMount = document.getElementById('local-ai-messages');
const citationsMount = document.getElementById('local-ai-citations');
const chatForm = document.getElementById('local-ai-chat-form');
const chatInput = document.getElementById('local-ai-input');
const sendBtn = document.getElementById('local-ai-send-btn');
const stopBtn = document.getElementById('local-ai-stop-btn');

const taskForm = document.getElementById('local-ai-task-form');
const taskTypeSelect = document.getElementById('local-ai-task-type');
const taskRagCheck = document.getElementById('local-ai-task-rag');
const taskPromptInput = document.getElementById('local-ai-task-prompt');
const taskRunBtn = document.getElementById('local-ai-task-run-btn');
const taskOutputEl = document.getElementById('local-ai-task-output');

const state = {
  history: [],
  abortController: null,
};

async function initLocalAI() {
  if (!isBackendConfigured()) {
    if (statusTextEl) {
      statusTextEl.innerHTML = '<strong>Backend not configured</strong> · Set FastAPI URL in <a href="./settings.html" class="text-link">Settings</a>.';
    }
    return;
  }

  try {
    const [status, modelsRes] = await Promise.all([
      fetchLocalAIStatus(),
      fetchLocalAIModels(),
    ]);

    if (localOnlyToggle) localOnlyToggle.checked = Boolean(status.local_only_mode);

    if (statusTextEl) {
      if (!status.reachable) {
        statusTextEl.innerHTML = `<strong>Ollama Offline</strong> · ${escapeHtml(status.setup_instructions || 'Start Ollama locally to run offline inference.')}`;
      } else if (status.models_count === 0) {
        statusTextEl.innerHTML = `<strong>Ollama Connected (0 models)</strong> · ${escapeHtml(status.setup_instructions || 'Pull a model manually using ollama pull.')}`;
      } else {
        statusTextEl.innerHTML = `<strong>Local AI Ready</strong> · Ollama online (${status.models_count} models) · ${status.local_only_mode ? 'Local-Only Privacy Mode ON' : 'Standard Router'}`;
      }
    }

    if (modelSelect) {
      const models = modelsRes.models || [];
      if (models.length === 0) {
        modelSelect.innerHTML = `<option value="${escapeHtml(status.default_model)}">${escapeHtml(status.default_model)} (default)</option>`;
      } else {
        modelSelect.innerHTML = models
          .map(
            (m) => `<option value="${escapeHtml(m.name)}" ${m.name === status.default_model ? 'selected' : ''}>${escapeHtml(m.name)} (${m.size_gb} GB)</option>`
          )
          .join('');
      }
    }
  } catch (err) {
    if (statusTextEl) statusTextEl.textContent = `Local AI status error: ${err.message}`;
  }
}

function renderMessages() {
  if (!messagesMount) return;
  if (state.history.length === 0) {
    messagesMount.innerHTML = '<p class="field-hint">Ask a question or analyze your saved knowledge offline.</p>';
    return;
  }
  messagesMount.innerHTML = state.history
    .map(
      (m, idx) => `
      <div class="panel panel--subtle" style="padding: 0.65rem 0.8rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem;">
          <strong style="font-size: 0.75rem; text-transform: uppercase;">${escapeHtml(m.role)}</strong>
          ${m.role === 'assistant' ? `<button type="button" class="btn btn--ghost btn--sm" data-copy-msg="${idx}" style="font-size: 0.7rem; padding: 2px 6px;">Copy</button>` : ''}
        </div>
        <div style="font-size: 0.875rem; white-space: pre-wrap;">${escapeHtml(m.content)}</div>
      </div>
    `
    )
    .join('');
  messagesMount.scrollTop = messagesMount.scrollHeight;
}

if (localOnlyToggle) {
  localOnlyToggle.addEventListener('change', async () => {
    try {
      await updateLocalAIConfig({ local_only_mode: localOnlyToggle.checked });
      await initLocalAI();
    } catch (err) {
      alert(`Could not update privacy mode: ${err.message}`);
    }
  });
}

if (clearBtn) {
  clearBtn.addEventListener('click', () => {
    state.history = [];
    if (citationsMount) citationsMount.style.display = 'none';
    renderMessages();
  });
}

if (stopBtn) {
  stopBtn.addEventListener('click', () => {
    if (state.abortController) {
      state.abortController.abort();
      state.abortController = null;
    }
  });
}

if (messagesMount) {
  messagesMount.addEventListener('click', async (ev) => {
    const btn = ev.target.closest('[data-copy-msg]');
    if (!btn) return;
    const msg = state.history[Number(btn.getAttribute('data-copy-msg'))];
    if (msg && navigator.clipboard) {
      await navigator.clipboard.writeText(msg.content);
      btn.textContent = 'Copied';
    }
  });
}

if (chatForm) {
  chatForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const prompt = chatInput.value.trim();
    if (!prompt) return;

    state.history.push({ role: 'user', content: prompt });
    const assistantMsg = { role: 'assistant', content: '' };
    state.history.push(assistantMsg);
    chatInput.value = '';
    renderMessages();

    sendBtn.disabled = true;
    stopBtn.disabled = false;
    state.abortController = new AbortController();

    const ragMode = ragSelect ? ragSelect.value : 'both';
    try {
      await streamLocalAIChat(
        {
          messages: state.history.slice(0, -1),
          model: modelSelect ? modelSelect.value : null,
          use_rag: ragMode !== 'none',
          rag_scope: ragMode === 'none' ? 'both' : ragMode,
        },
        {
          signal: state.abortController.signal,
          onCitations: (cites) => {
            if (!citationsMount || !cites.length) return;
            citationsMount.style.display = 'block';
            citationsMount.innerHTML = `
              <div class="panel panel--subtle" style="font-size: 0.75rem;">
                <strong>Grounded Local Sources:</strong>
                <ul style="margin-top: 0.25rem;">
                  ${cites.map((c) => `<li>[${escapeHtml(c.key)}] ${escapeHtml(c.title)} (${escapeHtml(c.source_type)})</li>`).join('')}
                </ul>
              </div>
            `;
          },
          onToken: (chunk) => {
            if (chunk.token) {
              assistantMsg.content += chunk.token;
              renderMessages();
            }
          },
          onError: (detail) => {
            assistantMsg.content = `Error: ${detail}`;
            renderMessages();
          },
        }
      );
    } catch (err) {
      if (err.name === 'AbortError') {
        assistantMsg.content += '\n[Generation stopped by user]';
      } else {
        assistantMsg.content = `Local AI unavailable: ${err.message}`;
      }
      renderMessages();
    } finally {
      sendBtn.disabled = false;
      stopBtn.disabled = true;
      state.abortController = null;
    }
  });
}

if (taskForm) {
  taskForm.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const prompt = taskPromptInput.value.trim();
    if (!prompt) return;
    taskRunBtn.disabled = true;
    taskOutputEl.textContent = 'Running local inference task...';
    try {
      const res = await runLocalAITask({
        task_type: taskTypeSelect.value,
        prompt,
        use_rag: taskRagCheck.checked,
        model: modelSelect ? modelSelect.value : null,
      });
      if (res.status === 'failed') {
        taskOutputEl.textContent = `Task failed: ${res.error}`;
      } else {
        taskOutputEl.textContent = res.result || '(Empty response)';
      }
    } catch (err) {
      taskOutputEl.textContent = `Task error: ${err.message}`;
    } finally {
      taskRunBtn.disabled = false;
    }
  });
}

initLocalAI();
