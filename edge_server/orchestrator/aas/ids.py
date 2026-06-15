"""
Deterministic identifier scheme (reference URL style).

Ids are derived from a stable `system_id` so re-discovering the same gateway (or
re-provisioning the same device) upserts the existing AAS instead of duplicating.

  system_id(gateway) = serial_number
  system_id(device)  = f"{gateway_serial}_{device_key}"
"""

import re

from .. import config

BASE = config.AAS_BASE_URL.rstrip("/")


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "-", str(text))


def id_short(text: str) -> str:
    """AAS id_short allows only letters, digits and underscore (AASd-002)."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", str(text))
    if s and s[0].isdigit():
        s = "_" + s
    return s or "Item"


def gateway_system_id(serial: str) -> str:
    return _slug(serial)


def device_system_id(gateway_serial: str, device_key: str) -> str:
    return _slug(f"{gateway_serial}_{device_key}")


def aas_id(system_id: str) -> str:
    return f"{BASE}/aas/{system_id}"


def asset_id(system_id: str) -> str:
    return f"{BASE}/assets/{system_id}"


def submodel_id(system_id: str, sm_name: str) -> str:
    return f"{BASE}/submodels/instances/{system_id}/{sm_name}"
