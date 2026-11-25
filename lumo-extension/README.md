# LUMO Browser Companion (Phase 15)

Manifest V3 browser extension for **Microsoft Edge** and **Google Chrome** (with Firefox `gecko` manifest compatibility) connecting your browser directly to your local LUMO Personal Workspace.

---

## 1. Features

- **Save Current Page**: Captures page title, URL, meta description, canonical URL, favicon, optional selected text, tags, collection, and personal note.
- **Save Selected Text**: Highlight any text on a webpage and save via the popup or right-click context menu (**Save selection to LUMO**).
- **Duplicate Detection**: Automatically checks if the current URL is already saved in your Personal Workspace.
- **Workspace Search**: Search your saved items, notes, and annotations directly from the popup and open results in LUMO.
- **Zero-Duplicate Storage**: Uses the local FastAPI backend (`/api/v1/extension/*`) and existing Workspace database; no duplicate local knowledge database is created.

---

## 2. Permissions & Security

- `activeTab` & `scripting`: Executes read-only metadata extraction **only** when the user explicitly clicks the extension icon or a context menu item.
- `contextMenus`: Registers **Save page to LUMO** and **Save selection to LUMO**.
- `storage`: Stores only extension preferences (`backendUrl`, `frontendUrl`, `theme`, `defaultCollectionId`).
- `host_permissions`: Restricted strictly to `http://127.0.0.1/*` and `http://localhost/*`.
- **Never captured**: Passwords, form inputs, cookies, authentication tokens, or browser history.

---

## 3. Installation (Developer Mode)

### Microsoft Edge
1. Start LUMO (`.\start_lumo.ps1` or backend on `127.0.0.1:8000`).
2. Open `edge://extensions` in Microsoft Edge.
3. Enable **Developer mode** (left sidebar).
4. Click **Load unpacked** and select the `lumo-extension/` folder.

### Google Chrome
1. Open `chrome://extensions` in Google Chrome.
2. Enable **Developer mode** (top-right toggle).
3. Click **Load unpacked** and select the `lumo-extension/` folder.

---

## 4. Testing

Run the extension unit tests with Node.js:
```powershell
node --test lumo-extension/tests/extension.test.mjs
```
Run the backend extension API tests:
```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_extension_api.py -v
```

---

## 5. Known Limitations

- **Local Backend Required**: Saving and searching require the local LUMO FastAPI server (`127.0.0.1:8000`) to be running.
- **Restricted Browser Pages**: `chrome://`, `edge://`, `about:`, and `file://` URLs cannot be captured due to browser security boundaries.
