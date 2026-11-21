"""Tests for the Backrest sensors and binary sensors."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.backrest.api import (
    BackrestConfig,
    BackrestConnectionError,
    Plan,
    PlanBackups,
)
from custom_components.backrest.diagnostics import async_get_config_entry_diagnostics


def _state(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    assert state is not None, entity_id
    return state.state


async def test_running_plan(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A plan with a running backup shows progress and the last result."""
    assert _state(hass, "sensor.dockervm_appdata_status") == "in_progress"
    assert _state(hass, "sensor.dockervm_appdata_progress") == "42.5"
    assert _state(hass, "binary_sensor.dockervm_appdata_backup_running") == STATE_ON
    assert _state(hass, "binary_sensor.dockervm_appdata_problem") == STATE_OFF
    assert (
        _state(hass, "sensor.dockervm_appdata_last_backup")
        == "2025-11-21T03:05:00+00:00"
    )
    assert (
        _state(hass, "sensor.dockervm_appdata_next_backup")
        == "2025-11-22T03:00:00+00:00"
    )
    assert _state(hass, "sensor.dockervm_appdata_data_added_by_last_backup") == "100.0"
    assert _state(hass, "sensor.dockervm_appdata_duration_of_last_backup") == "5.0"
    assert _state(hass, "sensor.dockervm_appdata_protected_data") == "20.0"
    assert _state(hass, "sensor.dockervm_appdata_successful_backups_30_days") == "30"
    assert _state(hass, "sensor.dockervm_appdata_failed_backups_30_days") == "0"
    assert _state(hass, "sensor.dockervm_appdata_last_error") == STATE_UNKNOWN


async def test_failed_plan(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """A failed, overdue plan reports the error and a problem."""
    assert _state(hass, "sensor.dockervm_offsite_status") == "error"
    assert _state(hass, "sensor.dockervm_offsite_progress") == STATE_UNKNOWN
    assert _state(hass, "binary_sensor.dockervm_offsite_backup_running") == STATE_OFF
    assert _state(hass, "binary_sensor.dockervm_offsite_problem") == STATE_ON
    assert _state(hass, "sensor.dockervm_offsite_last_error").startswith(
        "Fatal: unable to open repository"
    )
    assert _state(hass, "sensor.dockervm_offsite_data_added_by_last_backup") == (
        STATE_UNKNOWN
    )


async def test_repo_sensors(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Repos get snapshot counts and data added."""
    assert _state(hass, "sensor.dockervm_swissbackup_snapshots") == "35"
    assert _state(hass, "sensor.dockervm_elektra_sftp_data_added_30_days") == "5.0"


async def test_unavailable_and_recover(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Entities go unavailable while Backrest is down and come back."""
    config = mock_client.get_config.return_value
    mock_client.get_config.side_effect = BackrestConnectionError("down")
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor.dockervm_appdata_status") == STATE_UNAVAILABLE

    mock_client.get_config.side_effect = None
    mock_client.get_config.return_value = config
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor.dockervm_appdata_status") == "in_progress"


async def test_new_and_removed_plan(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """A new plan gets entities; a removed plan's entities go unavailable."""
    config: BackrestConfig = mock_client.get_config.return_value
    new_plan = Plan(id="photos", repo="elektra-sftp", paths=("/photos",), schedule=None)
    mock_client.get_config.return_value = BackrestConfig(
        instance=config.instance,
        repos=config.repos,
        plans=(config.plans[0], new_plan),
    )
    real = mock_client.get_all_plan_backups.side_effect

    async def backups(plan_ids: list[str]) -> dict[str, PlanBackups]:
        known = [pid for pid in plan_ids if pid != "photos"]
        result = real(known)
        result["photos"] = PlanBackups()
        return result

    mock_client.get_all_plan_backups.side_effect = backups
    await init_integration.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert _state(hass, "sensor.dockervm_photos_status") == STATE_UNKNOWN
    assert _state(hass, "sensor.dockervm_offsite_status") == STATE_UNAVAILABLE


async def test_diagnostics(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Diagnostics hide credentials, URIs and paths."""
    diag = await async_get_config_entry_diagnostics(hass, init_integration)
    text = str(diag)
    assert "hunter2" not in text
    assert "10.0.3.20" not in text
    assert "/opt/appdata" not in text
    assert diag["data"]["config"]["instance"] == "dockervm"
