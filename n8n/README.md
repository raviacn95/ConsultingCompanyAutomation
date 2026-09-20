# n8n — Job Apply Easier

Control plane for the dual-track apply system (**Ravi** SAP QA/Playwright + **Jaya** Teradata). n8n triggers and watches GitHub Actions; it does **not** reimplement mail apply or Easy Apply.

| Layer | What runs |
|---|---|
| **n8n** | Webhook / schedule / notify + GitHub `workflow_dispatch` |
| **GitHub Actions** | `apply-all.yml` / `watch-jobs.yml` on self-hosted `windows` runner |
| **PC scripts** | `scripts/apply_all_run.py`, `watch_jobs.py`, Easy Apply desk, SMTP |

Same outcome as the [Pages dashboard](https://raviacn95.github.io/ConsultingCompanyAutomation/) **Apply all** button — fewer clicks after credentials live once in n8n.

---

## Files

| Path | Purpose |
|---|---|
| [`workflows/job-apply-easier.json`](workflows/job-apply-easier.json) | Importable workflow export |

---

## Import

1. Open your n8n instance (self-hosted or cloud).
2. **Workflows → Import from File** → select `n8n/workflows/job-apply-easier.json`.
3. Leave the workflow **inactive** until env vars and the Windows runner are ready.
4. Open the canvas — sticky notes document triggers, inputs, and env vars.

**Wait nodes:** polling uses Wait → HTTP loop. The workflow must be **Active** for Wait resumes (or use Manual once with a short `POLL_MAX_ATTEMPTS` for a smoke test).

---

## Required credentials / env

Set these on the n8n host (Settings → Variables, or process env). The workflow reads them via `{{ $env.* }}` — **never** paste tokens into the JSON.

| Variable | Required | Example / notes |
|---|---|---|
| `GITHUB_TOKEN` | **Yes** | Fine-grained PAT: **Actions: Write**, **Contents: Read** (or classic `repo` + workflow). Same scope as Pages. |
| `GITHUB_OWNER` | No | Default `raviacn95` |
| `GITHUB_REPO` | No | Default `ConsultingCompanyAutomation` |
| `GITHUB_REF` | No | Default `main` |
| `NOTIFY_WEBHOOK_URL` | No | Discord or Slack **incoming webhook** URL |
| `POLL_MAX_ATTEMPTS` | No | Default `36` (~12 min at 20s) |
| `POLL_SECONDS` | No | Default `20` |

Enable env access in Code/HTTP nodes if your n8n build blocks it:

```text
N8N_BLOCK_ENV_ACCESS_IN_NODE=false
```

Optional: create an n8n **Header Auth** credential named `GitHub PAT` (`Authorization: Bearer <token>`) and attach it to the GitHub HTTP nodes instead of `$env.GITHUB_TOKEN`. Do not commit that credential.

---

## How it maps to Pages / Actions

| Pages control | Workflow file | n8n |
|---|---|---|
| **Apply all (mail + Easy Apply)** | `apply-all.yml` | Default webhook / manual / schedule |
| **Run now (harvest + mail)** | `watch-jobs.yml` | `action: "watch"` or `also_watch: true` |

**Apply-all inputs** (exact names from `.github/workflows/apply-all.yml` and `dashboard/run_controls.js`):

| Input | Type | Default | Meaning |
|---|---|---|---|
| `mail` | bool → `"true"`/`"false"` | true | Email apply (Ravi + Jaya paths never mixed) |
| `easy_apply` | bool string | true | Easy Apply desk for no-email queues |
| `easy_submit` | bool string | true | Pass `--submit` to desk |
| `easy_limit` | number string | `"50"` | Max Easy Apply jobs **per user** (cap 100) |
| `user` | `both` \| `ravi` \| `jaya` | `both` | Who to apply for |
| `local_repo` | string | `C:\Users\ravir\ConsultingCompanyAutomation` | Path on the runner PC |

---

## One-click / webhook

After **Activate**, copy the Production webhook URL from **Webhook: Apply easier**.

```http
POST /webhook/job-apply-easier
Content-Type: application/json
```

```json
{
  "action": "apply-all",
  "user": "both",
  "mail": true,
  "easy_apply": true,
  "easy_submit": true,
  "easy_limit": 50,
  "also_watch": false
}
```

### Examples

```bash
# Both users — same as Pages Apply all
curl -sS -X POST "$N8N_WEBHOOK_URL" -H "Content-Type: application/json" -d "{\"user\":\"both\"}"

# Ravi only
curl -sS -X POST "$N8N_WEBHOOK_URL" -H "Content-Type: application/json" -d "{\"user\":\"ravi\"}"

# Jaya only
curl -sS -X POST "$N8N_WEBHOOK_URL" -H "Content-Type: application/json" -d "{\"user\":\"jaya\"}"

# Watch jobs only (harvest + mail)
curl -sS -X POST "$N8N_WEBHOOK_URL" -H "Content-Type: application/json" -d "{\"action\":\"watch\",\"mail\":true}"
```

The webhook **waits** until the Actions run completes (or poll timeout), then returns JSON with `outcome`, `runUrl`, and a short auto-applied summary.

---

## Scheduled apply

Node **Schedule: Weekday 08:00 (disabled)** uses cron `0 8 * * 1-5` in the **n8n server timezone**.

1. Confirm Easy Apply profiles are logged in and the runner is online.
2. Open the node → enable it (uncheck disabled) → save → activate workflow.
3. Adjust cron if you want a different morning slot.

Schedule uses the same defaults as Pages Apply all (`user=both`, mail + easy apply + submit, limit 50).

---

## What the workflow does (steps)

1. **Trigger** — webhook, manual, or (optional) schedule.
2. **Normalize inputs** — validate `user`, coerce booleans to GitHub string inputs, read env.
3. **Dispatch** — `POST .../actions/workflows/{apply-all.yml|watch-jobs.yml}/dispatches`.
4. **Optional** — if `also_watch`, also dispatch `watch-jobs.yml` (fire-and-forget).
5. **Poll** — list recent `workflow_dispatch` runs until `completed` or max attempts.
6. **Summary** — fetch public `auto_applied_jobs.js` from Pages; parse `total` / `by_user` / `by_method`.
7. **Notify** — POST to `NOTIFY_WEBHOOK_URL` when set (Discord `content` + Slack-friendly `text`).
8. **Respond** — webhook clients get JSON; manual/schedule continues without failing the respond node.

---

## Dual-user safety

- n8n only passes `user=both|ravi|jaya` into Actions; it never sends SMTP or opens browsers.
- Runner scripts keep separate mailboxes, kit users, apply logs, and `.browser-profiles/{ravi|jaya}/...`.
- Auto-applied summary reports **ravi** and **jaya** counts separately; do not merge them in notifications as one pool.
- Truth-only resumes stay inside job-apply-kit `create_packet` — unchanged by this workflow.

---

## Limitations

- Self-hosted runner (`sapdesk-windows` / labels `self-hosted` + `Windows`) must be **online**.
- Easy Apply needs logged-in profiles under `.browser-profiles/`; missing login → job may exit with `needs_login` (see `apply_all_status.js`).
- CAPTCHA / ToS / fragile Submit selectors still apply — same as Pages Apply all.
- Pages `auto_applied_jobs.js` may lag a minute until the Actions job pushes `docs/`.
- Poll timeout (~12 min default) may be short for large Easy Apply batches; raise `POLL_MAX_ATTEMPTS` / `POLL_SECONDS`.
- Does not replace or break Pages / Actions; both paths remain valid.

---

## Smoke test

1. Set `GITHUB_TOKEN` in n8n env.
2. Ensure the Windows runner is idle/online.
3. **Manual: Test apply** with a small limit — temporarily set webhook body via pinning, or call:

```bash
curl -sS -X POST "$N8N_WEBHOOK_URL" -H "Content-Type: application/json" \
  -d "{\"user\":\"ravi\",\"easy_limit\":1,\"easy_submit\":false}"
```

4. Confirm a new run under [Actions → Apply all](https://github.com/raviacn95/ConsultingCompanyAutomation/actions/workflows/apply-all.yml).
5. Optional: set `NOTIFY_WEBHOOK_URL` and re-run to verify Discord/Slack.

---

## Related repo docs

- Root README → **GitHub Pages + Run now / Apply all**
- `.github/workflows/apply-all.yml`
- `dashboard/run_controls.js` (browser PAT dispatch — same API as n8n)
