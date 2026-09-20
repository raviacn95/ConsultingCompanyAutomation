"""Refresh the SAP Desk pipeline: curated prospects + public job signals."""

from __future__ import annotations

import csv
import json
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DASHBOARD = ROOT / "dashboard"
CURATED = DATA / "prospects.json"
UA = {"User-Agent": "SAPDeskLeadFinder/1.0 (agency research; +local)"}


def load_curated() -> dict:
    return json.loads(CURATED.read_text(encoding="utf-8"))


def fetch_json(url: str, timeout: int = 25):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def arbeitnow_sap() -> list[dict]:
    try:
        payload = fetch_json("https://www.arbeitnow.com/api/job-board-api")
    except Exception as exc:
        return [{"error": str(exc)}]
    jobs = payload.get("data") or []
    hits = []
    for job in jobs:
        blob = " ".join(
            [
                str(job.get("title") or ""),
                str(job.get("company_name") or job.get("company") or ""),
                str(job.get("description") or "")[:400],
                " ".join(job.get("tags") or []),
            ]
        ).lower()
        if "sap" not in blob and "s/4" not in blob and "s4hana" not in blob:
            continue
        hits.append(
            {
                "source": "arbeitnow",
                "title": job.get("title"),
                "company": job.get("company_name") or job.get("company"),
                "location": job.get("location"),
                "url": job.get("url"),
                "created_at": job.get("created_at"),
            }
        )
    return hits


def remotive_sap() -> list[dict]:
    try:
        payload = fetch_json("https://remotive.com/api/remote-jobs?search=SAP")
    except Exception as exc:
        return [{"error": str(exc)}]
    hits = []
    for job in payload.get("jobs") or []:
        title = (job.get("title") or "").lower()
        if "sap" not in title and "s/4" not in title:
            continue
        hits.append(
            {
                "source": "remotive",
                "title": job.get("title"),
                "company": job.get("company_name"),
                "location": job.get("candidate_required_location"),
                "url": job.get("url"),
                "created_at": job.get("publication_date"),
            }
        )
    return hits[:40]


def write_csv(prospects: list[dict], path: Path) -> None:
    fields = [
        "id",
        "heat",
        "status",
        "company",
        "country",
        "city",
        "margin",
        "buyer_type",
        "product",
        "industry",
        "talk_to",
        "price_anchor",
        "gross",
        "signal",
        "offer",
        "deadline",
        "primary_email",
        "linkedin_people",
        "email_subject",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in prospects:
            emails = [c.get("email") for c in row.get("contacts") or [] if c.get("email")]
            urls = row.get("urls") or {}
            writer.writerow(
                {
                    "id": row.get("id"),
                    "heat": row.get("heat"),
                    "status": row.get("status"),
                    "company": row.get("company"),
                    "country": row.get("country"),
                    "city": row.get("city"),
                    "margin": row.get("margin") or "",
                    "buyer_type": row.get("buyer_type"),
                    "product": row.get("product") or "",
                    "industry": row.get("industry"),
                    "talk_to": row.get("talk_to") or "",
                    "price_anchor": row.get("price_anchor") or "",
                    "gross": row.get("gross") or "",
                    "signal": row.get("signal"),
                    "offer": row.get("offer"),
                    "deadline": row.get("deadline") or "",
                    "primary_email": emails[0] if emails else "",
                    "linkedin_people": urls.get("linkedin_people") or urls.get("job") or "",
                    "email_subject": row.get("email_subject") or "",
                }
            )


def write_dashboard_js(bundle: dict, live: dict, harvest: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": date.today().isoformat(),
        "agency": bundle.get("agency"),
        "strategy": bundle.get("strategy"),
        "prospects": bundle.get("prospects"),
        "live_public_jobs": live,
        "harvest": harvest,
    }
    path.write_text(
        "window.SAP_DESK = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n",
        encoding="utf-8",
    )


def main() -> None:
    DATA.mkdir(parents=True, exist_ok=True)
    bundle = load_curated()
    live = {"arbeitnow": arbeitnow_sap(), "remotive": remotive_sap()}
    harvest = {}
    summary_path = DATA / "jobs_summary.json"
    if summary_path.exists():
        harvest = json.loads(summary_path.read_text(encoding="utf-8"))
    (DATA / "live_jobs.json").write_text(json.dumps({"signals": live, "harvest": harvest}, indent=2), encoding="utf-8")
    write_csv(bundle["prospects"], DATA / "prospects.csv")
    write_dashboard_js(bundle, live, harvest, DASHBOARD / "prospects.js")

    send_now = [p for p in bundle["prospects"] if p.get("margin") == "send"]
    print(f"Curated prospects: {len(bundle['prospects'])}")
    print(f"High-margin send now: {len(send_now)}")
    print(f"Arbeitnow SAP hits: {len(live['arbeitnow'])}")
    print(f"Remotive SAP hits: {len(live['remotive'])}")
    print(f"Wrote data/prospects.csv, data/live_jobs.json, dashboard/prospects.js")
    if harvest:
        print(f"Worldwide harvest: {harvest.get('unique_jobs')} jobs · SAP-tagged {harvest.get('sap_jobs')}")
        print(f"  {harvest.get('csv_all')}")
    pipe_path = DATA / "pipeline.json"
    if pipe_path.exists():
        pipe = json.loads(pipe_path.read_text(encoding="utf-8"))
        print(f"Harvest pipeline: send {pipe.get('send')} · later {pipe.get('later')} · {pipe.get('csv') or 'data/pipeline.csv'}")
    print("\nSend these (economic buyer, priced SOW):")
    for row in send_now:
        print(f"  {row['id']}  {row['company']}  [{row.get('margin','')}]")


if __name__ == "__main__":
    main()
