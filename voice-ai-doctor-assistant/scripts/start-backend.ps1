# Windows PowerShell: create venv (first run), install, start the API on http://127.0.0.1:8000
# Usage:  .\scripts\start-backend.ps1            (mock mode, no keys)
#         .\scripts\start-backend.ps1 -Live      (needs backend\.env with real keys)
param([switch]$Live)
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\backend")
if (-not (Test-Path .venv)) { py -3 -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
if ($Live) {
  & .\.venv\Scripts\python.exe -m pip install -r requirements-live.txt
  if (-not (Test-Path .env)) { Copy-Item .env.example .env; Write-Host "Created backend\.env - add your keys and set APP_MODE=live, then run again." -ForegroundColor Yellow; exit 1 }
  $env:APP_MODE = "live"
} else {
  & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
}
& .\.venv\Scripts\python.exe run.py
