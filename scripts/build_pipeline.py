"""Turn harvested SAP jobs into a sendable high-margin pipeline."""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DASH = ROOT / "dashboard"
SAP_JOBS = DATA / "sap_jobs.csv"
CURATED = DATA / "prospects.json"
OUT_JSON = DATA / "pipeline.json"
OUT_CSV = DATA / "pipeline.csv"
OUT_JS = DASH / "pipeline.js"

JUNK_TITLE = re.compile(
    r"\b(cdl|otr|truck driver|sap driver|werkstudent|praktikum|internship|"
    r"intern\b|trainee|apprentice|working student|studentische)\b",
    re.I,
)
SI_SUB = re.compile(
    r"accenture|deloitte|pwc|ey\b|ernst & young|kpmg|capgemini|infosys|wipro|"
    r"cognizant|hcltech|hcl tech|\btcs\b|tata consultancy|ntt data|genpact|"
    r"epam|yash tech|dxc|fujitsu|globant|bristlecone|sopra steria|tech mahindra|"
    r"ltimindtree|persistent|thoughtworks|endava|cgi\b|bearingpoint|nagarro|"
    r"wavestone|roland berger|mckinsey|bain\b|oliver wyman|kearney|"
    r"maxit|max corporate|talent connect|falconsmart|el fonze|elfonze|"
    r"pumo techno|pyramid global|versafile|birchman|irtish|knowledge artisan|"
    r"raah tech|bv teck|smx\b|ust\b|cpro |gicom|koenig\.|okadis|natuvion|"
    r"asapio|fortis it|passport business|sympacon|msg\b|dyflex|implico|"
    r"tenthpin|abresa|kurzenberg|brightside|birlasoft|alten\b|atos\b|"
    r"devoteam|all for one|clarkston|inwerken|octavia|sourceo|concentrix|"
    r"hudson manpower|themesoft|sonsoft|right search|talan\b|reply\b|"
    r"bechtle|zalaris|valantic|leverx|computek|qtech|datagroup|"
    r"sii deutschland|swan consultancy|ltm limited|logic, inc",
    re.I,
)
STAFF_SUB = re.compile(
    r"recruit|staffing|staffit|talent(s)? gmbh|job board|senior management forum|"
    r"consulting gmbh|it-services gmbh|contracting|headhunt",
    re.I,
)

