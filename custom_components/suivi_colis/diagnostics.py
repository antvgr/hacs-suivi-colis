"""Diagnostics for Suivi de Colis (Settings > Integrations > Download diagnostics)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_API_KEY, CONF_WEBHOOK_ID, DOMAIN, MB_PASSWORD, MB_USERNAME

TO_REDACT = {CONF_API_KEY, CONF_WEBHOOK_ID, MB_PASSWORD, MB_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Packages as stored and the raw data last received from 17track."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "quota": coordinator.quota,
        "packages": [pkg.to_dict() for pkg in coordinator.store.packages.values()],
        "removed_numbers": sorted(coordinator.store.removed_numbers),
        # Raw gettrackinfo/webhook items, unparsed
        "raw_17track": coordinator.api_client.last_raw,
    }
