"""VV HA Adapter — minimal Home Assistant MCP server for the VexaVoice profile.

Exposes ONLY:
  - find_home_entities: bounded name/domain/area search -> entity_id, name, state, area
  - read_home_state:    read specific entity IDs -> state + small curated attribute set

No generic service calls, no writes, no locks/garage/camera control, no history,
no bulk enumeration. The HA long-lived token arrives via HA_TOKEN (the wrapper
script loads it from a 0600 file outside Git/config).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP

HA_BASE_URL = os.environ.get("HA_BASE_URL", "http://10.0.10.117:8123").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

# Small curated attribute surface — never return the full attribute dict.
CURATED_ATTRS = (
    "unit_of_measurement", "device_class", "state_class",
    "brightness", "color_temp_kelvin", "color_temp",
    "current_temperature", "temperature", "hvac_action",
    "current_position", "locked", "volume_level", "source",
    "battery", "battery_level", "battery_percentage", "icon",
)

_REGISTRY_CACHE: dict = {}
_REG_LOCK = threading.Lock()


def _http(method: str, path: str, body: dict | None = None, timeout: float = 8.0):
    """Call the HA REST API. Raises RuntimeError on auth/HTTP failures."""
    if not HA_TOKEN:
        raise RuntimeError("HA_TOKEN is not set — adapter cannot authenticate to Home Assistant.")
    req = urllib.request.Request(
        HA_BASE_URL + path,
        method=method,
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"Home Assistant API error {e.code} on {method} {path}: {detail}") from None


def _entity_registry() -> dict:
    """entity_id -> area name, cached 60s. Gracefully degrades to {} if registry APIs fail."""
    with _REG_LOCK:
        now = time.time()
        if _REGISTRY_CACHE and now - _REGISTRY_CACHE["ts"] < 60:
            return _REGISTRY_CACHE["reg"]
        try:
            reg = {e["entity_id"]: e for e in _http("GET", "/api/config/entity_registry")}
            areas = {a["area_id"]: a["name"] for a in _http("GET", "/api/config/area_registry")}
            out = {}
            for eid, e in reg.items():
                aid = e.get("area_id")
                out[eid] = areas.get(aid) if aid else None
            _REGISTRY_CACHE.update(ts=now, reg=out)
            return out
        except Exception:
            return _REGISTRY_CACHE.get("reg", {})


def _curated_attrs(attrs: dict) -> dict:
    return {k: attrs[k] for k in CURATED_ATTRS if k in attrs}


mcp = FastMCP("vv-ha-adapter")


@mcp.tool()
def find_home_entities(query: str = "", domain: str = "", area: str = "", limit: int = 6) -> str:
    """Find Home Assistant entities by name, entity ID, domain, or area.

    Resolves a spoken device/room reference to a compact result list
    (entity_id, friendly name, domain, current state, area). Never returns
    the full entity inventory. At least one of query/domain/area is required.
    """
    limit = max(1, min(int(limit), 15))
    q = query.strip().lower()
    dom = domain.strip().lower()
    ar = area.strip().lower()
    if not q and not dom and not ar:
        return json.dumps({"error": "Provide at least one of query, domain, or area."})

    states = _http("GET", "/api/states") or []
    reg = _entity_registry()
    hits = []
    for st in states:
        eid = st.get("entity_id", "")
        attrs = st.get("attributes", {})
        name = attrs.get("friendly_name", eid)
        e_dom = eid.split(".", 1)[0] if "." in eid else ""
        e_area = reg.get(eid) or ""
        if dom and e_dom != dom:
            continue
        if ar and ar not in e_area.lower():
            continue
        if q and q not in eid.lower() and q not in name.lower() and q not in e_area.lower():
            continue
        hits.append({
            "entity_id": eid,
            "name": name,
            "domain": e_dom,
            "state": st.get("state"),
            "area": reg.get(eid),
        })
        if len(hits) >= limit:
            break

    if not hits:
        return json.dumps({"found": 0, "message": "No matching entities."})
    return json.dumps({"found": len(hits), "entities": hits})


@mcp.tool()
def read_home_state(entity_ids: list[str]) -> str:
    """Read the current state of specific Home Assistant entities.

    entity_ids: exact entity IDs, e.g. ["light.officesw", "sensor.outside_temp"].
    Returns each entity's state plus a small curated attribute set. Read-only.
    """
    if not entity_ids:
        return json.dumps({"error": "Provide at least one entity_id."})
    ids = [e.strip() for e in entity_ids if isinstance(e, str) and ENTITY_ID_RE.match(e.strip())][:10]
    if not ids:
        return json.dumps({"error": "No valid entity_ids (expected domain.name)."})

    results = []
    for eid in ids:
        try:
            st = _http("GET", f"/api/states/{eid}")
            results.append({
                "entity_id": eid,
                "name": st.get("attributes", {}).get("friendly_name", eid),
                "state": st.get("state"),
                "attributes": _curated_attrs(st.get("attributes", {})),
            })
        except RuntimeError as e:
            results.append({"entity_id": eid, "error": str(e)})
    return json.dumps({"entities": results})


def main() -> None:
    if not HA_TOKEN:
        raise SystemExit("HA_TOKEN missing — create the HA long-lived token, store it in the credentials file, then restart the gateway.")
    mcp.run()


if __name__ == "__main__":
    main()