"""Bounded, read-only OPC UA browsing; one short session per requested page."""
import asyncio
from urllib.parse import urlsplit

from asyncua import Client, ua
from pydantic import BaseModel, Field, field_validator


class BrowseReq(BaseModel):
    endpoint_url: str = Field(min_length=1, max_length=2048)
    node_id: str = Field(default="i=85", max_length=2048)  # Objects
    offset: int = Field(default=0, ge=0, le=5000)

    @field_validator("endpoint_url")
    @classmethod
    def endpoint(cls, value):
        url = urlsplit(value)
        if url.scheme != "opc.tcp" or not url.hostname or url.username or url.password:
            raise ValueError("Use an opc.tcp://host:port endpoint without credentials")
        _ = url.port  # validate malformed port numbers
        return value

    @field_validator("node_id")
    @classmethod
    def node(cls, value):
        try:
            ua.NodeId.from_string(value)
        except Exception as exc:
            raise ValueError("Invalid OPC UA NodeId") from exc
        return value


TYPES = {"Boolean": "bool", "SByte": "int8", "Byte": "uint8", "Int16": "int16",
         "UInt16": "uint16", "Int32": "int32", "UInt32": "uint32", "Int64": "int64",
         "UInt64": "uint64", "Float": "float32", "Double": "float64", "String": "string"}


async def browse(req: BrowseReq):
    async with asyncio.timeout(15):
        async with Client(req.endpoint_url, timeout=4) as client:
            params = ua.BrowseParameters()
            params.RequestedMaxReferencesPerNode = 100
            desc = ua.BrowseDescription()
            desc.NodeId = ua.NodeId.from_string(req.node_id)
            desc.ReferenceTypeId = ua.NodeId(ua.ObjectIds.HierarchicalReferences)
            desc.IncludeSubtypes = True
            desc.NodeClassMask = int(ua.NodeClass.Object | ua.NodeClass.Variable)
            desc.ResultMask = int(ua.BrowseResultMask.All)
            params.NodesToBrowse = [desc]
            result = (await client.uaclient.browse(params))[0]
            refs = []
            continuation = None
            try:
                while True:
                    result.StatusCode.check()
                    continuation = result.ContinuationPoint
                    refs.extend(result.References or [])
                    if len(refs) >= req.offset + 100 or not continuation:
                        break
                    nxt = ua.BrowseNextParameters()
                    nxt.ReleaseContinuationPoints = False
                    nxt.ContinuationPoints = [continuation]
                    result = (await client.uaclient.browse_next(nxt))[0]
                more = bool(continuation) or len(refs) > req.offset + 100
            finally:
                if continuation:
                    release = ua.BrowseNextParameters()
                    release.ReleaseContinuationPoints = True
                    release.ContinuationPoints = [continuation]
                    await client.uaclient.browse_next(release)

            async def describe(ref):
                nid = ref.NodeId.to_string()
                item = {"node_id": nid, "name": ref.DisplayName.Text or ref.BrowseName.Name or nid,
                        "node_class": ref.NodeClass.name, "datatype": None, "type_label": "",
                        "selectable": False}
                if ref.NodeClass == ua.NodeClass.Variable:
                    try:
                        node = client.get_node(ref.NodeId)
                        dtype = await node.read_data_type_as_variant_type()
                        rank = await node.read_value_rank()
                        item["type_label"] = dtype.name + (" (array or unspecified rank)" if rank != -1 else "")
                        item["datatype"] = TYPES.get(dtype.name) if rank == -1 else None
                        item["selectable"] = item["datatype"] is not None
                    except Exception:
                        item["type_label"] = "Type unavailable; enter manually"
                return item

            nodes = []
            # Sequential bounded reads avoid overwhelming resource-constrained PLCs.
            for ref in refs[req.offset:req.offset + 100]:
                nodes.append(await describe(ref))
            return {"nodes": nodes, "next_offset": req.offset + 100 if more and req.offset < 5000 else None,
                    "limit_reached": more and req.offset >= 5000}
