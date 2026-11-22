"""Shared fixtures for the Backrest tests."""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME, CONF_VERIFY_SSL
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.backrest.api import (
    BackrestConfig,
    OperationList,
    PlanBackups,
    RepoStats,
    SummaryDashboard,
)
from custom_components.backrest.api.models import latest_repo_stats
from custom_components.backrest.const import DOMAIN

FIXTURES = Path(__file__).parent / "fixtures"

ENTRY_DATA = {
    CONF_URL: "http://10.0.3.50:9898",
    CONF_USERNAME: "ha",
    CONF_PASSWORD: "hunter2",
    CONF_VERIFY_SSL: True,
}


def load_json(name: str) -> Any:
    """Load a JSON fixture."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load custom_components in every test."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the dockervm instance."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Backrest dockervm",
        unique_id="dockervm",
        data=dict(ENTRY_DATA),
    )


def _plan_backups(plan_id: str) -> PlanBackups:
    ops = OperationList.from_dict(load_json(f"operations_{plan_id}.json"))
    return PlanBackups.from_operations(ops.operations)


def _repo_stats(repo_id: str) -> RepoStats | None:
    """Return fixture stats for the Swiss repo; Elektra has none collected yet."""
    path = FIXTURES / f"operations_repo_{repo_id}.json"
    if not path.exists():
        return None
    return latest_repo_stats(OperationList.from_dict(load_json(path.name)).operations)


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Patch the API client with one that serves the fixtures."""
    with patch("custom_components.backrest.BackrestClient", autospec=True) as cls:
        client = cls.return_value
        client.url = ENTRY_DATA[CONF_URL]
        client.get_config = AsyncMock(
            return_value=BackrestConfig.from_dict(load_json("config.json"))
        )
        client.get_summary_dashboard = AsyncMock(
            return_value=SummaryDashboard.from_dict(load_json("summary.json"))
        )
        client.get_all_plan_backups = AsyncMock(
            side_effect=lambda plan_ids: {pid: _plan_backups(pid) for pid in plan_ids}
        )
        client.get_all_repo_stats = AsyncMock(
            side_effect=lambda repos: {r.id: _repo_stats(r.id) for r in repos}
        )
        yield client


@pytest.fixture
async def init_integration(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> MockConfigEntry:
    """Set up the integration with the fixtures."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
