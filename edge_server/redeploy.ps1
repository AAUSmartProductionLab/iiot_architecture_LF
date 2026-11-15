<#
Rebuild and restart the edge server on Windows (Docker Desktop, PowerShell 5.1+).

Everything runs in Docker except the orchestrator, which runs as a native Python
process. Inside Docker Desktop's VM the orchestrator can neither receive the
gateways' mDNS announcements nor see this PC's LAN address; natively, both work
without configuration.

  powershell -ExecutionPolicy Bypass -File redeploy.ps1           # rebuild, then run the orchestrator here
  powershell -ExecutionPolicy Bypass -File redeploy.ps1 -NoStart  # rebuild only; start it with run-orchestrator.ps1

Data volumes are preserved. Requires Docker Desktop and Python 3.11 or later.
#>
param([switch]$NoStart)

Set-Location $PSScriptRoot

function Log([string]$msg) { Write-Host "==> $msg" -ForegroundColor Green }

# Native commands do not throw on failure; check their exit code explicitly.
function Exec([string]$what, [scriptblock]$cmd) {
    & $cmd
    if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

function Find-Python {
    # Prefer the active environment (venv/conda), then the py launcher. The
    # version probe also skips the Microsoft Store 'python' alias.
    foreach ($candidate in @(@('python'), @('py', '-3'), @('python3'))) {
        if (-not (Get-Command $candidate[0] -ErrorAction SilentlyContinue)) { continue }
        $extra = @($candidate | Select-Object -Skip 1)
        $ok = & $candidate[0] @extra -c 'import sys; print(sys.version_info >= (3, 11))' 2>$null
        if ($ok -eq 'True') { return @{ Exe = $candidate[0]; Args = $extra } }
    }
    throw 'Python 3.11 or later was not found. Install it from https://www.python.org/downloads/ and re-run.'
}

function Stop-NativeOrchestrator {
    $procs = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'orchestrator\.main:app' })
    foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($procs.Count -gt 0) { Log 'Stopped the running native orchestrator' }
}

Log '[1/4] Stopping the edge-server stack'
Stop-NativeOrchestrator
Exec 'docker compose down' { docker compose down }

Log '[2/4] Preparing the orchestrator Python environment (.venv)'
$venvPy = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    $py = Find-Python
    $pyArgs = $py.Args
    Exec 'creating .venv' { & $py.Exe @pyArgs -m venv .venv }
}
Exec 'installing orchestrator requirements' {
    & $venvPy -m pip install --quiet --disable-pip-version-check -r requirements.txt
}

Log '[3/4] Building and starting the Docker services (all except the orchestrator)'
$services = @(docker compose config --services | Where-Object { $_ -and $_ -ne 'orchestrator' })
if ($services.Count -eq 0) { throw 'docker compose config returned no services' }
# Safety net: remove leftovers that share the fixed container names (as in redeploy.sh).
docker rm -f timescale hivemq mqtt-broker aas-environment aas-gui orchestrator 2>$null | Out-Null
Exec 'docker compose up' { docker compose up -d --build @services }
docker compose ps

if ($NoStart) {
    Log 'Done. Start the orchestrator with: powershell -ExecutionPolicy Bypass -File run-orchestrator.ps1'
    return
}
Log '[4/4] Starting the orchestrator (native)'
& (Join-Path $PSScriptRoot 'run-orchestrator.ps1')
