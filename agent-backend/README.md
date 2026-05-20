# Agentic AI Web Navigator

An autonomous web navigation agent that completes multi-step web tasks from natural language commands. Uses Playwright for browser control and Groq LLM for intelligent decision-making.

## Features

✅ **Autonomous Task Completion** - Complete complex web tasks from natural language goals  
✅ **LLM-Driven Reasoning** - Uses Groq Llama models for intelligent action selection  
✅ **Playwright-Based Control** - No HTML parsing, only visible element interaction  
✅ **Observable Elements** - Automatically extracts and assigns IDs to interactive elements  
✅ **Action History** - Maintains context of all actions and observations  
✅ **Self-Correcting** - Retries reasoning on parsing failures  
✅ **Step Limits** - Configurable maximum steps to prevent runaway execution  
✅ **Modular Architecture** - Clean separation of concerns across components  

## Core Components

### 1. **BrowserController** (`core/browser_controller.py`)
- Manages Playwright browser lifecycle
- Executes atomic browser actions (goto, click, type, scroll, etc.)
- Handles multi-tab navigation
- Provides robust error handling

### 2. **ObservationExtractor** (`core/observation_extractor.py`)
- Extracts visible, interactive page elements
- Uses Playwright locators (no raw HTML parsing)
- Identifies buttons, links, inputs, headings
- Generates LLM-friendly page descriptions

### 3. **MemoryStore** (`core/memory_store.py`)
- Maintains action execution history
- Provides context window for LLM reasoning
- Generates task execution summary
- Tracks success/failure metrics

### 4. **AgentReasoner** (`core/agent_reasoner.py`)
- LLM-based decision engine using Groq API
- Generates next action from context
- Validates action schema compliance
- Includes retry mechanism for parsing failures

### 5. **Action Schema** (`schemas/actions.py`)
- Defines strict action types and validation
- Supported actions: GOTO, CLICK, TYPE, SCROLL, BACK, NEW_TAB, CLOSE_TAB, DONE
- JSON serialization for consistency

## Architecture

```
User Goal (Natural Language)
        ↓
┌───────────────────────────────────┐
│   WebNavigatorAgent (Orchestrator) │
└───────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────┐
│  OBSERVE → REASON → EXECUTE → STORE Loop             │
│                                                      │
│  1. OBSERVE  - ObservationExtractor                  │
│               Extract visible elements              │
│                                                      │
│  2. REASON   - AgentReasoner (LLM)                   │
│               Decide next action                    │
│                                                      │
│  3. EXECUTE  - BrowserController                     │
│               Perform action in browser              │
│                                                      │
│  4. STORE    - MemoryStore                           │
│               Save action & observation              │
│                                                      │
│  5. REPEAT   - Until goal achieved or max steps     │
└─────────────────────────────────────────────────────┘
        ↓
Final Task Summary & Results
```

## Installation

