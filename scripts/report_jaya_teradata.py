"""Build local Markdown reports for Jaya Teradata harvest (used for Notion)."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "jaya_teradata"
JOBS = OUT / "jobs.csv"
SENT = OUT / "apply_log.csv"
QUEUED = OUT / "apply_queued.csv"
REPORTS = OUT / "reports"

CATEGORIES = [
    ("core_database", "Core Database & Data Warehousing"),
    ("performance", "Performance Engineering"),
    ("etl_informatica", "ETL & Informatica"),
    ("infrastructure", "Infrastructure & Operations"),
    ("security", "Security & Governance"),
    ("big_data_cloud", "Big Data & Cloud"),
    ("automation_tools", "Automation & Tools"),
]


def load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def md_table(rows: list[dict], cols: list[tuple[str, str]], limit: int = 25) -> str:
    if not rows:
        return "_None in this slice._"
    lines = ["| " + " | ".join(h for h, _ in cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in rows[:limit]:
        cells = []
        for _, key in cols:
            val = str(row.get(key) or "").replace("|", "/").replace("\n", " ")
            if key == "url" and val:
                val = f"[link]({val})"
            cells.append(val[:80])
        lines.append("| " + " | ".join(cells) + " |")
    extra = len(rows) - limit
    if extra > 0:
        lines.append(f"\n_{extra} more in `{path_name(JOBS)}`._")
    return "\n".join(lines)


def path_name(path: Path) -> str:
    return str(path)


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    jobs = load_csv(JOBS)
    sent = load_csv(SENT)
    queued = load_csv(QUEUED)
    by_tag: dict[str, list[dict]] = defaultdict(list)
    for row in jobs:
        tags = [t.strip() for t in (row.get("role_tags") or "core_database").split(",") if t.strip()]
        for tag in tags:
            by_tag[tag].append(row)
    sent_by_tag: dict[str, list[dict]] = defaultdict(list)
    for row in sent:
        tags = [t.strip() for t in (row.get("tags") or "").split(",") if t.strip()]
        for tag in tags or ["core_database"]:
            sent_by_tag[tag].append(row)

    overview = [
        "# Jaya Gupta — Teradata / EDW harvest",
        "",
        "Separate from Ravi Tosca/SAP applies. Files live under `data/jaya_teradata/`.",
        "",
        f"- Jobs harvested: **{len(jobs)}**",
        f"- Applications emailed: **{len(sent)}** from `jayagupta20252003@gmail.com`",
        f"- Queued (Indeed/ATS, no recruiter email): **{len(queued)}**",
        "- Resume: Jaya Gupta Teradata DBA (job-apply-kit `users/jaya`)",
        "",
        "## Keyword families",
    ]
    for tag, label in CATEGORIES:
        overview.append(f"- {label}: {len(by_tag.get(tag, []))} jobs, {len(sent_by_tag.get(tag, []))} emailed")
    (REPORTS / "overview.md").write_text("\n".join(overview) + "\n", encoding="utf-8")

    sent_md = ["# Applications sent", "", md_table(sent, [("Title", "title"), ("Company", "company"), ("To", "to"), ("Tags", "tags"), ("URL", "url")], 40)]
    (REPORTS / "sent.md").write_text("\n".join(sent_md) + "\n", encoding="utf-8")

    queued_md = ["# Queued for Easy Apply / career form", "", md_table(queued, [("Title", "title"), ("Company", "company"), ("Tags", "tags"), ("Reason", "reason"), ("URL", "url")], 30)]
    (REPORTS / "queued.md").write_text("\n".join(queued_md) + "\n", encoding="utf-8")

    for tag, label in CATEGORIES:
        rows = by_tag.get(tag, [])
        emailed = sent_by_tag.get(tag, [])
        body = [
            f"# {label}",
            "",
            f"Jobs in harvest: **{len(rows)}**. Emailed this run: **{len(emailed)}**.",
            "",
            "## Emailed",
            md_table(emailed, [("Title", "title"), ("Company", "company"), ("To", "to"), ("URL", "url")], 20),
            "",
            "## Harvest sample",
            md_table(rows, [("Title", "title"), ("Company", "company"), ("Location", "location"), ("URL", "url")], 25),
        ]
        slug = tag.replace("_", "-")
        (REPORTS / f"{slug}.md").write_text("\n".join(body) + "\n", encoding="utf-8")
    print("wrote", REPORTS)


if __name__ == "__main__":
    main()
