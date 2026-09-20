"""Persistent browser profiles per user × site (never mix Ravi / Jaya)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILES_ROOT = ROOT / ".browser-profiles"
SHOTS_ROOT = ROOT / "data" / "easy_apply_shots"

# Optional overrides: EASY_APPLY_PROFILE_RAVI_INDEED=/path/to/dir etc.
ENV_MAP = {
    ("ravi", "indeed"): "EASY_APPLY_PROFILE_RAVI_INDEED",
    ("ravi", "linkedin"): "EASY_APPLY_PROFILE_RAVI_LINKEDIN",
    ("ravi", "naukri"): "EASY_APPLY_PROFILE_RAVI_NAUKRI",
    ("jaya", "indeed"): "EASY_APPLY_PROFILE_JAYA_INDEED",
    ("jaya", "linkedin"): "EASY_APPLY_PROFILE_JAYA_LINKEDIN",
    ("jaya", "naukri"): "EASY_APPLY_PROFILE_JAYA_NAUKRI",
}

HOME_URL = {
    "indeed": "https://www.indeed.com/",
    "linkedin": "https://www.linkedin.com/feed/",
    "naukri": "https://www.naukri.com/",
    "other": "about:blank",
}


def profile_dir(user: str, site: str) -> Path:
    user = user.strip().lower()
    site = site.strip().lower()
    env_key = ENV_MAP.get((user, site))
    if env_key:
        override = (os.environ.get(env_key) or "").strip()
        if override:
            return Path(override)
    path = PROFILES_ROOT / user / site
    path.mkdir(parents=True, exist_ok=True)
    return path


def shots_dir(user: str) -> Path:
    path = SHOTS_ROOT / user.strip().lower()
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def launch_context(user: str, site: str, *, headless: bool = False):
    """Launch Edge persistent context for this user+site. Caller must not reuse across users."""
    from playwright.sync_api import sync_playwright

    user_data = profile_dir(user, site)
    home = HOME_URL.get(site, "about:blank")
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            str(user_data),
            channel="msedge",
            headless=headless,
            args=["--disable-popup-blocking", "--disable-infobars"],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900},
            accept_downloads=True,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            if site != "other" and "about:blank" in (page.url or "about:blank"):
                try:
                    page.goto(home, wait_until="domcontentloaded", timeout=45000)
                except Exception:
                    pass
            yield context, page
        finally:
            context.close()
