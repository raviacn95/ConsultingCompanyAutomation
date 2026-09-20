# Start local n8n for Job Apply Easier (Windows).
# Uses repo-local `n8n/node_modules` (npm install n8n once).
# Secrets stay in process env only — never committed.
#
# Usage:
#   .\n8n\start.ps1
#   .\n8n\start.ps1 -Background

param(
  [switch]$Background
)

$ErrorActionPreference = "Stop"
$N8nDir = $PSScriptRoot
$DataDir = Join-Path $N8nDir ".n8n-data"
$N8nCmd = Join-Path $N8nDir "node_modules\.bin\n8n.cmd"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

if (-not (Test-Path $N8nCmd)) {
  Write-Host "n8n not installed. Run: cd n8n; npm install n8n"
  exit 1
}

function Resolve-GitHubToken {
  if ($env:GITHUB_TOKEN -and $env:GITHUB_TOKEN.Trim().Length -gt 0) {
    return $env:GITHUB_TOKEN.Trim()
  }
  if ($env:GH_TOKEN -and $env:GH_TOKEN.Trim().Length -gt 0) {
    return $env:GH_TOKEN.Trim()
  }
  try {
    $saved = $env:GITHUB_TOKEN
    Remove-Item Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
    $tok = (gh auth token 2>$null)
    if ($saved) { $env:GITHUB_TOKEN = $saved }
    if ($tok) { return "$tok".Trim() }
  } catch {}
  return $null
}

$token = Resolve-GitHubToken
if ($token) { $env:GITHUB_TOKEN = $token }

if (-not $env:GITHUB_OWNER) { $env:GITHUB_OWNER = "raviacn95" }
if (-not $env:GITHUB_REPO) { $env:GITHUB_REPO = "ConsultingCompanyAutomation" }
if (-not $env:GITHUB_REF) { $env:GITHUB_REF = "main" }

$env:N8N_USER_FOLDER = $DataDir
$env:N8N_BLOCK_ENV_ACCESS_IN_NODE = "false"
if (-not $env:N8N_PORT) { $env:N8N_PORT = "5678" }
if (-not $env:N8N_DIAGNOSTICS_ENABLED) { $env:N8N_DIAGNOSTICS_ENABLED = "false" }
if (-not $env:N8N_PERSONALIZATION_ENABLED) { $env:N8N_PERSONALIZATION_ENABLED = "false" }
if (-not $env:N8N_HOST) { $env:N8N_HOST = "localhost" }
if (-not $env:N8N_PROTOCOL) { $env:N8N_PROTOCOL = "http" }
if (-not $env:N8N_WEBHOOK_URL) { $env:N8N_WEBHOOK_URL = "http://localhost:$($env:N8N_PORT)/" }
# Keep legacy alias for older docs
if (-not $env:WEBHOOK_URL) { $env:WEBHOOK_URL = $env:N8N_WEBHOOK_URL }

Write-Host "n8n data: $DataDir"
Write-Host "UI:       http://localhost:$($env:N8N_PORT)"
Write-Host "GITHUB_TOKEN set: $(if ($env:GITHUB_TOKEN) { 'yes' } else { 'NO — set before use' })"
Write-Host "GITHUB_OWNER/REPO: $($env:GITHUB_OWNER)/$($env:GITHUB_REPO)"
Write-Host "NOTIFY_WEBHOOK_URL: $(if ($env:NOTIFY_WEBHOOK_URL) { 'set' } else { 'unset (optional)' })"

if ($Background) {
  $outLog = Join-Path $DataDir "n8n-stdout.log"
  $errLog = Join-Path $DataDir "n8n-stderr.log"
  $pidFile = Join-Path $DataDir "n8n.pid"
  # Use Start-Process with Redirect* so we don't fight nested quoting
  $p = Start-Process -FilePath $N8nCmd `
    -WorkingDirectory $N8nDir `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru
  Set-Content -Path $pidFile -Value $p.Id
  Write-Host "Started background PID $($p.Id); logs under $DataDir"
} else {
  Set-Location $N8nDir
  & $N8nCmd
}
