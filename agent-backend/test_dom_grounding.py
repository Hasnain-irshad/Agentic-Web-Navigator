"""
Integration test: Validates the entire DOM grounding + World Model pipeline.
Tests: JS extraction → PageElement → Observation → WorldModel → LLM prompt → Action → CSS selector
"""
import asyncio
import json

# Test 1: PageElement and Observation data model
print("=" * 60)
print("TEST 1: PageElement and Observation data model")
print("=" * 60)

from core.observation_extractor import PageElement, Observation

elements = [
    PageElement(
        index=1,
        tag="input",
        text="Search in Daraz",
        css_selector="#q",
        element_type="input",
        attributes={"placeholder": "Search in Daraz", "name": "q", "type": "text"},
        is_clickable=True,
    ),
    PageElement(
        index=2,
        tag="a",
        text="Casio Men's Watch Rs.2500",
        css_selector="div.product:nth-of-type(1) > a",
        element_type="link",
        attributes={"href": "/product/12345", "class": "product-title"},
        is_clickable=True,
    ),
    PageElement(
        index=3,
        tag="a",
        text="Boys Digital Watch Rs.1200",
        css_selector="div.product:nth-of-type(2) > a",
        element_type="link",
        attributes={"href": "/product/67890", "class": "product-title"},
        is_clickable=True,
    ),
    PageElement(
        index=4,
        tag="button",
        text="Add to Cart",
        css_selector="button.add-to-cart",
        element_type="button",
        attributes={"class": "add-to-cart btn-primary"},
        is_clickable=True,
    ),
]

obs = Observation(
    url="https://www.daraz.pk/search?q=watches",
    title="Search Results - Daraz",
    elements=elements,
    page_text="Showing 100 results for watches. Casio Men's Watch Rs.2500. Boys Digital Watch Rs.1200.",
)

# Test get_element_by_index
assert obs.get_element_by_index(1).tag == "input", "Element 1 should be input"
assert obs.get_element_by_index(2).text == "Casio Men's Watch Rs.2500", "Element 2 should be Casio watch"
assert obs.get_element_by_index(4).text == "Add to Cart", "Element 4 should be Add to Cart"
assert obs.get_element_by_index(0) is None, "Element 0 should be None (out of bounds)"
assert obs.get_element_by_index(99) is None, "Element 99 should be None (out of bounds)"
print("✓ get_element_by_index works correctly")

# Test to_prompt_text (lightweight debug format)
prompt = obs.to_prompt_text()
assert "Elements:" in prompt, "Prompt should show element count"
assert "#q" not in prompt, "Prompt should NOT show CSS selectors"
print("✓ to_prompt_text formats correctly")


# Test 2: WorldModel Pipeline
print("\n" + "=" * 60)
print("TEST 2: WorldModel Pipeline (NEW)")
print("=" * 60)

from core.world_model import WorldModel, WorldModelBuilder, PageState

wm = WorldModelBuilder.build(obs)

# Page state detection
assert wm.page_state == PageState.SEARCH_RESULTS, f"Expected SEARCH_RESULTS, got {wm.page_state}"
print(f"✓ Page state detected: {wm.page_state.value}")

# Search input detection
assert wm.search is not None and wm.search.found, "Search input should be found"
assert wm.search.css_selector == "#q", f"Search css should be #q, got {wm.search.css_selector}"
print(f"✓ Search input found: css={wm.search.css_selector}, placeholder='{wm.search.placeholder}'")

# Product extraction
assert len(wm.products) >= 2, f"Should find >= 2 products, got {len(wm.products)}"
assert "Casio" in wm.products[0].title or "Casio" in wm.products[1].title, "Should find Casio watch"
print(f"✓ Found {len(wm.products)} products:")
for p in wm.products:
    print(f"    {p.rank}. {p.title} - {p.price} (css={p.css_selector[:40]})")

# Action extraction
assert len(wm.actions) >= 1, f"Should find >= 1 action, got {len(wm.actions)}"
assert any("cart" in a.label.lower() or "add" in a.label.lower() for a in wm.actions), "Should find Add to Cart"
print(f"✓ Found {len(wm.actions)} actions: {[a.label for a in wm.actions]}")

