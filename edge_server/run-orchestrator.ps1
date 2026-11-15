<#
Run the edge-server orchestrator natively on Windows (see redeploy.ps1 for why).
Uses the .venv created by redeploy.ps1. Keep the window open; Ctrl+C stops it.

  powershell -ExecutionPolicy Bypass -File run-orchestrator.ps1

The server address is detected automatically; override it with $env:SERVER_IP,
$env:PUBLIC_API_BASE_URL and $env:PUBLIC_MQTT_URL if detection picks a VPN or
other wrong interface. Other orchestrator settings (e.g. DISCOVERY_ENABLED) are
read from the environment the same way.
#>
Set-Location $PSScriptRoot

$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { throw 'No .venv found. Run redeploy.ps1 first.' }

# Free port 8000 if the Docker orchestrator was started (e.g. by 'docker compose up -d').
docker stop orchestrator 2>$null | Out-Null

$serverIp = & $venvPy -c 'from orchestrator import config; print(config.resolve_server_ip())'
Write-Host ''
Write-Host 'Dashboard:        http://localhost:5173'
Write-Host 'Orchestrator API: http://localhost:8000/api/health'
Write-Host "Gateways bridge to this server at $serverIp (set `$env:SERVER_IP to override)."
Write-Host 'Keep this window open; Ctrl+C stops the orchestrator.'
Write-Host ''
& $venvPy -m uvicorn orchestrator.main:app --host 0.0.0.0 --port 8000
