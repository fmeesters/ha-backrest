"""Tests for the backrest_backup events."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
)

from custom_components.backrest.api import (
    BackupProgress,
    BackupSummary,
    Operation,
    OperationKind,
    OperationStatus,
    PlanBackups,
)
from custom_components.backrest.events import EVENT_BACKUP, plan_events

START = datetime(2026, 11, 21, 18, 0, tzinfo=UTC)
END = datetime(2026, 11, 21, 19, 0, tzinfo=UTC)


def _op(
    op_id: int = 1,
    status: OperationStatus = OperationStatus.IN_PROGRESS,
    percent: float | None = 0.4,
    **kwargs: object,
) -> Operation:
    return Operation(
        id=op_id,
        flow_id=op_id,
        repo_id="goldfinger",
        plan_id="elektra-goldfinger",
        instance_id="elektra",
        snapshot_id="",
        status=status,
        started=START,
        ended=kwargs.pop("ended", None),  # type: ignore[arg-type]
        display_message=str(kwargs.pop("display_message", "")),
        kind=OperationKind.BACKUP,
        progress=None if percent is None else BackupProgress(percent, 10, 1000, 4, 400),
        **kwargs,  # type: ignore[arg-type]
    )


def test_started_progress_finished() -> None:
    """A backup starts, moves on and ends with a result."""
    running = _op(percent=0.4)
    [started] = plan_events(None, running, None)
    assert started["type"] == "started"
    assert started["progress"] == 40.0
    assert started["total_bytes"] == 1000

    further = _op(percent=0.55)
    [progress] = plan_events(running, further, None)
    assert progress["type"] == "progress"
    assert progress == progress | {"progress": 55.0, "previous_progress": 40.0}

    assert plan_events(further, further, None) == []

    done = _op(
        status=OperationStatus.SUCCESS,
        percent=1.0,
        ended=END,
        summary=BackupSummary(1, 2, 3, 2048, 6, 7, 3600.0, "abc"),
    )
    [finished] = plan_events(further, done, done)
    assert finished["type"] == "finished"
    assert finished["result"] == "success"
    assert finished["duration"] == 3600
    assert finished["data_added"] == 2048
    assert finished["error"] is None


def test_finished_with_error_and_next_started() -> None:
    """The followed backup failed and the next one already runs."""
    running = _op(op_id=1)
    failed = _op(
        op_id=1,
        status=OperationStatus.ERROR,
        percent=None,
        ended=END,
        display_message="repository locked",
    )
    nxt = _op(op_id=2, percent=0.01)
    events = plan_events(running, nxt, failed)
    assert [e["type"] for e in events] == ["finished", "started"]
    assert events[0]["result"] == "error"
    assert events[0]["error"] == "repository locked"
    assert events[1]["operation_id"] == 2


def test_unknown_result_and_no_events() -> None:
    """An ended backup we can no longer see ends as unknown; idle plans are quiet."""
    running = _op(op_id=1)
    [finished] = plan_events(running, None, None)
    assert finished["result"] == "unknown"
    done = _op(status=OperationStatus.SUCCESS, percent=None)
    assert plan_events(done, done, done) == []
    assert plan_events(None, None, None) == []


def test_first_refresh_running() -> None:
    """After a restart a running backup counts as started, not as progress."""
    running = _op()
    [started] = plan_events(None, running, None, first_refresh=True)
    assert started["type"] == "started"
    pending = replace(running, status=OperationStatus.PENDING)
    assert plan_events(None, pending, None, first_refresh=True) == []


async def test_events_on_the_bus(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry, mock_client: MagicMock
) -> None:
    """The coordinator fires events with the plan and instance."""
    events = async_capture_events(hass, EVENT_BACKUP)
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    # The fixtures have one running backup (appdata, 42.5%).
    [started] = events
    assert started.data["type"] == "started"
    assert started.data["instance"] == "dockervm"
    assert started.data["plan_id"] == "appdata"
    assert started.data["plan_name"] == "dockervm appdata"
    assert started.data["progress"] == 42.5

    real = mock_client.get_all_plan_backups.side_effect

    def finished(plan_ids: list[str]) -> dict[str, PlanBackups]:
        result = real(plan_ids)
        latest = result["appdata"].latest
        assert latest is not None
        done = replace(latest, status=OperationStatus.SUCCESS, ended=END)
        result["appdata"] = PlanBackups(latest=done, last_finished=done)
        return result

    mock_client.get_all_plan_backups.side_effect = finished
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert events[-1].data["type"] == "finished"
    assert events[-1].data["result"] == "success"
    assert events[-1].data["device_id"] is not None
