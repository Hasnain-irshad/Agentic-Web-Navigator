"""
Example tasks and usage patterns for the Agentic Web Navigator.

Run examples with:
    python main.py --goal "Your task here" --visible
    python main.py --goal "Your task here" --mock  # Use mock reasoner (no API key needed)
    python main.py --goal "Your task here" --output results.json
"""

import asyncio
from main import WebNavigatorAgent


# Example 1: Simple Google Search
async def example_google_search():
    """Example: Search for a query on Google."""
    agent = WebNavigatorAgent(
        goal="Search for 'Python web scraping' on Google and open the first result",
        max_steps=10,
        headless=False,  # Show browser window
    )
    result = await agent.run()
    print(f"\nResult: {result['status']}")
    return result


# Example 2: GitHub Repository Search
async def example_github_search():
    """Example: Find Python projects on GitHub."""
    agent = WebNavigatorAgent(
        goal="Go to GitHub, search for 'python async' repositories, and find the most starred one",
        max_steps=15,
        headless=False,
    )
    result = await agent.run()
    return result


# Example 3: Wikipedia Navigation
async def example_wikipedia():
    """Example: Navigate and search Wikipedia."""
    agent = WebNavigatorAgent(
        goal="Go to Wikipedia and find information about artificial intelligence",
        max_steps=8,
        headless=False,
    )
    result = await agent.run()
    return result


# Example 4: E-commerce Product Search
async def example_ecommerce():
    """Example: Search for a product on e-commerce site."""
    agent = WebNavigatorAgent(
        goal="Navigate to a product listing page and find items under $50",
        max_steps=12,
        headless=False,
    )
    result = await agent.run()
    return result


# Example 5: Using Mock Reasoner (No API Key Required)
async def example_mock():
    """Example: Test with mock reasoner (no Groq API key needed)."""
    agent = WebNavigatorAgent(
        goal="Test navigation using mock reasoner",
        max_steps=5,
        headless=False,
        use_mock=True,  # Use mock reasoner
    )
    result = await agent.run()
    return result


async def main():
    """Run example tasks."""
    print("Agentic Web Navigator - Example Tasks")
    print("=" * 50)
    print("\nExamples:")
    print("1. Google Search")
    print("2. GitHub Repository Search")
    print("3. Wikipedia Navigation")
    print("4. E-commerce Product Search")
    print("5. Mock Test (No API Key)")
    print("0. Exit")
    
    choice = input("\nSelect example (0-5): ").strip()
    
    try:
        if choice == "1":
            await example_google_search()
        elif choice == "2":
            await example_github_search()
        elif choice == "3":
            await example_wikipedia()
        elif choice == "4":
            await example_ecommerce()
        elif choice == "5":
            await example_mock()
        elif choice == "0":
            print("Exiting...")
            return
        else:
            print("Invalid choice")
    except KeyboardInterrupt:
        print("\n\nTask interrupted by user")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    asyncio.run(main())
