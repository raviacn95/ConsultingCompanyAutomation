"""Queue high-margin outreach and send verified To: via Gmail."""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTBOX = DATA / "outbox"
DASHBOARD = ROOT / "dashboard"
CURATED = DATA / "prospects.json"
LOG = DATA / "outreach_log.csv"
CAP = OUTBOX / "SAP_Desk_capability.txt"
ENV_PATH = ROOT / ".env"
JOBKIT_ENV = Path(r"C:\Users\ravir\job-apply-kit") / ".env"
PIPE = DATA / "pipeline.json"

SENDER_NAME = "Jaya Gupta"
SENDER_EMAIL = "jayagupta20252003@gmail.com"
SENDER_PHONE = "+91 9620252668"
AGENCY = "SAP Desk"
NOTION_CAPABILITY = "https://www.notion.so/SAP-Desk-capability-rate-card-3d0dfde0aa0c81dba913ddff60a91afe"
NOTION_PROFILE = "https://www.notion.so/fb8dfde0aa0c82e09138813571a86332"

JUNK_LOCAL = re.compile(
    r"^(career|careers|jobs|job|hr|recruiting|recruitment|bewerbung|karriere|talentacquisition|accommodation)",
    re.I,
)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def fill(text: str) -> str:
    t = text or ""
    t = t.replace("[Your name]", SENDER_NAME)
    t = t.replace("[Email]", SENDER_EMAIL)
    t = t.replace("[Mobile]", SENDER_PHONE)
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t.strip()


def with_notion(body: str) -> str:
    t = body.strip()
    if NOTION_CAPABILITY not in t:
        t += (
            f"\n\nCapability (Notion): {NOTION_CAPABILITY}"
            f"\nProfile (Notion): {NOTION_PROFILE}"
        )
    return t


def valid_email(raw: str | None) -> str | None:
    if not raw:
        return None
    addr = str(raw).strip().strip(".,;")
    if addr.lower() in {"nan", "none", "null"}:
        return None
    if addr.startswith(("_", "-", ".")):
        return None
    if not EMAIL_RE.match(addr):
        return None
    local = addr.split("@", 1)[0]
    if JUNK_LOCAL.match(local):
        return None
    return addr


def write_eml(path: Path, to_addrs: list[str], subject: str, body: str, attach: Path | None) -> None:
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    if to_addrs:
        msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg.set_content(body)
    if attach and attach.exists():
        msg.add_attachment(
            attach.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=attach.name,
        )
    path.write_bytes(msg.as_bytes())


def gmail_compose(to_addrs: list[str], subject: str, body: str) -> str:
    return (
        "https://mail.google.com/mail/?view=cm&fs=1&tf=1&authuser="
        + quote(SENDER_EMAIL, safe="")
        + "&to=" + quote(",".join(to_addrs), safe="")
        + "&su=" + quote(subject, safe="")
        + "&body=" + quote(body, safe="")
    )


def safe_name(company: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in company)[:40]


def harvest_person_email(raw: str | None) -> str | None:
    addr = valid_email(raw)
    if not addr:
        return None
    local = addr.split("@", 1)[0]
    if "." not in local:
        return None
    if re.search(r"job|career|recruit|bewerbung|karriere|accommodation|ams", local, re.I):
        return None
    return addr


