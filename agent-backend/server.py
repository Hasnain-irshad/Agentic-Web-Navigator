import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.middleware.cors import CORSMiddleware
from core.ws_agent import WSAgent
from utils import get_logger

from typing import Dict

logger = get_logger(__name__)

ACTIVE_SESSIONS: Dict[str, WSAgent] = {}

app = FastAPI(title="Agentic Web Navigator WS Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    logger.info("WebSocket connected.")
    try:
        while True:
            # Receive message from Electron Execution Engine
            data = await websocket.receive_text()
            payload = json.loads(data)
            
            session_id = payload.get("session_id")
            if not session_id:
                await websocket.send_json({"action": "error", "message": "Missing session_id"})
                continue

            agent = ACTIVE_SESSIONS.get(session_id)

            if payload.get("command"):
                goal = payload.get("command")
                logger.info(f"Received new command: {goal} for session {session_id}")

                if not agent:
                    agent = WSAgent(session_id=session_id)
                    ACTIVE_SESSIONS[session_id] = agent

                # Rule-based fast path: 'go back', 'refresh', 'scroll up/down', etc.
                # Bypasses LLM and planner; emits the action directly.
                intercepted = agent.try_intercept(goal)
                if intercepted is not None:
                    await websocket.send_json(intercepted)
                    continue

                agent.add_command(goal)

                # We need the state to make the first move, verify it exists.
                if "state" not in payload:
                    await websocket.send_json({
                        "action": "error",
                        "message": "Start session command must include initial DOM state.",
                        "reasoning": "Missing initial DOM state"
                    })
                    continue
            
            if not agent:
                await websocket.send_json({
                    "action": "error",
                    "message": "Agent not initialized. Send command first.",
                    "reasoning": "Missing goal"
                })
                continue
                
            state = payload.get("state")
            if not state:
                await websocket.send_json({
                    "action": "error",
                    "message": "Missing state payload.",
                    "reasoning": "Missing state"
                })
                continue

            try:
                # Agent processes observation and decides action
                action = await agent.step(state)
                await websocket.send_json(action)
            except Exception as e:
                logger.error(f"Error during agent step: {e}")
                await websocket.send_json({
                    "action": "error",
                    "message": f"Agent crashed: {str(e)}",
                    "reasoning": str(e)
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected.")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")

# CLI runner support (for `python server.py`)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
