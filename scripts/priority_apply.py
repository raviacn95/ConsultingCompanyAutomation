"""Guess easy + high-pay remote targets for Ravi and Jaya, then apply those first.

Ravi: Tosca / SAP QA only. Jaya: Teradata / EDW / Informatica / Hadoop only.
Never mix mailboxes.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = Path(r"C:\Users\ravir\job-apply-kit")
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(KIT))

from apply_jaya_teradata import (  # noqa: E402
    LOG_PATH as JAYA_LOG,
    boot_jobkit as boot_jaya,
    harvest_rows as jaya_harvest,
    is_bad_email,
    jd_text as jaya_jd,
)
from apply_remote_ravi import (  # noqa: E402
    LOG_PATH as RAVI_LOG,
    TOSCA_RE,
    boot_jobkit as boot_ravi,
    harvest_rows as ravi_harvest,
    jd_text as ravi_jd,
    latest_worldwide_csv,
)
from jobkit.salary import parse_salary  # noqa: E402

OUT_CSV = ROOT / "data" / "priority_targets.csv"
OUT_JS = ROOT / "dashboard" / "priority.js"
SEND_GAP_SEC = 2.5

SENIOR_RE = re.compile(
    r"\b(lead|leader|senior|sr\.?|principal|staff|architect|manager|specialist|consultant|head)\b",
    re.I,
)
QA_RE = re.compile(r"\b(test|qa|quality|sdet|automation|tosca|tricentis)\b", re.I)
PREMIUM_MARKET = (
    "usa",
    "united states",
    "uk",
    "united kingdom",
    "germany",
    "netherlands",
    "switzerland",
    "canada",
    "australia",
    "ireland",
    "singapore",
    "remote",
)
CONTRACT_RE = re.compile(r"\b(c2c|1099|w2|contract|contractor|day rate|daily rate|freelance)\b", re.I)
ATS_RE = re.compile(r"greenhouse\.io|jobs\.lever\.co|lever\.co", re.I)
SKIP_LOCAL = ("accessibility", "accommodation", "accommodations", "ada.", "adastaff", "youngstars")
INBOX_OVERRIDE = {
    "bristol myers": "taenablement@bms.com",
    "körber": "jobs@koerber.de",
    "korber": "jobs@koerber.de",
}


def _blob(row: dict) -> str:
    return " ".join(str(row.get(k) or "") for k in ("title", "description", "salary", "location", "country"))


def _market(row: dict) -> str:
    return f"{row.get('country') or ''} {row.get('location') or ''} {row.get('city') or ''}".lower()


def pay_guess(row: dict) -> tuple[int, list[str], str]:
    reasons: list[str] = []
    score = 0
    title = row.get("title") or ""
    parsed = parse_salary(_blob(row))
    ceiling = parsed.offer_ceiling_lpa
    salary_note = parsed.raw or (row.get("salary") or "").strip()
    if ceiling is not None:
        if ceiling >= 50:
            score += 45
            reasons.append(f"listed ~{ceiling:.0f} LPA+")
        elif ceiling >= 40:
            score += 38
            reasons.append(f"listed ~{ceiling:.0f} LPA")
        elif ceiling >= 30:
            score += 30
            reasons.append(f"listed ~{ceiling:.0f} LPA")
        elif ceiling >= 20:
            score += 10
            reasons.append(f"listed ~{ceiling:.0f} LPA (below 30)")
    if SENIOR_RE.search(title):
        score += 18
        reasons.append("senior/lead title")
    if CONTRACT_RE.search(_blob(row)):
        score += 12
        reasons.append("contract / C2C rate likely")
    market = _market(row)
    if any(key in market for key in PREMIUM_MARKET) or "remote" in market:
        if any(key in market for key in ("usa", "united states", "uk", "germany", "switzerland", "netherlands")):
            score += 22
            reasons.append("US/UK/EU remote market")
        else:
            score += 12
            reasons.append("premium-market remote")
    if "india" in market and ceiling is None:
        score += 4
        reasons.append("India remote (pay unknown)")
    return score, reasons, salary_note


def easy_guess(row: dict) -> tuple[int, list[str], str]:
    reasons: list[str] = []
    score = 0
    emails = [e for e in (row.get("_emails") or []) if not any(p in e for p in SKIP_LOCAL)]
    company = (row.get("company") or "").lower()
    for key, inbox in INBOX_OVERRIDE.items():
        if key in company and inbox not in emails:
            emails.append(inbox)
            row["_emails"] = emails
    url = row.get("url") or ""
    channel = "manual"
    if emails:
        score += 40
        reasons.append("recruiter email on the posting")
        channel = "email"
    if ATS_RE.search(url):
        score += 35
        reasons.append("Greenhouse/Lever API apply")
        channel = "ats" if channel == "manual" else channel
    if not emails and not ATS_RE.search(url):
        reasons.append("Indeed/Easy Apply — queued, not auto-sent")
    return score, reasons, channel


def ravi_fit(row: dict) -> tuple[int, list[str]]:
    title = row.get("title") or ""
    reasons: list[str] = []
    score = 0
    tosca = bool(row.get("_tosca") or TOSCA_RE.search(title) or TOSCA_RE.search(row.get("description") or ""))
    qa = bool(QA_RE.search(title))
    if tosca and qa:
        score += 40
        reasons.append("Tosca/Tricentis in a test role")
    elif tosca:
        score += 32
        reasons.append("Tosca/Tricentis mentioned")
    elif qa:
        score += 20
        reasons.append("SAP QA / test automation title")
    else:
        score -= 25
        reasons.append("SAP but not a test role — lower fit")
    if TOSCA_RE.search(title) and re.search(r"\b(sap|s/4)\b", title, re.I):
        score += 15
        reasons.append("Tosca + SAP in the title")
    return score, reasons


def jaya_fit(row: dict) -> tuple[int, list[str]]:
    title = (row.get("title") or "").lower()
    reasons: list[str] = []
    score = 0
    if "teradata" in title:
        score += 40
        reasons.append("Teradata in the title")
    elif "informatica" in title:
        score += 28
        reasons.append("Informatica title")
    elif "hadoop" in title or "hive" in title:
        score += 24
        reasons.append("Hadoop/Hive title")
    elif "etl" in title or "data engineer" in title:
        score += 12
        reasons.append("ETL / data engineer (adjacent)")
    if re.search(r"\b(tasm|tdwm|vantage|dba|viewpoint)\b", title):
        score += 15
        reasons.append("TASM/TDWM/Vantage/DBA")
    if re.search(r"\b(tester|testing|sdet|qa)\b", title) and "teradata" not in title:
        score -= 20
        reasons.append("QA/testing title — weaker DBA fit")
    return score, reasons


def score_row(row: dict, person: str) -> dict:
    pay, pay_why, salary_note = pay_guess(row)
    easy, easy_why, channel = easy_guess(row)
    fit, fit_why = ravi_fit(row) if person == "ravi" else jaya_fit(row)
    total = pay + easy + fit
    sendable = easy >= 35 and fit >= 20
    return {
        "person": person,
        "id": row.get("id") or "",
        "title": row.get("title") or "",
        "company": row.get("company") or "",
        "location": row.get("location") or row.get("country") or "",
        "url": row.get("url") or "",
        "emails": ";".join(row.get("_emails") or []),
        "channel": channel,
        "salary": salary_note,
        "pay": pay,
        "easy": easy,
        "fit": fit,
        "total": total,
        "sendable": sendable,
        "why": " · ".join(pay_why + easy_why + fit_why),
        "tosca": bool(row.get("_tosca")),
        "tags": row.get("_tags") or "",
    }


def rank_targets(*, min_total: int) -> dict[str, list[dict]]:
    ravi_rows = ravi_harvest(latest_worldwide_csv())
    jaya_rows = jaya_harvest(remote_only=True)
    ravi = [score_row(r, "ravi") for r in ravi_rows]
    jaya = [score_row(r, "jaya") for r in jaya_rows]
    ravi = [r for r in ravi if r["total"] >= min_total]
    jaya = [r for r in jaya if r["total"] >= min_total]
    ravi.sort(key=lambda r: (-r["sendable"], -r["total"], -r["easy"], -r["pay"]))
    jaya.sort(key=lambda r: (-r["sendable"], -r["total"], -r["easy"], -r["pay"]))
    return {"ravi": ravi, "jaya": jaya}


def write_outputs(ranked: dict[str, list[dict]]) -> None:
    fields = [
        "person",
        "total",
        "pay",
        "easy",
        "fit",
        "sendable",
        "title",
        "company",
        "location",
        "salary",
        "emails",
        "channel",
        "why",
        "url",
    ]
    rows = ranked["ravi"] + ranked["jaya"]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "guess": (
            "Easy = recruiter email or Greenhouse/Lever. "
            "High pay = senior/lead + US/UK/EU remote + listed 30 LPA+ / contract. "
            "Ravi only Tosca/SAP QA. Jaya only Teradata/EDW/Informatica/Hadoop."
        ),
        "ravi": ranked["ravi"][:25],
        "jaya": ranked["jaya"][:25],
        "ravi_sendable": sum(1 for r in ranked["ravi"] if r["sendable"]),
        "jaya_sendable": sum(1 for r in ranked["jaya"] if r["sendable"]),
    }
    OUT_JS.write_text("window.PRIORITY = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")


def upsert_by_url(store, row: dict, *, track: str, jd: str, source: str) -> int:
    url = (row.get("url") or "").strip()
    existing = store.find_by_url(url) if url else None
    if existing:
        store.update_job(existing.id, jd_text=jd, title=row.get("title") or existing.title, company=row.get("company") or existing.company)
        return existing.id
    jid = store.add_job(
        title=row.get("title") or "Role",
        company=row.get("company") or "Unknown",
        jd_text=jd,
        url=url,
        location=row.get("location") or "",
        source=source,
    )
    store.update_job(jid, track=track, score=32, status="matched", ctc_unknown=1, skip_reason="")
    return jid


def apply_ravi(targets: list[dict], *, limit: int) -> tuple[int, list[str]]:
    store, classify, ensure_packet, submit, load_profile, load_auto_settings = boot_ravi()
    settings = load_auto_settings()
    profile = load_profile()
    if profile.is_unsubmittable() or not settings.smtp_ready():
        raise SystemExit("Ravi mailbox not ready")
    if "jaya" in (settings.smtp_from or "").lower():
        raise SystemExit("Refusing Ravi priority send from Jaya mailbox")
    already = {addr.lower() for addr in store.emailed_addresses()}
    harvest = {r.get("id"): r for r in ravi_harvest(latest_worldwide_csv())}
    existing = list(csv.DictReader(RAVI_LOG.open(encoding="utf-8-sig", newline=""))) if RAVI_LOG.exists() else []
    sent = 0
    notes: list[str] = []
    for target in targets:
        if sent >= limit:
            break
        if not target["sendable"] and not (target["fit"] >= 32 and target["pay"] >= 18):
            continue
        raw = harvest.get(target["id"])
        if not raw:
            continue
        emails = [e for e in (raw.get("_emails") or []) if e not in already and not any(p in e for p in SKIP_LOCAL)]
        company = (raw.get("company") or "").lower()
        for key, inbox in INBOX_OVERRIDE.items():
            if key in company and inbox not in already and inbox not in emails:
                emails.append(inbox)
        jid = upsert_by_url(store, raw, track="automation", jd=ravi_jd(raw), source="priority_ravi")
        job = store.get_job(jid)
        if not job:
            continue
        if job.status == "applied" and not emails:
            continue
        plan = classify(job.url, job.jd_text, fetch_page=True, company=job.company, guess=bool(raw.get("_tosca")))
        if plan.channel == "email" and plan.email and any(p in plan.email.lower() for p in SKIP_LOCAL):
            if emails:
                plan = replace(plan, channel="email", email=emails[0], email_source="harvest")
            else:
                continue
        if plan.channel != "email" or not plan.email:
            if emails:
                plan = replace(plan, channel="email", email=emails[0], email_source="harvest")
            elif plan.channel in {"greenhouse", "lever"} and plan.can_submit:
                pass
            else:
                continue
        if plan.channel == "email" and plan.email.lower() in already:
            continue
        job = ensure_packet(job)
        detail = submit(job, plan, settings)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.update_job(job.id, status="applied", applied_via=plan.channel, applied_at=now, apply_error="")
        if plan.email:
            already.add(plan.email.lower())
        sent += 1
        line = f"Ravi #{job.id} {target['title'][:62]} -> {plan.email or plan.channel}  [{target['total']}]"
        notes.append(line)
        print(line, flush=True)
        existing.append(
            {
                "id": target["id"],
                "job_id": job.id,
                "title": target["title"],
                "company": target["company"],
                "channel": plan.channel,
                "to": plan.email or plan.channel,
                "tosca": raw.get("_tosca"),
                "detail": detail,
                "url": target["url"],
            }
        )
        time.sleep(SEND_GAP_SEC)
    existing = [r for r in existing if r.get("title")]
    with RAVI_LOG.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["id", "job_id", "title", "company", "channel", "to", "tosca", "detail", "url"]
        )
        writer.writeheader()
        writer.writerows(existing)
    return sent, notes


def apply_jaya(targets: list[dict], *, limit: int) -> tuple[int, list[str]]:
    store, classify, ensure_packet, submit, load_profile, load_auto_settings = boot_jaya()
    settings = load_auto_settings()
    profile = load_profile()
    if "jaya" not in profile.full_name.lower() or not settings.smtp_ready():
        raise SystemExit("Jaya mailbox not ready")
    already = {addr.lower() for addr in store.emailed_addresses()}
    harvest = {r.get("id"): r for r in jaya_harvest(remote_only=True)}
    existing = list(csv.DictReader(JAYA_LOG.open(encoding="utf-8-sig", newline=""))) if JAYA_LOG.exists() else []
    sent = 0
    notes: list[str] = []
    for target in targets:
        if sent >= limit:
            break
        if not target["sendable"] and not (target["fit"] >= 32 and target["pay"] >= 18):
            continue
        raw = harvest.get(target["id"])
        if not raw:
            continue
        emails = [e for e in (raw.get("_emails") or []) if e not in already and not is_bad_email(e)]
        jid = upsert_by_url(store, raw, track="teradata_dba", jd=jaya_jd(raw), source="priority_jaya")
        job = store.get_job(jid)
        if not job:
            continue
        if job.status == "applied" and not emails:
            continue
        plan = classify(job.url, job.jd_text, fetch_page=True, company=job.company, guess=True)
        if plan.channel == "email" and plan.email and is_bad_email(plan.email):
            if emails:
                plan = replace(plan, channel="email", email=emails[0], email_source="harvest")
            else:
                continue
        if plan.channel != "email" or not plan.email:
            if emails:
                plan = replace(plan, channel="email", email=emails[0], email_source="harvest")
            elif plan.channel in {"greenhouse", "lever"} and plan.can_submit:
                pass
            else:
                continue
        if plan.channel == "email" and plan.email.lower() in already:
            continue
        job = ensure_packet(job)
        detail = submit(job, plan, settings)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.update_job(job.id, status="applied", applied_via=plan.channel, applied_at=now, apply_error="")
        if plan.email:
            already.add(plan.email.lower())
        sent += 1
        line = f"Jaya #{job.id} {target['title'][:62]} -> {plan.email or plan.channel}  [{target['total']}]"
        notes.append(line)
        print(line, flush=True)
        existing.append(
            {
                "id": target["id"],
                "job_id": job.id,
                "title": target["title"],
                "company": target["company"],
                "channel": plan.channel,
                "to": plan.email or plan.channel,
                "remote": True,
                "tags": raw.get("_tags") or "",
                "detail": detail,
                "url": target["url"],
            }
        )
        time.sleep(SEND_GAP_SEC)
    existing = [r for r in existing if r.get("title")]
    with JAYA_LOG.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["id", "job_id", "title", "company", "channel", "to", "remote", "tags", "detail", "url"],
        )
        writer.writeheader()
        writer.writerows(existing)
    return sent, notes


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank and apply easy high-pay remote jobs for Ravi and Jaya")
    parser.add_argument("--apply", action="store_true", help="Send mail / ATS for sendable priority rows")
    parser.add_argument("--limit", type=int, default=12, help="Max new sends per person")
    parser.add_argument("--min-total", type=int, default=55)
    args = parser.parse_args()
    ranked = rank_targets(min_total=args.min_total)
    write_outputs(ranked)
    print(f"Ravi candidates {len(ranked['ravi'])} sendable {sum(1 for r in ranked['ravi'] if r['sendable'])}")
    print(f"Jaya candidates {len(ranked['jaya'])} sendable {sum(1 for r in ranked['jaya'] if r['sendable'])}")
    print("Top Ravi:")
    for row in ranked["ravi"][:12]:
        flag = "SEND" if row["sendable"] else "queue"
        print(f"  [{row['total']:3} {flag}] {row['title'][:58]} | {row['company'][:22]} | {row['why'][:90]}")
    print("Top Jaya:")
    for row in ranked["jaya"][:12]:
        flag = "SEND" if row["sendable"] else "queue"
        print(f"  [{row['total']:3} {flag}] {row['title'][:58]} | {row['company'][:22]} | {row['why'][:90]}")
    if not args.apply:
        print(f"Wrote {OUT_CSV} and {OUT_JS}. Re-run with --apply to send.")
        return 0
    ravi_sent, ravi_notes = apply_ravi(ranked["ravi"], limit=args.limit)
    jaya_sent, jaya_notes = apply_jaya(ranked["jaya"], limit=args.limit)
    print(f"Priority apply done. ravi_sent={ravi_sent} jaya_sent={jaya_sent}")
    for line in ravi_notes + jaya_notes:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
