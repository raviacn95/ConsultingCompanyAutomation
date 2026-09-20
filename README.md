# Consulting Company Automation

Local Windows workspace for two **separate** businesses that share a harvest engine and must never share a mailbox or resume.

| Track | What it is | Who | Mailbox | Resume |
|---|---|---|---|---|
| **SAP Desk** | Consulting outreach: priced 90-day S/4 workstream / Arbeitspaket to programme owners | Signed as **Jaya Gupta** (desk sender) | `jayagupta20252003@gmail.com` | Capability one-pager, not a job CV |
| **Ravi job apply** | Remote SAP QA / Playwright applications | **Ravi Kumar** | `ravik021995@gmail.com` (Reply-To often `ravirajkumar712@gmail.com`) | SAP S/4 / Playwright (Tosca only when JD names it). **No Teradata DBA** |
| **Jaya job apply** | Teradata / EDW / Informatica / Hadoop applications | **Jaya Gupta** | `jayagupta20252003@gmail.com` | Teradata DBA / Vantage / TASM / Hadoop. **Not Tosca/SDET** |

Do not send consulting SOW pitches as job applications. Do not send Ravi’s packet from Jaya’s mailbox, or the reverse. Apply scripts refuse a crossed From-address.

This repo emails recruiter addresses (and can submit Greenhouse / Lever when the kit can). Roles without an inbox stay in a queued CSV. For those, use the **Easy Apply desk** (`scripts/easy_apply_desk.py`): it fills Indeed / LinkedIn / Naukri forms from the active user’s kit vault + JD packet. Default is **fill-only** (you click Submit). Optional `--submit` exists but is fragile (CAPTCHA / ToS).

Companion toolkit (resumes, SMTP, tailored packets, SQLite apply store):

`C:\Users\ravir\job-apply-kit`

---

## What a watch cycle does

Every 1 hour (or on demand):

1. Harvest new SAP QA / Playwright / automation jobs into the worldwide Excel.
2. Export that Excel with **newest `harvested_at` first**. If Excel has the file locked, write `jobs_worldwide.updated.csv` instead.
3. Harvest Teradata-family jobs into `data/jaya_teradata/` (never into Ravi’s apply log).
4. If `--mail` is set: email **new** unused recruiter inboxes for Ravi (remote SAP QA / Playwright) and Jaya (remote Teradata-family).
5. Refresh `dashboard/watch.js` and append `data/watch_jobs.log`.

Each application email attaches **only** the JD-built resume from job-apply-kit (`create_packet`), not the static PDF/docx sitting in the profile. For Ravi, headline, summary, skills, bullets, and certs are rebuilt from **that posting’s JD** every send (truth-only facts from `profile.yaml`; Tosca/Tricentis lines are omitted unless the JD mentions them). Flow in the kit: parse JD must/nice/region cues (`jobkit/jd_parse.py`) → intersect with profile skills → up to **5** tailored bullets per company → SMTP via `_ensure_packet` / `apply_remote_ravi.py` / watch `--mail`.

---

## Prerequisites

- Windows, Python 3.11+ on `PATH` (`C:\Python313\python.exe` is what the watch task uses).
- From this folder:

```powershell
pip install -r requirements.txt
```

- Job Apply Kit at `C:\Users\ravir\job-apply-kit` with users `ravi` and `jaya` already profiled.
- SMTP (never commit these):
  - **Ravi:** Windows user env `JOBKIT_SMTP_USER` / `JOBKIT_SMTP_PASSWORD` (16-char Gmail app password).
  - **Jaya:** `JOBKIT_JAYA_SMTP_USER` / `JOBKIT_JAYA_SMTP_PASSWORD` in `job-apply-kit\.env` (this repo’s `.env` is also loaded for desk outreach).
- Optional: keep `data/jobs_worldwide.csv` closed in Excel when you want the main file updated in place.

---

## Repository layout

```
ConsultingCompanyAutomation/
  scripts/                 all runners (harvest, apply, desk, watch)
  dashboard/               SAP Desk UI (auto-refresh every 60s; Run now on Pages)
  docs/                    GitHub Pages root (mirror of dashboard/)
  data/                    worldwide harvest, desk pipeline, apply logs
  .github/workflows/       Watch jobs (self-hosted) + cloud stub
  data/jaya_teradata/      Jaya-only harvest, apply log, Markdown reports
  data/outbox/             queued SAP Desk .eml / LinkedIn notes
  requirements.txt         python-jobspy, pandas
```

