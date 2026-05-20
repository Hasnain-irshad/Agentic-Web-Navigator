import asyncio
from playwright.async_api import async_playwright
from core.observation_extractor import ObservationExtractor

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        extractor = ObservationExtractor(max_elements=100)
        
        print("Navigating to daraz.pk...")
        await page.goto("https://www.daraz.pk", timeout=60000)
        
        # Add basic listener for console to see if javascript logs an error
        page.on("console", lambda msg: print(f"Browser Console: {msg.text}"))
        
        print("Extracting...")
        obs = await extractor.extract(page)
        
        print(f"Extracted Elements: {len(obs.elements)}")
        print(f"Extraction Error: {obs.error}")
        print(f"Page Type: {obs.page_type}")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
