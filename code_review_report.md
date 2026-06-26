# IIoT Architecture Code Review Report 26/06/26

## Summary

This review focused on the gateway adapter, agent, and orchestrator code paths. The main consolidation opportunities are:

- Unify connector protocol client interfaces.
- Share connector config/request models between agent and adapter.
- Centralize device/gateway normalization logic.
- Reduce repeated AAS builder boilerplate.
- Consolidate adapter config/path handling.

## Key Findings

### 1. Connector client interface mismatch

- `edge_gateway/connectors/connector_class.py` currently supports mixed sync and async clients using `_maybe_await()`.
- ~~`S7Client` has sync `connect()`/`disconnect()` but async `subscribe()`.~~ [solved]
- `AsyncModbusClient` and `AsyncOPCUAClient` are fully async.
- ~~`AsyncOPCUAClient.subscribe()` contains a bug: it passes a node id string to `safe_read()` which expects an `OPCUAReadRequest`.~~ [solved]
- `MqttPublisher.publish()` exposes a dict-to-subtopic interface, but `Connector._publish()` bypasses it and manually publishes JSON.

### 2. Connector schema drift

- The gateway agent request model (`ConnectorReq` in `edge_gateway/agent/main.py`) is separate from adapter config validation (`edge_gateway/connectors/config_model.py`).
- The agent persists plain dict connector descriptors via `edge_gateway/agent/manifest.py`.
- The adapter reads config from env/file in `edge_gateway/connectors/run_adapter.py`.
- This creates a risk of inconsistent connector descriptor shapes between agent and adapter.

### 3. Repeated normalization and dictionary plumbing

- `device_key = c.get("device_key") or c.get("device_id")` is repeated in several files.
- `edge_server/orchestrator/registration_service.py` and `edge_server/orchestrator/api.py` repeatedly access flat dict keys on connectors and manifests.
- Similar gateway/device record shaping is repeated in registry and manifest handling.

### 4. AAS builder boilerplate

- Builder classes in `edge_server/orchestrator/aas/` share the same constructor pattern and repeated submodel creation logic.
- Common helper abstractions could reduce duplicated code in `AASBuilder`, `AssetInterfacesBuilder`, `HierarchicalStructuresBuilder`, `DigitalNameplateBuilder`, and `SoftwareNameplateBuilder`.

### 5. Adapter config persistence duplication

- `edge_gateway/agent/adapters.py` and `edge_gateway/connectors/run_adapter.py` both implement config path and loading logic.
- Centralizing this path/format logic would improve consistency and reduce drift.

## Recommended Refactor Plan

1. Define a shared `ProtocolClient` interface for adapter clients.
2. Refactor `S7Client`, `AsyncModbusClient`, and `AsyncOPCUAClient` to implement it.
3. Centralize connector descriptor schema in one shared module used by:
   - gateway API validation
   - agent manifest persistence
   - adapter config generation
   - adapter runtime parsing
4. Introduce shared helpers for connector normalization:
   - canonical `device_key` extraction
   - manifest/device descriptor access
5. Add AAS builder helpers for common submodel creation patterns.
6. Consolidate adapter config file path and config generation logic.

## High-payoff files

- `edge_gateway/connectors/connector_class.py`
- `edge_gateway/connectors/config_model.py`
- `edge_gateway/connectors/connector_components/s7_client_class.py`
- `edge_gateway/connectors/connector_components/opc_ua_client.py`
- `edge_gateway/connectors/connector_components/mqtt_pub_class.py`
- `edge_gateway/agent/main.py`
- `edge_gateway/agent/adapters.py`
- `edge_gateway/connectors/run_adapter.py`
- `edge_server/orchestrator/registration_service.py`
- `edge_server/orchestrator/api.py`
- `edge_server/orchestrator/aas/*.py`

## Important Notes

- A real bug exists in OPC UA subscribe path and should be fixed before further protocol unification.
- The connector and manifest model should be the single source of truth for both gateway and adapter.
- Shared typed models would reduce reliance on repeated dictionary access and improve maintainability.
