"""Load no-email queued rows and skip already easy-applied ids."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from .classify import classify_site

ROOT = Path(__file__).resolve().parents[2]

NO_EMAIL_RE = re.compile(
    r"no recruiter email|no sendable|ats api|easy apply|apply desk|career form",
    re.I,
)

USER_PATHS = {
    "ravi": {
        "queued": ROOT / "data" / "ravi_remote_apply_queued.csv",
        "log": ROOT / "data" / "ravi_easy_apply_log.csv",
        "kit_user": "ravi",
        "label": "Ravi Kumar",
    },
    "jaya": {
        "queued": ROOT / "data" / "jaya_teradata" / "apply_remote_queued.csv",
        "queued_all": ROOT / "data" / "jaya_teradata" / "apply_queued.csv",
        "log": ROOT / "data" / "jaya_teradata" / "easy_apply_log.csv",
        "kit_user": "jaya",
        "label": "Jaya Gupta",
    },
}

LOG_FIELDS = [
    "id",
    "title",
    "company",
    "site",
    "url",
    "status",
    "detail",
    "timestamp",
]


@dataclass
class QueuedJob:
    id: str
    title: str
    company: str
    url: str
    reason: str
    site: str


def user_config(user: str) -> dict:
    key = (user or "").strip().lower()
    if key not in USER_PATHS:
        raise SystemExit(f"Unknown --user {user!r}; use ravi or jaya")
    return USER_PATHS[key]


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def load_done_ids(log_path: Path) -> set[str]:
    """Ids already filled or submitted (skip). Failures may be retried."""
    done: set[str] = set()
    for row in _read_csv(log_path):
        status = (row.get("status") or "").strip().lower()
        if status in {"filled", "submitted"}:
            rid = (row.get("id") or "").strip()
            if rid:
                done.add(rid)
    return done


def is_no_email_reason(reason: str) -> bool:
    return bool(NO_EMAIL_RE.search(reason or ""))


def load_queued(
    user: str,
    *,
    site: str | None = None,
    include_other: bool = False,
    use_all_queued: bool = False,
) -> list[QueuedJob]:
    cfg = user_config(user)
    paths = [cfg["queued"]]
    if use_all_queued and cfg.get("queued_all"):
        paths.append(cfg["queued_all"])

    seen: set[str] = set()
    done = load_done_ids(cfg["log"])
    out: list[QueuedJob] = []
    for path in paths:
        for row in _read_csv(path):
            rid = (row.get("id") or "").strip()
            url = (row.get("url") or "").strip()
            if not rid or not url or rid in seen or rid in done:
                continue
            reason = row.get("reason") or ""
            if not is_no_email_reason(reason):
                # Still allow rows whose URL is clearly an Easy Apply board
                # even if reason text drifted — but only when reason looks empty
                # or explicitly mentions apply/manual.
                if reason.strip() and "already emailed" in reason.lower():
                    continue
                if reason.strip() and not re.search(r"apply|manual|indeed|linkedin|naukri", reason, re.I):
                    continue
            classified = classify_site(url)
            if site and classified != site:
                continue
            if classified == "other" and not include_other:
                continue
            seen.add(rid)
            out.append(
                QueuedJob(
                    id=rid,
                    title=(row.get("title") or "").strip(),
                    company=(row.get("company") or "").strip(),
                    url=url,
                    reason=reason.strip(),
                    site=classified,
                )
            )
    return out


def append_log(log_path: Path, row: dict) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    exists = log_path.is_file()
    with log_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=LOG_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in LOG_FIELDS})


def summarize_by_site(jobs: list[QueuedJob]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for job in jobs:
        counts[job.site] = counts.get(job.site, 0) + 1
    return counts
