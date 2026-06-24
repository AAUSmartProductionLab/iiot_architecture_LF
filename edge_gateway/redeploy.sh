#!/usr/bin/env bash
# Rebuild + restart the edge-gateway stack in the correct order:
#   1. tear the stack down (+ any per-connector adapter containers)
#   2. (re)build the agent image and the connector-adapter image
#   3. bring hivemq up, then the agent (compose orders them via depends_on)
#
# mDNS auto-discovery needs host networking (Linux only); it's ON by default.
# On Windows/Mac Docker Desktop host mode binds the VM, not the LAN, so run:
#   USE_HOST_NET=0 ./redeploy.sh
set -eu

cd "$(dirname "$0")"

BASE="-f docker-compose.yaml"
if [ "${USE_HOST_NET:-1}" = "1" ]; then
  HOST="-f docker-compose.host.yml"
else
  HOST=""
fi

echo "==> [1/4] Stopping the gateway stack"
docker compose $BASE $HOST down

echo "==> [2/4] Removing stale per-connector adapter containers"
# Adapters are launched by the agent via the Docker socket, not by compose, so a
# plain 'down' leaves them running on the old image. Drop them by their label.
docker ps -aq --filter "label=iiot.role=adapter" | xargs -r docker rm -f

echo "==> [3/4] Building images (gateway-agent + connector-adapter)"
# connector-adapter is a build-only service behind the 'build' profile.
docker compose $BASE --profile build build

echo "==> [4/4] Starting the stack (hivemq, then the agent)"
docker compose $BASE $HOST up -d

echo
echo "Current state:"
docker compose $BASE $HOST ps

cat <<'EOF'

Done.
- Connectors are restored into the manifest from the persisted volume, but their
  adapter containers are NOT auto-relaunched. Re-provision (or delete + re-add)
  each connector in the UI to start its adapter on the freshly built image.
- If you use the S7 simulator, restart it too (the down recreated gateway-net):
    docker compose -f docker-compose.sim.yml up -d --build
EOF
