#!/usr/bin/env bash
# Rebuild + restart the edge-gateway stack in the correct order:
#   1. tear the stack down (+ any per-connector adapter containers)
#   2. (re)build the agent image and the connector-adapter image
#   3. bring hivemq up, then the agent (compose orders them via depends_on)
#
# mDNS auto-discovery needs host networking (Linux only); it's ON by default.
# On Windows/Mac Docker Desktop host mode binds the VM, not the LAN, so run:
#   USE_HOST_NET=0 ./redeploy.sh
#
# Pass --sim to also (re)build and restart the S7 simulator after the gateway is
# back up. The down/up recreates gateway-net, so the sim must be restarted after.
set -eu

cd "$(dirname "$0")"

SIM=0
for arg in "$@"; do
  case "$arg" in
    --sim) SIM=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

BASE="-f docker-compose.yaml"
if [ "${USE_HOST_NET:-1}" = "1" ]; then
  HOST="-f docker-compose.host.yml"
else
  HOST=""
fi

echo "==> [1/5] Stopping the gateway stack"
docker compose $BASE $HOST down

echo "==> [2/5] Removing stale per-connector adapter containers"
# Adapters are launched by the agent via the Docker socket, not by compose, so a
# plain 'down' leaves them running on the old image. Drop them by their label.
docker ps -aq --filter "label=iiot.role=adapter" | xargs -r docker rm -f

echo "==> [3/5] Preparing the bridge extension"
EXT="broker/extensions/hivemq-bridge-extension"
# config.xml is gitignored + rewritten at runtime; seed it from the tracked
# template only when absent, so a configured broker <host> survives redeploys.
CFG="$EXT/conf/config.xml"
if [ ! -f "$CFG" ]; then
  cp "$CFG.template" "$CFG"
  echo "    seeded $CFG from template"
fi
# HiveMQ runs as a non-root user (uid 10000) and writes bridge.id / DISABLED into
# the extension dir at startup. On Linux bind mounts it must be able to create
# files there, or the extension fails to start with "Permission denied". Make the
# directories writable by any uid (files are left untouched).
find "$EXT" -type d -exec chmod a+rwx {} + 2>/dev/null || true
# HiveMQ drops a DISABLED marker when the extension's trial lapses (or fails to
# start); clearing it re-enables the bridge on the next start.
if [ -f "$EXT/DISABLED" ]; then
  rm -f "$EXT/DISABLED"
  echo "    removed $EXT/DISABLED"
fi

echo "==> [4/5] Building images (gateway-agent + connector-adapter)"
# connector-adapter is a build-only service behind the 'build' profile.
docker compose $BASE --profile build build

echo "==> [5/5] Starting the stack (hivemq, then the agent)"
# Safety-net: force-remove any leftover containers that share the fixed
# container_name values, in case a previous compose down didn't clean up.
docker rm -f hivemq gateway-agent 2>/dev/null || true
docker compose $BASE $HOST up -d

# Optional: restart the S7 simulator (own compose project so it doesn't treat the
# gateway containers as orphans). Runs after the gateway so gateway-net exists.
if [ "$SIM" = "1" ]; then
  echo "==> Restarting the S7 simulator (--sim)"
  docker compose -p s7-sim -f docker-compose.sim.yml down
  docker compose -p s7-sim -f docker-compose.sim.yml up -d --build
fi

echo
echo "Current state:"
docker compose $BASE $HOST ps

cat <<'EOF'

Done.
- Connectors are restored into the manifest from the persisted volume, but their
  adapter containers are NOT auto-relaunched. Re-provision (or delete + re-add)
  each connector in the UI to start its adapter on the freshly built image.
- The S7 simulator is left alone unless you pass --sim. To restart it manually:
    docker compose -p s7-sim -f docker-compose.sim.yml up -d --build
EOF
