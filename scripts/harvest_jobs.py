"""Worldwide job harvest: public APIs + Indeed/Google/Glassdoor/Bayt.

Resumable. Target: >= 10,000 unique postings. SAP-first, then ERP/IT fill.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DASH = ROOT / "dashboard"
JSONL = DATA / "jobs.jsonl"
CSV_ALL = DATA / "jobs_worldwide.csv"
CSV_SAP = DATA / "sap_jobs.csv"
SUMMARY = DATA / "jobs_summary.json"
UA = "SAPDeskHarvester/2.0 (research aggregator; +local)"

SAP_RE = re.compile(
    r"(?<![a-z0-9])(sap|s/?4hana|s4hana|s/4|abap|fico|successfactors|ariba|"
    r"concur|fiori|btp|ewm|s/4 hana|tosca|tricentis)(?![a-z0-9])",
    re.I,
)
TOSCA_RE = re.compile(r"\b(tosca|tricentis)\b", re.I)
SAP_AUTO_RE = re.compile(
    r"(sap.{0,48}((test|process)\s*)?automation)|(((test|process)\s*)?automation.{0,48}sap)",
    re.I,
)
MODULE_RE = re.compile(
    r"\b(mm|sd|pp|fi/?co|fico|ewm|wm|qm|pm|hr|hcm|basis|bw|bpc|mdg|tm|pp-?ds|"
    r"abap|fiori|btp|cpi|ariba|concur|is-?u|successfactors|ewm|otc|ptp|"
    r"tosca|tricentis|playwright|selenium)\b",
    re.I,
)

INDEED_COUNTRIES = [
    "India", "Germany", "USA", "UK", "Netherlands", "Canada", "Australia",
    "Switzerland", "Austria", "Belgium", "France", "Poland", "Singapore",
    "United Arab Emirates", "Ireland", "Sweden", "Italy", "Spain", "Brazil",
    "Mexico", "South Africa", "Philippines", "Malaysia", "Czech Republic",
    "Romania", "Denmark", "Finland", "Norway", "New Zealand", "Saudi Arabia",
    "Portugal", "Hungary", "Luxembourg", "Japan", "South Korea", "Thailand",
    "Vietnam", "Indonesia", "Argentina", "Chile", "Colombia", "Egypt",
    "Greece", "Turkey", "Israel", "Pakistan", "Qatar", "Bahrain",
    "Slovakia", "Bulgaria",
]

KEYWORDS = [
    "SAP",
    "SAP consultant",
    "S/4HANA",
    "ABAP",
    "SAP FICO",
    "SAP MM",
    "SAP SD",
    "SuccessFactors",
]

AUTO_KEYWORDS = [
    "Tosca",
    "Tricentis Tosca",
    "Tricentis",
    "SAP Automation",
    "SAP Test Automation",
    "SAP Tosca",
    "Tosca Automation",
    "Test Automation",
    "QA Automation",
    "Automation",
]

AUTO_COUNTRIES = [
    "India", "Germany", "USA", "UK", "Netherlands", "Canada", "Australia",
    "Switzerland", "Austria", "Poland", "Singapore", "Ireland", "France",
    "Belgium", "Sweden", "Czech Republic", "Romania", "Hungary", "UAE",
    "Philippines", "Malaysia", "South Africa", "Brazil", "Mexico",
]

CITY_FILL = [
    ("India", "Bengaluru"), ("India", "Hyderabad"), ("India", "Pune"),
    ("India", "Mumbai"), ("India", "Chennai"), ("India", "Gurgaon"),
    ("India", "Noida"), ("India", "Kolkata"), ("India", "Ahmedabad"),
    ("Germany", "Berlin"), ("Germany", "Munich"), ("Germany", "Hamburg"),
    ("Germany", "Frankfurt"), ("Germany", "Stuttgart"), ("Germany", "Cologne"),
    ("USA", "New York"), ("USA", "Chicago"), ("USA", "Dallas"),
    ("USA", "Atlanta"), ("USA", "Houston"), ("USA", "Austin"),
    ("UK", "London"), ("UK", "Manchester"),
    ("Netherlands", "Amsterdam"), ("Switzerland", "Zurich"),
    ("UAE", "Dubai"),
]

GREENHOUSE = [
    "sap", "accenture", "deloitte", "capgemini", "ibm", "nagarro", "siemens",
    "bosch", "airbus", "stripe", "shopify", "datadog", "cloudflare", "okta",
    "twilio", "snowflake", "databricks", "hashicorp", "gitlab", "elastic",
    "mongodb", "atlassian", "asana", "notion", "figma", "airbnb", "uber",
    "lyft", "doordash", "pinterest", "reddit", "discord", "dropbox", "box",
    "docusign", "zendesk", "hubspot", "salesforce", "servicenow", "workday",
    "intuit", "paypal", "square", "affirm", "robinhood", "coinbase",
    "anduril", "scaleai", "anthropic", "openai", "nvidia", "amd", "intel",
    "qualcomm", "arm", "broadcom", "appliedmaterials", "lamresearch",
    "asml", "infineon", "nxp", "stmicroelectronics", "renesas", "on-semi",
    "caterpillar", "john-deere", "ge", "gehealthcare", "honeywell", "3m",
    "pfizer", "novartis", "roche", "gsk", "astrazeneca", "sanofi", "bayer",
    "basf", "dow", "dupont", "lyondellbasell", "airliquide", "linde",
    "unilever", "nestle", "pepsico", "cocacola", "ab-inbev", "heineken",
    "adidas", "nike", "lvmh", "kering", "inditex", "h-m",
    "maersk", "dhl", "fedex", "ups", "dbschenker", "kuehnenagel",
    "siemens-energy", "vestas", "orsted", "enel", "iberdrola", "engie",
    "bp", "shell", "totalenergies", "equinor", "conocophillips",
    "jpmorganchase", "goldmansachs", "morganstanley", "blackrock",
    "vanguard", "fidelity", "capitalone", "amex", "visa", "mastercard",
    "mckinsey", "bcg", "bain", "kearney", "oliverwyman", "rolandberger",
    "bearingpoint", "wavestone", "cgi", "nttdata", "infosys", "wipro",
    "cognizant", "hcltech", "techmahindra", "ltimindtree", "persistent",
    "thoughtworks", "epam", "globant", "endava", "tietoevry", "capgemini-invent",
]

LEVER = [
    "netflix", "spotify", "plaid", "brex", "rippling", "ramp", "mercury",
    "notion", "figma", "vercel", "linear", "retool", "airtable", "canva",
    "grammarly", "loom", "calendly", "intercom", "mixpanel", "amplitude",
    "segment", "twilio", "sendgrid", "mailchimp", "confluent", "databricks",
    "palantir", "anduril", "shieldai", "samsara", "rivian", "lucidmotors",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def job_id(url: str, title: str, company: str) -> str:
    raw = (url or "").strip().lower() or f"{title}|{company}".lower()
    return hashlib.sha1(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def sap_score(title: str, description: str) -> tuple[int, str, bool]:
    blob = f"{title or ''} {description or ''}"
    hits = SAP_RE.findall(blob)
    modules = sorted({m.lower() for m in MODULE_RE.findall(blob)})
    score = len(hits) + (2 if SAP_RE.search(title or "") else 0)
    if TOSCA_RE.search(blob):
        score += 3
        if "tosca" not in modules:
            modules.append("tosca")
    if SAP_AUTO_RE.search(blob):
        score += 2
        if "automation" not in modules:
            modules.append("automation")
    is_flag = score > 0 or bool(TOSCA_RE.search(blob)) or bool(SAP_AUTO_RE.search(blob))
    return score, ",".join(modules[:8]), is_flag


def normalize(row: dict) -> dict:
    title = str(row.get("title") or "").strip()
    company = str(row.get("company") or "").strip()
    url = str(row.get("url") or row.get("job_url") or "").strip()
    desc = re.sub(r"\s+", " ", str(row.get("description") or ""))[:400]
    score, modules, is_sap = sap_score(title, desc)
    location = str(row.get("location") or "").strip()
    return {
        "id": job_id(url, title, company),
        "source": row.get("source") or row.get("site") or "",
        "site": row.get("site") or row.get("source") or "",
        "title": title,
        "company": company,
        "location": location,
        "country": str(row.get("country") or "").strip(),
        "city": str(row.get("city") or "").strip(),
        "job_type": str(row.get("job_type") or "").strip(),
        "is_remote": str(row.get("is_remote") or ""),
        "date_posted": str(row.get("date_posted") or "")[:32],
        "salary": str(row.get("salary") or "").strip(),
        "url": url,
        "description": desc,
        "emails": str(row.get("emails") or "").strip(),
        "sap_score": score,
        "sap_modules": modules,
        "is_sap": "yes" if is_sap else "no",
        "search_term": str(row.get("search_term") or ""),
        "harvested_at": row.get("harvested_at") or utc_now(),
    }


def load_seen() -> tuple[set[str], int]:
    seen: set[str] = set()
    if not JSONL.exists():
        return seen, 0
    count = 0
    with JSONL.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen.add(rec.get("id") or rec.get("url") or "")
            count += 1
    seen.discard("")
    return seen, count


def append_rows(rows: list[dict], seen: set[str]) -> int:
    added = 0
    DATA.mkdir(parents=True, exist_ok=True)
    with JSONL.open("a", encoding="utf-8") as handle:
        for raw in rows:
            rec = normalize(raw)
            if not rec["title"] or rec["id"] in seen:
                continue
            seen.add(rec["id"])
            handle.write(json.dumps(rec, ensure_ascii=False) + "\n")
            added += 1
    return added


def fetch_json(url: str, timeout: int = 25, headers: dict | None = None):
    hdrs = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def source_jobicy() -> list[dict]:
    out = []
    tags = ["sap", "erp", "consultant", "finance", "software"]
    geos = ["", "usa", "europe", "apac", "anywhere"]
    for tag in tags:
        for geo in geos:
            qs = urllib.parse.urlencode({k: v for k, v in {"count": 200, "tag": tag, "geo": geo}.items() if v})
            try:
                payload = fetch_json(f"https://jobicy.com/api/v2/remote-jobs?{qs}")
            except Exception:
                continue
            for job in payload.get("jobs") or []:
                out.append({
                    "source": "jobicy", "site": "jobicy",
                    "title": job.get("jobTitle"), "company": job.get("companyName"),
                    "location": job.get("jobGeo"), "url": job.get("url") or job.get("jobUrl"),
                    "description": job.get("jobExcerpt") or job.get("jobDescription"),
                    "job_type": job.get("jobType"), "search_term": tag,
                    "country": job.get("jobGeo"),
                })
    return out


def source_remotive() -> list[dict]:
    out = []
    for q in ["SAP", "ERP", "consultant", "software"]:
        try:
            payload = fetch_json(f"https://remotive.com/api/remote-jobs?search={urllib.parse.quote(q)}")
        except Exception:
            continue
        for job in payload.get("jobs") or []:
            out.append({
                "source": "remotive", "site": "remotive",
                "title": job.get("title"), "company": job.get("company_name"),
                "location": job.get("candidate_required_location"),
                "url": job.get("url"), "description": job.get("description"),
                "job_type": job.get("job_type"), "date_posted": job.get("publication_date"),
                "search_term": q,
            })
    return out


def source_remoteok() -> list[dict]:
    try:
        payload = fetch_json("https://remoteok.com/api")
    except Exception:
        return []
    out = []
    for job in payload:
        if not isinstance(job, dict) or not job.get("id") or job.get("legal"):
            continue
        out.append({
            "source": "remoteok", "site": "remoteok",
            "title": job.get("position") or job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "url": job.get("url") or job.get("apply_url"),
            "description": job.get("description"),
            "date_posted": job.get("date"),
            "search_term": "remoteok-feed",
        })
    return out


def source_arbeitnow() -> list[dict]:
    try:
        payload = fetch_json("https://www.arbeitnow.com/api/job-board-api")
    except Exception:
        return []
    out = []
    for job in payload.get("data") or []:
        out.append({
            "source": "arbeitnow", "site": "arbeitnow",
            "title": job.get("title"), "company": job.get("company_name"),
            "location": job.get("location"), "url": job.get("url"),
            "description": job.get("description"),
            "search_term": "arbeitnow-feed", "country": "Germany",
        })
    return out


def source_muse() -> list[dict]:
    out = []
    cats = ["Computer and IT", "Data and Analytics", "Finance", "Project Management"]
    for cat in cats:
        for page in range(1, 16):
            qs = urllib.parse.urlencode({"page": page, "descending": "true", "category": cat})
            try:
                payload = fetch_json(f"https://www.themuse.com/api/public/jobs?{qs}")
            except Exception:
                break
            results = payload.get("results") or []
            if not results:
                break
            for job in results:
                locs = job.get("locations") or []
                loc = locs[0].get("name") if locs else ""
                company = (job.get("company") or {}).get("name")
                out.append({
                    "source": "themuse", "site": "themuse",
                    "title": job.get("name"), "company": company,
                    "location": loc, "url": (job.get("refs") or {}).get("landing_page"),
                    "description": job.get("contents"),
                    "search_term": cat, "date_posted": job.get("publication_date"),
                })
    return out


def source_himalayas() -> list[dict]:
    out = []
    for offset in range(0, 800, 100):
        try:
            payload = fetch_json(f"https://himalayas.app/jobs/api?limit=100&offset={offset}")
        except Exception:
            break
        jobs = payload.get("jobs") or payload if isinstance(payload, list) else payload.get("data") or []
        if not jobs:
            break
        for job in jobs:
            if not isinstance(job, dict):
                continue
            out.append({
                "source": "himalayas", "site": "himalayas",
                "title": job.get("title") or job.get("jobTitle"),
                "company": job.get("companyName") or (job.get("company") or {}).get("name") if isinstance(job.get("company"), dict) else job.get("company"),
                "location": job.get("location") or job.get("timezone"),
                "url": job.get("applicationLink") or job.get("url") or job.get("guid"),
                "description": job.get("description") or job.get("excerpt"),
                "search_term": "himalayas-feed",
            })
    return out


def source_greenhouse() -> list[dict]:
    out = []

    def one(slug: str) -> list[dict]:
        rows = []
        try:
            payload = fetch_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
        except Exception:
            return rows
        for job in payload.get("jobs") or []:
            loc = (job.get("location") or {}).get("name") if isinstance(job.get("location"), dict) else job.get("location")
            rows.append({
                "source": "greenhouse", "site": "greenhouse",
                "title": job.get("title"), "company": slug,
                "location": loc, "url": job.get("absolute_url"),
                "search_term": f"gh:{slug}",
            })
        return rows

    with ThreadPoolExecutor(max_workers=12) as pool:
        futs = [pool.submit(one, slug) for slug in GREENHOUSE]
        for fut in as_completed(futs):
            out.extend(fut.result())
    return out


def source_lever() -> list[dict]:
    out = []

    def one(slug: str) -> list[dict]:
        rows = []
        try:
            payload = fetch_json(f"https://api.lever.co/v0/postings/{slug}?mode=json")
        except Exception:
            return rows
        if not isinstance(payload, list):
            return rows
        for job in payload:
            cats = job.get("categories") or {}
            rows.append({
                "source": "lever", "site": "lever",
                "title": job.get("text"), "company": slug,
                "location": cats.get("location"), "country": cats.get("location"),
                "url": job.get("hostedUrl") or job.get("applyUrl"),
                "description": job.get("descriptionPlain") or "",
                "job_type": cats.get("commitment"),
                "search_term": f"lever:{slug}",
            })
        return rows

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = [pool.submit(one, slug) for slug in LEVER]
        for fut in as_completed(futs):
            out.extend(fut.result())
    return out


def jobspy_search(site: str, term: str, country: str, location: str, wanted: int, offset: int = 0) -> list[dict]:
    from jobspy import scrape_jobs

    kwargs = {
        "site_name": [site],
        "search_term": term,
        "results_wanted": wanted,
        "verbose": 0,
        "offset": offset,
        "description_format": "markdown",
    }
    if location:
        kwargs["location"] = location
    if site in {"indeed", "glassdoor"}:
        kwargs["country_indeed"] = country
    if site == "google":
        where = location or country
        kwargs["google_search_term"] = f"{term} jobs in {where}"
        kwargs["location"] = where
    if site == "bayt":
        kwargs["location"] = location or country
    try:
        df = scrape_jobs(**kwargs)
    except Exception as exc:
        print(f"  ! {site} {country} {term!r} failed: {exc}")
        return []
    if df is None or getattr(df, "empty", True):
        return []
    rows = []
    for rec in df.to_dict(orient="records"):
        emails = rec.get("emails")
        if isinstance(emails, (list, tuple)):
            emails = ",".join(str(x) for x in emails if x)
        salary = ""
        if rec.get("min_amount") or rec.get("max_amount"):
            salary = f"{rec.get('min_amount') or ''}-{rec.get('max_amount') or ''} {rec.get('currency') or ''}".strip()
        rows.append({
            "source": site, "site": rec.get("site") or site,
            "title": rec.get("title"), "company": rec.get("company"),
            "location": rec.get("location"), "country": country,
            "city": location, "url": rec.get("job_url") or rec.get("job_url_direct"),
            "description": rec.get("description"),
            "job_type": rec.get("job_type"),
            "is_remote": rec.get("is_remote"),
            "date_posted": rec.get("date_posted"),
            "salary": salary, "emails": emails or rec.get("emails") or "",
            "search_term": term,
        })
    return rows


def run_apis(seen: set[str]) -> int:
    added = 0
    jobs = [
        ("jobicy", source_jobicy),
        ("remotive", source_remotive),
        ("remoteok", source_remoteok),
        ("arbeitnow", source_arbeitnow),
        ("himalayas", source_himalayas),
        ("themuse", source_muse),
        ("greenhouse", source_greenhouse),
        ("lever", source_lever),
    ]
    print("Phase 1 — public APIs and ATS boards")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = {pool.submit(fn): name for name, fn in jobs}
        for fut in as_completed(futs):
            name = futs[fut]
            try:
                rows = fut.result()
            except Exception as exc:
                print(f"  {name}: error {exc}")
                continue
            n = append_rows(rows, seen)
            added += n
            print(f"  {name}: +{n} unique (raw {len(rows)})  total={len(seen)}")
    return added


def run_jobspy_grid(seen: set[str], target: int, wanted: int) -> None:
    print("Phase 2 — Indeed worldwide (SAP-first keywords)")
    searches = []
    # High-yield first
    for country in INDEED_COUNTRIES:
        for term in KEYWORDS:
            searches.append(("indeed", term, country, "", wanted, 0))
    # Second page for the biggest markets
    for country in ["India", "Germany", "USA", "UK", "Netherlands", "Canada"]:
        for term in KEYWORDS[:4]:
            searches.append(("indeed", term, country, "", wanted, wanted))
    random.shuffle(searches)
    # Keep India/Germany/USA first after shuffle? Better: sort priority
    def rank(item):
        site, term, country, loc, _, off = item
        pri = 0 if country in {"India", "Germany", "USA", "UK"} else 1
        return pri, country, term, off

    searches.sort(key=rank)

    for i, (site, term, country, loc, want, off) in enumerate(searches, 1):
        if len(seen) >= target:
            print(f"Reached target {target} at Indeed search {i}")
            return
        rows = jobspy_search(site, term, country, loc, want, off)
        n = append_rows(rows, seen)
        print(f"  [{i}/{len(searches)}] indeed {country} {term!r} off={off} raw={len(rows)} +{n}  total={len(seen)}")
        time.sleep(0.4)


def run_fill(seen: set[str], target: int, wanted: int) -> None:
    if len(seen) >= target:
        return
    print("Phase 3 — city / Google / Glassdoor / Bayt fill")
    searches = []
    fill_terms = ["SAP", "SAP consultant", "S/4HANA", "ABAP"]
    for country, city in CITY_FILL:
        country_indeed = "United Arab Emirates" if country == "UAE" else country
        for term in fill_terms:
            searches.append(("indeed", term, country_indeed, city, wanted, 0))
    for country in ["India", "Germany", "USA", "UK", "Netherlands", "Canada", "Australia", "Singapore"]:
        for term in ["SAP consultant", "S/4HANA"]:
            searches.append(("google", term, country, "", 80, 0))
    for country in ["USA", "UK", "Germany", "India", "Canada", "Netherlands"]:
        for term in ["SAP", "SAP consultant"]:
            searches.append(("glassdoor", term, country, "", 80, 0))
    for loc in ["United Arab Emirates", "Saudi Arabia", "Qatar"]:
        searches.append(("bayt", "SAP consultant", loc, loc, 80, 0))

    for i, (site, term, country, loc, want, off) in enumerate(searches, 1):
        if len(seen) >= target:
            print(f"Reached target {target} during fill at {i}")
            return
        rows = jobspy_search(site, term, country, loc, want, off)
        n = append_rows(rows, seen)
        print(f"  fill [{i}/{len(searches)}] {site} {country} {loc or '-'} {term!r} raw={len(rows)} +{n}  total={len(seen)}")
        time.sleep(0.35)


def run_automation_grid(seen: set[str], target: int, wanted: int) -> None:
    print("Phase automation — Tosca / Tricentis / SAP test automation")
    searches: list[tuple] = []
    core = ["Tosca", "Tricentis Tosca", "Tricentis", "SAP Automation", "SAP Test Automation", "SAP Tosca"]
    broad = ["Tosca Automation", "Test Automation", "QA Automation", "Automation"]
    for country in AUTO_COUNTRIES:
        for term in core:
            searches.append(("indeed", term, country, "", wanted, 0))
    for country in ["India", "Germany", "USA", "UK", "Netherlands", "Canada", "Australia"]:
        for term in core[:4]:
            searches.append(("indeed", term, country, "", wanted, wanted))
        for term in broad:
            searches.append(("indeed", term, country, "", min(wanted, 120), 0))
        for term in ["Tosca", "SAP Test Automation", "Tricentis Tosca"]:
            searches.append(("google", term, country, "", 80, 0))
    for country, city in CITY_FILL:
        country_indeed = "United Arab Emirates" if country == "UAE" else country
        for term in ["Tosca", "SAP Automation", "Test Automation"]:
            searches.append(("indeed", term, country_indeed, city, min(wanted, 80), 0))

    def rank(item):
        site, term, country, loc, _, off = item
        pri = 0 if country in {"India", "Germany", "USA", "UK"} else 1
        core_pri = 0 if term in core else 1
        return pri, core_pri, country, term, off

    searches.sort(key=rank)
    start = len(seen)
    for i, (site, term, country, loc, want, off) in enumerate(searches, 1):
        if len(seen) >= target:
            print(f"Reached automation target {target} at search {i}")
            return
        rows = jobspy_search(site, term, country, loc, want, off)
        n = append_rows(rows, seen)
        print(
            f"  auto [{i}/{len(searches)}] {site} {country} {loc or '-'} {term!r} "
            f"raw={len(rows)} +{n}  total={len(seen)}  new={len(seen) - start}"
        )
        time.sleep(0.3)
    print(f"Automation pass added {len(seen) - start} unique jobs")


FIELDS = [
    "id", "source", "site", "title", "company", "location", "country", "city",
    "job_type", "is_remote", "date_posted", "salary", "url", "description",
    "emails", "sap_score", "sap_modules", "is_sap", "search_term", "harvested_at",
]


def export_csv() -> dict:
    rows: list[dict] = []
    if JSONL.exists():
        with JSONL.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    def clean_rec(rec: dict) -> dict:
        rec = dict(rec)
        for key in ("company", "title", "location", "country", "city"):
            val = str(rec.get(key) or "").strip()
            rec[key] = "" if val.lower() in {"nan", "none", "nat", "null"} else val
        return rec

    # Newest harvest first so Excel / Power Query refresh shows latest on top
    dedup = {}
    for rec in rows:
        rec = clean_rec(rec)
        dedup[rec.get("id")] = rec
    ordered = sorted(
        dedup.values(),
        key=lambda r: (r.get("harvested_at") or r.get("date_posted") or "", r.get("id") or ""),
        reverse=True,
    )
    DATA.mkdir(parents=True, exist_ok=True)

    def _write_csv(path: Path, records: list[dict]) -> Path:
        try:
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            return path
        except PermissionError:
            alt = path.with_name(path.stem + ".updated.csv")
            with alt.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
            print(f"Excel lock on {path.name}; wrote {alt.name}")
            return alt

    csv_all_path = _write_csv(CSV_ALL, ordered)
    sap_rows = [r for r in ordered if r.get("is_sap") == "yes"]
    companies: dict[str, dict] = {}
    for rec in sap_rows:
        name = (rec.get("company") or "").strip()
        if not name:
            continue
        key = name.lower()
        bucket = companies.setdefault(
            key,
            {
                "company": name,
                "job_count": 0,
                "countries": set(),
                "modules": set(),
                "sample_title": rec.get("title") or "",
                "sample_url": rec.get("url") or "",
                "max_sap_score": 0,
            },
        )
        bucket["job_count"] += 1
        if rec.get("country"):
            bucket["countries"].add(rec["country"])
        for mod in (rec.get("sap_modules") or "").split(","):
            if mod:
                bucket["modules"].add(mod)
        score = int(rec.get("sap_score") or 0)
        if score > bucket["max_sap_score"]:
            bucket["max_sap_score"] = score
            bucket["sample_title"] = rec.get("title") or bucket["sample_title"]
            bucket["sample_url"] = rec.get("url") or bucket["sample_url"]
    company_path = DATA / "sap_companies.csv"
    with company_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["company", "job_count", "countries", "modules", "max_sap_score", "sample_title", "sample_url"],
        )
        writer.writeheader()
        for bucket in sorted(companies.values(), key=lambda x: -x["job_count"]):
            writer.writerow(
                {
                    "company": bucket["company"],
                    "job_count": bucket["job_count"],
                    "countries": ", ".join(sorted(bucket["countries"]))[:120],
                    "modules": ",".join(sorted(bucket["modules"]))[:120],
                    "max_sap_score": bucket["max_sap_score"],
                    "sample_title": bucket["sample_title"],
                    "sample_url": bucket["sample_url"],
                }
            )
    csv_sap_path = _write_csv(CSV_SAP, sap_rows)
    sources: dict[str, int] = {}
    countries: dict[str, int] = {}
    for rec in ordered:
        sources[rec.get("source") or "unknown"] = sources.get(rec.get("source") or "unknown", 0) + 1
        countries[rec.get("country") or rec.get("location") or "unknown"] = countries.get(rec.get("country") or rec.get("location") or "unknown", 0) + 1
    summary = {
        "generated_at": utc_now(),
        "unique_jobs": len(ordered),
        "sap_jobs": len(sap_rows),
        "sources": dict(sorted(sources.items(), key=lambda x: -x[1])[:20]),
        "top_countries": dict(sorted(countries.items(), key=lambda x: -x[1])[:20]),
        "csv_all": str(csv_all_path),
        "csv_sap": str(csv_sap_path),
        "csv_companies": str(DATA / "sap_companies.csv"),
        "sap_companies": len(companies),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    DASH.mkdir(parents=True, exist_ok=True)
    (DASH / "jobs_summary.js").write_text(
        "window.JOBS_SUMMARY = " + json.dumps(summary, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--wanted", type=int, default=200)
    parser.add_argument("--extra", type=int, default=0, help="Add this many new unique jobs on top of the checkpoint")
    parser.add_argument("--focus", choices=["sap", "automation"], default="sap")
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--skip-apis", action="store_true")
    args = parser.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    seen, existing = load_seen()
    print(f"Checkpoint: {existing} rows, {len(seen)} unique ids")
    if args.export_only:
        summary = export_csv()
        print(json.dumps({k: summary[k] for k in ("unique_jobs", "sap_jobs", "sources")}, indent=2))
        return
    target = args.target
    if args.extra:
        target = len(seen) + args.extra
        print(f"Extra harvest: aiming for {target} unique ({args.extra} new)")
    if args.focus == "automation":
        run_automation_grid(seen, target, args.wanted)
    else:
        if len(seen) < target and not args.skip_apis:
            run_apis(seen)
        if len(seen) < target:
            run_jobspy_grid(seen, target, args.wanted)
        if len(seen) < target:
            run_fill(seen, target, args.wanted)
    try:
        summary = export_csv()
    except PermissionError:
        print("CSV is open (Excel). Jobs are in data/jobs.jsonl — close the CSV and re-run --export-only.")
        return
    print("---")
    print(f"Unique jobs: {summary['unique_jobs']}")
    print(f"SAP-tagged:  {summary['sap_jobs']}")
    print(f"Wrote {CSV_ALL}")
    print(f"Wrote {CSV_SAP}")
    if summary["unique_jobs"] < target:
        print(f"WARNING: below target {target}. Re-run to resume.")


if __name__ == "__main__":
    main()
