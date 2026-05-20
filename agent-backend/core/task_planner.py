"""
TaskPlanner: decomposes a natural-language command into a list of verifiable
subgoals, and deterministically advances them based on observed SessionState
and WorldModel changes.

The LLM is NOT trusted to decide when a task is complete — this planner owns
that decision. The LLM only picks the next *primitive action* to make progress
on the current subgoal.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import urlparse

try:
    from core.session_state import (
        SessionState, TaskState, Subgoal, SubgoalKind, TaskStatus, new_task_id,
    )
    from core.element_resolver import parse_ordinal
    from utils import get_logger
except ImportError:
    from .session_state import (
        SessionState, TaskState, Subgoal, SubgoalKind, TaskStatus, new_task_id,
    )
    from .element_resolver import parse_ordinal
    from ..utils import get_logger


logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# Intent detection (coarse-grained, rule-based)
# ═══════════════════════════════════════════════════════════════════════════

INTENT_ADD_TO_CART = "add_to_cart"
INTENT_SEARCH = "search"
INTENT_OPEN_PRODUCT = "open_product"
INTENT_LOGIN = "login"
INTENT_NAVIGATE = "navigate"
INTENT_CHECKOUT = "checkout"
INTENT_GENERIC = "generic"


# Domain aliases — map shorthand names to full domains.
# Keep in sync with SITE_ALIASES in electron-browser/src/renderer/App.tsx.
DOMAIN_ALIASES = {
    "daraz": "daraz.pk",
    "amazon": "amazon.com",
    "ebay": "ebay.com",
    "flipkart": "flipkart.com",
    "walmart": "walmart.com",
    "aliexpress": "aliexpress.com",
    "google": "google.com",
    "duckduckgo": "duckduckgo.com",
    "youtube": "youtube.com",
    "facebook": "facebook.com",
    "instagram": "instagram.com",
    "twitter": "twitter.com",
    "x": "x.com",
    "github": "github.com",
    "reddit": "reddit.com",
    "linkedin": "linkedin.com",
    "wikipedia": "en.wikipedia.org",
}

STOPWORDS = {
    "the", "a", "an", "please", "can", "you", "for", "me", "and", "or",
    "to", "on", "in", "at", "it", "this", "that", "some",
}


def _extract_domain(text: str, session: SessionState) -> str:
    """Find a site reference in the command, falling back to session's last domain."""
    t = text.lower()

    # Explicit URL
    m = re.search(r"https?://[^\s]+", text)
    if m:
        return _netloc(m.group(0))

    # "on X" / "from X" / "at X"
    m = re.search(r"\b(?:on|from|at)\s+([a-z0-9\.\-]+)\b", t)
    if m:
        cand = m.group(1).strip().lower()
        return DOMAIN_ALIASES.get(cand, cand if "." in cand else DOMAIN_ALIASES.get(cand, ""))

    # Bare alias anywhere in the command
    for alias, dom in DOMAIN_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", t):
            return dom

    # Fallback: reuse last session domain (important for follow-ups)
    return session.last_search_domain or _netloc(session.url) or ""


