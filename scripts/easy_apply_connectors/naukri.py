"""Naukri apply helpers."""

from __future__ import annotations


APPLY_SELECTORS = [
    "button:has-text('Apply')",
    "button:has-text('Apply on company site')",
    "#apply-button",
    "button.waves-effect.waves-ripple.btn",
    "a:has-text('Apply')",
    "button[id*='apply']",
]

SUBMIT_SELECTORS = [
    "button:has-text('Submit')",
    "button:has-text('Apply')",
    "button[type='submit']",
]


def open_apply(page) -> bool:
    for sel in APPLY_SELECTORS:
        try:
            loc = page.locator(sel)
            if not loc.count() or not loc.first.is_visible():
                continue
            text = (loc.first.inner_text() or "").strip().lower()
            if "login" in text or "register" in text:
                continue
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
            if "submit" not in text and text != "apply":
                continue
            loc.first.click(timeout=3000)
            page.wait_for_timeout(1200)
            return True
        except Exception:
            continue
    return False