PRICE = {
    "India": ("₹3.8L/mo named functional · ₹5.5L/mo architect, 90-day SOW", "40–50%"),
    "Germany": ("€1,050/day Arbeitspaket, 3-month minimum", "25–35% DE / 45%+ India CET"),
    "UK": ("£850/day named S/4 workstream, 3-month minimum", "25–40%"),
    "USA": ("$1,100/day named S/4 workstream, 90-day SOW", "25–40%"),
    "Australia": ("A$1,200/day named S/4 workstream, 3-month minimum", "25–40%"),
    "Netherlands": ("€1,050/day Arbeitspaket, 3-month minimum", "25–35%"),
    "Switzerland": ("CHF 1,250/day Arbeitspaket, 3-month minimum", "25–35%"),
    "Argentina": ("USD 650/day remote named consultant, 90-day SOW", "35–45%"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def clean(value: str) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none", "nat", "null"} else text


def primary_country(countries: list[str]) -> str:
    order = ["India", "Germany", "UK", "USA", "Australia", "Netherlands", "Switzerland", "Argentina"]
    counts: dict[str, int] = {}
    for item in countries:
        counts[item] = counts.get(item, 0) + 1
    for name in order:
        if counts.get(name):
            return name
    return max(counts, key=counts.get) if counts else ""


def classify(company: str, titles: list[str]) -> tuple[str, str]:
    blob = " | ".join(titles)
    if titles and sum(1 for t in titles if JUNK_TITLE.search(t)) / len(titles) >= 0.5:
        return "skip", "junk"
    if SI_SUB.search(company) or SI_SUB.search(blob[:400]):
        return "later", "si_staffing"
    if STAFF_SUB.search(company):
        return "skip", "si_staffing"
    if re.search(r"\b(inhouse|in-house|internal)\b", blob, re.I):
        return "send", "end_client"
    return "send", "end_client"


def linkedin_people(company: str) -> str:
    q = f'{company} SAP (program OR "IT head" OR architect OR "application owner")'
    return "https://www.linkedin.com/search/results/people/?keywords=" + quote_plus(q)


def pitch(company: str, country: str, title: str, n: int, modules: str, price: str) -> dict:
    mods = modules.replace(",", "/") or "S/4"
    de = country == "Germany"
    if de:
        note = (
            f"{company} hat {n} offene SAP-Stellen (u. a. {title}). Das ist ein Workstream, "
            f"kein Recruiter-Problem. Ich stelle eine benannte Person auf ein 90-Tage-Arbeitspaket "
            f"zu {price.split(',')[0]}. Kein CV vorher. 15 Minuten diese Woche. — [Your name], SAP Desk"
        )
        subject = f"{company} — {n} offene SAP-Sitze, Arbeitspaket statt CV-Paket"
        body = (
            f"Hallo,\n\n"
            f"{company} sucht aktuell {n} SAP-Profile, darunter: {title}.\n\n"
            f"Angebot: eine benannte Beraterin/ein benannter Berater, {price}. "
            f"Module im Signal: {mods}. 10-Tage-Ersatz. CVs erst nach SOW.\n\n"
            f"Welcher Stream ist rot?\n\n"
            f"Mit freundlichen Grüßen\n[Your name] | SAP Desk\n[Mobile]"
        )
        f2 = f"Die {n} SAP-Sitze sind noch offen. {price.split(',')[0]} steht. 15 Min — ja oder nein?"
        f3 = f"Ich schließe die Akte zu {company}. Ein Wort mit dem Modul, falls es kippt."
        call = f"Blunt: {n} offene SAP-Rollen heißen, der Stream rutscht. {price.split(',')[0]}. Welches Modul ist rot?"
    else:
        note = (
            f"{company} has {n} open SAP seats (including {title}). That is a late workstream, "
            f"not a recruiting campaign. Named consultant on a 90-day SOW at {price.split(',')[0]}. "
            f"No CV until we agree the SOW. 15 min this week. — [Your name], SAP Desk"
        )
        subject = f"{company} — {n} open SAP seats, 90-day SOW not a CV pack"
        body = (
            f"Hello,\n\n"
            f"{company} is hiring {n} SAP roles right now, including: {title}.\n\n"
            f"Offer: one named consultant, {price}. Signal modules: {mods}. "
            f"10-day replacement. I will not attach CVs to this mail.\n\n"
            f"Which workstream is actually red?\n\n"
            f"Regards,\n[Your name] | SAP Desk\n[Mobile]"
        )
        f2 = f"Those {n} SAP seats are still open. {price.split(',')[0]} is the number. Thursday 15 min — yes or no?"
        f3 = f"Closing {company}. Reply with the module if a stream goes red."
        call = f"Blunt: {n} open SAP roles means the workstream is late. {price.split(',')[0]}. Which module is red?"
    return {
        "linkedin_note": note,
        "email_subject": subject,
        "email_body": body,
        "followup_2": f2,
        "followup_3": f3,
        "call_opener": call,
    }


def load_jobs() -> list[dict]:
    if not SAP_JOBS.exists():
        raise SystemExit("Missing data/sap_jobs.csv — run scripts/harvest_jobs.py first")
    with SAP_JOBS.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def overlaps_curated(key: str, curated_keys: set[str]) -> bool:
    if key in curated_keys:
        return True
    for item in curated_keys:
        if len(key) >= 5 and (key in item or item in key):
            return True
    return False


def load_curated_names() -> set[str]:
    if not CURATED.exists():
        return set()
    bundle = json.loads(CURATED.read_text(encoding="utf-8"))
    names = set()
    for row in bundle.get("prospects") or []:
        names.add(re.sub(r"[^a-z0-9]+", "", (row.get("company") or "").lower()))
    return names


def rollup(jobs: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for job in jobs:
        title = clean(job.get("title"))
        company = clean(job.get("company"))
        if not company or not title:
            continue
        if JUNK_TITLE.search(title):
            continue
        key = re.sub(r"[^a-z0-9]+", "", company.lower())
        if not key:
            continue
        bucket = buckets.setdefault(
            key,
            {
                "company": company,
                "titles": [],
                "urls": [],
                "countries": [],
                "modules": set(),
                "max_score": 0,
                "emails": set(),
            },
        )
        bucket["titles"].append(title)
        url = clean(job.get("url"))
        if url:
            bucket["urls"].append(url)
        country = clean(job.get("country"))
        if country:
            bucket["countries"].append(country)
        for mod in clean(job.get("sap_modules")).split(","):
            if mod:
                bucket["modules"].add(mod)
        try:
            bucket["max_score"] = max(bucket["max_score"], int(job.get("sap_score") or 0))
        except ValueError:
            pass
        email = clean(job.get("emails"))
        if email and "@" in email:
            bucket["emails"].add(email.split(",")[0].strip())
    return list(buckets.values())


def to_prospect(idx: int, bucket: dict, curated_keys: set[str]) -> dict | None:
    company = bucket["company"]
    key = re.sub(r"[^a-z0-9]+", "", company.lower())
    if overlaps_curated(key, curated_keys):
        return None
    n = len(bucket["titles"])
    if n < 2:
        return None
    country = primary_country(bucket["countries"])
    margin, buyer = classify(company, bucket["titles"])
    if buyer == "junk":
        return None
    if margin == "send" and n < 3:
        margin = "later"
    if margin == "send" and country not in PRICE:
        margin = "later"
    if margin == "send" and n >= 5:
        heat = "hot"
    elif margin == "send":
        heat = "warm"
    else:
        heat = "warm"
    price, gross = PRICE.get(country, ("Rate card on a 90-day SOW — no perm fee", "ask"))
    modules = ",".join(sorted(bucket["modules"])[:8])
    title = bucket["titles"][0]
    copy = pitch(company, country, title, n, modules, price)
    emails = sorted(bucket["emails"])
    contacts = [{"name": "Hiring contact from posting", "email": emails[0]}] if emails else []
    pid = f"H{idx:03d}"
    return {
        "id": pid,
        "origin": "harvest",
        "heat": heat,
        "status": "todo",
        "margin": margin,
        "company": company,
        "country": country or "Unknown",
        "city": country or "",
        "buyer_type": buyer,
        "industry": "SAP hiring signal",
        "job_count": n,
        "signal": f"{n} open SAP-tagged roles. Example: {title}",
        "offer": "Named 90-day workstream on your SOW. CVs after commercial yes.",
        "talk_to": "SAP programme / IT / application owner — not TA",
        "price_anchor": price,
        "gross": gross,
        "sap_modules": modules,
        "product": "arbeitspaket" if country in {"Germany", "Netherlands", "Switzerland"} else "workstream_in",
        "deadline": None,
        "contacts": contacts,
        "urls": {
            "job": bucket["urls"][0] if bucket["urls"] else "",
            "linkedin_people": linkedin_people(company),
        },
        **copy,
    }


def write_csv(rows: list[dict]) -> None:
    fields = [
        "id", "origin", "margin", "heat", "company", "country", "buyer_type",
        "job_count", "price_anchor", "sap_modules", "signal", "email_subject",
        "linkedin_note", "job_url", "linkedin_people",
    ]
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "id": row["id"],
                    "origin": row["origin"],
                    "margin": row["margin"],
                    "heat": row["heat"],
                    "company": row["company"],
                    "country": row["country"],
                    "buyer_type": row["buyer_type"],
                    "job_count": row.get("job_count") or "",
                    "price_anchor": row.get("price_anchor") or "",
                    "sap_modules": row.get("sap_modules") or "",
                    "signal": row.get("signal") or "",
                    "email_subject": row.get("email_subject") or "",
                    "linkedin_note": row.get("linkedin_note") or "",
                    "job_url": (row.get("urls") or {}).get("job") or "",
                    "linkedin_people": (row.get("urls") or {}).get("linkedin_people") or "",
                }
            )


def main() -> None:
    jobs = load_jobs()
    curated_keys = load_curated_names()
    people = rollup(jobs)
    prospects = []
    idx = 1
    for bucket in sorted(people, key=lambda b: -len(b["titles"])):
        row = to_prospect(idx, bucket, curated_keys)
        if not row:
            continue
        prospects.append(row)
        idx += 1
    # Dashboard: send + later only, cap skip noise
    desk = [p for p in prospects if p["margin"] in {"send", "later"}]
    payload = {
        "generated_at": utc_now(),
        "from_jobs": len(jobs),
        "companies_rolled": len(people),
        "pipeline": len(prospects),
        "send": sum(1 for p in desk if p["margin"] == "send"),
        "later": sum(1 for p in desk if p["margin"] == "later"),
        "prospects": desk,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    DASH.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_JS.write_text("window.PIPELINE = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")
    write_csv(desk)
    print(f"Jobs in: {len(jobs)}")
    print(f"Companies rolled: {len(people)}")
    print(f"Pipeline send: {payload['send']}  later: {payload['later']}")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JS}")


if __name__ == "__main__":
    main()
