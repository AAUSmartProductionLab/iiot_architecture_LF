"""Thin Eclipse BaSyx v2 REST client + structural validator.

- IDs are Base64URL-encoded in URL paths.
- Writes are idempotent (PUT, then POST on 404); deterministic IDs avoid dupes.
- Objects are validated before posting via an AASToJsonEncoder ->
  StrictAASFromJsonDecoder round-trip.
"""

import base64
import json
import logging

import httpx
from basyx.aas.adapter.json import AASToJsonEncoder, StrictAASFromJsonDecoder

from . import config

log = logging.getLogger("basyx")

BASYX = config.BASYX_URL.rstrip("/")


def to_validated_json(obj) -> dict:
    """Serialize an AAS object to JSON, validating it via a strict round-trip."""
    payload = json.dumps(obj, cls=AASToJsonEncoder)
    json.loads(payload, cls=StrictAASFromJsonDecoder)  # raises if invalid
    return json.loads(payload)


def b64(identifier: str) -> str:
    """Base64URL-encode an AAS/Submodel identifier for use in a URL path."""
    return base64.urlsafe_b64encode(identifier.encode()).decode()


async def _upsert(client: httpx.AsyncClient, collection: str, obj_json: dict) -> None:
    enc = b64(obj_json["id"])
    r = await client.put(f"{BASYX}/{collection}/{enc}", json=obj_json)
    if r.status_code in (200, 204):
        return
    if r.status_code == 404:
        c = await client.post(f"{BASYX}/{collection}", json=obj_json)
        c.raise_for_status()
        return
    r.raise_for_status()


async def upsert_submodel(client: httpx.AsyncClient, sm_obj) -> None:
    await _upsert(client, "submodels", to_validated_json(sm_obj))


async def upsert_shell(client: httpx.AsyncClient, aas_obj) -> None:
    await _upsert(client, "shells", to_validated_json(aas_obj))


async def delete_shell_with_submodels(aas_id: str) -> bool:
    """Delete a shell and its referenced submodels from BaSyx (idempotent).

    Returns True if the shell existed and was removed, False if it was already
    absent. Missing submodels are ignored so a partial state still cleans up.
    """
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        r = await client.get(f"{BASYX}/shells/{b64(aas_id)}")
        if r.status_code == 404:
            return False
        r.raise_for_status()
        shell = r.json()
        for ref in shell.get("submodels", []):
            keys = ref.get("keys", [])
            if not keys:
                continue
            sm_id = keys[0]["value"]
            sr = await client.delete(f"{BASYX}/submodels/{b64(sm_id)}")
            if sr.status_code not in (200, 204, 404):
                sr.raise_for_status()
        dr = await client.delete(f"{BASYX}/shells/{b64(aas_id)}")
        if dr.status_code not in (200, 204, 404):
            dr.raise_for_status()
        return True


async def fetch_shell_with_submodels(aas_id: str) -> dict:
    """Read a shell and resolve its referenced submodels (for the UI proxy)."""
    async with httpx.AsyncClient(timeout=config.HTTP_TIMEOUT) as client:
        r = await client.get(f"{BASYX}/shells/{b64(aas_id)}")
        r.raise_for_status()
        shell = r.json()
        submodels = []
        for ref in shell.get("submodels", []):
            keys = ref.get("keys", [])
            if not keys:
                continue
            sm_id = keys[0]["value"]
            sr = await client.get(f"{BASYX}/submodels/{b64(sm_id)}")
            if sr.status_code == 200:
                submodels.append(sr.json())
        return {"shell": shell, "submodels": submodels}
