"""LinkedIn Easy Apply helpers (extends kit form_fill click patterns)."""

from __future__ import annotations


APPLY_SELECTORS = [
    "button.jobs-apply-button",
    "button:has-text('Easy Apply')",
]

SUBMIT_SELECTORS = [
    "button:has-text('Submit application')",
    "button[aria-label='Submit application']",
    "button:has-text('Submit')",
]


def open_apply(page) -> bool:
    for sel in APPLY_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                label = (loc.first.inner_text() or "").lower()
                # Skip "Apply" that leaves LinkedIn for external ATS when we want Easy Apply
                if "easy apply" not in label and "jobs-apply-button" not in sel:
                    continue
                loc.first.click(timeout=3000)
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    # Role-based fallback (kit style)
    try:
        loc = page.get_by_role("button", name="Easy Apply")
        if loc.count() and loc.first.is_visible():
            loc.first.click(timeout=3000)
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


def click_submit(page) -> bool:
    for sel in SUBMIT_SELECTORS:
        try:
            loc = page.locator(sel)
            if not loc.count() or not loc.first.is_visible():
                continue
            text = (loc.first.inner_text() or "").strip().lower()
            if text in {"next", "continue", "review"}:
                continue
            if "submit" not in text and "done" not in text:
                continue
            loc.first.click(timeout=3000)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            continue
    return False
