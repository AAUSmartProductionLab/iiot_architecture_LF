# One-line installer for the IIoT edge server on Windows (Docker Desktop,
# PowerShell 5.1+): clones (or updates) the repo, then runs
# edge_server/redeploy.ps1. That starts the Docker services and runs the
# orchestrator natively, so gateway auto-discovery works without configuration.
#
#   irm https://raw.githubusercontent.com/AAUSmartProductionLab/iiot_architecture_LF/main/edge_server/install.ps1 | iex
#
# Override defaults with environment variables before running, e.g.
#   $env:BRANCH = 'main'; $env:TARGET_DIR = "$HOME\iiot"
# Use install.sh for Linux servers.

# Scriptblock scope: 'irm | iex' runs in the caller's session, so keep variables
# local and throw instead of 'exit' (which would close the caller's window).
& {
    $RepoUrl = if ($env:REPO_URL) { $env:REPO_URL } else { 'https://github.com/AAUSmartProductionLab/iiot_architecture_LF.git' }
    $Branch = if ($env:BRANCH) { $env:BRANCH } else { 'main' }
    $TargetDir = if ($env:TARGET_DIR) { $env:TARGET_DIR } else { Join-Path $HOME 'iiot_architecture_LF' }

    function Log([string]$msg) { Write-Host "==> $msg" -ForegroundColor Green }
    function Fail([string]$msg) { throw "ERROR: $msg" }

    # --- prerequisites -------------------------------------------------------
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) { Fail 'git is not installed (https://git-scm.com/download/win).' }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Docker Desktop is not installed.' }
    docker compose version *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'docker compose (v2) is not available.' }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { Fail 'cannot talk to the Docker daemon. Start Docker Desktop and retry.' }

    # --- clone or update -----------------------------------------------------
    if (Test-Path (Join-Path $TargetDir '.git')) {
        Log "Updating existing checkout in $TargetDir"
        git -C $TargetDir fetch --depth 1 origin $Branch
        if ($LASTEXITCODE -ne 0) { Fail 'git fetch failed.' }
        git -C $TargetDir checkout $Branch
        if ($LASTEXITCODE -ne 0) { Fail 'git checkout failed.' }
        git -C $TargetDir reset --hard "origin/$Branch"  # deploy target: match remote exactly
        if ($LASTEXITCODE -ne 0) { Fail 'git reset failed.' }
    } else {
        Log "Cloning $RepoUrl ($Branch) into $TargetDir"
        git clone --branch $Branch --depth 1 $RepoUrl $TargetDir
        if ($LASTEXITCODE -ne 0) { Fail 'git clone failed.' }
    }

    # --- build + start -------------------------------------------------------
    # Own process with -ExecutionPolicy Bypass, so a restrictive policy cannot
    # block the freshly cloned script.
    Log 'Building and starting the edge server'
    $shell = (Get-Process -Id $PID).Path
    & $shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $TargetDir 'edge_server\redeploy.ps1')
}
