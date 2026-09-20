"""Detect login walls and CAPTCHA before / during Easy Apply."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WallHit:
    kind: str  # needs_login | captcha
    detail: str


LOGIN_URL_BITS = (
    "/login",
    "/account/login",
    "/auth/",
    "signin",
    "sign-in",
    "checkpoint",
    "/mnjuser/login",
    "accounts.google.com",
)

LOGIN_TEXT_BITS = (
    "sign in to continue",
    "log in to continue",
    "sign in to apply",
    "log in to apply",
    "join now",
    "create an account to continue",
    "please sign in",
    "please log in",
)

CAPTCHA_BITS = (
    "captcha",
    "recaptcha",
    "hcaptcha",
    "verify you are human",
    "confirm you are a human",
    "unusual traffic",
    "are you a robot",
    "security check",
    "challenge-platform",
    "cf-challenge",
)


def check_walls(page) -> WallHit | None:
    url = (page.url or "").lower()
    for bit in LOGIN_URL_BITS:
        if bit in url:
            return WallHit("needs_login", f"URL looks like a login wall ({bit})")
    try:
        body = (page.locator("body").inner_text(timeout=2000) or "")[:8000].lower()
    except Exception:
        body = ""
    for bit in CAPTCHA_BITS:
        if bit in url or bit in body:
            return WallHit("captcha", f"Detected '{bit}' — stop and solve manually")
    try:
        if page.locator("iframe[src*='recaptcha'], iframe[src*='hcaptcha'], .g-recaptcha").count():
            return WallHit("captcha", "CAPTCHA iframe present")
    except Exception:
        pass
    for bit in LOGIN_TEXT_BITS:
        if bit in body:
            return WallHit("needs_login", f"Page asks to sign in ({bit})")
    return None
