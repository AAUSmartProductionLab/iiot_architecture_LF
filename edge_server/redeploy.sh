#!/usr/bin/env bash
# Rebuild + restart the edge-server stack (orchestrator, BaSyx, HiveMQ, ingestor,
# TimescaleDB, dashboard) in one step. Data volumes are preserved.
#
# mDNS auto-discovery needs host networking (Linux only); it's ON by default. On
# Windows/Mac Docker Desktop host mode binds the VM, not the LAN, so run:
#   USE_HOST_NET=0 ./redeploy.sh
# which starts the orchestrator in bridge mode (no mDNS — register gateways with
# the dashboard's "Register gateway" button).
set -eu

cd "$(dirname "$0")"

BASE="-f docker-compose.yaml"
if [ "${USE_HOST_NET:-1}" = "1" ]; then
  HOST="-f docker-compose.host.yml"
else
  HOST=""
fi

echo "==> [1/3] Stopping the edge-server stack"
docker compose $BASE $HOST down

echo "==> [2/3] Building images (orchestrator, ingestor, dashboard)"
docker compose $BASE build

echo "==> [3/3] Starting the stack"
docker compose $BASE $HOST up -d

echo
echo "Current state:"
docker compose $BASE $HOST ps

cat <<'EOF'

Done.
- Dashboard:        http://localhost:5173
- AAS viewer:       http://localhost:8082
- Orchestrator API: http://localhost:8000/api/health
Data volumes (TimescaleDB, HiveMQ, AAS) are preserved across redeploys; add `-v`
to a manual `docker compose down` only if you want to wipe them.
EOF
