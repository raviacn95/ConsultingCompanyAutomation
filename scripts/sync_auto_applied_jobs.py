"""Build Pages list of every successful auto-apply (email + Easy Apply submit).

Reads existing per-user logs (never mixes Ravi/Jaya sources):
  data/ravi_remote_apply_log.csv
  data/jaya_teradata/apply_log.csv
  data/ravi_easy_apply_log.csv          (status=submitted only)
  data/jaya_teradata/easy_apply_log.csv (status=submitted only)

Writes:
  data/auto_applied_jobs.json
  dashboard/auto_applied_jobs.js  → window.AUTO_APPLIED_JOBS = {...}
  docs/auto_applied_jobs.js       (mirror when docs/ exists)

Dedupes by (user, url) then (user, job_id). Caps at MAX_ROWS (newest first).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "data" / "auto_applied_jobs.json"
DASH_JS = ROOT / "dashboard" / "auto_applied_jobs.js"
DOCS_JS = ROOT / "docs" / "auto_applied_jobs.js"

MAX_ROWS = 400

APPLIED_AT_RE = re.compile(
    r"(?:Applied|applied_at)\s*[: ]?\s*(\d{4}-\d{2}-\d{2}T[\d:+.\-Z]+)",
    re.I,
)
ISO_RE = re.compile(r"\d{4}-\d{2}-\d{2}T[\d:+.\-Z]+")

SOURCES = (
    {
        "user": "ravi",
        "kind": "email",
        "path": ROOT / "data" / "ravi_remote_apply_log.csv",
    },
    {
        "user": "jaya",
        "kind": "email",
        "path": ROOT / "data" / "jaya_teradata" / "apply_log.csv",
    },
    {
        "user": "ravi",
        "kind": "easy",
        "path": ROOT / "data" / "ravi_easy_apply_log.csv",
    },
    {
        "user": "jaya",
        "kind": "easy",
        "path": ROOT / "data" / "jaya_teradata" / "easy_apply_log.csv",
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_csv(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if any((v or "").strip() for v in r.values())]


def _normalize_ts(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    # Prefer Zulu for dashboard sortability
    if text.endswith("+00:00"):
        return text[:-6] + "Z"
    return text


def _parse_applied_at(detail: str, fallback: str = "") -> str:
    detail = detail or ""
    m = APPLIED_AT_RE.search(detail)
    if m:
        return _normalize_ts(m.group(1))
    m = ISO_RE.search(detail)
    if m:
        return _normalize_ts(m.group(0))
    return _normalize_ts(fallback)


def _norm_channel(raw: str, *, method: str, site: str = "") -> str:
    ch = (raw or site or "").strip().lower()
    if method == "easy_apply":
        if ch in {"indeed", "linkedin", "naukri"}:
            return ch
        return site.strip().lower() if site else "other"
    if ch in {"email", "greenhouse", "lever"}:
        return ch if ch != "email" else "email"
    if ch in {"indeed", "linkedin", "naukri"}:
        return ch
    return "email" if method == "email" else (ch or "other")


def _from_email_row(user: str, row: dict, order: int) -> dict | None:
    title = (row.get("title") or "").strip()
    url = (row.get("url") or "").strip()
    if not title and not url:
        return None
    channel_raw = (row.get("channel") or "email").strip().lower()
    method = "email"
    # greenhouse/lever still come from the email-apply scripts
    detail = row.get("detail") or ""
    applied_at = _parse_applied_at(detail)
    job_id = (row.get("job_id") or row.get("id") or "").strip()
    return {
        "user": user,
        "channel": _norm_channel(channel_raw, method=method),
        "job_title": title,
        "company": (row.get("company") or "").strip(),
        "url": url,
        "applied_at": applied_at,
        "method": method,
        "outcome": "applied",
        "job_id": job_id,
        "to": (row.get("to") or "").strip(),
        "_order": order,
    }


def _from_easy_row(user: str, row: dict, order: int) -> dict | None:
    status = (row.get("status") or "").strip().lower()
    # Only count real Easy Apply submits as auto-applied (not fill-only)
    if status != "submitted":
        return None
    title = (row.get("title") or "").strip()
    url = (row.get("url") or "").strip()
    if not title and not url:
        return None
    site = (row.get("site") or "").strip().lower()
    return {
        "user": user,
        "channel": _norm_channel(site, method="easy_apply", site=site),
        "job_title": title,
        "company": (row.get("company") or "").strip(),
        "url": url,
        "applied_at": _normalize_ts(row.get("timestamp") or ""),
        "method": "easy_apply",
        "outcome": "submitted",
        "job_id": (row.get("id") or "").strip(),
        "to": "",
        "_order": order,
    }


def collect_records() -> list[dict]:
    records: list[dict] = []
    seq = 0
    for src in SOURCES:
        rows = _read_csv(src["path"])
        for row in rows:
            seq += 1
            if src["kind"] == "email":
                rec = _from_email_row(src["user"], row, seq)
            else:
                rec = _from_easy_row(src["user"], row, seq)
            if rec:
                records.append(rec)
    return records


def dedupe(records: list[dict]) -> list[dict]:
    """Keep one row per (user, url) or (user, job_id); prefer dated + newest."""

    def sort_key(r: dict) -> tuple:
        # Newest first: applied_at desc, then higher _order (later appends)
        at = r.get("applied_at") or ""
        return (1 if at else 0, at, r.get("_order") or 0)

    ranked = sorted(records, key=sort_key, reverse=True)
    seen_url: set[str] = set()
    seen_jid: set[str] = set()
    out: list[dict] = []
    for r in ranked:
        user = r["user"]
        url = (r.get("url") or "").strip().lower()
        jid = (r.get("job_id") or "").strip()
        url_key = f"{user}|{url}" if url else ""
        jid_key = f"{user}|{jid}" if jid else ""
        if url_key and url_key in seen_url:
            continue
        if jid_key and jid_key in seen_jid:
            continue
        if url_key:
            seen_url.add(url_key)
        if jid_key:
            seen_jid.add(jid_key)
        clean = {k: v for k, v in r.items() if not k.startswith("_")}
        out.append(clean)
    return out


def write_outputs(jobs: list[dict], *, cap: int = MAX_ROWS) -> dict:
    capped = jobs[: max(1, min(cap, 2000))]
    by_user = {"ravi": 0, "jaya": 0}
    by_method = {"email": 0, "easy_apply": 0}
    for j in capped:
        u = j.get("user")
        if u in by_user:
            by_user[u] += 1
        m = j.get("method")
        if m in by_method:
            by_method[m] += 1

    payload = {
        "generated_at": utc_now(),
        "cap": cap,
        "total": len(capped),
        "total_before_cap": len(jobs),
        "by_user": by_user,
        "by_method": by_method,
        "jobs": capped,
        "note": (
            "Successful auto-applies only: email/ATS from apply logs + Easy Apply "
            "status=submitted. Ravi and Jaya never mixed. Newest first."
        ),
    }

    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    body = "window.AUTO_APPLIED_JOBS = " + json.dumps(payload, ensure_ascii=False) + ";\n"
    DASH_JS.parent.mkdir(parents=True, exist_ok=True)
    DASH_JS.write_text(body, encoding="utf-8")
    if DOCS_JS.parent.is_dir():
        DOCS_JS.write_text(body, encoding="utf-8")
    return payload


def sync(*, cap: int = MAX_ROWS) -> dict:
    jobs = dedupe(collect_records())
    return write_outputs(jobs, cap=cap)


def main() -> int:
    p = argparse.ArgumentParser(description="Sync auto-applied jobs into dashboard/docs JS")
    p.add_argument("--cap", type=int, default=MAX_ROWS, help="Max rows on Pages (default 400)")
    args = p.parse_args()
    payload = sync(cap=max(1, min(int(args.cap or MAX_ROWS), 2000)))
    print(
        f"Wrote {payload['total']} auto-applied jobs "
        f"(ravi={payload['by_user']['ravi']} jaya={payload['by_user']['jaya']}; "
        f"before_cap={payload['total_before_cap']}) -> {DASH_JS.name}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
