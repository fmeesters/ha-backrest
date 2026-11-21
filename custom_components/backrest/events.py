"""Backup events: tell automations when a backup starts, progresses and ends.

Every plan gets the same `backrest_backup` event, so one automation can follow all
plans (and plans added later) without listing entity IDs.
"""

from __future__ import annotations

from typing import Any

from .api import Operation, OperationStatus

EVENT_BACKUP = "backrest_backup"

TYPE_STARTED = "started"
TYPE_PROGRESS = "progress"
TYPE_FINISHED = "finished"

_RESULT = {
    OperationStatus.SUCCESS: "success",
    OperationStatus.WARNING: "warning",
    OperationStatus.ERROR: "error",
    OperationStatus.SYSTEM_CANCELLED: "cancelled",
    OperationStatus.USER_CANCELLED: "cancelled",
}


def _percent(op: Operation | None) -> float | None:
    if op is None or not op.status.is_running:
        return None
    if op.progress is None:
        return 0.0
    return round(op.progress.percent_done * 100, 1)


def _base(op: Operation) -> dict[str, Any]:
    data: dict[str, Any] = {
        "operation_id": op.id,
        "repo_id": op.repo_id,
        "started": op.started.isoformat() if op.started else None,
    }
    if op.progress is not None:
        data["bytes_done"] = op.progress.bytes_done
        data["total_bytes"] = op.progress.total_bytes
        data["files_done"] = op.progress.files_done
        data["total_files"] = op.progress.total_files
    return data


def plan_events(
    previous_latest: Operation | None,
    latest: Operation | None,
    last_finished: Operation | None,
    *,
    first_refresh: bool = False,
) -> list[dict[str, Any]]:
    """Return the events for one plan, comparing the newest backup before and now.

    `previous_latest` is the newest backup at the previous update; on the first
    update after setup there is none, and a backup that is already running counts
    as started (so a Live Activity reappears after a restart).
    """
    events: list[dict[str, Any]] = []
    followed = previous_latest
    if followed is not None and not followed.status.is_running:
        followed = None
    same = followed is not None and latest is not None and latest.id == followed.id

    # The backup we were following has ended (it may no longer be the newest).
    if followed is not None and not (same and latest and latest.status.is_running):
        ended = latest if same else None
        if ended is None and last_finished and last_finished.id == followed.id:
            ended = last_finished
        result = _RESULT.get(ended.status, "unknown") if ended else "unknown"
        data = _base(ended or followed)
        data.update(
            type=TYPE_FINISHED,
            result=result,
            progress=None,
            previous_progress=_percent(followed),
            ended=ended.ended.isoformat() if ended and ended.ended else None,
            duration=ended.duration if ended else None,
            data_added=ended.summary.data_added if ended and ended.summary else None,
            error=(ended.display_message or None)
            if ended and result in ("error", "warning")
            else None,
        )
        events.append(data)

    if latest is None or not latest.status.is_running:
        return events

    percent = _percent(latest)
    if not same:
        data = _base(latest)
        data.update(type=TYPE_STARTED, progress=percent, previous_progress=None)
        events.append(data)
    elif not first_refresh:
        before = _percent(followed)
        if before != percent:
            data = _base(latest)
            data.update(type=TYPE_PROGRESS, progress=percent, previous_progress=before)
            events.append(data)
    return events