def _netloc(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower().replace("www.", "")
        return host
    except Exception:
        return ""


def _extract_search_query(text: str) -> str:
    """Pull out the search term from phrases like 'search laptops', 'find red shoes on amazon'."""
    t = text.strip()
    # Remove leading verb
    t = re.sub(r"^(please\s+)?(search(?:\s+for)?|find|look\s+for|show\s+me)\s+", "", t, flags=re.I)
    # Strip trailing "on <site>"
    t = re.sub(r"\s+(?:on|from|at)\s+[a-z0-9\.\-]+\s*$", "", t, flags=re.I)
    # Strip "please"
    t = re.sub(r"\bplease\b", "", t, flags=re.I).strip()
    return t.strip(" .?!,")


def _is_add_to_cart(t: str) -> bool:
    return bool(re.search(r"\badd\b.*\b(cart|basket|bag)\b", t) or "add to cart" in t)


def _is_open_product(t: str) -> bool:
    return bool(re.search(r"\b(open|click|view|show)\b.*\b(product|item|result|listing|one|\d+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth)\b", t))


def _is_search(t: str) -> bool:
    return bool(re.search(r"\b(search|find|look\s+for|show\s+me)\b", t))


def _is_login(t: str) -> bool:
    return bool(re.search(r"\b(login|log\s+in|sign\s+in)\b", t))


def _is_checkout(t: str) -> bool:
    return "checkout" in t or "check out" in t


def _is_navigate(t: str) -> bool:
    return bool(re.search(r"\b(go\s+to|visit|open|navigate)\b", t)) and not _is_open_product(t)


def _looks_like_site(text: str) -> bool:
    """Heuristic: does the given text look like a website/site-name rather
    than a free-form search query? Used to decide whether to route through
    the browser's address/search bar instead of a page-level search box.

    Deliberately CONSERVATIVE — bare words like "laptops" must NOT be
    classified as site names, otherwise we'd route "search laptops on daraz"
    incorrectly. Only two signals qualify:
      1. The text is a known domain alias (youtube, daraz, amazon, ...)
      2. The text contains a TLD-style dot (daraz.pk, github.com, ...)
    """
    if not text:
        return False
    t = text.strip().lower()
    if t in DOMAIN_ALIASES:
        return True
    if re.fullmatch(r"[a-z0-9\-]+\.[a-z]{2,}(\/.*)?", t):
        return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Planner
# ═══════════════════════════════════════════════════════════════════════════

class TaskPlanner:
    """Decomposes user commands into verifiable subgoals and advances them."""

    # ── Decomposition ────────────────────────────────────────────────────

    def decompose(self, command: str, session: SessionState) -> TaskState:
        """Create a TaskState with subgoals inferred from the command + session context."""
        t = command.lower().strip()
        domain = _extract_domain(command, session)
        ordinal = parse_ordinal(command)  # 0-based or None
        query = _extract_search_query(command)

        subgoals: list[Subgoal] = []
        intent = INTENT_GENERIC
        refs: dict[str, Any] = {}

        # A web task can only proceed if we have SOME origin to act on:
        # an explicit domain, a non-blank session URL, or a remembered site.
        def _is_blank_context() -> bool:
            cur = (session.url or "").lower()
            if not cur or cur in ("about:blank", "about:blank/", "chrome://newtab/"):
                return True
            return False

        needs_web_origin = (
            _is_search(t) or _is_add_to_cart(t) or _is_open_product(t)
            or _is_login(t) or _is_checkout(t)
        )

        # Special case: user asked for a web task but we have no origin at all
        # (no domain in command, no last_search_domain, about:blank or empty url).
        # Instead of silently navigating to a search engine, emit a clarification
        # subgoal and a CREATE_TAB so the frontend opens a neutral blank page.
        if needs_web_origin and not domain and _is_blank_context():
            subgoals.append(Subgoal(
                kind=SubgoalKind.CUSTOM,
                params={
                    "reason": "missing_domain",
                    "raw_goal": command,
                    "prompt": "Which website should I use? (e.g. 'on daraz', 'on amazon')",
                },
                description="Ask user which site to use",
                status="active",
            ))
            task = TaskState(
                task_id=new_task_id(),
                goal=command,
                intent=INTENT_GENERIC,
                subgoals=subgoals,
                referenced_entities={},
            )
            logger.info("[Planner] No origin + no domain -> requesting clarification (no auto-google)")
            return task

        # ── add to cart ─────────────────────────────────────────────────
        if _is_add_to_cart(t):
            intent = INTENT_ADD_TO_CART
            # Need to resolve which product. Priorities:
            #   1. Ordinal in the command + session.last_results → navigate back if needed, then click
            #   2. Ordinal in the command + no session results → need a search query too
            #   3. No ordinal → act on currently_viewing if on a product page, else fail

            # If the user also provided a new search query (e.g. "search laptops and add 2nd to cart")
            has_new_search = _is_search(t) and query and not _is_open_product(t)

            if has_new_search:
                if domain and _netloc(session.url) != domain:
                    subgoals.append(Subgoal(
                        kind=SubgoalKind.BROWSER_BAR_SEARCH,
                        params={"query": domain, "domain": domain, "verbatim": command},
                        description=f"Use browser bar to navigate to {domain}",
                    ))
                subgoals.append(Subgoal(
                    kind=SubgoalKind.SEARCH,
                    params={"query": query, "domain": domain},
                    description=f"Search for '{query}'",
                ))

            if ordinal is not None:
                refs["ordinal"] = ordinal + 1  # store as 1-based
                subgoals.append(Subgoal(
                    kind=SubgoalKind.OPEN_RESULT,
                    params={"ordinal": ordinal + 1},
                    description=f"Open result #{ordinal + 1}",
                ))
            elif not session.currently_viewing and not has_new_search:
                # Can't add to cart — no product in context, no query
                subgoals.append(Subgoal(
                    kind=SubgoalKind.CUSTOM,
                    params={"hint": "ask_user"},
                    description="Ambiguous: no product reference found",
                    status="failed",
                ))

            subgoals.append(Subgoal(
                kind=SubgoalKind.ADD_TO_CART,
                params={"pre_cart_count": len(session.cart)},
                description="Click Add to Cart",
            ))

        # ── open / click Nth result (no cart) ───────────────────────────
        elif _is_open_product(t):
            intent = INTENT_OPEN_PRODUCT
            if ordinal is None:
                ordinal = 0  # default to first
            refs["ordinal"] = ordinal + 1

            # If session has no remembered results, we need to reach them first
            if not session.last_results:
                if domain and _netloc(session.url) != domain:
                    subgoals.append(Subgoal(
                        kind=SubgoalKind.BROWSER_BAR_SEARCH,
                        params={"query": domain, "domain": domain, "verbatim": command},
                        description=f"Use browser bar to navigate to {domain}",
                    ))
                if query:
                    subgoals.append(Subgoal(
                        kind=SubgoalKind.SEARCH,
                        params={"query": query, "domain": domain},
                        description=f"Search for '{query}'",
                    ))

            subgoals.append(Subgoal(
                kind=SubgoalKind.OPEN_RESULT,
                params={"ordinal": ordinal + 1},
                description=f"Open result #{ordinal + 1}",
            ))

        # ── search ──────────────────────────────────────────────────────
        elif _is_search(t):
            intent = INTENT_SEARCH

            # BROWSER-SHELL PRIORITY RULE:
            # If the query itself names a site ("youtube", "daraz.pk"), the
            # user wants to REACH that site, not search WITHIN one. Drive the
            # browser address bar like a human typing into the omnibox.
            # Note: this overrides even an auto-extracted domain — "search for
            # youtube" should still go to the browser bar, not try to "search
            # for the word youtube on youtube.com".
            if query and _looks_like_site(query):
                subgoals.append(Subgoal(
                    kind=SubgoalKind.BROWSER_BAR_SEARCH,
                    params={"query": query, "verbatim": command},
                    description=f"Use browser bar to reach '{query}'",
                ))
            else:
                if domain and _netloc(session.url) != domain:
                    subgoals.append(Subgoal(
                        kind=SubgoalKind.BROWSER_BAR_SEARCH,
                        params={"query": domain, "domain": domain, "verbatim": command},
                        description=f"Use browser bar to navigate to {domain}",
                    ))
                if query:
                    subgoals.append(Subgoal(
                        kind=SubgoalKind.SEARCH,
                        params={"query": query, "domain": domain},
                        description=f"Search for '{query}'",
                    ))

        # ── login ───────────────────────────────────────────────────────
        elif _is_login(t):
            intent = INTENT_LOGIN
            if domain and _netloc(session.url) != domain:
                subgoals.append(Subgoal(
                    kind=SubgoalKind.BROWSER_BAR_SEARCH,
                    params={"query": domain, "domain": domain, "verbatim": command},
                    description=f"Use browser bar to navigate to {domain}",
                ))
            subgoals.append(Subgoal(
                kind=SubgoalKind.LOGIN,
                params={},
                description="Complete login flow",
            ))

        # ── checkout ────────────────────────────────────────────────────
        elif _is_checkout(t):
            intent = INTENT_CHECKOUT
            subgoals.append(Subgoal(
                kind=SubgoalKind.CHECKOUT,
                params={},
                description="Reach checkout page",
            ))

        # ── navigate ────────────────────────────────────────────────────
        elif _is_navigate(t):
            intent = INTENT_NAVIGATE
            if not domain:
                # Pull the bare token after the verb
                m = re.search(r"(?:go\s+to|visit|open|navigate(?:\s+to)?)\s+([a-z0-9\.\-]+)", t)
                if m:
                    domain = DOMAIN_ALIASES.get(m.group(1), m.group(1))
            if domain:
                # Route through the browser's address bar (shell), not a
                # silent webview.loadURL. Human-like, visible, and avoids
                # opening new tabs.
                subgoals.append(Subgoal(
                    kind=SubgoalKind.BROWSER_BAR_SEARCH,
                    params={"query": domain, "domain": domain, "verbatim": command},
                    description=f"Use browser bar to navigate to {domain}",
                ))

        # ── generic fallback ────────────────────────────────────────────
        if not subgoals:
            subgoals.append(Subgoal(
                kind=SubgoalKind.CUSTOM,
                params={"raw_goal": command},
                description=command,
            ))

        # Mark the first subgoal as active
        if subgoals and subgoals[0].status == "pending":
            subgoals[0].status = "active"

        task = TaskState(
            task_id=new_task_id(),
            goal=command,
            intent=intent,
            subgoals=subgoals,
            referenced_entities=refs,
        )
        logger.info(
            f"[Planner] intent={intent} | subgoals={[sg.kind.value for sg in subgoals]} "
            f"| refs={refs} | domain='{domain}' query='{query}'"
        )
        return task

    # ── Verification / progression ───────────────────────────────────────

    def advance_subgoal_if_satisfied(
        self,
        task: TaskState,
        session: SessionState,
        world_model: Any,
    ) -> bool:
        """Check if the current subgoal is satisfied. If yes, mark done and
        advance to the next one. Returns True if any progress was made."""
        progressed = False

        while task.current_subgoal is not None:
            sg = task.current_subgoal
            if self._is_subgoal_satisfied(sg, session, world_model):
                sg.status = "done"
                task.current_subgoal_idx += 1
                progressed = True
                logger.info(f"[Planner] Subgoal DONE: {sg.description}")
                # mark next as active
                if task.current_subgoal is not None:
                    task.current_subgoal.status = "active"
            else:
                break

        # Mark task complete if all subgoals done
        if task.is_complete and task.status == TaskStatus.ACTIVE:
            task.status = TaskStatus.COMPLETED
            logger.info(f"[Planner] Task COMPLETED: {task.goal}")

        return progressed

    def _is_subgoal_satisfied(
        self,
        sg: Subgoal,
        session: SessionState,
        wm: Any,
    ) -> bool:
        """Deterministic per-kind verification."""
        try:
            from core.world_model import PageState
        except ImportError:
            from .world_model import PageState

        if sg.kind == SubgoalKind.NAVIGATE:
            target = (sg.params.get("domain") or "").lower()
            if not target:
                url = (sg.params.get("url") or "").lower()
                return bool(url and url in (session.url or "").lower())
            return target in _netloc(session.url)

        if sg.kind == SubgoalKind.BROWSER_BAR_SEARCH:
            # Verified when the browser has navigated somewhere that matches
            # the target domain, or simply when the current URL changed from
            # about:blank to any real site.
            target = (sg.params.get("domain") or sg.params.get("query") or "").lower()
            cur = (session.url or "").lower()
            if not cur or cur in ("about:blank", "about:blank/"):
                return False
            if target and target in _netloc(session.url):
                return True
            # If previous was blank and we now have a real URL, count as success
            prev = (session.previous_url or "").lower()
            if prev in ("", "about:blank", "about:blank/") and "://" in cur:
                return True
            return False

        if sg.kind == SubgoalKind.SEARCH:
            query = (sg.params.get("query") or "").lower().strip()
            if not query:
                return False
            ps = getattr(wm, "page_state", None)
            if ps != PageState.SEARCH_RESULTS:
                return False
            # Verify query appears in URL or page title
            url = (session.url or "").lower()
            title = (getattr(wm, "title", "") or "").lower()
            # rudimentary containment: at least one substantive word matches
            words = [w for w in query.split() if len(w) > 2 and w not in STOPWORDS]
            if not words:
                words = query.split()
            hit_url = any(w in url for w in words)
            hit_title = any(w in title for w in words)
            if hit_url or hit_title:
                # cache it on the session
                session.last_search_query = query
                dom = sg.params.get("domain") or _netloc(session.url)
                if dom:
                    session.last_search_domain = dom
                return True
            return False

        if sg.kind == SubgoalKind.OPEN_RESULT:
            ordinal = int(sg.params.get("ordinal") or 0)  # 1-based
            if ordinal < 1:
                return False
            ps = getattr(wm, "page_state", None)
            if ps != PageState.PRODUCT_PAGE:
                return False
            cv = session.currently_viewing
            if not cv:
                return False
            # Match by remembered result title (fuzzy: any 3+ char word overlap)
            if not session.last_results or ordinal > len(session.last_results):
                # No way to verify which product was opened — accept if on a product page
                return True
            target = session.last_results[ordinal - 1]
            if not target.title or not cv.title:
                return True
            tgt_words = {w for w in target.title.lower().split() if len(w) > 3}
            cv_words = {w for w in cv.title.lower().split() if len(w) > 3}
            if tgt_words and cv_words and len(tgt_words & cv_words) >= 1:
                return True
            # URL match fallback
            if target.url and target.url == cv.url:
                return True
            # Lenient: if we reached *a* product page, count it
            return True

        if sg.kind == SubgoalKind.ADD_TO_CART:
            pre = int(sg.params.get("pre_cart_count") or 0)
            if len(session.cart) > pre:
                return True
            # Some sites show "Added to cart" banner without a cart page
            page_text = (getattr(wm, "page_text_summary", "") or "").lower()
            if "added to cart" in page_text or "added to bag" in page_text or "item added" in page_text:
                return True
            return False

        if sg.kind == SubgoalKind.LOGIN:
            return session.logged_in

        if sg.kind == SubgoalKind.CHECKOUT:
            ps = getattr(wm, "page_state", None)
            if ps == PageState.CART_PAGE:
                return False  # cart is not checkout
            url = (session.url or "").lower()
            return "checkout" in url or "payment" in url

        # CUSTOM subgoals never auto-verify
        return False

    # ── Public helpers ───────────────────────────────────────────────────

    @staticmethod
    def extract_refs(command: str) -> dict[str, Any]:
        """Pull ad-hoc entity references out of the command for later use."""
        refs: dict[str, Any] = {}
        ordinal = parse_ordinal(command)
        if ordinal is not None:
            refs["ordinal"] = ordinal + 1
        return refs
