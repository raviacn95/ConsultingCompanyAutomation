"""Harvest Teradata / EDW / Informatica / Hadoop roles into a separate data folder.

Does not write to jobs_worldwide.csv or ravi_remote_apply_log.csv.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "jaya_teradata"
JSONL = OUT / "jobs.jsonl"
CSV_PATH = OUT / "jobs.csv"
SUMMARY = OUT / "summary.json"

sys.path.insert(0, str(ROOT / "scripts"))
import harvest_jobs as h  # noqa: E402

h.DATA = OUT
h.JSONL = JSONL
h.CSV_ALL = CSV_PATH
h.CSV_SAP = OUT / "jobs_matched.csv"
h.SUMMARY = SUMMARY

TERADATA_RE = re.compile(
    r"\b(teradata|tasm|tdwm|dbql|bteq|vantagecloud)\b",
    re.I,
)
VIEWPOINT_RE = re.compile(r"\bteradata viewpoint\b|\bviewpoint ssl\b|\bviewpoint portal\b", re.I)
WEAK_TITLE = re.compile(
    r"\b(conversational designer|servicenow|accountant|sap security|"
    r"manufacturing|knowledge operations|cloud ai|contracts coordinator|"
    r"product designer|sales|recruiter|marketing)\b",
    re.I,
)
TITLE_KEEP = re.compile(
    r"\b(teradata|dba|database admin|informatica|powercenter|iics|"
    r"hadoop|hive|hdfs|dataproc|edw|tasm|tdwm|etl|data engineer|"
    r"data warehouse|sql developer)\b",
    re.I,
)
INFA_RE = re.compile(r"\b(informatica|powercenter)\b", re.I)
HADOOP_RE = re.compile(r"\b(hadoop|hdfs|dataproc)\b", re.I)
HIVE_RE = re.compile(r"\bhive\b", re.I)
EDW_RE = re.compile(r"\b(enterprise data warehouse|\bedw\b|data warehouse dba)\b", re.I)

COUNTRIES = [
    "India",
    "USA",
    "UK",
    "Germany",
    "Canada",
    "Netherlands",
    "Australia",
    "Singapore",
    "Ireland",
    "United Arab Emirates",
]

KEYWORDS = [
    "Teradata DBA",
    "Teradata Administrator",
    "Teradata Vantage",
    "Teradata Database Administration",
    "Teradata EDW",
    "TASM Teradata",
    "TDWM Teradata",
    "Teradata performance tuning",
    "Informatica PowerCenter",
    "Informatica ETL Teradata",
    "Hadoop Administrator",
    "Hive HDFS Administrator",
    "Teradata Hadoop",
    "GCP Dataproc Hadoop",
]


def is_jaya_role(title: str, description: str, search_term: str = "") -> bool:
    del search_term
    title = title or ""
    desc = description or ""
    if WEAK_TITLE.search(title):
        return False
    blob = f"{title} {desc}"
    if TITLE_KEEP.search(title) and (
        TERADATA_RE.search(blob)
        or VIEWPOINT_RE.search(blob)
        or INFA_RE.search(blob)
        or HADOOP_RE.search(blob)
        or HIVE_RE.search(blob)
        or EDW_RE.search(blob)
        or re.search(r"\b(dba|tasm|tdwm|etl|warehouse)\b", blob, re.I)
    ):
        return True
    if TERADATA_RE.search(title) or VIEWPOINT_RE.search(blob):
        return True
    if INFA_RE.search(title) and re.search(r"\b(etl|powercenter|iics|warehouse|teradata)\b", blob, re.I):
        return True
    if HADOOP_RE.search(title) and (HIVE_RE.search(blob) or re.search(r"\badmin", title, re.I)):
        return True
    if re.search(r"\b(dba|database administrator)\b", title, re.I) and TERADATA_RE.search(blob):
        return True
    return False


def role_tags(title: str, description: str) -> list[str]:
    blob = f"{title or ''} {description or ''}".lower()
    tags: list[str] = []
    if TERADATA_RE.search(blob) or "data warehouse" in blob or "edw" in blob or "star schema" in blob:
        tags.append("core_database")
    if re.search(r"\b(tasm|tdwm|dbql|explain plan|skew|spool|ppi|performance tun)", blob):
        tags.append("performance")
    if INFA_RE.search(blob) or re.search(r"\b(etl|autosys|batch job)\b", blob):
        tags.append("etl_informatica")
    if re.search(r"\b(linux|unix|bteq|patch|release management|incident|cab|production support)\b", blob):
        tags.append("infrastructure")
    if re.search(r"\b(cyberark|backup|recovery|access governance|security admin|roles and profiles)\b", blob):
        tags.append("security")
    if HADOOP_RE.search(blob) or HIVE_RE.search(blob) or re.search(r"\b(gcp|gcs|dataproc|stackdriver)\b", blob):
        tags.append("big_data_cloud")
    if re.search(r"\b(jira|servicenow|cherwell|datadog|urbancode|winscp|putty|json payload)\b", blob):
        tags.append("automation_tools")
    return tags or ["core_database"]


def append_filtered(rows: list[dict], seen: set[str]) -> int:
    added = 0
    OUT.mkdir(parents=True, exist_ok=True)
    with JSONL.open("a", encoding="utf-8") as handle:
        for raw in rows:
            title = str(raw.get("title") or "")
            desc = str(raw.get("description") or "")
            term = str(raw.get("search_term") or "")
            if not is_jaya_role(title, desc, term):
                continue
            rec = h.normalize(raw)
            if not rec["title"] or rec["id"] in seen:
                continue
            rec["role_tags"] = ",".join(role_tags(title, desc))
            seen.add(rec["id"])
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    return added


def seed_from_worldwide(seen: set[str]) -> int:
    candidates = [
        ROOT / "data" / "jobs_worldwide.csv",
        ROOT / "data" / "jobs_worldwide.updated.csv",
    ]
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        return 0
    src = max(existing, key=lambda p: p.stat().st_mtime)
    rows = []
    with src.open(encoding="utf-8-sig", newline="") as fh:
        for rec in csv.DictReader(fh):
            if is_jaya_role(rec.get("title") or "", rec.get("description") or "", rec.get("search_term") or ""):
                rec["source"] = rec.get("source") or "worldwide-seed"
                rec["search_term"] = rec.get("search_term") or "seed"
                rows.append(rec)
    return append_filtered(rows, seen)


def export() -> dict:
    recs: list[dict] = []
    if JSONL.exists():
        with JSONL.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    recs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    dedup = {r.get("id"): r for r in recs if r.get("id")}
    ordered = sorted(
        dedup.values(),
        key=lambda r: (r.get("harvested_at") or r.get("date_posted") or "", r.get("id") or ""),
        reverse=True,
    )
    OUT.mkdir(parents=True, exist_ok=True)
    fields = list(h.FIELDS) + ["role_tags"]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ordered)
    remote = 0
    emailed = 0
    tags: dict[str, int] = {}
    for rec in ordered:
        loc = f"{rec.get('location') or ''} {rec.get('is_remote') or ''}".lower()
        if str(rec.get("is_remote") or "").lower() in {"true", "1", "yes"} or "remote" in loc:
            remote += 1
        if rec.get("emails") and str(rec.get("emails")).lower() not in {"nan", "none", ""}:
            emailed += 1
        for tag in (rec.get("role_tags") or "core_database").split(","):
            tags[tag] = tags.get(tag, 0) + 1
    summary = {
        "generated_at": h.utc_now(),
        "unique_jobs": len(ordered),
        "remote_jobs": remote,
        "with_emails": emailed,
        "tags": tags,
        "csv": str(CSV_PATH),
        "jsonl": str(JSONL),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def run_grid(seen: set[str], target: int, wanted: int) -> None:
    searches: list[tuple] = []
    core = KEYWORDS[:8]
    for country in COUNTRIES:
        for term in KEYWORDS:
            searches.append(("indeed", term, country, "", wanted, 0))
    for country in ["India", "USA", "UK", "Germany"]:
        for term in core:
            searches.append(("indeed", term, country, "", wanted, wanted))
            searches.append(("google", term, country, "", min(wanted, 60), 0))
    for country, city in [
        ("India", "Bengaluru"),
        ("India", "Hyderabad"),
        ("India", "Pune"),
        ("India", "Chennai"),
        ("USA", "Dallas"),
        ("USA", "Chicago"),
        ("USA", "Atlanta"),
        ("Germany", "Frankfurt"),
        ("UK", "London"),
    ]:
        for term in ["Teradata DBA", "Informatica PowerCenter", "Hadoop Administrator"]:
            searches.append(("indeed", term, country, city, min(wanted, 80), 0))

    def rank(item):
        site, term, country, loc, _, off = item
        pri = 0 if country in {"India", "USA", "UK", "Germany"} else 1
        core_pri = 0 if "Teradata" in term else 1
        return pri, core_pri, country, term, off

    searches.sort(key=rank)
    start = len(seen)
    for i, (site, term, country, loc, want, off) in enumerate(searches, 1):
        if len(seen) >= target:
            print(f"Reached target {target} at search {i}")
            return
        rows = h.jobspy_search(site, term, country, loc, want, off)
        n = append_filtered(rows, seen)
        print(
            f"  td [{i}/{len(searches)}] {site} {country} {loc or '-'} {term!r} "
            f"raw={len(rows)} +{n}  total={len(seen)}  new={len(seen) - start}",
            flush=True,
        )
        time.sleep(0.3)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=1500)
    parser.add_argument("--wanted", type=int, default=80)
    parser.add_argument("--extra", type=int, default=0, help="Add this many new unique jobs on top of the checkpoint")
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    seen, existing = h.load_seen()
    print(f"Teradata checkpoint: {existing} rows, {len(seen)} unique  dir={OUT}")
    if args.export_only:
        print(json.dumps(export(), indent=2))
        return 0
    seeded = seed_from_worldwide(seen)
    print(f"Seeded {seeded} matching rows from jobs_worldwide.updated.csv")
    target = args.target
    if args.extra:
        target = len(seen) + args.extra
        print(f"Extra harvest: aiming for {target} unique ({args.extra} new)")
    run_grid(seen, target, args.wanted)
    summary = export()
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
