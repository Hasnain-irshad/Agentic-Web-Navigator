# Agentic Web Navigator

An autonomous web-navigation system that completes multi-step web tasks from a natural-language goal.  
A Python agent reasons about each step using an LLM and drives a custom Electron browser to perform real browser actions.

---

# Architecture

The project contains two processes communicating over a WebSocket connection.

```text
+---------------------------+         WebSocket          +-----------------------------+
|      agent-backend        | <------------------------> |      electron-browser       |
|  (FastAPI + LLM planner)  |     ws://127.0.0.1:8000/ws|  (Electron + React UI)      |
|                           |                            |                             |
|  - Task planner           |                            |  - Address bar / tabs       |
|  - World model + memory   |                            |  - <webview> for sites      |
|  - Action reasoner (Groq) |                            |  - History + bookmarks      |
+---------------------------+                            +-----------------------------+
```

The backend decides **what** action should happen next.  
The Electron browser executes the action on a real webpage and sends back updated observations.

This loop continues until the task is completed.

---

# Repository Structure

```text
.
├── agent-backend/      # FastAPI WebSocket server + LLM agent
└── electron-browser/   # Electron + React + TypeScript desktop browser
```

---

# Features

- Autonomous browser navigation
- LLM-powered task planning
- Real webpage interaction using Electron
- WebSocket-based communication
- Multi-step reasoning and execution
- Browser history and bookmarks
- CLI and GUI support
- Playwright integration for automation

---

# Requirements

Before running the project, ensure you have:

- Python 3.9+
- Node.js 18+
- npm 7+
- A Groq API key

Get a free API key from:

👉 https://console.groq.com

---

# Setup

## 1. Backend Setup

Navigate to the backend folder:

```bash
cd agent-backend
```

Create a virtual environment:

```bash
python -m venv venv
```

Activate the environment:

### Windows

```bash
venv\Scripts\activate
```

### macOS / Linux

```bash
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Install Playwright Chromium:

```bash
playwright install chromium
```

---

## Environment Configuration

Create a `.env` file inside `agent-backend/`.

You can copy values from `.env.example`.

Example configuration:

```env
GROQ_API_KEY=your_groq_key_here
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
HEADLESS=false
BROWSER_TIMEOUT=30000
MAX_STEPS=25
OBSERVATION_MAX_ELEMENTS=80
```

---

## 2. Electron Browser Setup

Navigate to the Electron application:

```bash
cd electron-browser
```

Install dependencies:

```bash
npm install
```

---

# Running the Project

You need **two terminals** running simultaneously.

---

## Terminal 1 — Start Backend

```bash
cd agent-backend
python server.py
```

The backend server starts at:

```text
ws://127.0.0.1:8000/ws
```

---

## Terminal 2 — Start Electron Browser

```bash
cd electron-browser
npm start
```

Wait for Webpack compilation to finish.

The Electron desktop application will launch automatically.

---

# How It Works

1. User enters a goal in the Electron sidebar.
2. The renderer sends the goal and session ID through WebSocket.
3. The backend agent plans the next action using the Groq LLM.
4. Electron executes the action on the active webpage.
5. The browser captures a fresh observation:
   - URL
   - headings
   - visible interactive elements
6. The updated observation is sent back to the backend.
7. The loop continues until the task is completed.

---

# Common Commands

## Backend Commands

| Command | Purpose |
|---|---|
| `python server.py` | Run WebSocket agent server |
| `python main.py "<goal>"` | Run one-shot CLI task |
| `python gui.py` | Launch standalone Tkinter GUI |
| `pytest test_suite.py` | Run backend tests |

---

## Electron Commands

| Command | Purpose |
|---|---|
| `npm start` | Development mode with hot reload |
| `npm run build` | Production build |
| `npm run package` | Create distributable installer |
| `npm run lint` | Run ESLint |
| `npm test` | Run Jest tests |

---

# Troubleshooting

## Electron IPC Error

### Error

```text
TypeError: Cannot read properties of undefined (reading 'ipcRenderer')
```

### Cause

You opened:

```text
http://localhost:1212
```

inside a regular browser instead of the Electron app.

### Solution

Run the Electron application using:

```bash
npm start
```

---

## Backend Not Connecting

Ensure the backend server is running before launching Electron:

```bash
python server.py
```

---

## Playwright Errors

If Chromium fails on first run:

```bash
playwright install chromium
```

Run the command inside the activated virtual environment.

---

# Documentation

For deeper implementation details:

- `agent-backend/ARCHITECTURE.md`
- `electron-browser/src`

---

# License

This project is intended for educational and research purposes.

---

# Notes

- Example `.env` values are placeholders only.
- Add screenshots, badges, and CI status later if needed.
- After updating the README on GitHub, sync your local repository:

```bash
git pull
```
