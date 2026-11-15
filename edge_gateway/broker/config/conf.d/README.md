`bridge.conf` in this directory is written by the gateway agent when the bridge is
configured from the dashboard (POST /api/configure) and is not tracked in git.
Mosquitto loads every `*.conf` here at startup.
