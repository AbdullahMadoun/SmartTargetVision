param(
  [Parameter(Mandatory = $true)]
  [Alias("Host")]
  [string]$RemoteHost,

  [Parameter(Mandatory = $true)]
  [int]$Port,

  [string]$User = "root",
  [string]$KeyPath = "$HOME\.ssh\vast_key"
)

Write-Host ""
Write-Host "  Opening SSH tunnel to ${User}@${RemoteHost}:${Port} ..." -ForegroundColor Cyan
Write-Host ""
Write-Host "  Once connected, open in your browser:" -ForegroundColor Green
Write-Host "    http://127.0.0.1:8080" -ForegroundColor Yellow
Write-Host ""
Write-Host "  For native TurboVNC Viewer (better quality on slow connections):" -ForegroundColor Green
Write-Host "    Connect to: localhost::5900   (double colon = explicit port)" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Press Ctrl+C to close the tunnel." -ForegroundColor DarkGray
Write-Host ""

ssh `
  -i $KeyPath `
  -o StrictHostKeyChecking=accept-new `
  -o ConnectTimeout=10 `
  -N `
  -L 8080:127.0.0.1:8080 `
  -L 6080:127.0.0.1:6080 `
  -L 5900:127.0.0.1:5900 `
  -p $Port `
  "${User}@${RemoteHost}"
