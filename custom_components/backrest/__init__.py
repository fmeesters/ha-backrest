"""The Backrest integration: monitor restic backups made by Backrest."""

from __future__ import annotations

from homeassistant.const import (
    CONF_PASSWORD,
    CONF_URL,
    CONF_USERNAME,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BackrestClient
from .const import DOMAIN, MANUFACTURER
from .coordinator import BackrestConfigEntry, BackrestCoordinator
from .entity import plan_identifier, repo_identifier

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


def create_client(hass: HomeAssistant, data: dict[str, object]) -> BackrestClient:
    """Build an API client from config entry data."""
    verify_ssl = bool(data.get(CONF_VERIFY_SSL, True))
    return BackrestClient(
        async_get_clientsession(hass, verify_ssl=verify_ssl),
        str(data[CONF_URL]),
        str(data[CONF_USERNAME]) if data.get(CONF_USERNAME) else None,
        str(data[CONF_PASSWORD]) if data.get(CONF_PASSWORD) else None,
        verify_ssl=verify_ssl,
    )


async def async_setup_entry(hass: HomeAssistant, entry: BackrestConfigEntry) -> bool:
    """Set up Backrest from a config entry."""
    coordinator = BackrestCoordinator(
        hass, entry, create_client(hass, dict(entry.data))
    )
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # The instance device must exist before plan and repo devices point at it.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.instance)},
        manufacturer=MANUFACTURER,
        model="Backrest instance",
        name=f"Backrest {coordinator.instance}",
        configuration_url=coordinator.client.url,
        entry_type=dr.DeviceEntryType.SERVICE,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BackrestConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: BackrestConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a plan or repo device once it is gone from Backrest."""
    data = entry.runtime_data.data
    instance = entry.runtime_data.instance
    current = {(DOMAIN, instance)}
    current |= {plan_identifier(instance, plan_id) for plan_id in data.plans}
    current |= {repo_identifier(instance, repo.repo) for repo in data.repos.values()}
    return not device.identifiers & current
