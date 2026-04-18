<#
.SYNOPSIS
    One-click connect to your Vast.ai drone simulation.
.DESCRIPTION
    Reads connection info from .vast-connection.json (saved by deploy_vast_vm.py),
    opens an SSH tunnel, and launches the browser. No arguments needed.
.EXAMPLE
    .\scripts\vast_connect.ps1
#>

param(
  [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"

# ── Locate connection config ────────────────────────────────────────
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }

# Search order: explicit param → repo root → script dir parent
$searchPaths = @()
if ($ConfigPath) { $searchPaths += $ConfigPath }
$searchPaths += Join-Path $PSScriptRoot "..\\.vast-connection.json"
$searchPaths += Join-Path $PSScriptRoot ".vast-connection.json"

$configFile = $null
foreach ($candidate in $searchPaths) {
  $resolved = Resolve-Path $candidate -ErrorAction SilentlyContinue
  if ($resolved -and (Test-Path $resolved)) {
    $configFile = $resolved.Path
    break
  }
}

if (-not $configFile) {
  Write-Host ""
  Write-Host "  ERROR: No .vast-connection.json found." -ForegroundColor Red
  Write-Host ""
  Write-Host "  Run the deploy script first:" -ForegroundColor Yellow
  Write-Host "    python scripts/deploy_vast_vm.py --host <IP> --port <PORT> --ssh-key <KEY>" -ForegroundColor DarkGray
  Write-Host ""
  exit 1
}

$config = Get-Content $configFile -Raw | ConvertFrom-Json
$RemoteHost = $config.host
$Port = $config.port
$User = if ($config.user) { $config.user } else { "root" }
$KeyPath = if ($config.ssh_key) { $config.ssh_key } else { "$HOME\.ssh\vast_key" }

# ── Display connection info ─────────────────────────────────────────
Write-Host ""
Write-Host "  ╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "  ║     DRONE-MCP SIMULATION CONNECT         ║" -ForegroundColor Cyan
Write-Host "  ╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Server:  ${User}@${RemoteHost}:${Port}" -ForegroundColor White
Write-Host "  Key:     ${KeyPath}" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Opening SSH tunnel..." -ForegroundColor Yellow

# ── Check if tunnel ports are already in use ────────────────────────
$portsInUse = @()
foreach ($p in @(8080, 6080, 5900)) {
  $conn = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue
  if ($conn) { $portsInUse += $p }
}
if ($portsInUse.Count -gt 0) {
  Write-Host ""
  Write-Host "  WARNING: Ports already in use: $($portsInUse -join ', ')" -ForegroundColor Yellow
  Write-Host "  Another tunnel may be running. Close it first or press Enter to try anyway." -ForegroundColor DarkGray
  Read-Host "  Press Enter to continue"
}

# ── Launch browser after short delay ────────────────────────────────
$browserJob = Start-Job -ScriptBlock {
  Start-Sleep -Seconds 3
  Start-Process "http://127.0.0.1:8080"
}

# ── Print access info ───────────────────────────────────────────────
Write-Host ""
Write-Host "  ┌──────────────────────────────────────────┐" -ForegroundColor Green
Write-Host "  │  Operator UI:   http://127.0.0.1:8080    │" -ForegroundColor Green
Write-Host "  │  noVNC Viewer:  http://127.0.0.1:6080    │" -ForegroundColor Green
Write-Host "  │  Raw VNC:       localhost::5900           │" -ForegroundColor Green
Write-Host "  └──────────────────────────────────────────┘" -ForegroundColor Green
Write-Host ""
Write-Host "  Browser will open automatically in 3 seconds..." -ForegroundColor DarkGray
Write-Host "  Press Ctrl+C to disconnect." -ForegroundColor DarkGray
Write-Host ""

# ── Open SSH tunnel (blocks until Ctrl+C) ───────────────────────────
ssh `
  -i $KeyPath `
  -o StrictHostKeyChecking=accept-new `
  -o ConnectTimeout=10 `
  -o ServerAliveInterval=30 `
  -o ServerAliveCountMax=3 `
  -N `
  -L 8080:127.0.0.1:8080 `
  -L 6080:127.0.0.1:6080 `
  -L 5900:127.0.0.1:5900 `
  -p $Port `
  "${User}@${RemoteHost}"

# Cleanup
Remove-Job $browserJob -Force -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "  Tunnel closed." -ForegroundColor Yellow