# Element resolution (WorldModel → real CSS selector)
product_1 = wm.get_product_by_ordinal(1)
assert product_1 is not None, "Should resolve 1st product"
elem = wm.resolve_element(product_1.element_index)
assert elem is not None, "Should resolve to real element"
assert elem.css_selector, "Should have CSS selector"
print(f"✓ Ordinal resolution: product #1 → [{elem.index}] css={elem.css_selector[:40]}")

# LLM prompt output
model_prompt = wm.to_prompt()
assert "SEARCH_RESULTS" in model_prompt, "Prompt should contain page state"
assert "SEARCH INPUT: Available" in model_prompt, "Prompt should show search available"
assert "ITEMS ON PAGE" in model_prompt, "Prompt should list items"
print(f"✓ WorldModel.to_prompt() generates structured output")
print(f"\n--- WorldModel Prompt Preview ---\n{model_prompt[:600]}\n")


# Test 3: LLM Prompt Builder
print("=" * 60)
print("TEST 3: LLM Prompt Builder")
print("=" * 60)

from core.llm_prompt_builder import build_action_prompt, get_system_prompt

full_prompt = build_action_prompt(wm, "search for watches and add 2nd item to cart")
assert "GOAL" in full_prompt, "Prompt should contain GOAL"
assert "CURRENT PAGE STATE" in full_prompt, "Prompt should contain page state"
assert "AVAILABLE ACTIONS RIGHT NOW" in full_prompt, "Prompt should show available actions"
print("✓ build_action_prompt generates complete prompt")

sys_prompt = get_system_prompt()
assert "STRICT RULES" in sys_prompt, "System prompt should contain rules"
assert "MUST NOT" in sys_prompt, "System prompt should forbid hallucination"
print("✓ System prompt has strict behavioral constraints")


# Test 4: Ordinal Parsing
print("\n" + "=" * 60)
print("TEST 4: Ordinal Parsing")
print("=" * 60)

from core.element_resolver import parse_ordinal

assert parse_ordinal("click 1st product") == 0, "1st → 0"
assert parse_ordinal("click 2nd product") == 1, "2nd → 1"
assert parse_ordinal("click 3rd product") == 2, "3rd → 2"
assert parse_ordinal("click first item") == 0, "first → 0"
assert parse_ordinal("click second item") == 1, "second → 1"
assert parse_ordinal("no ordinal here") is None, "No ordinal → None"
print("✓ parse_ordinal works correctly")


# Test 5: Action Schema
print("\n" + "=" * 60)
print("TEST 5: Action Schema with element_index")
print("=" * 60)

from schemas.actions import Action, ActionType

action = Action(action_type=ActionType.CLICK, element_index=3, reasoning="Click the 2nd product")
assert action.element_index == 3
print("✓ Action with element_index created correctly")

action = Action.from_dict({"action_type": "click", "element_index": "3", "reasoning": "test"})
assert action.element_index == 3
print("✓ Action.from_dict handles string element_index")


# Test 6: End-to-end resolution
print("\n" + "=" * 60)
print("TEST 6: End-to-end WorldModel resolution")
print("=" * 60)

# Simulate what SessionAgent._resolve_via_world_model does
# "search_input" → resolves to search element
search_elem = wm.resolve_element(wm.search.element_index)
assert search_elem.tag == "input", "Search should resolve to input"
assert search_elem.css_selector == "#q"
print(f"✓ 'search_input' → [{search_elem.index}] <{search_elem.tag}> css={search_elem.css_selector}")

# "second_product" → resolves to 2nd product
product_2 = wm.get_product_by_ordinal(2)
assert product_2 is not None
p2_elem = wm.resolve_element(product_2.element_index)
assert p2_elem is not None
print(f"✓ '2nd product' → [{p2_elem.index}] '{p2_elem.text[:30]}' css={p2_elem.css_selector[:40]}")

# "add_to_cart" → resolves to cart button
cart_action = wm.actions[0]
cart_elem = wm.resolve_element(cart_action.element_index)
assert cart_elem is not None
assert cart_elem.tag == "button"
print(f"✓ 'add_to_cart' → [{cart_elem.index}] '{cart_elem.text}' css={cart_elem.css_selector}")


print("\n" + "=" * 60)
print("ALL TESTS PASSED ✓")
print("=" * 60)
print("\nWorld Model pipeline is working:")
print("  DOM extraction → PageElement → Observation")
print("  → WorldModelBuilder.build() → WorldModel")
print("  → to_prompt() (compact LLM view) → resolve_element() (real CSS)")
print("  → Playwright executes")
