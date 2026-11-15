# Verify stored data

The read-only verifier checks recent measurements against the simulator definitions:
expected topics, device identities, datapoint names, units and JSON types. It does
not deploy flows or change database contents.

Set PostgreSQL environment variables `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and
`PGPASSWORD`, then run from the repository root:

```bash
python tests/evaluation/verify_contract.py --condition full --gateway-serial GW1 --protocol festo --since 2026-11-15T10:00:00Z
```

Replace `GW1` with the gateway's manifest serial and `--since` with the start of
your test. For Node-RED use `--condition baseline` and omit `--gateway-serial`.
Set `UNS_PREFIX` if different from `uns/enterprise/site/area/line`.

The default fixture is `festo`; the generic simulators also support `--protocol
opcua`, `modbus` or `s7`. Output is JSON, with exit code 0 when all points pass
and 1 otherwise. Compare values with a direct source read to verify physical accuracy.

See the [Festo setup](../simulators/FESTO.md) and [Node-RED instructions](../README.md).

## Mapping and discovery controls

Both server environment settings default to `true`:

| Setting | When disabled |
| --- | --- |
| `DISCOVERY_ENABLED=false` | Register gateways manually; liveness checks remain active. |
| `AUTO_MAPPING_ENABLED=false` | Populate `topic_map` manually; AAS events and backfill do not update mappings. |

Recreate the affected orchestrator or ingestor service after changing these settings.
Restart the ingestor after manual SQL changes to reload its mapping cache. Existing
mappings are not deleted when automatic mapping is disabled.
