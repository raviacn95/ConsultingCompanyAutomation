# n8n local setup (this machine)

Self-hosted n8n for **Job Apply Easier**, started automatically under this repo.

## Open

| Item | Value |
|---|---|
| **UI** | http://localhost:5678 |
| **Production webhook** | `POST http://localhost:5678/webhook/job-apply-easier` |
| **Port** | `5678` |
| **Data dir** | `n8n/.n8n-data/` (gitignored) |
| **n8n version** | `2.39.8` (local `n8n/node_modules`) |

Owner account was created for the editor. Login details are only in the gitignored file `n8n/.n8n-data/OWNER_CREDS.txt` — change the password after first login.

## How it was started

1. Installed n8n locally: `cd n8n && npm install n8n` (not global, not Docker).
2. Imported `workflows/job-apply-easier.json` via CLI (`n8n import:workflow`).
3. Published/activated the workflow (`n8n publish:workflow --id=job-apply-easier`).
4. Started with `.\n8n\start.ps1 -Background`.

Process env for the n8n process includes:

- `GITHUB_TOKEN` — from `gh auth token` (keyring account with `repo` + `workflow`); **not** written to any committed file
- `GITHUB_OWNER=raviacn95`
- `GITHUB_REPO=ConsultingCompanyAutomation`
- `GITHUB_REF=main`
- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`
- `N8N_USER_FOLDER` → `n8n/.n8n-data`
- `NOTIFY_WEBHOOK_URL` — **not set** (optional Discord/Slack)

PID of the listening process is stored in `n8n/.n8n-data/n8n.pid`. Logs: `n8n-stdout.log` / `n8n-stderr.log` in the same folder.

## Restart

```powershell
# Stop (uses PID file if present)
$pidPath = "n8n\.n8n-data\n8n.pid"
if (Test-Path $pidPath) {
  $p = Get-Content $pidPath
  Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
}
# Also free the port if needed
Get-NetTCPConnection -LocalPort 5678 -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }

# Start again (resolves GITHUB_TOKEN from env or gh auth)
.\n8n\start.ps1 -Background
```

Foreground (logs in the terminal): `.\n8n\start.ps1`

If `node_modules` is missing: `cd n8n; npm install n8n`

## Smoke test (safe)

Watch-only (no Easy Apply submit):

```powershell
Invoke-RestMethod -Uri "http://localhost:5678/webhook/job-apply-easier" `
  -Method POST -ContentType "application/json" `
  -Body '{"action":"watch","mail":true}'
```

Or apply without submitting Easy Apply:

```powershell
Invoke-RestMethod -Uri "http://localhost:5678/webhook/job-apply-easier" `
  -Method POST -ContentType "application/json" `
  -Body '{"user":"ravi","easy_limit":1,"easy_submit":false}'
```

The webhook waits until the Actions run finishes (or poll timeout). Confirm runs at:
https://github.com/raviacn95/ConsultingCompanyAutomation/actions

## Optional remaining step

Set `NOTIFY_WEBHOOK_URL` in the process environment (Discord or Slack incoming webhook) before restart if you want completion notifications. Not required for apply/watch.

## Related

See [README.md](README.md) for workflow inputs and dual-user safety notes.
