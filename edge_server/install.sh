#!/usr/bin/env bash
# One-line installer for the IIoT edge server: clones (or updates) the repo and
# brings the server stack up via edge_server/redeploy.sh.
#
#   curl -fsSL https://raw.githubusercontent.com/AAUSmartProductionLab/iiot_architecture_LF/main/edge_server/install.sh | bash
#
# Override defaults via env vars, e.g. to pin a branch / install location and run
# without host networking (Windows/Mac):
#   curl -fsSL <url> | BRANCH=main TARGET_DIR=~/iiot USE_HOST_NET=0 bash
set -eu

REPO_URL="${REPO_URL:-https://github.com/AAUSmartProductionLab/iiot_architecture_LF.git}"
BRANCH="${BRANCH:-main}"
TARGET_DIR="${TARGET_DIR:-$HOME/iiot_architecture_LF}"
export USE_HOST_NET="${USE_HOST_NET:-1}"  # consumed by redeploy.sh

log() { printf '\033[1;32m==>\033[0m %s\n' "$*"; }
err() { printf '\033[1;31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# --- prerequisites ----------------------------------------------------------
command -v git >/dev/null 2>&1    || err "git is not installed."
command -v docker >/dev/null 2>&1 || err "docker is not installed."
docker compose version >/dev/null 2>&1 || err "docker compose (v2) is not available."
docker info >/dev/null 2>&1        || err "cannot talk to the Docker daemon. If dockerd is running, your user is likely not in the 'docker' group: run  sudo usermod -aG docker \$USER  then re-login (or 'newgrp docker') and retry."

# --- clone or update --------------------------------------------------------
if [ -d "$TARGET_DIR/.git" ]; then
  log "Updating existing checkout in $TARGET_DIR"
  git -C "$TARGET_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$TARGET_DIR" checkout "$BRANCH"
  git -C "$TARGET_DIR" reset --hard "origin/$BRANCH"   # deploy target: match remote exactly
else
  log "Cloning $REPO_URL ($BRANCH) into $TARGET_DIR"
  git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$TARGET_DIR"
fi

# --- build + start ----------------------------------------------------------
log "Building and starting the edge-server stack"
cd "$TARGET_DIR/edge_server"
chmod +x redeploy.sh
./redeploy.sh

log "Edge server is up. Dashboard: http://localhost:5173"
