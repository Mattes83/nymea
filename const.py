"""Constants for the nymea integration."""

from __future__ import annotations

DOMAIN = "nymea"

# Configuration constants
CONF_WEBSOCKET_PORT = "websocket_port"


def normalize_uuid(value: str | None) -> str | None:
    """Return the nymea server uuid in a canonical form for use as unique ID.

    nymea reports its uuid with braces ("{5dec...}") both in the zeroconf TXT
    record and in JSONRPC.Hello. Strip braces and lowercase so both sources
    compare equal. Returns None for empty values.
    """
    if not value:
        return None
    normalized = value.strip().strip("{}").strip().lower()
    return normalized or None
