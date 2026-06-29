# run_demo.ps1 — bring up the full demo:
#   - Docker: api (:8000) + scheduler, running against the LOCAL Postgres (current data)
#   - UI (Next.js) on :3000 in its own window
#
#   Usage:  powershell -ExecutionPolicy Bypass -File .\run_demo.ps1
#
# The Docker services use `restart: unless-stopped`, so after a reboot they come
# back on their own — you then only need the UI (this script relaunches both safely).

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Write-Host "Starting Docker api + scheduler (against local Postgres)..." -ForegroundColor Cyan
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build api scheduler

Write-Host "Waiting for API health..." -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(60); $apiOk = $false
while ((Get-Date) -lt $deadline) {
  try { if ((Invoke-RestMethod http://localhost:8000/health -TimeoutSec 5).status -eq "ok") { $apiOk = $true; break } } catch {}
  Start-Sleep -Seconds 3
}
if ($apiOk) { Write-Host "API healthy -> http://localhost:8000" -ForegroundColor Green } else { Write-Host "API not healthy yet — check: docker compose logs api" -ForegroundColor Yellow }

Write-Host "Launching UI on http://localhost:3000 ..." -ForegroundColor Cyan
Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue |
  Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { try { Stop-Process -Id $_ -Force } catch {} }
# Launch via cmd so npm.cmd is used (PowerShell blocks npm.ps1 by default).
Start-Process cmd -ArgumentList '/k', "cd /d $root\ui && npm run dev"

Write-Host ""
Write-Host "Demo is starting:" -ForegroundColor Green
Write-Host "  UI         http://localhost:3000" -ForegroundColor Green
Write-Host "  API docs   http://localhost:8000/docs" -ForegroundColor Green
Write-Host "  Scheduler  docker compose logs -f scheduler" -ForegroundColor Green
Write-Host ""
Write-Host "Stop Docker services with:  docker compose down"