def already_sent_ids() -> set[str]:
    ids: set[str] = set()
    if not LOG.exists():
        return ids
    with LOG.open(encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            status = (row.get("status") or "").lower()
            if status.startswith("sent"):
                ids.add(row.get("id") or "")
    ids.discard("")
    return ids


def collect_curated() -> list[dict]:
    bundle = json.loads(CURATED.read_text(encoding="utf-8"))
    rows = []
    for row in bundle.get("prospects") or []:
        if row.get("margin") != "send":
            continue
        emails = []
        seen = set()
        for contact in row.get("contacts") or []:
            addr = valid_email(contact.get("email"))
            if addr and addr.lower() not in seen:
                seen.add(addr.lower())
                emails.append(addr)
        rows.append({**row, "origin": "curated", "to": emails})
    return rows


def collect_harvest() -> list[dict]:
    if not PIPE.exists():
        return []
    payload = json.loads(PIPE.read_text(encoding="utf-8"))
    rows = []
    for row in payload.get("prospects") or []:
        if row.get("margin") != "send":
            continue
        emails = []
        seen = set()
        for contact in row.get("contacts") or []:
            addr = harvest_person_email(contact.get("email"))
            if addr and addr.lower() not in seen:
                seen.add(addr.lower())
                emails.append(addr)
        if not emails:
            continue
        rows.append({**row, "origin": "harvest", "to": emails})
    return rows


def jaya_smtp() -> tuple[str, str]:
    """Jaya sending mailbox only — same keys as job-apply-kit users/jaya/auto.yaml."""
    user = (
        os.environ.get("JOBKIT_JAYA_SMTP_USER")
        or os.environ.get("GMAIL_USER")
        or SENDER_EMAIL
    ).strip()
    password = (
        os.environ.get("JOBKIT_JAYA_SMTP_PASSWORD")
        or os.environ.get("GMAIL_APP_PASSWORD")
        or ""
    ).replace(" ", "").strip()
    if user.lower() != SENDER_EMAIL.lower():
        raise RuntimeError(f"refusing non-Jaya SMTP user {user}")
    if not password:
        raise RuntimeError("JOBKIT_JAYA_SMTP_PASSWORD missing from job-apply-kit .env")
    return user, password


def send_smtp(to_addrs: list[str], subject: str, body: str, attach: Path | None) -> None:
    user, password = jaya_smtp()
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
    msg["To"] = ", ".join(to_addrs)
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Reply-To"] = SENDER_EMAIL
    msg.set_content(body)
    if attach and attach.exists():
        msg.add_attachment(
            attach.read_bytes(),
            maintype="text",
            subtype="plain",
            filename=attach.name,
        )
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(user, password)
        smtp.send_message(msg)


def chrome_exe() -> Path:
    candidates = [
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError("chrome_not_found")


RAVI_COMPOSE = "Compose Mail - ravirajkumar712@gmail.com - Gmail - Google Chrome"
RAVI_COMPOSE_SHORT = "Compose Mail - ravirajkumar712@gmail.com"


def send_via_logged_in_gmail(url: str, title_token: str) -> None:
    """Open compose in Chrome Default (ravirajkumar712) and Send with Ctrl+Enter."""
    chrome = chrome_exe()
    ps = f"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject WScript.Shell
function Close-RaviCompose {{
  for ($i = 0; $i -lt 8; $i++) {{
    if ($w.AppActivate({json.dumps(RAVI_COMPOSE_SHORT)})) {{
      Start-Sleep -Milliseconds 400
      $w.SendKeys('^w')
      Start-Sleep -Milliseconds 700
    }} else {{
      break
    }}
  }}
}}
Close-RaviCompose
$chrome = {json.dumps(str(chrome))}
$url = {json.dumps(url)}
Start-Process -FilePath $chrome -ArgumentList @('--profile-directory=Default','--new-window', $url)
$focused = $false
for ($i = 0; $i -lt 50; $i++) {{
  Start-Sleep -Milliseconds 400
  if ($w.AppActivate({json.dumps(RAVI_COMPOSE)})) {{ $focused = $true; break }}
  if ($w.AppActivate({json.dumps(RAVI_COMPOSE_SHORT)})) {{ $focused = $true; break }}
}}
if (-not $focused) {{
  Write-Output "FOCUS_FAIL"
  exit 2
}}
Start-Sleep -Seconds 4
$w.AppActivate({json.dumps(RAVI_COMPOSE)}) | Out-Null
Start-Sleep -Milliseconds 400
$w.SendKeys('^{{ENTER}}')
Start-Sleep -Seconds 5
Write-Output "SEND_KEYS_OK"
"""
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0 or "SEND_KEYS_OK" not in out:
        raise RuntimeError(f"gmail_tab_send_failed: {out.strip() or completed.returncode}")


def build_items(*, include_harvest: bool = True) -> tuple[list[dict], list[dict], list[dict]]:
    items = collect_curated()
    if include_harvest:
        items.extend(collect_harvest())
    log_rows = []
    gmail_opens = []
    linkedin_blocks = []
    OUTBOX.mkdir(parents=True, exist_ok=True)
    for row in items:
        body = with_notion(fill(row.get("email_body") or row.get("linkedin_note") or ""))
        if SENDER_EMAIL not in body:
            body = body.rstrip() + f"\n\n{SENDER_NAME}\n{SENDER_EMAIL}\n{AGENCY}"
        subject = fill(row.get("email_subject") or f"{row.get('company')} — {AGENCY}")
        to_addrs = row.get("to") or []
        fname = f"{row['id']}_{safe_name(row['company'])}.eml"
        path = OUTBOX / fname
        attach = CAP if row["id"] == "P001" else None
        write_eml(path, to_addrs, subject, body, attach)
        gmail = gmail_compose(to_addrs, subject, body) if to_addrs else ""
        status = "ready_to_send" if to_addrs else "linkedin_only"
        record = {
            "id": row["id"],
            "origin": row.get("origin"),
            "company": row.get("company"),
            "to": "; ".join(to_addrs),
            "subject": subject,
            "body": body,
            "status": status,
            "eml": str(path),
            "gmail": gmail,
            "attach": str(attach) if attach else "",
            "linkedin": (row.get("urls") or {}).get("linkedin_people") or "",
            "linkedin_note": fill(row.get("linkedin_note") or ""),
            "queued_at": utc_now(),
        }
        log_rows.append(record)
        if to_addrs:
            gmail_opens.append(record)
        else:
            linkedin_blocks.append(record)
    return log_rows, gmail_opens, linkedin_blocks


def write_sidecar(log_rows: list[dict], gmail_opens: list[dict], linkedin_blocks: list[dict]) -> Path:
    with LOG.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "id",
                "origin",
                "company",
                "to",
                "subject",
                "status",
                "eml",
                "gmail",
                "linkedin",
                "queued_at",
            ],
        )
        writer.writeheader()
        for row in log_rows:
            writer.writerow({k: row.get(k, "") for k in writer.fieldnames})

    li_path = OUTBOX / "LINKEDIN_SEND_TODAY.txt"
    li_bits = [
        "LinkedIn notes — already filled as Ravi Raj Kumar.",
        "Open the people-search URL, connect / InMail, paste the note. Do not attach a CV.",
        "",
    ]
    for row in linkedin_blocks:
        li_bits.append("=" * 72)
        li_bits.append(f"{row['id']}  {row['company']}")
        li_bits.append(row["linkedin"] or "(no people-search URL)")
        li_bits.append("")
        li_bits.append(row["linkedin_note"])
        li_bits.append("")
    li_path.write_text("\n".join(li_bits), encoding="utf-8")

    send_page = OUTBOX / "send.html"
    send_page.write_text(render_send_page(gmail_opens, linkedin_blocks), encoding="utf-8")

    DASHBOARD.mkdir(parents=True, exist_ok=True)
    (DASHBOARD / "outbox.js").write_text(
        "window.SAP_OUTBOX = "
        + json.dumps(
            {
                "generated_at": utc_now(),
                "sender": f"{SENDER_NAME} <{SENDER_EMAIL}>",
                "ready_to_send": [
                    {k: r.get(k) for k in ("id", "company", "to", "subject", "gmail", "status")}
                    for r in gmail_opens
                ],
                "linkedin_only": [
                    {k: r.get(k) for k in ("id", "company", "linkedin", "subject", "status")}
                    for r in linkedin_blocks
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + ";\n",
        encoding="utf-8",
    )
    return send_page


def dispatch(gmail_opens: list[dict], method: str) -> str:
    """Send verified emails from Jaya's Gmail only. Skip ids already in the sent log."""
    if not gmail_opens:
        return "none"
    if method in {"auto", "smtp"}:
        jaya_smtp()
        sent_already = already_sent_ids()
        sent_any = False
        for row in gmail_opens:
            if row["id"] in sent_already:
                row["status"] = "already_sent"
                print(f"Skip already sent {row['id']} {row['company']}")
                continue
            attach = Path(row["attach"]) if row.get("attach") else None
            send_smtp(row["to"].split("; "), row["subject"], row["body"], attach)
            row["status"] = "sent_smtp"
            sent_any = True
            print(f"SMTP sent as {SENDER_EMAIL}: {row['id']} -> {row['to']}")
            time.sleep(1.5)
        return "smtp" if sent_any else "already_sent"
    return "queued"


def render_send_page(gmail_opens: list[dict], linkedin_blocks: list[dict]) -> str:
    gmail_html = []
    for row in gmail_opens:
        gmail_html.append(
            f"<article><h2>{html.escape(row['id'])} — {html.escape(row['company'])}</h2>"
            f"<p class='to'>To: {html.escape(row['to'])}</p>"
            f"<p class='sub'>{html.escape(row['subject'])}</p>"
            f"<p>Status: {html.escape(row.get('status') or '')}</p>"
            f"<p><a class='btn' href='{html.escape(row['gmail'], quote=True)}'>Open in Gmail</a></p>"
            f"</article>"
        )
    li_html = []
    for row in linkedin_blocks:
        note = html.escape(row.get("linkedin_note") or "")
        url = html.escape(row["linkedin"] or "#", quote=True)
        li_html.append(
            f"<article><h2>{html.escape(row['id'])} — {html.escape(row['company'])}</h2>"
            f"<p><a href='{url}' target='_blank' rel='noopener'>Open LinkedIn people search</a></p>"
            f"<pre>{note}</pre>"
            f"<button type='button' data-copy='{quote(row.get('linkedin_note') or '')}'>Copy note</button>"
            f"</article>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>SAP Desk — send now</title>
  <style>
    body {{ font-family: Georgia, serif; max-width: 720px; margin: 32px auto; padding: 0 16px; background: #f3eee4; color: #1c1916; }}
    h1 {{ font-size: 28px; }}
    article {{ background: #fffdf8; border: 1px solid #ddd4c6; border-radius: 12px; padding: 16px; margin: 12px 0; }}
    .btn {{ display: inline-block; background: #21564a; color: #fff; padding: 10px 14px; border-radius: 8px; text-decoration: none; }}
    pre {{ white-space: pre-wrap; background: #1c1916; color: #f3eee4; padding: 12px; border-radius: 8px; font-size: 13px; }}
    button {{ cursor: pointer; padding: 8px 12px; }}
    .muted {{ color: #5c564e; }}
  </style>
</head>
<body>
  <h1>Send these now</h1>
  <p class="muted">From {SENDER_NAME} &lt;{SENDER_EMAIL}&gt;. Verified emails are sent from this Gmail. LinkedIn still needs you.</p>
  <h2>Email (verified addresses)</h2>
  {''.join(gmail_html) or '<p>No verified emails.</p>'}
  <h2>LinkedIn (no public email)</h2>
  <p class="muted">Open the people search, message the programme / IT lead, paste the note. Price is already in it.</p>
  {''.join(li_html)}
  <script>
    document.body.addEventListener("click", (ev) => {{
      const btn = ev.target.closest("[data-copy]");
      if (!btn) return;
      navigator.clipboard.writeText(decodeURIComponent(btn.getAttribute("data-copy")));
      btn.textContent = "Copied";
      setTimeout(() => {{ btn.textContent = "Copy note"; }}, 1200);
    }});
  </script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue and send SAP Desk outreach via Gmail")
    parser.add_argument(
        "--method",
        choices=["auto", "smtp", "gmail", "queue"],
        default="auto",
        help="auto = SMTP if app password exists, else send from logged-in Gmail tab",
    )
    args = parser.parse_args()
    load_env(JOBKIT_ENV)
    load_env(ENV_PATH)
    print(f"Sending mailbox: {SENDER_NAME} <{SENDER_EMAIL}> (job-apply-kit Jaya SMTP)")
    print(f"Notion capability: {NOTION_CAPABILITY}")
    print(f"Notion profile:    {NOTION_PROFILE}")
    log_rows, gmail_opens, linkedin_blocks = build_items()
    used = "queued"
    if args.method != "queue":
        try:
            used = dispatch(gmail_opens, args.method)
        except Exception as exc:
            print(f"Send failed ({exc}). Mail is still queued in {OUTBOX}", file=sys.stderr)
            used = "queued"
    write_sidecar(log_rows, gmail_opens, linkedin_blocks)

    print(f"Queued {len(log_rows)} high-margin messages in {OUTBOX}")
    print(f"Verified To: {len(gmail_opens)}  method={used}")
    for row in gmail_opens:
        print(f"  {row['id']}  {row['company']}  ->  {row['to']}  [{row['status']}]")
    print(f"LinkedIn-only: {len(linkedin_blocks)}  ->  {OUTBOX / 'LINKEDIN_SEND_TODAY.txt'}")
    print(f"Log: {LOG}")
    print("Harvest recruiting scrapes were NOT mailed.")
    if used == "queued" and gmail_opens:
        print("No Gmail app password in .env — put GMAIL_APP_PASSWORD= (16-char) and re-run for SMTP.")
        print("Or re-run with --method gmail while Chrome is logged into Gmail.")


if __name__ == "__main__":
    main()
