"""Send Ravi applications to remote Tosca jobs whose public apply inboxes were found after harvest."""

from __future__ import annotations

import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_remote_ravi import boot_jobkit

ROOT = Path(__file__).resolve().parents[1]
LOG_PATH = ROOT / "data" / "ravi_remote_apply_log.csv"

EXTRAS = [
    ("https://in.indeed.com/viewjob?jk=5b08ebe986afdc9c", "team@testdel.com"),
    ("https://www.indeed.com/viewjob?jk=a861c4c8700df094", "jobs@anaxontech.com"),
    ("https://in.indeed.com/viewjob?jk=a5cedc16d5112d4f", "nvinod@thoughtframeworks.com"),
    ("https://de.indeed.com/viewjob?jk=4019479a47d67d14", "kontakt@ghcsolutions.de"),
]


def main() -> int:
    store, classify, ensure_packet, submit, _load_profile, load_auto_settings = boot_jobkit()
    settings = load_auto_settings()
    already = {addr.lower() for addr in store.emailed_addresses()}
    rows = list(csv.DictReader(LOG_PATH.open(encoding="utf-8"))) if LOG_PATH.exists() else []
    sent = 0
    for url, email in EXTRAS:
        job = store.find_by_url(url)
        print(f"{url[-24:]} job={job.id if job else None} status={job.status if job else None}")
        if not job or job.status == "applied":
            continue
        if email.lower() in already:
            print(f"  skip already emailed {email}")
            continue
        marker = f"Please email your CV / resume and application to {email}."
        if marker.lower() not in (job.jd_text or "").lower():
            store.update_job(
                job.id,
                jd_text=f"{job.jd_text}\n\n{marker}",
                track="automation",
                score=30,
                status="matched",
                skip_reason="",
            )
            job = store.get_job(job.id) or job
        plan = classify(job.url, job.jd_text, fetch_page=False, company=job.company, guess=False)
        print(f"  plan {plan.channel} {plan.email} {plan.reason}")
        if plan.channel != "email" or not plan.can_submit:
            continue
        job = ensure_packet(job)
        detail = submit(job, plan, settings)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store.update_job(job.id, status="applied", applied_via="email", applied_at=now, apply_error="")
        already.add(email.lower())
        rows.append(
            {
                "id": "tosca-extra",
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "channel": "email",
                "to": plan.email,
                "tosca": True,
                "detail": detail,
                "url": url,
            }
        )
        sent += 1
        print(f"APPLIED {job.title[:60]} -> {plan.email}")
        time.sleep(2.5)
    fieldnames = ["id", "job_id", "title", "company", "channel", "to", "tosca", "detail", "url"]
    with LOG_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"extra sent={sent} total_log={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
