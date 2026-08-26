"""VV HA Adapter — minimal Home Assistant MCP server for the VexaVoice profile.

Exposes ONLY:
  - find_home_entities:   bounded name/domain/area search (word-overlap aware) -> entity_id, name, state, area
  - read_home_state:      read specific entity IDs -> state + small curated attribute set
  - control_entity:       on/off/toggle for light|switch|fan; open/close/stop for cover
                          (locks, alarms, cameras and all other domains are hard-denied)
  - run_approved_routine: run an allowlisted HA script by name (allowlist file, no arbitrary services)

No history, no bulk enumeration, no arbitrary service calls, no config writes.
The HA long-lived token arrives via HA_TOKEN (the wrapper script loads it from a 0600 file).
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

HERE = os.path.dirname(os.path.abspath(__file__))
ALLOWED_SCRIPTS_FILE = os.path.join(HERE, "allowed_scripts.json")

ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

# Small curated attribute surface — never return the full attribute dict.
CURATED_ATTRS = (
    "unit_of_measurement", "device_class", "state_class",
    "brightness", "color_temp_kelvin", "color_temp",
    "current_temperature", "temperature", "hvac_action",
    "current_position", "locked", "volume_level", "source",
    "battery", "battery_level", "battery_percentage", "icon",
)

# Entity control: whitelisted domains + action -> HA service map.
# Everything else (locks, alarms, cameras, sensors, media, config...) is NOT controllable.
CONTROL_SERVICES = {
    "light":  {"on": "turn_on",  "off": "turn_off", "toggle": "toggle"},
    "switch": {"on": "turn_on",  "off": "turn_off", "toggle": "toggle"},
    "fan":    {"on": "turn_on",  "off": "turn_off", "toggle": "toggle"},
    "cover":  {"open": "open_cover", "close": "close_cover", "stop": "stop_cover"},
}

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


def _tokens(text: str) -> set[str]:
    """Word tokens with camelCase/digit-boundary splitting and light stemming.

    'MasterFanMod' -> {master, fan, mod}; 'master2button2' -> {master, 2, button}.
    'lamps' -> {lamps, lamp} so a 'lamp' query still matches plural names.
    """
    words: list[str] = []
    for chunk in re.findall(r"[A-Za-z0-9]+", text):
        words.extend(p.lower() for p in re.findall(r"[A-Z][a-z]*|[a-z]+|[0-9]+", chunk) if p)
    out: set[str] = set()
    for w in words:
        out.add(w)
        if w.endswith("s") and len(w) > 3:
            out.add(w[:-1])
    return out


def _overlap_score(q_tokens: set[str], cand_tokens: set[str]) -> int:
    """Count query tokens matched in candidate tokens (equal, prefix, or suffix)."""
    low = {t for t in cand_tokens if len(t) >= 2}
    score = 0
    for qt in q_tokens:
        if qt in low:
            score += 1
        elif len(qt) >= 3 and any(t.startswith(qt) or qt.startswith(t) for t in low if len(t) >= 3):
            score += 1
    return score


def _load_allowed_scripts() -> set[str]:
    try:
        with open(ALLOWED_SCRIPTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return {s if s.startswith("script.") else f"script.{s}" for s in data}
    except Exception:
        return set()


mcp = FastMCP("vv-ha-adapter")


@mcp.tool()
def find_home_entities(query: str = "", domain: str = "", area: str = "", limit: int = 6) -> str:
    """Find Home Assistant entities by name, entity ID, domain, or area.

    Resolves a spoken device/room reference to a compact result list
    (entity_id, friendly name, domain, current state, area). Matching is
    forgiving: it tries exact substrings first, then word-overlap (so
    "master bedroom lamps" can match "Master Bed Lamp L"). At least one of
    query/domain/area is required. Never returns the full entity inventory.
    """
    limit = max(1, min(int(limit), 10))
    q = query.strip().lower()
    dom = domain.strip().lower()
    ar = area.strip().lower()
    if not q and not dom and not ar:
        return json.dumps({"error": "Provide at least one of query, domain, or area."})

    states = _http("GET", "/api/states") or []
    reg = _entity_registry()
    q_tokens = _tokens(q) if q else set()
    NOISE_DOMAINS = {"automation", "script", "scene", "group", "zone"}

    scored = []
    for st in states:
        eid = st.get("entity_id", "")
        e_dom = eid.split(".", 1)[0] if "." in eid else ""
        if e_dom in NOISE_DOMAINS:
            continue
        attrs = st.get("attributes", {})
        name = attrs.get("friendly_name", eid)
        e_area = reg.get(eid) or ""
        if dom and e_dom != dom:
            continue
        if ar and ar not in e_area.lower():
            continue
        if not q:
            scored.append((0, eid, name, st.get("state"), e_area))
            continue
        eid_l, name_l, area_l = eid.lower(), name.lower(), e_area.lower()
        substr = (q in eid_l) or (q in name_l) or (q in area_l)
        overlap = _overlap_score(q_tokens, _tokens(name_l) | _tokens(eid_l)) + _overlap_score(q_tokens, _tokens(area_l))
        if substr:
            score = 1000 + len(q) + overlap
        elif overlap >= 1:
            score = overlap * 10
            if e_dom in q_tokens:
                score += 5  # query named the device domain explicitly (e.g. 'fan')
        else:
            continue
        scored.append((score, eid, name, st.get("state"), e_area))

    scored.sort(key=lambda x: (-x[0], x[2].lower()))
    hits = [
        {"entity_id": eid, "name": name, "domain": eid.split(".", 1)[0],
         "state": state, "area": area}
        for _, eid, name, state, area in scored[:limit]
    ]

    if not hits:
        return json.dumps({"found": 0, "message": "No matching entities. Try a shorter word, e.g. 'lamp' or the room name."})
    partial = q and not any(s >= 1000 for s, *_ in scored[:len(hits)])
    out = {"found": len(hits), "entities": hits}
    if partial:
        out["note"] = "No exact name match; showing closest partial matches (device names may be concatenated, e.g. 'MasterFanMod')."
    return json.dumps(out)


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


@mcp.tool()
def control_entity(entity_id: str, action: str) -> str:
    """Control a single Home Assistant entity.

    Actions: on/off/toggle for lights, switches, and fans; open/close/stop
    for covers. Use find_home_entities first to resolve the entity ID.
    Locks, alarms, cameras, sensors, and all other domains are NOT
    controllable through this tool — only light, switch, fan, and cover.
    When the user means 'the <device>' in a room and several matching entities
    of the same domain are in the same state, control all of them instead of
    asking which one; ask only when their states differ or the action is risky.
    """
    eid = entity_id.strip().lower()
    if not ENTITY_ID_RE.match(eid):
        return json.dumps({"error": f"Invalid entity_id '{entity_id}' (expected domain.name)."})
    domain = eid.split(".", 1)[0]
    if domain not in CONTROL_SERVICES:
        return json.dumps({
            "error": f"Domain '{domain}' is not controllable. Allowed domains: {sorted(CONTROL_SERVICES)}. "
                     "Locks, alarms, cameras, and other domains are excluded by design."
        })
    action = action.strip().lower()
    svc = CONTROL_SERVICES[domain].get(action)
    if not svc:
        return json.dumps({"error": f"Action '{action}' is not valid for domain '{domain}'. Valid actions: {sorted(CONTROL_SERVICES[domain])}."})

    try:
        before = _http("GET", f"/api/states/{eid}")
    except RuntimeError:
        return json.dumps({"error": f"Entity '{entity_id}' was not found in Home Assistant."})
    if before.get("state") in ("unavailable", "unknown"):
        return json.dumps({"error": f"Entity '{entity_id}' is {before.get('state')} and cannot be controlled right now."})

    try:
        _http("POST", f"/api/services/{domain}/{svc}", body={"entity_id": eid})
    except RuntimeError as e:
        return json.dumps({"error": str(e)})

    time.sleep(0.4)  # let the state propagate before confirming
    try:
        after = _http("GET", f"/api/states/{eid}")
        return json.dumps({
            "entity_id": eid,
            "name": after.get("attributes", {}).get("friendly_name", eid),
            "action": f"{domain}.{svc}",
            "state_before": before.get("state"),
            "state_after": after.get("state"),
        })
    except RuntimeError:
        return json.dumps({"entity_id": eid, "action": f"{domain}.{svc}", "state_before": before.get("state"), "state_after": "unknown"})


@mcp.tool()
def run_approved_routine(script: str) -> str:
    """Run an approved Home Assistant routine (script) by name.

    Examples: 'good_morning', 'goodnight', 'movie_mode', 'prepare_leave_home',
    'relax_mode', 'secure_house'. Only scripts in the adapter allowlist can be
    run; the script must also exist in Home Assistant. No arbitrary services.
    """
    name = script.strip()
    if not name.startswith("script."):
        name = f"script.{name}"
    short = name.split(".", 1)[1]

    allowed = _load_allowed_scripts()
    if name not in allowed:
        return json.dumps({"error": f"Script '{name}' is not in the approved routines allowlist. Approved: {sorted(allowed) or 'none configured yet'}."})

    try:
        st = _http("GET", f"/api/states/{name}")
        if st.get("state") == "unavailable":
            return json.dumps({"error": f"Script '{name}' is unavailable in Home Assistant right now."})
    except RuntimeError:
        return json.dumps({"error": f"Script '{name}' is approved but does not exist in Home Assistant yet — create it in HA first."})

    try:
        _http("POST", f"/api/services/script/{short}", body={})
    except RuntimeError as e:
        return json.dumps({"error": str(e)})
    return json.dumps({"started": name, "message": f"Routine '{name}' has been started."})


def main() -> None:
    if not HA_TOKEN:
        raise SystemExit("HA_TOKEN missing — create the HA long-lived token, store it in the credentials file, then restart the gateway.")
    mcp.run()


if __name__ == "__main__":
    main()