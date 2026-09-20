"""Apply Jaya Gupta to Teradata / EDW / Informatica / Hadoop jobs.

Writes only under data/jaya_teradata/. Never touches ravi_remote_apply_log.csv.
Sends from Jaya's job-apply-kit mailbox (JOBKIT_JAYA_SMTP_*), resume from Jaya profile.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = Path(r"C:\Users\ravir\job-apply-kit")
OUT = ROOT / "data" / "jaya_teradata"
CSV_PATH = OUT / "jobs.csv"
LOG_PATH = OUT / "apply_log.csv"
QUEUED_PATH = OUT / "apply_queued.csv"
REMOTE_QUEUED_PATH = OUT / "apply_remote_queued.csv"

SKIP_EMAIL_LOCAL = ("accessibility", "accommodation", "accommodations", "ada.")
COMPANY_INBOX = {
    "mnj software": "hr@mnjsoftware.com",
    "cspring": "info@cspring.com",
    "concept plus": "info@conceptplus.com",
    "v4c.ai": "info@v4c.ai",
}
GREENHOUSE_REWRITE = {
    "pinterest": "https://boards.greenhouse.io/pinterest/jobs/8076015",
}

sys.path.insert(0, str(ROOT / "scripts"))
from harvest_teradata import is_jaya_role, role_tags  # noqa: E402

REMOTE_KEYS = ("remote", "wfh", "work from home", "home office", "anywhere", "telecommut")
SKIP_TITLE = re.compile(r"\b(intern|internship|student|apprentice|werkstudent|praktikum)\b", re.I)
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
SEND_GAP_SEC = 2.5


def boot_jobkit():
    sys.path.insert(0, str(KIT))
    from jobkit.paths import set_active_user

    set_active_user("jaya")
    from jobkit import store
    from jobkit.apply_channel import classify
    from jobkit.auto import _ensure_packet, _submit
    from jobkit.profile import load_profile
    from jobkit.settings import load_auto_settings

    return store, classify, _ensure_packet, _submit, load_profile, load_auto_settings


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def is_remote(row: dict) -> bool:
    if _truthy(row.get("is_remote") or ""):
        return True
    loc = f"{row.get('location') or ''} {row.get('city') or ''} {row.get('job_type') or ''}".lower()
    return any(key in loc for key in REMOTE_KEYS)


def parse_emails(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "-"}:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for match in EMAIL_RE.findall(text.replace(";", " ").replace(",", " ")):
        addr = match.strip().rstrip(".,;:)>").lower()
        if addr in seen or addr.endswith(("indeed.com", "linkedin.com", "naukri.com")):
            continue
        if not re.match(r"^[a-z0-9]", addr):
            continue
        seen.add(addr)
        out.append(addr)
    return out


def is_bad_email(addr: str) -> bool:
    local = (addr or "").split("@", 1)[0].lower()
    return any(local.startswith(p) or p in local for p in SKIP_EMAIL_LOCAL)


def company_inbox(company: str) -> str:
    key = (company or "").strip().lower()
    for name, email in COMPANY_INBOX.items():
        if name in key:
            return email
    return ""


def harvest_rows(*, remote_only: bool = False) -> list[dict]:
    if not CSV_PATH.is_file():
        raise SystemExit(f"Missing harvest file: {CSV_PATH}")
    rows: list[dict] = []
    seen_url: set[str] = set()
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            title = row.get("title") or ""
            desc = row.get("description") or ""
            if not is_jaya_role(title, desc, row.get("search_term") or ""):
                continue
            if SKIP_TITLE.search(title):
                continue
            if re.search(r"\bsnp\b|\bsap data migration\b", title, re.I) and "teradata" not in title.lower():
                continue
            url = (row.get("url") or "").strip()
            key = url or f"{title}|{row.get('company')}"
            if key in seen_url:
                continue
            seen_url.add(key)
            row["_emails"] = parse_emails(row.get("emails") or "")
            extra = company_inbox(row.get("company") or "")
            if extra and extra not in row["_emails"]:
                row["_emails"].append(extra)
            gh = GREENHOUSE_REWRITE.get((row.get("company") or "").strip().lower())
            if gh:
                row["url"] = gh
            row["_remote"] = is_remote(row) or bool(re.search(r"\bremote\b", title, re.I))
            if remote_only and not row["_remote"]:
                continue
            row["_tags"] = row.get("role_tags") or ",".join(role_tags(title, desc))
            rows.append(row)

    def rank(row: dict) -> tuple:
        title = (row.get("title") or "").lower()
        td_title = "teradata" in title
        india = "india" in f"{row.get('country') or ''} {row.get('location') or ''}".lower()
        return (not td_title, not row["_remote"], not india, not bool(row["_emails"]))

    rows.sort(key=rank)
    return rows


def jd_text(row: dict) -> str:
    desc = str(row.get("description") or "").strip()
    emails = row.get("_emails") or []
    extra = []
    if emails:
        extra.append("Please email your CV / resume and application to " + ", ".join(emails) + ".")
    loc = row.get("location") or ""
    if loc:
        extra.append(f"Location: {loc}")
    if row.get("_remote"):
        extra.append("This is a remote / work-from-home role.")
    extra.append("Teradata DBA / EDW / Informatica / Hadoop administration application.")
    extra.append("Keywords: TASM, TDWM, Viewpoint, DBQL, BTEQ, Informatica PowerCenter, Hive, GCS.")
    return (desc + "\n\n" + "\n".join(extra)).strip()


def upsert_job(store, row: dict) -> int:
    url = (row.get("url") or "").strip()
    existing = store.find_by_url(url) if url else None
    if not existing:
        existing = store.find_duplicate(row.get("title") or "", row.get("company") or "")
    if existing and existing.status == "applied":
        return existing.id
    if existing:
        store.update_job(
            existing.id,
            jd_text=jd_text(row),
            location=row.get("location") or existing.location,
            title=row.get("title") or existing.title,
            company=row.get("company") or existing.company,
        )
        jid = existing.id
    else:
        jid = store.add_job(
            title=row.get("title") or "Teradata DBA",
            company=row.get("company") or "Unknown",
            jd_text=jd_text(row),
            url=url,
            location=row.get("location") or "",
            source="harvest_teradata",
        )
    store.update_job(
        jid,
        track="teradata_dba",
        score=28,
        status="matched",
        ctc_unknown=1,
        skip_reason="",
    )
    return jid


def write_log(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main(*, remote_only: bool = False) -> int:
    store, classify, ensure_packet, submit, load_profile, load_auto_settings = boot_jobkit()
    profile = load_profile()
    settings = load_auto_settings()
    if profile.is_unsubmittable() or "jaya" not in profile.full_name.lower():
        raise SystemExit("Active profile is not Jaya Gupta")
    if not settings.smtp_ready():
        raise SystemExit("Jaya SMTP is not ready — JOBKIT_JAYA_SMTP_USER / JOBKIT_JAYA_SMTP_PASSWORD")
    blob = f"{settings.smtp_from} {settings.smtp_username}".lower()
    if "ravik" in blob or "ravi" in blob:
        raise SystemExit("Refusing to send Jaya Teradata applications from Ravi mailbox")
    if "jaya" not in blob:
        raise SystemExit(f"Unexpected Jaya SMTP from-address {settings.smtp_from or settings.smtp_username}")

    rows = harvest_rows(remote_only=remote_only)
    already = {addr.lower() for addr in store.emailed_addresses()}
    existing_log: list[dict] = []
    if LOG_PATH.exists():
        with LOG_PATH.open(encoding="utf-8", newline="") as fh:
            existing_log = list(csv.DictReader(fh))
    seen_keys = {(r.get("to") or "").lower() + "|" + (r.get("url") or "") for r in existing_log}
    applied_rows: list[dict] = []
    queued_rows: list[dict] = []
    sent = 0
    errors = 0
    print(
        f"Active user jaya | from {settings.smtp_from or settings.smtp_username} | "
        f"rows {len(rows)} | log {LOG_PATH}"
    )

    for row in rows:
        title = row.get("title") or ""
        company = row.get("company") or ""
        url = row.get("url") or ""
        harvest_id = row.get("id") or ""
        tags = row.get("_tags") or ""
        try:
            jid = upsert_job(store, row)
            job = store.get_job(jid)
            if not job:
                queued_rows.append(
                    {"id": harvest_id, "title": title, "company": company, "url": url, "tags": tags, "reason": "missing after ingest"}
                )
                continue
            if job.status == "applied":
                queued_rows.append(
                    {
                        "id": harvest_id,
                        "title": title,
                        "company": company,
                        "url": url,
                        "tags": tags,
                        "reason": f"already applied job #{jid}",
                    }
                )
                continue
            plan = classify(
                job.url,
                job.jd_text,
                fetch_page=bool(remote_only),
                company=job.company,
                guess=True if remote_only else bool(row.get("_remote")) and "teradata" in title.lower(),
            )
            if plan.channel == "email" and plan.email and is_bad_email(plan.email):
                queued_rows.append(
                    {
                        "id": harvest_id,
                        "title": title,
                        "company": company,
                        "url": url,
                        "tags": tags,
                        "reason": f"skipped non-recruiter inbox {plan.email}",
                    }
                )
                continue
            if plan.channel == "email" and plan.email:
                addr = plan.email.lower()
                if addr in already:
                    queued_rows.append(
                        {
                            "id": harvest_id,
                            "title": title,
                            "company": company,
                            "url": url,
                            "tags": tags,
                            "reason": f"already emailed {plan.email}",
                        }
                    )
                    continue
                job = ensure_packet(job)
                detail = submit(job, plan, settings)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update_job(job.id, status="applied", applied_via=plan.channel, applied_at=now, apply_error="")
                already.add(addr)
                sent += 1
                applied_rows.append(
                    {
                        "id": harvest_id,
                        "job_id": jid,
                        "title": title,
                        "company": company,
                        "channel": plan.channel,
                        "to": plan.email,
                        "remote": row.get("_remote"),
                        "tags": tags,
                        "detail": detail,
                        "url": url,
                    }
                )
                print(f"APPLIED #{jid} {title[:60]} -> {plan.email}")
                time.sleep(SEND_GAP_SEC)
                continue
            if plan.channel in {"greenhouse", "lever"} and plan.can_submit:
                job = ensure_packet(job)
                detail = submit(job, plan, settings)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update_job(job.id, status="applied", applied_via=plan.channel, applied_at=now, apply_error="")
                sent += 1
                applied_rows.append(
                    {
                        "id": harvest_id,
                        "job_id": jid,
                        "title": title,
                        "company": company,
                        "channel": plan.channel,
                        "to": plan.channel,
                        "remote": row.get("_remote"),
                        "tags": tags,
                        "detail": detail,
                        "url": url,
                    }
                )
                print(f"APPLIED #{jid} {title[:60]} via {plan.channel}")
                time.sleep(1)
                continue
            queued_rows.append(
                {
                    "id": harvest_id,
                    "title": title,
                    "company": company,
                    "url": url,
                    "tags": tags,
                    "reason": plan.reason or "No recruiter email / ATS API",
                }
            )
        except Exception as exc:  # noqa: BLE001
            errors += 1
            msg = str(exc)
            queued_rows.append(
                {"id": harvest_id, "title": title, "company": company, "url": url, "tags": tags, "reason": msg[:300]}
            )
            print(f"ERROR {title[:60]}: {msg[:160]}")
            if any(token in msg.lower() for token in ("daily user sending limit", "too many login", "421", "454 4.7")):
                print("Stopping: mailbox rate-limited")
                break

    merged = existing_log + [r for r in applied_rows if (r.get("to") or "").lower() + "|" + (r.get("url") or "") not in seen_keys]
    write_log(
        LOG_PATH,
        ["id", "job_id", "title", "company", "channel", "to", "remote", "tags", "detail", "url"],
        merged,
    )
    queued_path = REMOTE_QUEUED_PATH if remote_only else QUEUED_PATH
    write_log(queued_path, ["id", "title", "company", "url", "tags", "reason"], queued_rows)
    print(f"Done. sent={sent} queued={len(queued_rows)} errors={errors} log={LOG_PATH} queued={queued_path}")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-only", action="store_true")
    args = parser.parse_args()
    raise SystemExit(main(remote_only=args.remote_only))