### Scripts

| Script | Purpose |
|---|---|
| `watch_jobs.py` | Hourly cycle: harvest + Excel + apply mail for Ravi and Jaya. Optional `--easy-apply-fill` (fill-only, off by default). Installs hidden Windows task `SAPDeskWatchJobs`. |
| `easy_apply_desk.py` | Indeed / LinkedIn / Naukri fill (default) or optional submit for **no-email** queued rows. Separate browser profiles per user. |
| `harvest_jobs.py` | Worldwide jobs (Indeed / Google via JobSpy + public APIs). Writes `jobs_worldwide.csv` + `sap_jobs.csv`. |
| `harvest_teradata.py` | Jaya keyword harvest into `data/jaya_teradata/`. Seeds from the newest worldwide CSV. |
| `apply_remote_ravi.py` | Email Ravi to remote SAP QA / Playwright rows that have a recruiter inbox. |
| `apply_jaya_teradata.py` | Email Jaya to Teradata-family roles (`--remote-only` for the watch cycle). |
| `apply_tosca_extra.py` | One-off Ravi Tosca inboxes found after harvest (TestDel, ANAXON, Thought Frameworks, ghc). |
| `report_jaya_teradata.py` | Rebuild local Markdown reports under `data/jaya_teradata/reports/`. |
| `rebuild_jaya_apply_log.py` | Rebuild Jaya `apply_log.csv` from job-apply-kit mail events. |
| `run_pipeline.py` | Desk: export harvest → `build_pipeline.py` → `find_sap_leads.py`. |
| `build_pipeline.py` | Turn SAP-tagged jobs + curated prospects into send/later/skip pipeline. |
| `find_sap_leads.py` | Refresh live SAP signals (Arbeitnow, Remotive, …) onto the desk. |
| `apply_high_margin.py` | Overlay priced SOW / Arbeitspaket copy onto `prospects.json`. |
| `queue_outreach.py` | Send or queue SAP Desk pitches from **Jaya’s** mailbox only. |

---

## Two people, two apply tracks

### Ravi Kumar — SAP QA / Playwright

- Kit user: `ravi`
- Track: `automation`
- Source file: newest of `data/jobs_worldwide.csv` or `data/jobs_worldwide.updated.csv`
- Filter: remote + (**SAP test/QA/automation** and/or **Playwright**). Tosca-only (no SAP, no Playwright) is skipped. Tosca is allowed when the JD also has SAP or Playwright.
- Skip: intern / Praktikum (unless Playwright / SAP QA / Tosca), food company “Tosca”, ADA inboxes (`accessibility@`, `accommodation@`)
- Sent log: `data/ravi_remote_apply_log.csv` (append; do not wipe on a zero-send cycle)
- Queued: `data/ravi_remote_apply_queued.csv` (Indeed / no email / already mailed that inbox)

```powershell
python -u scripts\apply_remote_ravi.py
```

### Jaya Gupta — Teradata / EDW / ETL

- Kit user: `jaya`
- Track: `teradata_dba`
- Isolated folder: `data/jaya_teradata/` — **never** write to Ravi’s apply log
- Role test uses title + JD (not `search_term`). “Viewpoint” only as Teradata Viewpoint. Weak titles (SAP Security, conversational designer, …) dropped. SAP SNP migration skipped unless Teradata is in the title.
- Company inbox fallbacks: MNJ `hr@mnjsoftware.com`, CSpring `info@cspring.com`, Concept Plus `info@conceptplus.com`, V4C `info@v4c.ai`
- Sent: `data/jaya_teradata/apply_log.csv`
- Queued: `apply_queued.csv` (all) and `apply_remote_queued.csv` (watch / `--remote-only`)

```powershell
python -u scripts\apply_jaya_teradata.py --remote-only
python -u scripts\apply_jaya_teradata.py
python -u scripts\report_jaya_teradata.py
```

Keyword families (also used for Notion / local reports): Core Database, Performance (TASM/TDWM), ETL & Informatica, Infrastructure, Security, Big Data & Cloud, Automation & Tools.

---

## Easy Apply desk (Indeed / LinkedIn / Naukri)

For queued rows whose reason is **no recruiter email / ATS API** (the bulk of both queues). This path does **not** re-mail already-emailed inboxes.

