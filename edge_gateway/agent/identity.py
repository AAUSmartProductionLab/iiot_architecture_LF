"""Zero-config, stable gateway identity (Linux/Windows, stdlib only).

Resolves gateway_id/serial_number, persisting them so a gateway keeps the same
identity (and AAS) across restarts. Per field, in order:
  1. env (GATEWAY_ID / SERIAL_NUMBER)
  2. persisted identity file (IDENTITY_FILE)
  3. derived from a stable machine token, then persisted
  4. random UUID, then persisted

Identity is keyed to the machine token / file, so several simulated gateways on
one host collide — set distinct GATEWAY_ID or IDENTITY_FILE per instance.
"""

import json
import os
import re
import socket
import sys
import uuid
from pathlib import Path

IDENTITY_FILE = os.getenv(
    "IDENTITY_FILE",
    str(Path(__file__).resolve().parent / "agent_identity.json"),
)


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return s or "gateway"


def _machine_token() -> str:
    """Best-effort stable per-machine token (hex). Falls back to MAC, then random."""
    # Linux
    for p in ("/etc/machine-id", "/var/lib/dbus/machine-id"):
        try:
            v = Path(p).read_text().strip()
            if v:
                return v
        except Exception:
            pass
    # Windows registry MachineGuid
    if sys.platform.startswith("win"):
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography"
            ) as k:
                val, _ = winreg.QueryValueEx(k, "MachineGuid")
                if val:
                    return str(val).replace("-", "")
        except Exception:
            pass
    # MAC-based node id
    node = uuid.getnode()
    if node:
        return f"{node:012x}"
    return uuid.uuid4().hex  # last resort


def _load_file(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _save_file(path: str, data: dict) -> None:
    try:
        Path(path).write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # non-fatal: identity still holds for this process lifetime


def resolve_identity() -> dict:
    stored = _load_file(IDENTITY_FILE)

    gateway_id = os.getenv("GATEWAY_ID") or stored.get("gateway_id")
    serial = os.getenv("SERIAL_NUMBER") or stored.get("serial_number")

    if not gateway_id or not serial:
        token = _machine_token()
        if not gateway_id:
            gateway_id = f"gw-{_slug(socket.gethostname())}-{token[:6]}"
        if not serial:
            serial = f"SN-{token[:12].upper()}"
        _save_file(IDENTITY_FILE, {"gateway_id": gateway_id, "serial_number": serial})

    return {"gateway_id": gateway_id, "serial_number": serial}
