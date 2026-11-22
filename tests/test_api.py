"""Tests for the Backrest API client (no Home Assistant involved)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import aiohttp
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.backrest.api import (
    BackrestAuthenticationError,
    BackrestClient,
    BackrestConnectionError,
    BackrestResponseError,
    OperationKind,
    OperationList,
    OperationStatus,
    PlanBackups,
    Repo,
    RepoStats,
)

from .conftest import load_json

URL = "http://backrest.local:9898"


@pytest.fixture
async def client(aioclient_mock: AiohttpClientMocker) -> AsyncGenerator[BackrestClient]:
    """Return a client that talks to the mocked HTTP session."""
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    yield BackrestClient(session, URL + "/", "ha", "pw")
    await session.close()


async def test_get_config(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """Config is parsed and secrets are not kept."""
    aioclient_mock.post(f"{URL}/v1.Backrest/GetConfig", json=load_json("config.json"))
    config = await client.get_config()
    assert config.instance == "dockervm"
    assert [plan.id for plan in config.plans] == ["appdata", "offsite"]
    assert config.plans[0].schedule == "cron 0 3 * * *"
    assert config.plans[1].schedule == "every 1 d"
    assert config.repos[0].guid == "3f1c9a"
    assert not hasattr(config.repos[0], "password")
    assert aioclient_mock.mock_calls[0][2] == {}


async def test_summary(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """int64 strings, missing defaults and the overdue flag are handled."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetSummaryDashboard", json=load_json("summary.json")
    )
    summary = await client.get_summary_dashboard()
    appdata = summary.plans["appdata"]
    assert appdata.backups_success_30d == 30
    assert appdata.backups_failed_30d == 0
    assert appdata.protected_bytes == 21474836480
    assert appdata.next_backup == datetime(2025, 11, 22, 3, 0, tzinfo=UTC)
    assert appdata.overdue is False
    assert summary.plans["offsite"].overdue is True
    assert summary.repos["swissbackup"].total_snapshots == 35


async def test_plan_backups(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """The newest and the newest finished backup are picked out."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetOperations", json=load_json("operations_appdata.json")
    )
    backups = await client.get_plan_backups("appdata")
    assert aioclient_mock.mock_calls[0][2] == {
        "selector": {"planId": "appdata"},
        "lastN": "40",
    }
    assert backups.latest is not None
    assert backups.latest.id == 102
    assert backups.latest.status is OperationStatus.IN_PROGRESS
    assert backups.latest.progress is not None
    assert backups.latest.progress.percent_done == 0.425
    assert backups.last_finished is not None
    assert backups.last_finished.id == 100
    assert backups.last_finished.kind is OperationKind.BACKUP
    assert backups.last_finished.duration == 300
    assert backups.last_finished.summary is not None
    assert backups.last_finished.summary.data_added == 104857600


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("STATUS_WARNING", OperationStatus.WARNING),
        (7, OperationStatus.WARNING),
        ("4", OperationStatus.ERROR),
        ("STATUS_SOMETHING_NEW", OperationStatus.UNKNOWN),
    ],
)
def test_status_parse(value: object, expected: OperationStatus) -> None:
    """Enum values by name, by number and unknown ones are accepted."""
    assert OperationStatus.parse(value) is expected


@pytest.mark.parametrize("status", [401, 403])
async def test_http_auth_error(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient, status: int
) -> None:
    """HTTP 401/403 means bad credentials."""
    aioclient_mock.post(f"{URL}/v1.Backrest/GetConfig", status=status)
    with pytest.raises(BackrestAuthenticationError):
        await client.get_config()


async def test_connect_auth_error(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """A Connect 'unauthenticated' error means bad credentials."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetConfig",
        status=400,
        json={"code": "unauthenticated", "message": "bad password"},
    )
    with pytest.raises(BackrestAuthenticationError):
        await client.get_config()


async def test_connect_error(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """Other Connect errors keep their code."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetConfig",
        status=500,
        json={"code": "internal", "message": "boom"},
    )
    with pytest.raises(BackrestResponseError) as err:
        await client.get_config()
    assert err.value.code == "internal"


async def test_not_json(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """An HTML page (for example a proxy error) is a response error."""
    aioclient_mock.post(f"{URL}/v1.Backrest/GetConfig", text="<html>bad gateway</html>")
    with pytest.raises(BackrestResponseError):
        await client.get_config()


@pytest.mark.parametrize("exc", [aiohttp.ClientConnectionError, TimeoutError])
async def test_connection_error(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient, exc: type[Exception]
) -> None:
    """Network problems and timeouts become connection errors."""
    aioclient_mock.post(f"{URL}/v1.Backrest/GetConfig", exc=exc)
    with pytest.raises(BackrestConnectionError):
        await client.get_config()


def test_scheduled_run_is_skipped() -> None:
    """A pending run planned for later is not the latest backup."""
    ops = OperationList.from_dict(load_json("operations_offsite.json")).operations
    backups = PlanBackups.from_operations(ops)
    assert backups.latest is not None
    assert backups.latest.id == 90
    assert backups.latest.status is OperationStatus.ERROR

    now = datetime(2100, 1, 2, tzinfo=UTC)
    queued = PlanBackups.from_operations(ops, now=now)
    assert queued.latest is not None
    assert queued.latest.status is OperationStatus.PENDING
    assert not queued.latest.status.is_running


async def test_repo_stats(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """The newest successful stats run wins; failed runs are skipped."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetOperations",
        json=load_json("operations_repo_swissbackup.json"),
    )
    repo = Repo(id="swissbackup", uri="s3:x", guid="7d2e11")
    stats = await client.get_all_repo_stats([repo])
    assert aioclient_mock.mock_calls[0][2] == {
        "selector": {"repoGuid": "7d2e11"},
        "lastN": "200",
    }
    assert stats == {
        "swissbackup": RepoStats(
            total_size=11811160064,
            total_uncompressed_size=17716740096,
            compression_ratio=1.5,
            snapshot_count=35,
        )
    }


async def test_repo_stats_without_guid(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """A repo without a GUID cannot be selected, so no request is made."""
    assert await client.get_repo_stats(Repo(id="old", uri="", guid="")) is None
    assert aioclient_mock.call_count == 0


async def test_repo_stats_none_collected(
    aioclient_mock: AiohttpClientMocker, client: BackrestClient
) -> None:
    """No stats operation yet means no statistics."""
    aioclient_mock.post(
        f"{URL}/v1.Backrest/GetOperations", json=load_json("operations_appdata.json")
    )
    repo = Repo(id="elektra-sftp", uri="sftp:x", guid="3f1c9a")
    assert await client.get_repo_stats(repo) is None