### Architecture

- CLI: `scripts/easy_apply_desk.py`
- Connectors: `scripts/easy_apply_connectors/` (`indeed.py`, `linkedin.py`, `naukri.py`, classify + queue + walls)
- Reuses job-apply-kit: `set_active_user`, `create_packet`, `form_fill.fill_application_page` / `fill_payload`
- Persistent Edge profiles (gitignored): `.browser-profiles/<ravi|jaya>/<indeed|linkedin|naukri>/`
- Optional env overrides: `EASY_APPLY_PROFILE_RAVI_INDEED`, `EASY_APPLY_PROFILE_JAYA_LINKEDIN`, etc.
- Logs: `data/ravi_easy_apply_log.csv`, `data/jaya_teradata/easy_apply_log.csv`
- Failure screenshots: `data/easy_apply_shots/` (gitignored)

**Why fill-first:** sites ban bots and show CAPTCHA. JobKit Autofill already fills fields and leaves Submit to a human. This desk automates navigation + the same fill for no-email queues. It does **not** claim an undetectable Indeed/LinkedIn bypass.

### Commands

```powershell
# List no-email queued jobs by site (does not open a browser)
python -u scripts\easy_apply_desk.py --user ravi --list
python -u scripts\easy_apply_desk.py --user jaya --list --site indeed

# Login once per user × site (session stays in .browser-profiles)
python -u scripts\easy_apply_desk.py --user ravi --login --site indeed
python -u scripts\easy_apply_desk.py --user jaya --login --site linkedin

# Fill only (default, safe) — prepares JD packet + fills fields; you click Submit
python -u scripts\easy_apply_desk.py --user ravi --fill-only --limit 5
python -u scripts\easy_apply_desk.py --user jaya --fill-only --site indeed --limit 3

# Optional: attempt Submit where selectors are stable (stops on login/CAPTCHA)
python -u scripts\easy_apply_desk.py --user ravi --submit --site indeed --limit 2
```

Watch integration (off by default; never auto-`--submit`):

```powershell
python -u scripts\watch_jobs.py --once --mail --easy-apply-fill --easy-apply-limit 5
```

### Limits (still needs a human)

- First-time login and 2FA / CAPTCHA
- External “Apply on company site” ATS flows with odd fields
- File inputs some sites block from automation (resume path is logged; attach manually)
- Mass `--submit` will burn accounts — keep `--limit` low
- Workday / custom career sites are `other` and skipped unless you `--include-other` for listing only

Do not commit passwords, cookies, or session dumps. Profiles stay under `.browser-profiles/` (gitignored).

---

## Harvest

Checkpoint is append-only JSONL, then a newest-first CSV export.

**Worldwide (SAP QA + Playwright / automation)**

```powershell
python -u scripts\harvest_jobs.py --focus automation --extra 250 --wanted 40 --skip-apis
python -u scripts\harvest_jobs.py --export-only
```

| Flag | Meaning |
|---|---|
| `--focus sap` | SAP / S/4 / module keywords (default) |
| `--focus automation` | Playwright, SAP test automation, Tosca/Tricentis, QA automation |
| `--extra N` | Stop after about N **new** unique rows |
| `--wanted N` | Per-search result cap |
| `--target N` | Grow until this many unique jobs (full backfill) |
| `--skip-apis` | Indeed/Google/Glassdoor only (watch uses this; APIs already in the checkpoint) |
| `--export-only` | Rebuild Excel + `dashboard/jobs_summary.js` from `data/jobs.jsonl` |

Sources: Indeed / Google (JobSpy), Greenhouse boards, Lever, Jobicy, The Muse, Arbeitnow, RemoteOK, Remotive.

**Jaya Teradata folder**

```powershell
python -u scripts\harvest_teradata.py --extra 120 --wanted 40
python -u scripts\harvest_teradata.py --export-only
```

Writes `data/jaya_teradata/jobs.jsonl`, `jobs.csv`, `summary.json`. Also seeds matching rows from the newest worldwide CSV.

If Excel has `jobs_worldwide.csv` open, harvest writes `jobs_worldwide.updated.csv`. Apply and Teradata seed pick the **newest** of the two files.

---

## Watch: run now / every 1 hour

