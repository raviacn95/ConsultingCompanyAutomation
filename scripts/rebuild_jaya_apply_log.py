"""Rebuild data/jaya_teradata/apply_log.csv from Jaya's job-apply-kit mail events."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

KIT = Path(r"C:\Users\ravir\job-apply-kit")
LOG = Path(r"C:\Users\ravir\ConsultingCompanyAutomation\data\jaya_teradata\apply_log.csv")
CSV = Path(r"C:\Users\ravir\ConsultingCompanyAutomation\data\jaya_teradata\jobs.csv")

sys.path.insert(0, str(KIT))
from jobkit.paths import set_active_user

set_active_user("jaya")
from jobkit import store


def main() -> None:
    jobs_by_url = {}
    if CSV.exists():
        with CSV.open(encoding="utf-8-sig", newline="") as fh:
            for row in csv.DictReader(fh):
                jobs_by_url[(row.get("url") or "").strip()] = row
    rows = []
    for event in store.list_mail_events():
        if event.direction != "sent":
            continue
        job = store.get_job(event.job_id) if event.job_id else None
        if not job or job.source != "harvest_teradata":
            continue
        harvest = jobs_by_url.get((job.url if job else "") or "", {})
        rows.append(
            {
                "id": harvest.get("id") or "",
                "job_id": event.job_id or "",
                "title": (job.title if job else "") or event.subject or "",
                "company": job.company if job else "",
                "channel": "email",
                "to": event.to_addr,
                "remote": harvest.get("is_remote") or "",
                "tags": harvest.get("role_tags") or "",
                "detail": f"Emailed {event.to_addr}",
                "url": job.url if job else "",
            }
        )
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["id", "job_id", "title", "company", "channel", "to", "remote", "tags", "detail", "url"],
        )
        writer.writeheader()
        writer.writerows(rows)
    print("rebuilt", len(rows), "sent rows")


if __name__ == "__main__":
    main()