### Prerequisites
- Python 3.9+
- Groq API Key (free tier available at https://console.groq.com)

### Setup Steps

1. **Clone/Download the project**
   ```bash
   cd agentic_web_navigator
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install chromium
   ```

5. **Configure environment**
   ```bash
   # Copy template
   cp .env.template .env
   
   # Edit .env and add your Groq API key
   # GROQ_API_KEY=your_key_here
   ```

## Usage

### GUI Interface (Easiest)

```bash
# Launch the graphical interface
python gui.py
```

The GUI provides:
- Task goal input
- Real-time execution log with color-coded output
- Configuration options (headless, mock mode, max steps)
- Task summary and metrics
- Save results as JSON

See [GUI_GUIDE.txt](GUI_GUIDE.txt) for detailed GUI instructions.

### Basic Command Line

```bash
# Search for something on Google
python main.py --goal "Search for 'artificial intelligence' on Google"

# Run in visible mode (see browser)
python main.py --goal "Find Python projects on GitHub" --visible

# Use mock reasoner (no API key needed, for testing)
python main.py --goal "Navigate to example.com" --mock

# Set custom step limit
python main.py --goal "Your task" --max-steps 15

# Save results to file
python main.py --goal "Your task" --output results.json
```

### Python API

```python
import asyncio
from main import WebNavigatorAgent

async def run_task():
    agent = WebNavigatorAgent(
        goal="Find the latest Python news",
        max_steps=10,
        headless=False,  # Show browser window
        use_mock=False,   # Use real LLM (requires API key)
    )
    result = await agent.run()
    print(result)

asyncio.run(run_task())
```

## Configuration

Environment variables in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | - | Your Groq API key (required) |
| `LLM_MODEL` | llama-3.1-8b-instant | Model to use |
| `LLM_TEMPERATURE` | 0.1 | Model temperature (lower = more deterministic) |
| `LLM_MAX_TOKENS` | 1024 | Max tokens per response |
| `HEADLESS` | true | Run browser in headless mode |
| `BROWSER_TIMEOUT` | 30000 | Browser action timeout (ms) |
| `MAX_STEPS` | 20 | Default maximum steps |
| `OBSERVATION_MAX_ELEMENTS` | 50 | Max elements to extract per page |

## Supported Actions

The agent can execute these atomic actions:

### Navigation
- `GOTO` - Navigate to URL
- `BACK` - Go back in browser history
- `NEW_TAB` - Open new tab
- `CLOSE_TAB` - Close current tab

### Interaction
- `CLICK` - Click on element
- `TYPE` - Type text into input field
- `SCROLL` - Scroll page (up/down)

### Control
- `DONE` - Mark task as complete

## Examples

### Example 1: Search and Click
```bash
python main.py --goal "Search for 'Python' on Google and click the Wikipedia result" --visible
```

### Example 2: Multiple Steps
```bash
python main.py --goal "Go to GitHub, search for 'machine learning', find most starred repo" --visible
```

### Example 3: Testing with Mock
```bash
python main.py --goal "Test navigation" --mock
```

### Example 4: Batch Execution
```python
# Run multiple tasks
import asyncio
from main import WebNavigatorAgent

async def run_tasks():
    tasks = [
        "Search for Python on Google",
        "Find GitHub Python repositories",
    ]
    
    for task in tasks:
        agent = WebNavigatorAgent(task, headless=False)
        result = await agent.run()
        print(f"Task: {task}")
        print(f"Status: {result['status']}")
        print()

asyncio.run(run_tasks())
```

## Hard Constraints (Enforced)

✓ **No authentication** - Navigates public web only  
✓ **No CAPTCHA** - Avoids and skips CAPTCHA pages  
✓ **No payments** - Never initiates transactions  
✓ **No HTML parsing** - Uses only Playwright locators  
✓ **No hardcoded flows** - Pure LLM-driven logic  
✓ **No BeautifulSoup** - Observable elements only  
✓ **One action per step** - Strict action schema  

## Limitations & Known Issues

- Large pages may take time to extract elements
- JavaScript-heavy sites may have limited element visibility initially
- Complex interactions (drag-drop, file upload) not supported
- CAPTCHA pages will cause task failure
- Session-based authentication not supported

## Troubleshooting

### API Key Issues
```
Error: GROQ_API_KEY environment variable is required
```
**Solution:** Create `.env` file with your Groq API key

### Browser Timeout
```
Error: Browser timeout after 30000ms
```
**Solution:** Increase `BROWSER_TIMEOUT` in `.env` or `--max-steps`

### No Elements Found
```
Warning: Extracted 0 elements
```
**Solution:** 
- Try `--visible` to see page state
- Page may require scroll to load elements
- Site might block Playwright (use headless=false to debug)

### LLM Rate Limit
```
Error: Rate limit exceeded
```
**Solution:** Wait and retry. Groq free tier has request limits.

## Project Structure

```
agentic_web_navigator/
├── main.py                      # Main entry point
├── config.py                    # Configuration
├── requirements.txt             # Dependencies
├── .env.template               # Environment template
├── core/
│   ├── __init__.py
│   ├── browser_controller.py    # Playwright wrapper
│   ├── observation_extractor.py # Element extraction
│   ├── agent_reasoner.py        # LLM reasoning
│   └── memory_store.py          # Context & history
├── schemas/
│   ├── __init__.py
│   └── actions.py               # Action definitions
├── utils/
│   ├── __init__.py
│   ├── logger.py                # Logging setup
│   └── validators.py            # Validation helpers
└── examples/
    └── sample_tasks.py          # Example usage
```

## Performance Tips

1. **Use `--visible` during testing** - See what agent is doing
2. **Start with mock mode** - Verify logic without API calls
3. **Set appropriate `MAX_STEPS`** - Complex tasks need more steps
4. **Monitor element extraction** - Check console output
5. **Use headless=false** - Better visibility for debugging

## Development

### Adding New Actions

1. Add to `ActionType` enum in `schemas/actions.py`
2. Add validation in `Action._validate()`
3. Implement handler in `BrowserController._execute_action()`
4. Update system prompt in `agent_reasoner.py`

### Extending Observation Extraction

1. Add new element type method in `ObservationExtractor`
2. Call it in `extract()` method
3. Ensure selector strategy works with `_find_element()`

## License

MIT

An autonomous AI web navigation agent that completes multi-step web tasks from natural language commands using Playwright and Groq LLM.

## Features

- **Autonomous Navigation**: Executes web tasks without human intervention
- **LLM-Powered Reasoning**: Uses Groq's Llama models for decision-making
- **Observable Elements Only**: Works with visible buttons, links, inputs, and text
- **Self-Correcting Loop**: Handles failures and retries with step limits
- **Task Summaries**: Outputs detailed execution reports

## Installation

```bash
# Navigate to project directory
cd agentic_web_navigator

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Configuration

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your Groq API key:
   ```
   GROQ_API_KEY=your_api_key_here
   ```

Get a free API key at: https://console.groq.com/keys

## Usage

### Basic Usage

```bash
python main.py --goal "Go to google.com and search for Python programming"
```

### Command Line Options

| Option | Short | Description |
|--------|-------|-------------|
| `--goal` | `-g` | Natural language task description (required) |
| `--max-steps` | `-s` | Maximum steps to attempt (default: 20) |
| `--visible` | `-v` | Run browser in visible mode |
| `--mock` | `-m` | Use mock reasoner (for testing, no API) |
| `--output` | `-o` | Save JSON summary to file |

### Examples

```bash
# Search on Wikipedia
python main.py -g "Go to wikipedia.org and search for 'Artificial Intelligence'"

# Visible browser mode for debugging
python main.py -g "Navigate to github.com" --visible

# Save output to file
python main.py -g "Search for Python tutorials on google.com" -o result.json

# Test mode (no API calls)
python main.py -g "Test navigation" --mock --visible
```

## Architecture

```
agentic_web_navigator/
├── core/
│   ├── browser_controller.py   # Playwright browser automation
│   ├── observation_extractor.py # Extract visible page elements
│   ├── memory_store.py          # Action history and context
│   └── agent_reasoner.py        # Groq LLM decision engine
├── schemas/
│   └── actions.py               # Action types and validation
├── utils/
│   └── logger.py                # Logging utilities
├── main.py                      # Agent orchestration loop
└── config.py                    # Configuration settings
```

## Supported Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| `goto` | Navigate to URL | `value` (URL) |
| `click` | Click element | `selector` (text/label) |
| `type` | Type into input | `selector`, `value` |
| `scroll` | Scroll page | `direction` (up/down) |
| `back` | Browser back | - |
| `new_tab` | Open new tab | - |
| `close_tab` | Close current tab | - |
| `done` | Complete task | - |

## How It Works

1. **Observe**: Extract visible elements from the current page
2. **Reason**: LLM decides the next action based on goal, observation, and history
3. **Execute**: Perform the atomic browser action
4. **Store**: Record action and result in memory
5. **Repeat**: Continue until goal is achieved or step limit reached

## Limitations

- No authentication/login flows
- No CAPTCHA solving
- No payment processing
- Single action per reasoning step
- Step limit to prevent infinite loops

## License

MIT License
