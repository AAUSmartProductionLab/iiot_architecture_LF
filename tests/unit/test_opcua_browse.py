import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from agent.opcua_browse import BrowseReq


@pytest.mark.parametrize("payload", [
    {"endpoint_url": "https://host"},
    {"endpoint_url": "opc.tcp://user:password@host:4840"},
    {"endpoint_url": "opc.tcp://host:bad"},
    {"endpoint_url": "opc.tcp://host:4840", "node_id": "not-a-node"},
    {"endpoint_url": "opc.tcp://host:4840", "offset": -1},
])
def test_reject_invalid_request(payload):
    with pytest.raises(ValidationError):
        BrowseReq(**payload)


def test_gateway_timeout_is_reported(monkeypatch):
    from agent import main
    async def timeout(req):
        raise TimeoutError()
    monkeypatch.setattr(main, "browse", timeout)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(main.browse_opcua(BrowseReq(endpoint_url="opc.tcp://host:4840")))
    assert exc.value.status_code == 504


def test_orchestrator_routes_to_selected_gateway(monkeypatch):
    from orchestrator import api
    monkeypatch.setattr(api.registry, "get", lambda id: {"ip": "10.0.0.25", "port": 8000} if id == "gw" else None)
    calls = []
    class Client:
        def __init__(self, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, json):
            calls.append((url, json))
            return SimpleNamespace(is_error=False, json=lambda: {"nodes": []})
    monkeypatch.setattr(api.httpx, "AsyncClient", Client)
    req = api.OpcuaBrowseReq(endpoint_url="opc.tcp://plc:4840", node_id="ns=2;s=folder", offset=100)
    assert asyncio.run(api.browse_opcua("gw", req)) == {"nodes": []}
    assert calls == [("http://10.0.0.25:8000/api/opcua/browse", req.model_dump())]
    with pytest.raises(HTTPException) as exc:
        asyncio.run(api.browse_opcua("missing", req))
    assert exc.value.status_code == 404
