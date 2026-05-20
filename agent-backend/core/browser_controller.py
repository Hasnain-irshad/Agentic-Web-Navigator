import asyncio
import random
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

try:
    from schemas import Action, ActionType, ActionResult
    from config import Config
    from utils import get_logger
except ImportError:
    from ..schemas import Action, ActionType, ActionResult
    from ..config import Config
    from ..utils import get_logger


logger = get_logger(__name__)

# Realistic user agents for stealth mode
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


class BrowserController:
    """
    Controls browser automation via Playwright with stealth features.
    
    Handles browser lifecycle and executes atomic browser actions.
    Includes humanization features to reduce bot detection.
    
    Usage:
        async with BrowserController() as browser:
            result = await browser.execute_action(action)
            page = await browser.get_current_page()
    """
    
    def __init__(self, headless: Optional[bool] = None) -> None:
        """
        Initialize the BrowserController.
        
        Args:
            headless: Whether to run browser in headless mode.
                     Defaults to Config.HEADLESS if not specified.
        """
        self._headless = headless if headless is not None else Config.HEADLESS
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: list[Page] = []
        self._current_page_index: int = 0
        
    async def __aenter__(self) -> "BrowserController":
        """Async context manager entry - starts browser."""
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit - stops browser."""
        await self.stop()
    
    async def _human_delay(self, min_ms: int = 100, max_ms: int = 500) -> None:
        """Add a random human-like delay between actions."""
        if not Config.HUMANIZE_ENABLED:
            return

        # Use provided min/max or fall back to config
        min_delay = min_ms if min_ms is not None else Config.HUMAN_MIN_DELAY_MS
        max_delay = max_ms if max_ms is not None else Config.HUMAN_MAX_DELAY_MS
        delay = random.randint(min_delay, max_delay) / 1000
        await asyncio.sleep(delay)

    async def _detect_captcha_or_block(self, page: Page) -> bool:
        """
        Detect if page is showing CAPTCHA or bot detection challenge.
        
        Returns:
            True if CAPTCHA/block detected, False otherwise
        """
        try:
            url = (page.url or "").lower()
            # Common CAPTCHA/bot block indicators
            captcha_indicators = [
                "captcha", "challenge", "sorry", "unusual_traffic",
                "verify", "robot", "recaptcha", "hcaptcha",
                "cloudflare", "check_browser", "security_challenge"
            ]
            
            # Check URL
            for indicator in captcha_indicators:
                if indicator in url:
                    return True
            
            # Check page content for CAPTCHA markers
            try:
                content = await page.content()
                content_lower = content.lower()
                for indicator in captcha_indicators:
                    if indicator in content_lower:
                        return True
                
                # Check for specific elements
                if await page.locator('iframe[src*="captcha"]').count() > 0:
                    return True
                if await page.locator('[data-captcha]').count() > 0:
                    return True
                if await page.locator('.g-recaptcha').count() > 0:
                    return True
                if await page.locator('[class*="captcha"]').count() > 0:
                    return True
            except Exception:
                pass
            
            return False
        except Exception:
            return False

    async def _human_move_mouse_to_element(self, page: Page, element) -> None:
        """Move the mouse toward the element in small human-like steps."""
        if not Config.MOUSE_MOVE_ENABLED:
            return

        try:
            box = await element.bounding_box()
            if not box:
                return

            target_x = box["x"] + box["width"] / 2 + random.uniform(-Config.CLICK_JITTER_PX, Config.CLICK_JITTER_PX)
            target_y = box["y"] + box["height"] / 2 + random.uniform(-Config.CLICK_JITTER_PX, Config.CLICK_JITTER_PX)

            # Start from current mouse position if possible; fallback to (0,0)
            try:
                # Playwright doesn't expose current mouse position; just make multiple small moves
                steps = random.randint(8, 18)
                for i in range(steps):
                    # Interpolate with slight randomness
                    t = (i + 1) / steps
                    x = target_x * t + random.uniform(-2, 2)
                    y = target_y * t + random.uniform(-2, 2)
                    await page.mouse.move(x, y)
                    await asyncio.sleep(random.uniform(0.01, 0.04))
            except Exception:
                # Best-effort; don't fail the action if mouse move fails
                return
        except Exception:
            return

    async def _human_type(self, page: Page, element, text: str) -> None:
        """Type text with per-character delays, typos, mid-word pauses, and varied rhythm."""
        if not Config.HUMANIZE_ENABLED:
            await element.fill(text)
            return

        # Ensure focus
        try:
            await element.click()
        except Exception:
            pass

        letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        words = text.split()
        
        for word_idx, word in enumerate(words):
            # Occasionally pause before typing word (simulates reading from clipboard mentally)
            if word_idx > 0 and random.random() < 0.15:
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            for ch_idx, ch in enumerate(word):
                # Randomized delay per character (more variation)
                base_delay = random.randint(Config.TYPING_DELAY_MIN_MS, Config.TYPING_DELAY_MAX_MS)
                
                # Sometimes slow down at word boundaries
                if ch_idx == 0 and random.random() < 0.3:
                    base_delay = int(base_delay * 1.5)
                # Sometimes speed up
                elif ch_idx > len(word) - 2 and random.random() < 0.3:
                    base_delay = int(base_delay * 0.6)
                
                # Possibly introduce a typo
                if random.random() < Config.TYPING_ERROR_RATE:
                    typo = random.choice(letters)
                    await page.keyboard.type(typo, delay=base_delay)
                    await asyncio.sleep(random.uniform(0.05, 0.2))
                    await page.keyboard.press("Backspace")
                    await asyncio.sleep(random.uniform(0.02, 0.08))

                await page.keyboard.type(ch, delay=base_delay)
                
                # Micro-pauses to mimic thinking/hesitation (more frequent)
                if random.random() < 0.05:  # Increased from 0.02
                    await asyncio.sleep(random.uniform(0.15, 0.5))
                
                # Occasional mid-word pause (very realistic typing)
                if ch_idx > 2 and ch_idx < len(word) - 1 and random.random() < 0.02:
                    await asyncio.sleep(random.uniform(0.2, 0.5))
            
            # Space between words (if not last word)
            if word_idx < len(words) - 1:
                await asyncio.sleep(random.uniform(0.05, 0.15))  # Time for space key
                await page.keyboard.type(" ")
    
    async def _pre_action_scroll(self, page: Page) -> None:
        """Scroll randomly before an action to simulate human reading/browsing."""
        if not Config.HUMANIZE_ENABLED:
            return
        
        try:
            # Small random scroll up or down
            scroll_amount = random.randint(-300, 300)
            if scroll_amount == 0:  # Ensure we scroll
                scroll_amount = random.choice([-200, 200])
            
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            
            # Micro-pause after scroll
            await asyncio.sleep(random.uniform(0.2, 0.6))
            
            # Sometimes move mouse while scrolling (realistic)
            if random.random() < 0.6:
                try:
                    viewport = page.viewport_size or {"width": 1280, "height": 720}
                    x = random.randint(50, max(50, viewport["width"] - 50))
                    y = random.randint(50, max(50, viewport["height"] - 50))
                    await page.mouse.move(x, y, steps=random.randint(2, 5))
                except Exception:
                    pass
        except Exception:
            # Best-effort; don't fail if scroll doesn't work
            return

    async def _random_request_headers(self) -> dict:
        """Generate realistic, slightly randomized HTTP headers."""
        headers = {
            "accept-language": random.choice(["en-US,en;q=0.9", "en-GB,en;q=0.9", "en-US,en;q=0.8"]),
            "dnt": "1",
            "upgrade-insecure-requests": "1",
            "sec-ch-ua": '"Chromium";v="120", "Google Chrome";v="120", ";Not A Brand";v="99"',
            "sec-ch-ua-mobile": "?0",
        }
        # Occasionally include a referer to look like a real navigation
        if random.random() < 0.5:
            headers["referer"] = random.choice(["https://www.google.com/", "https://www.bing.com/", "https://www.duckduckgo.com/"])
        return headers

    async def _maybe_set_extra_headers(self) -> None:
        """Set extra HTTP headers on the browser context with some randomness."""
        if not self._context or not Config.HUMANIZE_ENABLED:
            return
        try:
            headers = await self._random_request_headers()
            await self._context.set_extra_http_headers(headers)
        except Exception:
            # Best-effort; don't fail if headers can't be set
            return

    async def _simulate_reading(self, page: Page, max_scrolls: int = 4) -> None:
        """Simulate a human reading the page by scrolling and pausing."""
        if not Config.HUMANIZE_ENABLED:
            return

        try:
            # Small initial pause to simulate page render reading
            await asyncio.sleep(random.uniform(0.4, 1.2))

            scrolls = random.randint(1, max(1, max_scrolls))
            for _ in range(scrolls):
                # Scroll a bit or to a random position
                amount = random.randint(200, 800)
                if random.random() < 0.3:
                    # scroll up sometimes
                    amount = -amount
                await page.evaluate(f"window.scrollBy(0, {amount})")
                # Random pause between scrolls
                await asyncio.sleep(random.uniform(0.6, 2.4))

            # Move mouse slightly to simulate reading the page
            try:
                viewport = page.viewport_size or {"width": 1280, "height": 720}
                x = random.randint(50, max(50, viewport["width"] - 50))
                y = random.randint(50, max(50, viewport["height"] - 50))
                await page.mouse.move(x, y, steps=random.randint(4, 12))
            except Exception:
                pass

            # Final thinking pause
            await asyncio.sleep(random.uniform(0.5, 2.0))
        except Exception:
            return

    async def _maybe_random_interaction(self, page: Page) -> None:
        """Occasionally perform small interactions (hover, focus) to mimic a user."""
        if not Config.HUMANIZE_ENABLED:
            return
        try:
            # With small probability perform a hover on a random link
            if random.random() < 0.25:
                try:
                    links = page.locator("a:visible")
                    count = await links.count()
                    if count > 0:
                        idx = random.randint(0, max(0, count - 1))
                        el = links.nth(idx)
                        await el.scroll_into_view_if_needed()
                        await el.hover()
                        await asyncio.sleep(random.uniform(0.2, 0.8))
                except Exception:
                    pass

            # Maybe move mouse in small arcs
            if random.random() < 0.5:
                try:
                    viewport = page.viewport_size or {"width": 1280, "height": 720}
                    base_x = random.randint(100, viewport["width"] - 100)
                    base_y = random.randint(100, viewport["height"] - 100)
                    steps = random.randint(3, 10)
                    for i in range(steps):
                        await page.mouse.move(base_x + random.uniform(-20, 20), base_y + random.uniform(-20, 20))
                        await asyncio.sleep(random.uniform(0.02, 0.08))
                except Exception:
                    pass
        except Exception:
            return
    
    async def start(self) -> None:
        """
        Launch the browser with stealth configuration and persistent profile.
        
        Uses a persistent user data directory to store cookies and history,
        making the browser appear as a returning user.
        
        Raises:
            RuntimeError: If browser fails to start
        """
        try:
            import os
            from pathlib import Path
            
            # Create persistent profile directory
            profile_dir = Path.home() / ".agentic_browser_profile"
            profile_dir.mkdir(exist_ok=True)
            
            # Optionally force headful mode when humanization is enabled
            if Config.HUMANIZE_ENABLED and Config.FORCE_HEADFUL_ON_HUMANIZE:
                self._headless = False

            logger.info(f"Starting browser (headless={self._headless}, stealth=enabled, persistent_profile=True)")
            self._playwright = await async_playwright().start()
            
            # Stealth browser args to reduce detection
            browser_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-dev-shm-usage",
                "--disable-extensions",
            ]
            
            # Randomize viewport slightly for fingerprint variation
            width = 1280 + random.randint(-80, 80)
            height = 720 + random.randint(-60, 60)
            
            # Prepare launch options, possibly with proxy and slow_mo
            launch_kwargs = dict(
                user_data_dir=str(profile_dir),
                headless=self._headless,
                args=browser_args,
                viewport={"width": width, "height": height},
                user_agent=random.choice(USER_AGENTS),
                locale="en-US",
                timezone_id=random.choice(["America/New_York", "Europe/London", "Asia/Kolkata", "America/Chicago"]),
                geolocation={"latitude": 40.7128, "longitude": -74.0060},
                permissions=["geolocation"],
                accept_downloads=True,
            )

            # Add slow_mo if configured
            if getattr(Config, "SLOW_MO_MS", 0) and Config.SLOW_MO_MS > 0:
                launch_kwargs["slow_mo"] = Config.SLOW_MO_MS

            # Pick proxy if provided
            try:
                if getattr(Config, "PROXY_SERVERS", None) and Config.PROXY_SERVERS:
                    proxy_choice = random.choice(Config.PROXY_SERVERS)
                    launch_kwargs["proxy"] = {"server": proxy_choice}
            except Exception:
                pass

            # Use persistent context to store cookies and history
            try:
                self._context = await self._playwright.chromium.launch_persistent_context(**launch_kwargs)
            except Exception as e:
                logger.warning(f"Failed to launch persistent context (profile may be locked): {e}")
                logger.info("Falling back to non-persistent browser context...")
                # Remove user_data_dir for non-persistent fallback
                launch_kwargs.pop("user_data_dir", None)
                browser = await self._playwright.chromium.launch(**launch_kwargs)
                
                # Create a new context manually since launch() doesn't return one directly
                # Ensure we apply the same permissions/geoloc/viewport manually if needed
                context_kwargs = {
                    "viewport": launch_kwargs.get("viewport"),
                    "user_agent": launch_kwargs.get("user_agent"),
                    "locale": launch_kwargs.get("locale"),
                    "timezone_id": launch_kwargs.get("timezone_id"),
                    "geolocation": launch_kwargs.get("geolocation"),
                    "permissions": launch_kwargs.get("permissions"),
                    "accept_downloads": launch_kwargs.get("accept_downloads"),
                }
                self._context = await browser.new_context(**context_kwargs)
            # Set initial randomized headers for the context
            try:
                await self._maybe_set_extra_headers()
            except Exception:
                pass
            # Inject stealth scripts to hide automation indicators
            # Inject an expanded stealth script to mask common automation signals
            await self._context.add_init_script("""
                // navigator.webdriver
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

                // plugins
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });

                // languages
                Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

                // chrome runtime
                window.chrome = { runtime: {} };

                // permissions
                const originalQuery = window.navigator.permissions.query;
                window.navigator.permissions.__proto__.query = function(parameters) {
                    if (parameters && parameters.name === 'notifications') {
                        return Promise.resolve({ state: Notification.permission });
                    }
                    return originalQuery(parameters);
                };

                // hardwareConcurrency and deviceMemory
                try {
                    Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
                    Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
                } catch (e) {}

                // Mock WebGL renderer/vendor
                (function() {
                    try {
                        const getParameter = WebGLRenderingContext.prototype.getParameter;
                        WebGLRenderingContext.prototype.getParameter = function(parameter) {
                            // 37445 = UNMASKED_VENDOR_WEBGL, 37446 = UNMASKED_RENDERER_WEBGL
                            if (parameter === 37445) return 'Intel Inc.';
                            if (parameter === 37446) return 'Intel Iris OpenGL Engine';
                            return getParameter.call(this, parameter);
                        };
                    } catch (e) {}
                })();

                // Canvas fingerprint noise
                (function() {
                    const toDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function() {
                        try {
                            const ctx = this.getContext('2d');
                            if (ctx) {
                                ctx.fillStyle = 'rgba(0,0,0,0.0)';
                                ctx.fillRect(0,0,1,1);
                            }
                        } catch(e) {}
                        return toDataURL.apply(this, arguments);
                    };
                })();
            """)
            
            # Get existing page or create new one
            pages = self._context.pages
            if pages:
                initial_page = pages[0]
            else:
                initial_page = await self._context.new_page()
            
            initial_page.set_default_timeout(Config.BROWSER_TIMEOUT)
            self._pages = [initial_page]
            self._current_page_index = 0
            self._browser = None  # Persistent context doesn't use separate browser
            
            logger.info("Browser started with persistent profile (cookies/history preserved)")
            
        except Exception as e:
            logger.error(f"Failed to start browser: {e}")
            await self.stop()
            raise RuntimeError(f"Browser startup failed: {e}") from e
    
    async def stop(self) -> None:
        """Close browser and cleanup resources."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
            
            self._pages.clear()
            logger.info("Browser stopped")
            
        except Exception as e:
            logger.warning(f"Error during browser cleanup: {e}")
    
    async def get_current_page(self) -> Page:
        """
        Get the currently active page.
        
        Returns:
            The current Playwright Page object
            
        Raises:
            RuntimeError: If no page is available
        """
        if not self._pages:
            raise RuntimeError("No browser page available")
        return self._pages[self._current_page_index]
    
    # ── Last observation cache — set by session agent before actions ───
    _last_observation = None

    def set_observation(self, observation) -> None:
        """Cache the latest observation so element_index can be resolved."""
        self._last_observation = observation

    async def execute_action(self, action: Action) -> ActionResult:
        """
        Execute a browser action.
        
        If the action has an element_index, resolve it to a real CSS selector
        from the cached observation before executing.
        
        Args:
            action: The Action to execute
            
        Returns:
            ActionResult indicating success/failure and details
        """
        # ── Resolve element_index → real CSS selector ─────────────────
        if action.element_index is not None and action.selector is None:
            resolved = self._resolve_element_index(action.element_index)
            if resolved:
                action.selector = resolved
                logger.info(f"Resolved element [{action.element_index}] → {resolved}")
            else:
                return ActionResult(
                    success=False,
                    message=f"Element [{action.element_index}] not found in observation (have {len(self._last_observation.elements) if self._last_observation else 0} elements)"
                )

        action_handlers = {
            ActionType.GOTO: self._handle_goto,
            ActionType.CLICK: self._handle_click,
            ActionType.TYPE: self._handle_type,
            ActionType.SCROLL: self._handle_scroll,
            ActionType.BACK: self._handle_back,
            ActionType.NEW_TAB: self._handle_new_tab,
            ActionType.CLOSE_TAB: self._handle_close_tab,
            ActionType.PRESS_KEY: self._handle_press_key,
            ActionType.DONE: self._handle_done,
        }
        
        handler = action_handlers.get(action.action_type)
        if not handler:
            return ActionResult(
                success=False,
                message=f"Unknown action type: {action.action_type}"
            )
        
        try:
            logger.info(f"Executing action: {action.action_type.value} (selector={action.selector}, element_index={action.element_index})")
            result = await handler(action)
            return result
            
        except Exception as e:
            error_msg = f"Action {action.action_type.value} failed: {str(e)}"
            logger.error(error_msg)
            return ActionResult(success=False, message=error_msg)

    def _resolve_element_index(self, index: int) -> str | None:
        """
        Resolve a 1-based element index to a real CSS selector.
        
        Args:
            index: 1-based index from the LLM's chosen element
            
        Returns:
            CSS selector string or None
        """
        if not self._last_observation:
            logger.warning("No observation cached — cannot resolve element_index")
            return None
        
        elem = self._last_observation.get_element_by_index(index)
        if elem:
            logger.debug(f"Element [{index}]: tag={elem.tag} text='{elem.text[:40]}' css={elem.css_selector}")
            return elem.css_selector
        
        logger.warning(f"Element index {index} out of range (have {len(self._last_observation.elements)} elements)")
        return None
    
    async def _handle_goto(self, action: Action) -> ActionResult:
        """Navigate to a URL with enhanced anti-detection features."""
        page = await self.get_current_page()
        url = action.value
        
        try:
            # Random delay BEFORE navigation to avoid rapid successive requests
            await self._human_delay(min_ms=800, max_ms=2000)
            
            # Randomize headers just before navigation to vary requests
            await self._maybe_set_extra_headers()

            response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else "unknown"

            # Extended delay AFTER page load for anti-detection
            await asyncio.sleep(random.uniform(1.5, 3.5))
            
            # CRITICAL: Wait for network to be idle and page fully interactive
            try:
                await page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                logger.debug(f"Network idle wait timeout (non-critical): {e}")
                # Continue anyway; some sites never reach networkidle
                await asyncio.sleep(1.0)
            
            # Detect if we hit a CAPTCHA or bot challenge
            if await self._detect_captcha_or_block(page):
                logger.warning(f"CAPTCHA/bot challenge detected at {url}")
                # Long wait for human to solve manually + simulate reading
                await self._simulate_reading(page, max_scrolls=3)
                # Additional delay after CAPTCHA page (in case it's still loading)
                await asyncio.sleep(random.uniform(2.0, 4.0))

            # Simulate human reading/interaction after navigation
            await self._simulate_reading(page, max_scrolls=2)

            return ActionResult(
                success=True,
                message=f"Navigated to {url}",
                data={"url": page.url, "status": status}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to navigate to {url}: {e}"
            )
    
    async def _handle_click(self, action: Action) -> ActionResult:
        """Click on an element — tries CSS selector first (grounded), then fallback strategies."""
        page = await self.get_current_page()
        selector = action.selector
        
        try:
            # Pre-click scroll: Sometimes scroll before clicking (realistic human behavior)
            if random.random() < 0.4:
                await self._pre_action_scroll(page)
            
            await self._human_delay(min_ms=500, max_ms=1500)

            # ── Grounded approach: try the real CSS selector first ─────
            element = await self._find_element_by_css(page, selector)
            
            # ── Fallback: multi-strategy search ────────────────────────
            if not element:
                element = await self._find_element(page, selector)
            
            if not element:
                return ActionResult(
                    success=False,
                    message=f"Element not found: {selector}"
                )
            
            # Scroll element into view
            try:
                await element.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.2, 0.5))
            except Exception:
                pass
            
            # Move mouse toward element
            await self._human_move_mouse_to_element(page, element)

            # Hover
            try:
                await element.hover()
                hover_time = random.uniform(0.3, 0.9) if random.random() < 0.6 else random.uniform(0.1, 0.3)
                await asyncio.sleep(hover_time)
            except Exception:
                pass
            
            # Click
            await element.click()

            # Wait for potential navigation
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                pass

            await self._human_delay(min_ms=800, max_ms=1500)

            await self._maybe_random_interaction(page)
            if random.random() < 0.7:
                await self._simulate_reading(page, max_scrolls=2)
            
            return ActionResult(
                success=True,
                message=f"Clicked element (selector: {selector[:60]})",
                data={"url": page.url}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to click '{selector[:60]}': {e}"
            )
    
    async def _handle_type(self, action: Action) -> ActionResult:
        """Type text into an input element — tries CSS selector first (grounded), then fallback."""
        page = await self.get_current_page()
        selector = action.selector
        value = action.value or ""
        
        try:
            if random.random() < 0.3:
                await self._pre_action_scroll(page)
            
            await self._human_delay(min_ms=600, max_ms=1200)

            # ── Grounded approach: try the real CSS selector first ─────
            element = await self._find_element_by_css(page, selector)
            
            # Check if it's editable, if not fall back
            if element:
                try:
                    if not await element.is_editable():
                        element = None
                except Exception:
                    element = None
            
            # ── Fallback: specialized input finder ────────────────────
            if not element:
                element = await self._find_input_element(page, selector)
            
            if not element:
                return ActionResult(
                    success=False,
                    message=f"Input element not found: {selector[:60]}"
                )
            
            if not await element.is_editable():
                 return ActionResult(
                    success=False,
                    message=f"Element found but not editable: {selector[:60]}"
                )
            
            # Scroll into view
            try:
                await element.scroll_into_view_if_needed()
            except Exception:
                pass
            
            try:
                await element.hover()
                await asyncio.sleep(random.uniform(0.1, 0.3))
            except Exception:
                pass
            
            await element.click()
            await self._human_delay(min_ms=300, max_ms=700)

            # Clear existing content
            try:
                await element.evaluate("el => el.select()")
                await asyncio.sleep(random.uniform(0.05, 0.1))
            except Exception:
                pass
            await element.fill("")

            await self._human_type(page, element, value)

            await self._human_delay(min_ms=400, max_ms=1000)
            
            if random.random() < 0.4:
                await self._maybe_random_interaction(page)
            
            return ActionResult(
                success=True,
                message=f"Typed '{value}' into element (selector: {selector[:60]})"
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to type into '{selector[:60]}': {e}"
            )
    
    async def _handle_scroll(self, action: Action) -> ActionResult:
        """Scroll the page with sophisticated human-like behavior."""
        page = await self.get_current_page()
        direction = action.direction
        
        try:
            # Sometimes pause before scrolling (simulates reading)
            if random.random() < 0.3:
                await asyncio.sleep(random.uniform(0.3, 1.0))
            
            # Human-like delay before scrolling
            await self._human_delay(min_ms=300, max_ms=800)
            
            # Randomize scroll amount to appear human (vary more)
            if direction == "down":
                scroll_amount = random.randint(300, 900)  # More variation
                if random.random() < 0.2:  # Sometimes scroll more aggressively
                    scroll_amount = random.randint(1000, 1500)
            else:
                scroll_amount = random.randint(-900, -300)
                if random.random() < 0.2:
                    scroll_amount = random.randint(-1500, -1000)
            
            # Smooth scroll or instant (humans do both)
            if random.random() < 0.7:
                # Smooth scroll with multiple steps
                steps = random.randint(3, 7)
                step_amount = scroll_amount / steps
                for _ in range(steps):
                    await page.evaluate(f"window.scrollBy(0, {step_amount})")
                    await asyncio.sleep(random.uniform(0.05, 0.15))
            else:
                # Instant scroll
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            
            # Simulate mouse movement while page is visible
            try:
                viewport = page.viewport_size or {"width": 1280, "height": 720}
                x = random.randint(50, max(50, viewport["width"] - 50))
                y = random.randint(50, max(50, viewport["height"] - 50))
                # More realistic mouse movements
                steps = random.randint(4, 10)
                await page.mouse.move(x, y, steps=steps)
            except Exception:
                pass
            
            # Varying delay after scrolling (simulate reading content at different speeds)
            read_time = random.uniform(0.3, 2.0)
            if random.random() < 0.3:  # Sometimes read longer
                read_time = random.uniform(2.0, 4.0)
            await asyncio.sleep(read_time)
            
            return ActionResult(
                success=True,
                message=f"Scrolled {direction}"
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to scroll: {e}"
            )
    
    async def _handle_back(self, action: Action) -> ActionResult:
        """Navigate back in browser history."""
        page = await self.get_current_page()
        
        try:
            await page.go_back(wait_until="domcontentloaded")
            
            return ActionResult(
                success=True,
                message="Navigated back",
                data={"url": page.url}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to go back: {e}"
            )
    
    async def _handle_new_tab(self, action: Action) -> ActionResult:
        """Open a new browser tab."""
        try:
            if not self._context:
                return ActionResult(
                    success=False,
                    message="Browser context not available"
                )
            
            new_page = await self._context.new_page()
            new_page.set_default_timeout(Config.BROWSER_TIMEOUT)
            self._pages.append(new_page)
            self._current_page_index = len(self._pages) - 1
            
            return ActionResult(
                success=True,
                message=f"Opened new tab (total: {len(self._pages)})",
                data={"tab_count": len(self._pages)}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to open new tab: {e}"
            )
    
    async def _handle_close_tab(self, action: Action) -> ActionResult:
        """Close the current tab."""
        try:
            if len(self._pages) <= 1:
                return ActionResult(
                    success=False,
                    message="Cannot close the last tab"
                )
            
            current_page = self._pages[self._current_page_index]
            await current_page.close()
            self._pages.pop(self._current_page_index)
            
            # Adjust current page index
            if self._current_page_index >= len(self._pages):
                self._current_page_index = len(self._pages) - 1
            
            return ActionResult(
                success=True,
                message=f"Closed tab (remaining: {len(self._pages)})",
                data={"tab_count": len(self._pages)}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to close tab: {e}"
            )
    
    async def _handle_press_key(self, action: Action) -> ActionResult:
        """Press a keyboard key with enhanced human-like behavior."""
        page = await self.get_current_page()
        key = action.key or "Enter"
        
        try:
            # Occasional pre-key action scroll (humans sometimes scroll before submitting)
            if random.random() < 0.15:  # 15% chance
                await self._pre_action_scroll(page)
            
            # Variable delay based on key type (Enter is often pressed after deliberation)
            if key.lower() in ["enter", "return"]:
                # Longer delay before Enter (humans deliberate)
                await self._human_delay(min_ms=600, max_ms=1500)
            else:
                # Shorter delay for other keys
                await self._human_delay(min_ms=300, max_ms=800)
            
            # Sometimes pause and check what's on screen before submitting
            if key.lower() in ["enter", "return"] and random.random() < 0.3:
                await asyncio.sleep(random.uniform(0.3, 0.8))
            
            # Press the key
            await page.keyboard.press(key)
            
            # Extended wait for potential navigation (with timeout handling)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=5000)
            except Exception:
                # Page might not trigger load state; continue anyway
                await asyncio.sleep(0.5)
            
            # Extended delay after key press to simulate page reading
            await asyncio.sleep(random.uniform(1.0, 3.5))
            
            # Simulate reading after navigation (more aggressive for search results)
            read_chance = 0.85 if key.lower() in ["enter", "return"] else 0.6
            if random.random() < read_chance:
                await self._simulate_reading(page, max_scrolls=random.randint(1, 3))
            
            return ActionResult(
                success=True,
                message=f"Pressed {key} key",
                data={"url": page.url}
            )
            
        except Exception as e:
            return ActionResult(
                success=False,
                message=f"Failed to press {key}: {e}"
            )
    
    async def _handle_done(self, action: Action) -> ActionResult:
        """Signal task completion."""
        return ActionResult(
            success=True,
            message="Task marked as complete",
            data={"done": True}
        )
    
    async def _find_element_by_css(self, page: Page, css_selector: str):
        """
        Find element using a real CSS selector from DOM extraction.
        This is the primary, grounded element-finding method.
        
        Args:
            page: Playwright page
            css_selector: Real CSS selector from observation extraction
            
        Returns:
            Locator if found and visible, None otherwise
        """
        if not css_selector:
            return None
        try:
            element = page.locator(css_selector).first
            if await element.count() > 0:
                # Verify it's visible
                try:
                    if await element.is_visible():
                        return element
                except Exception:
                    # Even if is_visible throws, the element exists
                    return element
        except Exception as e:
            logger.debug(f"CSS selector failed: {css_selector} — {e}")
        return None

    async def _find_element(self, page: Page, selector: str):
        """
        Find an element using multiple strategies.
        
        Args:
            page: Playwright page
            selector: Selector string (CSS, text, or role-based)
            
        Returns:
            Locator if found, None otherwise
        """
        import re
        selector_lower = selector.lower()

        # Detect ordinals like first/1st, second/2nd, third/3rd, or numeric ordinals
        ordinal_map = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
        idx = None
        ord_match = re.search(r"\b(first|1st|second|2nd|third|3rd|fourth|4th|(\d+)(?:st|nd|rd|th)?)\b", selector_lower)
        if ord_match:
            word = ord_match.group(1)
            try:
                if word.isdigit():
                    idx = int(word)
                else:
                    idx = ordinal_map.get(word, None)
            except Exception:
                idx = None

        # Helper to choose .nth(index-1) when ordinal provided, otherwise .first
        def choose_locator(loc):
            try:
                if idx and idx > 0:
                    return loc.nth(idx - 1)
                return loc.first
            except Exception:
                return loc.first

        # Special handling for search/result/item ordinals
        if re.search(r'(?:first|1st|second|2nd|third|3rd)\s*(?:link|result|item)', selector_lower):
            search_result_strategies = [
                # Google search results
                lambda: choose_locator(page.locator("div#search a h3")).locator(".."),
                lambda: choose_locator(page.locator("div#search h3 a")),
                lambda: choose_locator(page.locator("div.g a[href*='http']")),
                lambda: choose_locator(page.locator("#rso a h3")).locator(".."),
                # Bing search results
                lambda: choose_locator(page.locator(".b_algo h2 a")),
                # Generic search results
                lambda: choose_locator(page.locator("h3 a")),
                lambda: choose_locator(page.locator("a h3")).locator(".."),
                # Main content links
                lambda: choose_locator(page.locator("main a[href^='http']")),
                lambda: choose_locator(page.locator("article a")),
            ]

            for strategy in search_result_strategies:
                try:
                    element = strategy()
                    if await element.count() > 0 and await element.is_visible():
                        return element
                except Exception:
                    continue
        
        # Handle numbered item requests for e-commerce (first item, product 1, etc.)
        if re.search(r'(?:first|1st|second|2nd|product|item)', selector_lower):
            item_strategies = [
                # Daraz specific selectors
                lambda: choose_locator(page.locator("[data-qa-locator='product-item'] a")),
                lambda: choose_locator(page.locator(".Bm3ON a")),  # Daraz product card class
                lambda: choose_locator(page.locator("[data-tracking='product-card'] a")),
                lambda: choose_locator(page.locator(".buTCk a")),  # Daraz grid item
                lambda: choose_locator(page.locator(".gridItem a")),
                # Generic e-commerce selectors
                lambda: choose_locator(page.locator("[data-sku]:visible a")),
                lambda: choose_locator(page.locator("[data-product-id]:visible a")),
                lambda: choose_locator(page.locator("[class*='product']:visible a")),
                lambda: choose_locator(page.locator("[class*='Product']:visible a")),
                lambda: choose_locator(page.locator(".product-card:visible a")),
                lambda: choose_locator(page.locator("article a:visible")),
                # First/Nth link that looks like a product (has image nearby)
                lambda: choose_locator(page.locator("a:has(img)")),
            ]

            for strategy in item_strategies:
                try:
                    element = strategy()
                    if await element.count() > 0 and await element.is_visible():
                        return element
                except Exception:
                    continue
        
        # Clean the selector - extract text from LLM output formats like:
        # "LINK: 'Daraz.pk'" -> "Daraz.pk"
        # "[9] LINK: 'Daraz'" -> "Daraz"
        # "result link text" -> "result link text"
        clean_selector = selector
        
        # Parse format: [number] TYPE: 'text' or TYPE: 'text'
        import re
        match = re.search(r"(?:\[\d+\])?\s*(?:LINK|BUTTON|INPUT):\s*['\"]?([^'\"]+)['\"]?", selector, re.IGNORECASE)
        if match:
            clean_selector = match.group(1).strip()
        
        # Standard strategies with cleaned selector
        strategies = [
            # Try as CSS selector first
            lambda: choose_locator(page.locator(selector)),
            # Try link with clean text
            lambda: choose_locator(page.locator(f"a:has-text('{clean_selector}')")),
            # Try as text content with clean selector
            lambda: choose_locator(page.get_by_text(clean_selector, exact=False)),
            # Try partial match on link text
            lambda: choose_locator(page.get_by_role("link", name=clean_selector)),
            # Try as placeholder
            lambda: choose_locator(page.get_by_placeholder(clean_selector)),
            # Try as label
            lambda: choose_locator(page.get_by_label(clean_selector)),
            # Try as button
            lambda: choose_locator(page.get_by_role("button", name=clean_selector)),
        ]
        
        for strategy in strategies:
            try:
                element = strategy()
                if await element.count() > 0 and await element.is_visible():
                    return element
            except Exception:
                continue
        
        return None

    async def _find_input_element(self, page: Page, selector: str):
        """
        Find an INPUT element specifically.
        
        Avoids matching non-interactive elements like divs or spans that happen
        to have similar text, which causes fill() errors.
        
        Uses safer strategies with proper error handling for is_editable().
        """
        # Helper to safely check if element is editable
        async def is_safely_editable(elem) -> bool:
            try:
                if await elem.count() == 0:
                    return False
                if not await elem.is_visible():
                    return False
                # Wrap is_editable in try/except as it throws on certain elements
                return await elem.is_editable()
            except Exception:
                return False
        
        # Strategy 1: Try input-specific CSS selectors first (most reliable)
        input_css_selectors = [
            f"input[name='{selector}']",
            f"input[id='{selector}']",
            f"textarea[name='{selector}']",
            f"textarea[id='{selector}']",
            f"input[placeholder*='{selector}' i]",
            f"textarea[placeholder*='{selector}' i]",
            f"input[aria-label*='{selector}' i]",
            f"textarea[aria-label*='{selector}' i]",
            # Google uses name='q' for search
            "input[name='q']",
            "textarea[name='q']",
        ]
        
        for css_sel in input_css_selectors:
            try:
                element = page.locator(css_sel).first
                if await is_safely_editable(element):
                    return element
            except Exception:
                continue
        
        # Strategy 2: Role-based (combobox is used by Google Search)
        role_strategies = [
            lambda: page.get_by_role("combobox", name=selector).first,
            lambda: page.get_by_role("combobox").first,  # Fallback: any combobox
            lambda: page.get_by_role("textbox", name=selector).first,
            lambda: page.get_by_role("searchbox", name=selector).first,
            lambda: page.get_by_role("textbox").first,  # Fallback: first textbox
        ]
        
        for strategy in role_strategies:
            try:
                element = strategy()
                if await is_safely_editable(element):
                    return element
            except Exception:
                continue
        
        # Strategy 3: Placeholder and label (more generic)
        generic_strategies = [
            lambda: page.get_by_placeholder(selector).first,
            lambda: page.get_by_label(selector).first,
        ]
        
        for strategy in generic_strategies:
            try:
                element = strategy()
                if await is_safely_editable(element):
                    return element
            except Exception:
                continue
        
        # Strategy 4: Try exact selector as last resort
        try:
            element = page.locator(selector).first
            if await is_safely_editable(element):
                return element
        except Exception:
            pass
        
        return None
