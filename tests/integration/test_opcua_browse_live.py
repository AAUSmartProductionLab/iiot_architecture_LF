"""Browse real OPC UA folders, types and pages against the Festo simulator."""
import asyncio
import socket

from asyncua import ua
from agent.opcua_browse import BrowseReq, browse
from festo_module import create_server, node_id, POINTS


def test_browse_festo_and_pages():
    async def check():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        endpoint = f"opc.tcp://127.0.0.1:{port}"
        server, _ = await create_server(endpoint)
        folder = await server.nodes.objects.add_object(2, "ManyTags")
        for i in range(105):
            await folder.add_variable(ua.NodeId(f"many_{i}", 2), f"Tag{i}", ua.Variant(i, ua.VariantType.Int32))
        array = await folder.add_variable(ua.NodeId("array", 2), "Array", [1, 2])
        async with server:
            root = await browse(BrowseReq(endpoint_url=endpoint))
            module = next(n for n in root["nodes"] if n["name"] == "FestoTrialModule")
            result = await browse(BrowseReq(endpoint_url=endpoint, node_id=module["node_id"]))
            assert len(result["nodes"]) == 9
            expected = {node_id(s): "bool" if dt == "Boolean" else dt.lower() for _, s, dt in POINTS}
            assert {n["node_id"]: n["datatype"] for n in result["nodes"]} == expected
            assert all(n["selectable"] for n in result["nodes"])
            first = await browse(BrowseReq(endpoint_url=endpoint, node_id=folder.nodeid.to_string()))
            assert len(first["nodes"]) == 100 and first["next_offset"] == 100
            second = await browse(BrowseReq(endpoint_url=endpoint, node_id=folder.nodeid.to_string(), offset=100))
            assert len(second["nodes"]) == 6 and second["next_offset"] is None
            assert not set(n["node_id"] for n in first["nodes"]) & set(n["node_id"] for n in second["nodes"])
            item = next(n for n in second["nodes"] if n["node_id"] == array.nodeid.to_string())
            assert not item["selectable"]
    asyncio.run(check())
