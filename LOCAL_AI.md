# LUMO Offline AI Intelligence Engine (Local Ollama)

LUMO integrates locally hosted language models via **Ollama** (`http://localhost:11434`) through the central `AIProviderRouter`, enabling offline chat, SSE streaming, document tasks, and grounded local RAG without external API keys.

---

## 1. Windows Ollama Setup & Model Selection

1. Install **Ollama for Windows** and ensure the local Ollama service is running (`http://127.0.0.1:11434`).
2. Manually pull a model suited for your hardware (e.g. 8GB VRAM / 16GB RAM):
   ```powershell
   ollama pull llama3.2
   # Or smaller/faster alternatives:
   ollama pull qwen2.5:3b
   ollama pull phi3:mini
   ```
   *(LUMO never downloads models automatically.)*
3. Open **Settings** (`http://127.0.0.1:3000/settings.html`) -> **Local AI & Ollama Models** to view installed models, set your preferred model, test connection latency, and toggle **Local-Only Privacy Mode**.

---

## 2. Local-Only Privacy Mode

When `local_only_mode` (`LOCAL_ONLY_AI=true`) is enabled:
- All AI requests route strictly to local **Ollama**.
- External providers (`gemini`, `grok`) are explicitly blocked—no silent external fallback ever occurs.
- Retrieved documents and workspace items remain on your local machine.

---

## 3. Architecture & Resource Protection

- **Concurrency Guard**: `OllamaProvider` uses a bounded semaphore (`_INFERENCE_SEMAPHORE`) so multiple large models are never loaded into 8GB VRAM simultaneously.
- **Context Budget**: `gather_local_rag_context()` enforces `LOCAL_AI_MAX_CONTEXT_CHARS` (default `12000`), deduplicates chunks, and sanitizes text via `ContextBuilder._sanitize_for_prompt()` against prompt injection.
- **Cancellation**: Streaming SSE chat (`POST /api/v1/local-ai/chat/stream`) monitors `request.is_disconnected()`, and background tasks support `POST /api/v1/local-ai/tasks/{task_id}/cancel`.

---

## 4. APIs (`/api/v1/local-ai`)

- `GET /api/v1/local-ai/status` — Ollama reachability, privacy mode, model count, and setup guidance.
- `POST /api/v1/local-ai/config` — Update `local_only_mode`, `ollama_enabled`, `ollama_model`, or `primary_provider`.
- `GET /api/v1/local-ai/models` — List locally installed Ollama models with size and capabilities.
- `POST /api/v1/local-ai/test` — Test latency and health of a local model.
- `POST /api/v1/local-ai/chat` — Multi-turn local chat with optional grounded RAG (`[L1]` citations).
- `POST /api/v1/local-ai/chat/stream` — Real-time Server-Sent Events (`text/event-stream`) token streaming.
- `POST /api/v1/local-ai/tasks` — Run summarization, study notes, FAQ, extraction, comparison, or classification tasks.
- `GET /api/v1/local-ai/tasks/{task_id}` & `POST /api/v1/local-ai/tasks/{task_id}/cancel`.

---

## 5. Testing

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_local_ai.py -v
```
