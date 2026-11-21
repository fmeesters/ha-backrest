"""Tests for setting up and unloading the Backrest integration."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.typing import WebSocketGenerator

from custom_components.backrest.api import (
    BackrestAuthenticationError,
    BackrestConnectionError,
)
from custom_components.backrest.const import DOMAIN
from custom_components.backrest.entity import device_name


async def test_setup_and_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry loads and unloads."""
    assert init_integration.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED


@pytest.mark.parametrize(
    ("side_effect", "state"),
    [
        (BackrestConnectionError("down"), ConfigEntryState.SETUP_RETRY),
        (BackrestAuthenticationError("nope"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_setup_errors(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    side_effect: Exception,
    state: ConfigEntryState,
) -> None:
    """Unreachable means retry later; bad credentials start reauth."""
    mock_client.get_config.side_effect = side_effect
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is state
    flows = hass.config_entries.flow.async_progress()
    assert bool(flows) is isinstance(side_effect, BackrestAuthenticationError)


async def test_devices(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """One device for the instance, one per plan and one per repo."""
    devices = dr.async_entries_for_config_entry(
        device_registry, init_integration.entry_id
    )
    assert sorted(device.name for device in devices) == [
        "Backrest dockervm",
        "dockervm appdata",
        "dockervm elektra-sftp",
        "dockervm offsite",
        "dockervm swissbackup",
    ]
    instance = device_registry.async_get_device(identifiers={(DOMAIN, "dockervm")})
    assert instance is not None
    assert all(
        device.via_device_id == instance.id for device in devices if device != instance
    )


async def test_remove_stale_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    hass_ws_client: WebSocketGenerator,
) -> None:
    """Only devices of plans that no longer exist can be removed."""
    assert await async_setup_component(hass, "config", {})
    client = await hass_ws_client(hass)

    async def remove(identifier: str) -> bool:
        device = device_registry.async_get_or_create(
            config_entry_id=init_integration.entry_id,
            identifiers={(DOMAIN, identifier)},
        )
        await client.send_json_auto_id(
            {
                "type": "config/device_registry/remove_config_entry",
                "config_entry_id": init_integration.entry_id,
                "device_id": device.id,
            }
        )
        return bool((await client.receive_json())["success"])

    assert await remove("dockervm_plan_appdata") is False
    assert await remove("dockervm_plan_gone") is True


def test_device_name() -> None:
    """The instance name is not repeated when the ID already starts with it."""
    assert device_name("dockervm", "dockervm-elektra") == "dockervm-elektra"
    assert device_name("Elektra", "elektra-swiss") == "elektra-swiss"
    assert device_name("dockervm", "swiss") == "dockervm swiss"
