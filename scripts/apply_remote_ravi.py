"""Apply Ravi Kumar to remote SAP QA / Playwright jobs from the worldwide harvest CSV.

Sends from Ravi's job-apply-kit mailbox (JOBKIT_SMTP_USER / JOBKIT_SMTP_PASSWORD).
The kit can email recruiter addresses or submit Greenhouse/Lever. Indeed / Naukri /
Workday / LinkedIn Easy Apply postings without an address are logged as queued.

Targets: SAP test/QA/automation and/or Playwright (SDET). Tosca-only roles (no SAP
and no Playwright) are skipped. Tosca is allowed only when the JD also has SAP or Playwright.
"""

from __future__ import annotations

import csv
import os
import re
import sys
import time
import winreg
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = Path(r"C:\Users\ravir\job-apply-kit")
LOG_PATH = ROOT / "data" / "ravi_remote_apply_log.csv"
QUEUED_PATH = ROOT / "data" / "ravi_remote_apply_queued.csv"


def latest_worldwide_csv() -> Path:
    """Use the harvest Excel file, or the sidecar if Excel locked the main file."""
    candidates = [
        ROOT / "data" / "jobs_worldwide.csv",
        ROOT / "data" / "jobs_worldwide.updated.csv",
    ]
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        raise SystemExit("Missing harvest file: data/jobs_worldwide.csv")
    return max(existing, key=lambda p: p.stat().st_mtime)

