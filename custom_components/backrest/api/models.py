"""Typed models for the parts of the Backrest API that the integration uses.

Backrest speaks Connect RPC with protobuf-JSON. That encoding has a few quirks
that the parsers below deal with in one place:

* 64-bit integers arrive as strings ("1732200000000").
* Fields with their default value (0, "", false) are left out entirely.
* Enums arrive by name ("STATUS_SUCCESS"), older clients may send numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any


def _int(value: Any) -> int:
    """Parse a protobuf-JSON integer (number or numeric string)."""
    if value is None or value == "":
        return 0
    return int(value)


def _float(value: Any) -> float:
    """Parse a protobuf-JSON float."""
    if value is None or value == "":
        return 0.0
    return float(value)


def _datetime_ms(value: Any) -> datetime | None:
    """Turn a unix timestamp in milliseconds into an aware datetime."""
    millis = _int(value)
    if millis <= 0:
        return None
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


class OperationStatus(StrEnum):
    """Status of a Backrest operation (proto enum OperationStatus)."""

    UNKNOWN = "STATUS_UNKNOWN"
    PENDING = "STATUS_PENDING"
    IN_PROGRESS = "STATUS_INPROGRESS"
    SUCCESS = "STATUS_SUCCESS"
    WARNING = "STATUS_WARNING"
    ERROR = "STATUS_ERROR"
    SYSTEM_CANCELLED = "STATUS_SYSTEM_CANCELLED"
    USER_CANCELLED = "STATUS_USER_CANCELLED"

    @classmethod
    def parse(cls, value: Any) -> OperationStatus:
        """Parse an enum value sent by name or by number."""
        if isinstance(value, int) or (isinstance(value, str) and value.isdigit()):
            return _STATUS_BY_NUMBER.get(int(value), cls.UNKNOWN)
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN

    @property
    def is_running(self) -> bool:
        """Return True while the operation is actually running."""
        return self is OperationStatus.IN_PROGRESS

    @property
    def is_finished(self) -> bool:
        """Return True once the operation has a final outcome."""
        return self not in (
            OperationStatus.UNKNOWN,
            OperationStatus.PENDING,
            OperationStatus.IN_PROGRESS,
        )


_STATUS_BY_NUMBER = {
    0: OperationStatus.UNKNOWN,
    1: OperationStatus.PENDING,
    2: OperationStatus.IN_PROGRESS,
    3: OperationStatus.SUCCESS,
    4: OperationStatus.ERROR,
    5: OperationStatus.SYSTEM_CANCELLED,
    6: OperationStatus.USER_CANCELLED,
    7: OperationStatus.WARNING,
}


@dataclass(frozen=True, slots=True)
class Repo:
    """A repository configured in Backrest (passwords and env are not kept)."""

    id: str
    uri: str
    guid: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Repo:
        """Parse a Repo message."""
        return cls(id=data["id"], uri=data.get("uri", ""), guid=data.get("guid", ""))


@dataclass(frozen=True, slots=True)
class Plan:
    """A backup plan configured in Backrest."""

    id: str
    repo: str
    paths: tuple[str, ...]
    schedule: str | None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        """Parse a Plan message."""
        return cls(
            id=data["id"],
            repo=data.get("repo", ""),
            paths=tuple(data.get("paths", [])),
            schedule=_describe_schedule(data.get("schedule") or {}),
        )


def _describe_schedule(schedule: dict[str, Any]) -> str | None:
    """Give a short, human readable form of a Schedule message."""
    if schedule.get("disabled"):
        return "disabled"
    if cron := schedule.get("cron"):
        return f"cron {cron}"
    if hours := schedule.get("maxFrequencyHours"):
        return f"every {hours} h"
    if days := schedule.get("maxFrequencyDays"):
        return f"every {days} d"
    return None


@dataclass(frozen=True, slots=True)
class BackrestConfig:
    """The Backrest configuration, reduced to what the integration needs."""

    instance: str
    repos: tuple[Repo, ...]
    plans: tuple[Plan, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackrestConfig:
        """Parse a Config message."""
        return cls(
            instance=data.get("instance", ""),
            repos=tuple(Repo.from_dict(repo) for repo in data.get("repos", [])),
            plans=tuple(Plan.from_dict(plan) for plan in data.get("plans", [])),
        )


@dataclass(frozen=True, slots=True)
class Summary:
    """Statistics for one plan or repo over the last 30 days."""

    id: str
    backups_success_30d: int
    backups_warning_30d: int
    backups_failed_30d: int
    bytes_scanned_30d: int
    bytes_added_30d: int
    total_snapshots: int
    bytes_scanned_avg: int
    bytes_added_avg: int
    protected_bytes: int
    next_backup: datetime | None
    overdue: bool

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Summary:
        """Parse a SummaryDashboardResponse.Summary message."""
        history = data.get("historyLast30days") or []
        return cls(
            id=data["id"],
            backups_success_30d=_int(data.get("backupsSuccessLast30days")),
            backups_warning_30d=_int(data.get("backupsWarningLast30days")),
            backups_failed_30d=_int(data.get("backupsFailed30days")),
            bytes_scanned_30d=_int(data.get("bytesScannedLast30days")),
            bytes_added_30d=_int(data.get("bytesAddedLast30days")),
            total_snapshots=_int(data.get("totalSnapshots")),
            bytes_scanned_avg=_int(data.get("bytesScannedAvg")),
            bytes_added_avg=_int(data.get("bytesAddedAvg")),
            protected_bytes=_int(data.get("protectedBytes")),
            next_backup=_datetime_ms(data.get("nextBackupTimeMs")),
            overdue=bool(history and history[-1].get("overdue")),
        )


@dataclass(frozen=True, slots=True)
class SummaryDashboard:
    """Response of GetSummaryDashboard."""

    plans: dict[str, Summary]
    repos: dict[str, Summary]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryDashboard:
        """Parse a SummaryDashboardResponse message."""
        plans = [Summary.from_dict(item) for item in data.get("planSummaries", [])]
        repos = [Summary.from_dict(item) for item in data.get("repoSummaries", [])]
        return cls(
            plans={summary.id: summary for summary in plans},
            repos={summary.id: summary for summary in repos},
        )


@dataclass(frozen=True, slots=True)
class BackupProgress:
    """Live progress of a running backup (restic status message)."""

    percent_done: float
    total_files: int
    total_bytes: int
    files_done: int
    bytes_done: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupProgress:
        """Parse a BackupProgressStatusEntry message."""
        return cls(
            percent_done=_float(data.get("percentDone")),
            total_files=_int(data.get("totalFiles")),
            total_bytes=_int(data.get("totalBytes")),
            files_done=_int(data.get("filesDone")),
            bytes_done=_int(data.get("bytesDone")),
        )


@dataclass(frozen=True, slots=True)
class BackupSummary:
    """Result of a finished backup (restic summary message)."""

    files_new: int
    files_changed: int
    files_unmodified: int
    data_added: int
    total_files_processed: int
    total_bytes_processed: int
    total_duration: float
    snapshot_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupSummary:
        """Parse a BackupProgressSummary message."""
        return cls(
            files_new=_int(data.get("filesNew")),
            files_changed=_int(data.get("filesChanged")),
            files_unmodified=_int(data.get("filesUnmodified")),
            data_added=_int(data.get("dataAdded")),
            total_files_processed=_int(data.get("totalFilesProcessed")),
            total_bytes_processed=_int(data.get("totalBytesProcessed")),
            total_duration=_float(data.get("totalDuration")),
            snapshot_id=data.get("snapshotId", ""),
        )


@dataclass(frozen=True, slots=True)
class RepoStats:
    """Repository statistics from `restic stats` (a Backrest stats operation)."""

    total_size: int
    total_uncompressed_size: int
    compression_ratio: float
    snapshot_count: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RepoStats:
        """Parse a RepoStats message."""
        return cls(
            total_size=_int(data.get("totalSize")),
            total_uncompressed_size=_int(data.get("totalUncompressedSize")),
            compression_ratio=_float(data.get("compressionRatio")),
            snapshot_count=_int(data.get("snapshotCount")),
        )


class OperationKind(StrEnum):
    """Which kind of work an operation does (the proto `op` oneof)."""

    BACKUP = "operationBackup"
    INDEX_SNAPSHOT = "operationIndexSnapshot"
    FORGET = "operationForget"
    PRUNE = "operationPrune"
    RESTORE = "operationRestore"
    STATS = "operationStats"
    RUN_HOOK = "operationRunHook"
    CHECK = "operationCheck"
    RUN_COMMAND = "operationRunCommand"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class Operation:
    """One entry in the Backrest operation log."""

    id: int
    flow_id: int
    repo_id: str
    plan_id: str
    instance_id: str
    snapshot_id: str
    status: OperationStatus
    started: datetime | None
    ended: datetime | None
    display_message: str
    kind: OperationKind
    progress: BackupProgress | None = None
    summary: BackupSummary | None = None
    error_count: int = 0
    stats: RepoStats | None = None

    def is_scheduled(self, now: datetime) -> bool:
        """Return True for a pending operation that is planned for later."""
        return (
            self.status is OperationStatus.PENDING
            and self.started is not None
            and self.started > now
        )

    @property
    def duration(self) -> float | None:
        """Return the run time in seconds once the operation has ended."""
        if self.started is None or self.ended is None:
            return None
        return (self.ended - self.started).total_seconds()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Operation:
        """Parse an Operation message."""
        kind = next(
            (
                k
                for k in OperationKind
                if k is not OperationKind.OTHER and k.value in data
            ),
            OperationKind.OTHER,
        )
        progress: BackupProgress | None = None
        summary: BackupSummary | None = None
        error_count = 0
        stats: RepoStats | None = None
        if kind is OperationKind.STATS:
            stats_op = data.get(kind.value) or {}
            if "stats" in stats_op:
                stats = RepoStats.from_dict(stats_op["stats"])
        if kind is OperationKind.BACKUP:
            backup = data.get(kind.value) or {}
            last_status = backup.get("lastStatus") or {}
            if "status" in last_status:
                progress = BackupProgress.from_dict(last_status["status"])
            if "summary" in last_status:
                summary = BackupSummary.from_dict(last_status["summary"])
            error_count = len(backup.get("errors", []))
        return cls(
            id=_int(data.get("id")),
            flow_id=_int(data.get("flowId")),
            repo_id=data.get("repoId", ""),
            plan_id=data.get("planId", ""),
            instance_id=data.get("instanceId", ""),
            snapshot_id=data.get("snapshotId", ""),
            status=OperationStatus.parse(data.get("status", "STATUS_UNKNOWN")),
            started=_datetime_ms(data.get("unixTimeStartMs")),
            ended=_datetime_ms(data.get("unixTimeEndMs")),
            display_message=data.get("displayMessage", ""),
            kind=kind,
            progress=progress,
            summary=summary,
            error_count=error_count,
            stats=stats,
        )


@dataclass(frozen=True, slots=True)
class PlanBackups:
    """The newest backup operation and the newest finished one for a plan."""

    latest: Operation | None = None
    last_finished: Operation | None = None

    @classmethod
    def from_operations(
        cls, operations: list[Operation], now: datetime | None = None
    ) -> PlanBackups:
        """Pick the relevant backups out of a plan's recent operations.

        Backrest creates the next scheduled run as a pending operation that
        starts in the future. That one is not a backup yet, so it is skipped.
        """
        now = now or datetime.now(tz=UTC)
        backups = sorted(
            (
                op
                for op in operations
                if op.kind is OperationKind.BACKUP and not op.is_scheduled(now)
            ),
            key=lambda op: op.id,
            reverse=True,
        )
        latest = backups[0] if backups else None
        last_finished = next((op for op in backups if op.status.is_finished), None)
        return cls(latest=latest, last_finished=last_finished)


def latest_repo_stats(operations: list[Operation]) -> RepoStats | None:
    """Return the statistics of the newest successful stats operation."""
    return next(
        (
            op.stats
            for op in sorted(operations, key=lambda op: op.id, reverse=True)
            if op.kind is OperationKind.STATS
            and op.status is OperationStatus.SUCCESS
            and op.stats is not None
        ),
        None,
    )


@dataclass(slots=True)
class OperationList:
    """Response of GetOperations."""

    operations: list[Operation] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperationList:
        """Parse an OperationList message."""
        return cls([Operation.from_dict(op) for op in data.get("operations", [])])
