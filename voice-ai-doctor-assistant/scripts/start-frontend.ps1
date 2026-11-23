# Windows PowerShell: install and start the dashboard on http://localhost:5173
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\frontend")
if (-not (Test-Path node_modules)) { npm install }
npm run dev