REMOTE_KEYS = ("remote", "wfh", "work from home", "home office", "anywhere", "telecommut")
SKIP_TITLE = re.compile(
    r"\b(intern|internship|student|apprentice|werkstudent|medical coder|"
    r"food technologist|social media|hrbp|charge entry|ambulance coding)\b",
    re.I,
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
TOSCA_RE = re.compile(r"\b(tosca|tricentis)\b", re.I)
SAP_RE = re.compile(r"\b(sap|s/4|s4hana|s/4hana)\b", re.I)
PLAYWRIGHT_RE = re.compile(r"\bplaywright\b", re.I)
TEST_ROLE_RE = re.compile(
    r"\b(test|qa|quality|sdet|automation|tester|quality assurance)\b",
    re.I,
)
SEND_GAP_SEC = 2.5


def load_ravi_smtp() -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment")
    for name in ("JOBKIT_SMTP_USER", "JOBKIT_SMTP_PASSWORD"):
        try:
            val, _ = winreg.QueryValueEx(key, name)
        except OSError as exc:
            raise SystemExit(f"Missing Windows user env {name}") from exc
        os.environ[name] = str(val).replace(" ", "")


def boot_jobkit():
    load_ravi_smtp()
    sys.path.insert(0, str(KIT))
    from jobkit.paths import set_active_user

    set_active_user("ravi")
    from jobkit import store
    from jobkit.apply_channel import classify
    from jobkit.auto import _ensure_packet, _submit
    from jobkit.profile import load_profile
    from jobkit.settings import load_auto_settings

    return store, classify, _ensure_packet, _submit, load_profile, load_auto_settings


def _truthy(value: str) -> bool:
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _role_text(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title", "description", "sap_modules"))


def is_remote(row: dict) -> bool:
    if _truthy(row.get("is_remote") or ""):
        return True
    loc = f"{row.get('location') or ''} {row.get('city') or ''} {row.get('job_type') or ''}".lower()
    return any(key in loc for key in REMOTE_KEYS)


def is_food_tosca(row: dict) -> bool:
    company = (row.get("company") or "").strip().lower()
    title = row.get("title") or ""
    if company not in {"tosca", "la tosca foods"}:
        return False
    return not bool(re.search(r"\b(test|qa|automation|tricentis|sap|sdet|playwright)\b", title, re.I))


def is_tosca(row: dict) -> bool:
    if is_food_tosca(row):
        return False
    return bool(TOSCA_RE.search(_role_text(row)))


def is_sap(row: dict) -> bool:
    if is_food_tosca(row):
        return False
    if str(row.get("is_sap") or "").strip().lower() == "yes":
        return True
    return bool(SAP_RE.search(_role_text(row)))


def is_playwright(row: dict) -> bool:
    if is_food_tosca(row):
        return False
    return bool(PLAYWRIGHT_RE.search(_role_text(row)))


def is_sap_qa(row: dict) -> bool:
    """SAP in a test/QA/automation context (Tosca/Playwright on the JD also counts)."""
    if not is_sap(row):
        return False
    blob = _role_text(row)
    return bool(TEST_ROLE_RE.search(blob) or TOSCA_RE.search(blob) or PLAYWRIGHT_RE.search(blob))


def is_ravi_target(row: dict) -> bool:
    """SAP QA/test/automation and/or Playwright. Skip Tosca-only (no SAP, no Playwright)."""
    if is_food_tosca(row):
        return False
    pw = is_playwright(row)
    sap_qa = is_sap_qa(row)
    tosca = is_tosca(row)
    if tosca and not is_sap(row) and not pw:
        return False
    return bool(pw or sap_qa)


def relevance(row: dict) -> tuple:
    title = (row.get("title") or "").lower()
    pw_title = bool(PLAYWRIGHT_RE.search(title))
    sap_title = bool(SAP_RE.search(title))
    test_title = bool(TEST_ROLE_RE.search(title))
    # Best first: Playwright+SAP title, Playwright, SAP QA title, then email presence.
    return (
        not (pw_title and sap_title),
        not pw_title,
        not (sap_title and test_title),
        not sap_title,
        not bool(row.get("_emails")),
    )


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
        if not re.match(r"^[a-z0-9]", addr) or addr.startswith("-"):
            continue
        seen.add(addr)
        out.append(addr)
    return out


def harvest_rows(csv_path: Path) -> list[dict]:
    rows: list[dict] = []
    seen_url: set[str] = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if not is_remote(row) or not is_ravi_target(row):
                continue
            if SKIP_TITLE.search(row.get("title") or "") and not (
                is_playwright(row) or is_tosca(row) or is_sap_qa(row)
            ):
                continue
            url = (row.get("url") or "").strip()
            key = url or f"{row.get('title')}|{row.get('company')}"
            if key in seen_url:
                continue
            seen_url.add(key)
            row["_emails"] = parse_emails(row.get("emails") or "")
            row["_tosca"] = is_tosca(row)
            row["_playwright"] = is_playwright(row)
            rows.append(row)
    rows.sort(key=relevance)
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
    if _truthy(row.get("is_remote") or "") or any(k in loc.lower() for k in REMOTE_KEYS):
        extra.append("This is a remote / work-from-home role.")
    # Marker for track only — not a job title (extract_role must ignore this).
    extra.append("[Applicant track: Ravi Kumar — SAP S/4 / Playwright test automation]")
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
            title=row.get("title") or "SAP role",
            company=row.get("company") or "Unknown",
            jd_text=jd_text(row),
            url=url,
            location=row.get("location") or "",
            source="harvest_remote",
        )
    store.update_job(
        jid,
        track="automation",
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


def main() -> int:
    csv_path = latest_worldwide_csv()
    store, classify, _ensure_packet, _submit, load_profile, load_auto_settings = boot_jobkit()
    profile = load_profile()
    settings = load_auto_settings()
    # Static master PDF is only a fact source — every send builds a JD .docx packet.
    if profile.is_unsubmittable():
        raise SystemExit("Ravi profile is marked unsubmittable")
    if not settings.smtp_ready():
        raise SystemExit("Ravi SMTP is not ready — JOBKIT_SMTP_USER / JOBKIT_SMTP_PASSWORD")
    if settings.smtp_from.lower().startswith("jaya") or "jayagupta" in settings.smtp_username.lower():
        raise SystemExit("Refusing to send Ravi applications from Jaya mailbox")

    rows = harvest_rows(csv_path)
    already = {addr.lower() for addr in store.emailed_addresses()}
    existing_log: list[dict] = []
    if LOG_PATH.exists():
        with LOG_PATH.open(encoding="utf-8-sig", newline="") as fh:
            existing_log = [r for r in csv.DictReader(fh) if r.get("to") or r.get("title")]
    seen_keys = {(r.get("to") or "").lower() + "|" + (r.get("url") or "") for r in existing_log}
    applied_rows: list[dict] = []
    queued_rows: list[dict] = []
    sent = 0
    errors = 0

    print(
        f"Active user ravi | from {settings.smtp_from or settings.smtp_username} | "
        f"JD-tailored packets | source {csv_path.name} | remote SAP/Playwright rows {len(rows)}"
    )

    for row in rows:
        title = row.get("title") or ""
        company = row.get("company") or ""
        url = row.get("url") or ""
        harvest_id = row.get("id") or ""
        try:
            jid = upsert_job(store, row)
            job = store.get_job(jid)
            if not job:
                queued_rows.append(
                    {"id": harvest_id, "title": title, "company": company, "url": url, "reason": "job missing after ingest"}
                )
                continue
            if job.status == "applied":
                queued_rows.append(
                    {
                        "id": harvest_id,
                        "title": title,
                        "company": company,
                        "url": url,
                        "reason": f"already applied job #{jid}",
                    }
                )
                continue
            plan = classify(
                job.url,
                job.jd_text,
                fetch_page=False,
                company=job.company,
                guess=bool(row.get("_playwright") or row.get("_tosca")),
            )
            if plan.channel == "email" and plan.email:
                addr = plan.email.lower()
                if addr in already:
                    queued_rows.append(
                        {
                            "id": harvest_id,
                            "title": title,
                            "company": company,
                            "url": url,
                            "reason": f"already emailed {plan.email}",
                        }
                    )
                    continue
                job = _ensure_packet(job)
                detail = _submit(job, plan, settings)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update_job(
                    job.id,
                    status="applied",
                    applied_via=plan.channel,
                    applied_at=now,
                    apply_error="",
                )
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
                        "tosca": row.get("_tosca"),
                        "detail": detail,
                        "url": url,
                    }
                )
                print(f"APPLIED #{jid} {title[:60]} -> {plan.email}")
                time.sleep(SEND_GAP_SEC)
                continue
            if plan.channel in {"greenhouse", "lever"} and plan.can_submit:
                job = _ensure_packet(job)
                detail = _submit(job, plan, settings)
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                store.update_job(
                    job.id,
                    status="applied",
                    applied_via=plan.channel,
                    applied_at=now,
                    apply_error="",
                )
                sent += 1
                applied_rows.append(
                    {
                        "id": harvest_id,
                        "job_id": jid,
                        "title": title,
                        "company": company,
                        "channel": plan.channel,
                        "to": plan.channel,
                        "tosca": row.get("_tosca"),
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
                    "reason": plan.reason or "No recruiter email / ATS API",
                }
            )
        except Exception as exc:  # noqa: BLE001 — keep going unless mailbox is blocked
            errors += 1
            msg = str(exc)
            queued_rows.append(
                {"id": harvest_id, "title": title, "company": company, "url": url, "reason": msg[:300]}
            )
            print(f"ERROR {title[:60]}: {msg[:160]}")
            if any(
                token in msg.lower()
                for token in ("daily user sending limit", "too many login", "421", "454", "550-5.4.5")
            ):
                print("Stopping: mailbox rate-limited")
                break

    merged = existing_log + [
        r for r in applied_rows if (r.get("to") or "").lower() + "|" + (r.get("url") or "") not in seen_keys
    ]
    write_log(
        LOG_PATH,
        ["id", "job_id", "title", "company", "channel", "to", "tosca", "detail", "url"],
        merged,
    )
    write_log(QUEUED_PATH, ["id", "title", "company", "url", "reason"], queued_rows)
    print(
        f"Done. sent={sent} queued={len(queued_rows)} errors={errors} "
        f"log={LOG_PATH.name} queued_log={QUEUED_PATH.name}"
    )
    if sent:
        try:
            from sync_auto_applied_jobs import sync as sync_auto_applied  # noqa: WPS433

            sync_auto_applied()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN sync_auto_applied_jobs: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
