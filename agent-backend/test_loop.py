import asyncio
from core.session_agent import SessionAgent
from utils import get_logger

async def test_dynamic_login():
    logger = get_logger(__name__)
    agent = SessionAgent(headless=True)
    await agent.start_session()
    
    def on_event(event, message):
        print(f"[{event.upper()}] {message}")

    goal = 'Search for SS CASE IT university student portal and login with credentials as roll number "2230-0076" and password as "5487776"'
    print(f"Goal: {goal}")
    res = await agent.execute_command(goal, callback=on_event)
    print("Result:", res)
    await agent.end_session()

if __name__ == "__main__":
    asyncio.run(test_dynamic_login())