```powershell
# harvest + mail only (default scheduled path)
python -u scripts\watch_jobs.py --once --mail

# optional: also fill-only Easy Apply for no-email rows (never auto-submit)
python -u scripts\watch_jobs.py --once --mail --easy-apply-fill --easy-apply-limit 5

# harvest only (no SMTP)
python -u scripts\watch_jobs.py --once

# register / remove the Windows task (runs while the PC is on)
python -u scripts\watch_jobs.py --install
python -u scripts\watch_jobs.py --uninstall
```

Task name: **`SAPDeskWatchJobs`**. Schedule: every 1 hour, every day, hidden window, working directory this repo. A lock file skips overlap if a cycle is still running. Dashboard cards for Ravi and Jaya refresh from `dashboard/watch.js` every 60 seconds.

Mail is **one inbox per company/address**. Already-emailed addresses (job-apply-kit store) are skipped. Most Indeed rows stay queued.

Quiet hours in job-apply-kit `auto.yaml` (typically 22:00–08:00) apply to the kit’s own scheduler. The watch `--mail` apply scripts send when you run them.

Log: `data/watch_jobs.log`  
Dashboard stamp: `dashboard/watch.js`

---

## SAP Desk (consulting outreach)

This is **not** a job apply. It sells a named workstream (India ₹ / Germany € Arbeitspaket) to people who own a slipped S/4 programme. Recruiting-scrape addresses are **not** mailed as desk pitches.

```powershell
python -u scripts\run_pipeline.py              # export + rebuild pipeline
python -u scripts\run_pipeline.py --harvest    # also pull more jobs first
python -u scripts\apply_high_margin.py         # priced products on prospects
python -u scripts\queue_outreach.py            # SMTP if Jaya app password exists
python -u scripts\queue_outreach.py --method queue
python -u scripts\queue_outreach.py --method gmail
```

- Curated accounts: `data/prospects.json`
- Send/later/skip table: `data/pipeline.json`, `data/pipeline.csv`
- Outbox: `data/outbox/` (`.eml`, `send.html`, `LINKEDIN_SEND_TODAY.txt`)
- Send log: `data/outreach_log.csv`
- Sender is hard-coded to Jaya / SAP Desk. Capability Notion links are appended to the note.

Markets and list prices live in `build_pipeline.py` / `apply_high_margin.py` (India named functional vs architect; Germany Arbeitspaket; skip prime-SI subcontracting and free health checks).

---

## Dashboard

