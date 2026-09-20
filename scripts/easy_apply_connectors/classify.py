"""Classify job URLs into indeed / linkedin / naukri / other."""

from __future__ import annotations

from urllib.parse import urlparse

SITE_HOSTS = {
    "indeed": ("indeed.com", "indeed.co", "indeed.fr", "indeed.de", "indeed.co.uk", "indeed.ca"),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "naukri": ("naukri.com", "naukrigulf.com"),
}


def classify_site(url: str) -> str:
    host = (urlparse(url or "").hostname or "").lower().lstrip("www.")
    if not host:
        return "other"
    for site, suffixes in SITE_HOSTS.items():
        if any(host == s or host.endswith("." + s) for s in suffixes):
            return site
    return "other"
