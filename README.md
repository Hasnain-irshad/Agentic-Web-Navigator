# Agentic Web Navigator

An autonomous web-navigation system that completes multi-step web tasks from a natural-language goal. A Python agent reasons about each step using an LLM and drives a custom Electron browser to actually perform the actions.

## Architecture

The project has two processes that talk over a WebSocket:

+---------------------------+         WebSocket          +-----------------------------+
|      agent-backend        | <------------------------> |      electron-browser       |
|  (FastAPI + LLM planner)  |     ws://127.0.0.1:8000/ws |  (Electron + React UI)      |
|                           |                            |                             |
|  - Task planner           |                            |  - Address bar / tabs       |
|  - World model + memory   |                            |  - <webview> for sites      |
|  - Action reasoner (Groq) |                            |  - History + bookmarks      |
+---------------------------+                            +-----------------------------+



The backend decides **what** to do next. The Electron browser executes the action on a real page and reports back the new observation. Loop continues until the goal is satisfied.

## Repository layout

.
├── agent-backend/      Python FastAPI WebSocket server + LLM agent
└── electron-browser/   Electron + React + TypeScript desktop browser



## Requirements

- **Python 3.9+** (for the backend)
- **Node.js 18+** and **npm 7+** (for the Electron app)
- A **Groq API key** — free tier at https://console.groq.com

## Setup

### 1. Backend

```bash
cd agent-backend
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
Create a .env file in agent-backend/ (copy from .env.example) and fill in your key:


GROQ_API_KEY=your_groq_key_here
LLM_MODEL=llama-3.3-70b-versatile
LLM_TEMPERATURE=0.2
LLM_MAX_TOKENS=2048
HEADLESS=false
BROWSER_TIMEOUT=30000
MAX_STEPS=25
OBSERVATION_MAX_ELEMENTS=80
2. Electron browser

cd electron-browser
npm install
Running
You need two terminals — start the backend first so the Electron app can connect to its WebSocket.

Terminal 1 — backend:


cd agent-backend
# activate the venv first (see Setup)
python server.py
Server starts on ws://127.0.0.1:8000/ws.

Terminal 2 — Electron browser:


cd electron-browser
npm start
Wait for webpack to finish — the Electron window opens automatically. Type a goal into the agent chat sidebar to start a task.

Common commands
Backend
Command	Purpose
python server.py	Run the WebSocket agent server (dev, autoreload)
python main.py "<goal>"	Run a one-shot task in the CLI
python gui.py	Standalone Tkinter GUI for the agent
pytest test_suite.py	Run the test suite
Electron
Command	Purpose
npm start	Dev: webpack-dev-server + Electron with hot reload
npm run build	Production build of main + renderer
npm run package	Build a distributable installer
npm run lint	ESLint
npm test	Jest
How a task runs
User enters a goal in the Electron sidebar.
Renderer sends the goal + a session_id over the WebSocket.
Backend WSAgent plans the next action (goto, click, type, scroll, done, …) using the Groq LLM, given the current page observation.
Electron executes the action against the active <webview>, captures a fresh observation (visible interactive elements, headings, URL).
Observation is sent back to the backend, which decides the next action — or terminates with a result.
See agent-backend/ARCHITECTURE.md and electron-browser/src for deeper details.

Troubleshooting
TypeError: Cannot read properties of undefined (reading 'ipcRenderer') — you opened http://localhost:1212 in a regular browser instead of using the Electron window that npm start launches. The preload script only exposes window.electron inside Electron.
Backend not connecting — confirm python server.py is running and listening on 127.0.0.1:8000 before launching the Electron app.
Playwright errors on first run — re-run playwright install chromium inside the activated venv.
License
This project is for educational and research use.



Two notes:

- I used the env keys I saw in your `.env` for the example block — values are placeholders, no real secret leaks.
- I didn't add a license badge / CI badge / screenshots — add those once you have them.

Once it's pasted, GitHub will commit it directly to `main` on the remote. Pull that commit locally with `git pull` so your local stays in sync.