Open `dashboard/index.html` locally (file:// works), or the **GitHub Pages** copy under `docs/` once Pages is enabled.

| File | Role |
|---|---|
| `index.html` | Desk: prospects, pipeline, harvest counts, last watch, **Run now** / **Apply all**, **Auto-applied jobs** table |
| `run_controls.js` | Pages control: dispatch Actions + poll runs (PAT in localStorage only) |
| `pitch.html` | Printable one-pager |
| `jobs_summary.js` | Unique / SAP-tagged counts from harvest export |
| `watch.js` | Last watch cycle (start/finish, Ravi/Jaya mail lines) |
| `apply_all_status.js` | Last Apply-all run state (`needs_login`, step tails) |
| `auto_applied_jobs.js` | Successful auto-applies (email + Easy Apply submit), newest first; filter Ravi / Jaya / All |
| `pipeline.js` | Built by `build_pipeline.py` |
| `prospects.js` / `outbox.js` | Desk sidecars |

---

## GitHub Pages + Run now / Apply all (no Cursor)

Static Pages cannot run Python. Execution is **GitHub Actions on a Windows self-hosted runner** on the PC that already has `job-apply-kit` and SMTP.

### 1. Push this repo and enable Pages

1. Create/push the GitHub repo (default branch `main`).
2. **Settings → Pages → Build and deployment → Source:** Deploy from a branch → Branch `main` → folder **`/docs`** → Save.
3. Site URL: `https://<owner>.github.io/ConsultingCompanyAutomation/`

### 2. Register a self-hosted runner (preferred)

On this Windows PC (the one with kit + SMTP):

1. Repo **Settings → Actions → Runners → New self-hosted runner → Windows**.
2. Follow GitHub’s download / `config.cmd` / `run.cmd` steps.
3. Add labels so the workflow matches: at least **`windows`** (default) so `runs-on: [self-hosted, Windows]` picks it up.
4. Keep the runner process (or Windows service) running while you want “Run now” / “Apply all” / hourly Actions to work.

**Watch jobs** (`.github/workflows/watch-jobs.yml`) runs harvest + optional mail:

```text
python -u scripts\watch_jobs.py --once --mail
```

**Apply all** (`.github/workflows/apply-all.yml`) skips harvest and focuses on apply:

```text
python -u scripts\apply_all_run.py --mail --easy-apply --easy-submit --easy-limit 50 --user both
```

That means: email apply (`apply_remote_ravi.py` + `apply_jaya_teradata.py --remote-only`) **and** Easy Apply desk with `--submit` for Indeed / LinkedIn / Naukri no-email queues. **“All” = up to `easy_limit` per user per run** (default 50, hard cap 100) — not infinite.

Both workflows run inside `C:\Users\ravir\ConsultingCompanyAutomation` (override via `local_repo`), then copy `dashboard/` → `docs/` and push so Pages updates. Status lands in `docs/apply_all_status.js`. The **Auto-applied jobs** section is rebuilt by `scripts/sync_auto_applied_jobs.py` from the existing per-user logs (`data/ravi_remote_apply_log.csv`, `data/jaya_teradata/apply_log.csv`, plus Easy Apply `*_easy_apply_log.csv` rows with `status=submitted` only) into `docs/auto_applied_jobs.js` (cap 400, newest first; Ravi/Jaya never mixed).

**Easy Apply login:** profiles live under `.browser-profiles/{ravi|jaya}/{indeed|linkedin|naukri}/` (gitignored). Log in once:

```text
python -u scripts\easy_apply_desk.py --user ravi --login --site indeed
```

If profiles are missing, Apply all fails gracefully with `needs_login` in `apply_all_status.js` (does not hang on CAPTCHA forever).

### 3. Click Run now or Apply all on the site

1. Open the Pages URL.
2. Expand **Token & repo setup**. Owner/repo auto-fill on `*.github.io`; paste a PAT with permission to dispatch workflows (`repo` classic, or fine-grained **Actions: Write** + **Contents: Read**).
3. **Save in browser** — token is stored in `localStorage` only; clear anytime with **Clear token**.
4. **Run now (harvest + mail)** → `workflow_dispatch` on `watch-jobs.yml`.
5. **Apply all (mail + Easy Apply)** → `workflow_dispatch` on `apply-all.yml` (warns once: leave PC on, runner online, profiles logged in).
6. **Refresh run status** polls both workflows. After the runner finishes and pushes, reload for new counts / `apply_all_status.js`.

**No-token fallback:** use the **Watch Actions** / **Apply all Actions** links → **Run workflow**.

Cloud machines cannot see your kit path or Windows SMTP. Workflow `Watch jobs (cloud note)` only records that a run was requested; it does not send mail.

### 4. Secrets (only if you later try a cloud Windows runner)

Do **not** commit `.env` or app passwords. If you ever change the workflow to `windows-latest`, store SMTP in Actions secrets (`JOBKIT_SMTP_*`, `JOBKIT_JAYA_SMTP_*`) and vendor/submodule job-apply-kit — not required for the self-hosted path above.

---

## Data files (do not mix)

### Worldwide / Ravi

| Path | Contents |
|---|---|
| `data/jobs.jsonl` | Append-only harvest checkpoint |
| `data/jobs_worldwide.csv` | All unique jobs, newest first (Excel) |
| `data/jobs_worldwide.updated.csv` | Sidecar when Excel locks the main file |
| `data/sap_jobs.csv` | SAP-tagged slice |
| `data/sap_companies.csv` | Company rollup from SAP rows |
| `data/jobs_summary.json` | Counts + sources |
| `data/ravi_remote_apply_log.csv` | Ravi emails actually sent |
| `data/ravi_remote_apply_queued.csv` | Remote SAP QA / Playwright with no sendable inbox |
| `data/watch_jobs.log` | One line per watch cycle |

### Jaya Teradata (isolated)

| Path | Contents |
|---|---|
| `data/jaya_teradata/jobs.jsonl` | Checkpoint |
| `data/jaya_teradata/jobs.csv` | Unique Teradata-family jobs |
| `data/jaya_teradata/summary.json` | Counts + role tags |
| `data/jaya_teradata/apply_log.csv` | Jaya emails sent |
| `data/jaya_teradata/apply_queued.csv` | All queued |
| `data/jaya_teradata/apply_remote_queued.csv` | Remote-only queue from watch |
| `data/jaya_teradata/reports/*.md` | Overview, sent, queued, per keyword family |

### SAP Desk

| Path | Contents |
|---|---|
| `data/prospects.json` | Curated India + Germany accounts |
| `data/pipeline.json` / `.csv` | Send / later / skip + copy |
| `data/live_jobs.json` | Public-board SAP signals |
| `data/outreach_log.csv` | Desk sends |
| `data/outbox/` | Queued messages and LinkedIn-only list |

`.env` is gitignored. Never commit SMTP passwords or app passwords.

---

## Job Apply Kit (how mail actually goes out)

Apply scripts `set_active_user("ravi"|"jaya")`, ingest the harvest row, classify the channel, build a **JD-tailored** `.docx` (`{name}-{title}-{company}.docx`), and call `_submit`.

- Email: MIME attach that tailored file only. Send is refused if the tailored file is missing.
- Greenhouse / Lever: kit apply API when `can_submit`.
- Indeed / Naukri / Workday / LinkedIn: logged as queued (`No recruiter email / ATS API`).

Quality rules for JD→resume live in `job-apply-kit/prompts/enterprise_jd_resume.md` (ATS, truth-only, dual-track lock). The kit must not invent Tosca on Jaya’s packet or Teradata DBA on Ravi’s.

Manual Easy Apply: JobKit Autofill extension (`python -m jobkit extension-install` in the kit). It fills forms; it does not click Submit.

---

## Notion

Private drafts for Jaya’s Teradata work sit under:

[Jaya Gupta — Teradata / EDW applications](https://www.notion.so/3d1dfde0aa0c819fb725e118d4a09728)

Children (kept separate from older SAP Desk pages): Applications sent, Queued Easy Apply, Harvest inventory, plus one page per keyword family.

SAP Desk capability / rate-card pages are consulting collateral, not job-apply reports. Rebuild local Markdown anytime with `report_jaya_teradata.py` before copying into Notion.

---

## Filters and anti-pollution

- Classify Tosca / Teradata from **title + JD**, not from the Indeed `search_term` (that is how SAP Security and “unique viewpoint” leaked in).
- Skip intern / Praktikum / student unless the role is clearly Tosca for Ravi.
- Skip the food company named Tosca.
- Skip ADA / accommodation mailboxes.
- One email per inbox per person (kit `emailed_addresses()`).
- Desk pipeline also drops SI subcontractors, staffing houses, and junk titles (CDL, truck driver, “SAP driver”).

---

## Command cheat sheet

```powershell
cd C:\Users\ravir\ConsultingCompanyAutomation

# Daily: find new jobs, refresh Excel, send new recruiter mail
python -u scripts\watch_jobs.py --once --mail

# Desk: rebuild send list
python -u scripts\run_pipeline.py
python -u scripts\queue_outreach.py --method queue

# Reports
python -u scripts\report_jaya_teradata.py
```

Open `dashboard/index.html` and `data/jobs_worldwide.csv` (newest rows at the top).

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `sent=0` after a watch | No **new** recruiter inboxes. Indeed rows stay queued. Check `*_queued.csv` reasons. |
| Apply looks stale vs Excel | Apply now uses the newest of `jobs_worldwide.csv` and `.updated.csv`. Close Excel so the main file can update. |
| Google `429` / `/sorry` | JobSpy hit Google’s rate limit. Indeed still writes rows. Retry later. |
| Excel PermissionError | Sidecar `*.updated.csv` was written; dashboard still works. |
| Wrong From-address | Scripts exit if Ravi would send as Jaya or the reverse. Check `active_user` and SMTP env. |
| Empty Ravi apply log after a zero-send | Older code overwrote the log. Current `apply_remote_ravi.py` **appends**. Rebuild from kit store if needed. |
| Mailbox `421` / daily limit | Apply stops that cycle. Wait; do not keep retrying the same inbox. |

---

## Limits (by design)

- No bot login to Indeed / Naukri / Workday / LinkedIn Easy Apply.
- No mixing of Ravi SAP/Playwright facts onto Jaya packets, or Teradata DBA facts onto Ravi packets.
- Consulting desk mail is Jaya-only and is not a job application.
- Harvest quality depends on public pages; Google may throttle; descriptions can be short.
)
