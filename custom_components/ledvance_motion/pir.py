"""Interpret the motion field without confusing other SMART+ sensor types."""

from collections.abc import Mapping, Sequence
from typing import Any


def motion_value(raw: object) -> bool | None:
    """Decode only known motion states. Unknown values must stay unknown."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().casefold()
        if value == "pir":
            return True
        if value == "none":
            return False
    return None


def motion_dp(schema: Sequence, dps: Mapping) -> str | None:
    """Prefer the PIR field in this device's schema, then a known motion enum."""
    codes = {
        row.get("code"): str(row["id"])
        for row in schema
        if isinstance(row, Mapping) and row.get("id") is not None
    }
    for code in ("pir_state", "pir"):
        if code in codes:
            return codes[code]
        if code in dps:
            return code
    # LEDVANCE uses DP 1 for several devices. "none" alone could belong
    # to a different sensor. Require a positive PIR report for this fallback.
    if "1" in codes.values():
        return None
    raw = dps.get("1", dps.get(1))
    if isinstance(raw, str) and raw.strip().casefold() == "pir":
        return "1"
    return None


def read_motion(dps: Mapping[str, Any], dp: str) -> bool | None:
    """Read a known field across numbered and named cloud responses."""
    if isinstance(dps.get("dps"), Mapping):
        dps = dps["dps"]
    for key in dict.fromkeys((dp, "pir_state", "pir")):
        if key in dps:
            return motion_value(dps[key])
    return None
