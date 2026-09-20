"""Indeed Easy Apply helpers."""

from __future__ import annotations


APPLY_SELECTORS = [
    "button:has-text('Easily apply')",
    "button:has-text('Apply now')",
    "a:has-text('Easily apply')",
    "a:has-text('Apply now')",
    "#indeed-apply-button",
    "button.ia-IndeedApplyButton",
    "button[aria-label*='Apply']",
]

SUBMIT_SELECTORS = [
    "button:has-text('Submit your application')",
    "button:has-text('Submit application')",
    "button:has-text('Submit')",
    "button[aria-label*='Submit']",
    "button.ia-continueButton[type='submit']",
]


def open_apply(page) -> bool:
    for sel in APPLY_SELECTORS:
        try:
            loc = page.locator(sel)
            if loc.count() and loc.first.is_visible():
                loc.first.click(timeout=3000)
                page.wait_for_timeout(1000)
                return True
        except Exception:
            continue
    return False


def click_submit(page) -> bool:
    for sel in SUBMIT_SELECTORS:
        try:
            loc = page.locator(sel)
            if not loc.count() or not loc.first.is_visible():
                continue
            text = (loc.first.inner_text() or "").strip().lower()
            if "continue" in text and "submit" not in text:
                continue
            loc.first.click(timeout=3000)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            continue
    return False
