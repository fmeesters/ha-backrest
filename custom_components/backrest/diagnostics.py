"""Diagnostics for the Backrest integration."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .coordinator import BackrestConfigEntry

# Repo URIs can hold host names, user names and bucket names; paths reveal
# the layout of the backed up machine.
TO_REDACT = {CONF_PASSWORD, CONF_USERNAME, CONF_URL, "uri", "paths"}


def _lists(value: Any) -> Any:
    """Turn tuples into lists; async_redact_data only walks dicts and lists."""
    if isinstance(value, dict):
        return {key: _lists(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_lists(item) for item in value]
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BackrestConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "last_update_success": coordinator.last_update_success,
        "data": async_redact_data(_lists(asdict(coordinator.data)), TO_REDACT),
    }
