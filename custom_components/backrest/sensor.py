"""Sensors for the Backrest integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import Operation, OperationStatus
from .const import MAX_STATE_LENGTH
from .coordinator import BackrestConfigEntry, PlanData, RepoData
from .entity import BackrestPlanEntity, BackrestRepoEntity

# Read-only integration: the coordinator does all the I/O.
PARALLEL_UPDATES = 0

STATUS_OPTIONS = ["pending", "in_progress", "success", "warning", "error", "cancelled"]

_STATUS_STATE = {
    OperationStatus.PENDING: "pending",
    OperationStatus.IN_PROGRESS: "in_progress",
    OperationStatus.SUCCESS: "success",
    OperationStatus.WARNING: "warning",
    OperationStatus.ERROR: "error",
    OperationStatus.SYSTEM_CANCELLED: "cancelled",
    OperationStatus.USER_CANCELLED: "cancelled",
}

type StateType = str | int | float | datetime | None


def _status(data: PlanData) -> str | None:
    latest = data.backups.latest
    return _STATUS_STATE.get(latest.status) if latest else None


def _progress(data: PlanData) -> float | None:
    latest = data.backups.latest
    if latest is None or not latest.status.is_running:
        return None
    if latest.progress is None:
        return 0.0
    return round(latest.progress.percent_done * 100, 1)


def _running(data: PlanData) -> Operation | None:
    latest = data.backups.latest
    return latest if latest is not None and latest.status.is_running else None


def _current_started(data: PlanData) -> datetime | None:
    running = _running(data)
    return running.started if running else None


def _estimated_end(data: PlanData) -> datetime | None:
    """Extrapolate the end time from the run time so far and the percent done."""
    running = _running(data)
    if running is None or running.started is None or running.progress is None:
        return None
    done = running.progress.percent_done
    if not 0.01 <= done < 1:
        return None
    elapsed = (dt_util.utcnow() - running.started).total_seconds()
    if elapsed <= 0:
        return None
    end = running.started + timedelta(seconds=elapsed / done)
    # Whole minutes, so the state does not change on every update.
    return end.replace(second=0, microsecond=0) + timedelta(minutes=1)


def _last_backup(data: PlanData) -> datetime | None:
    finished = data.backups.last_finished
    return (finished.ended or finished.started) if finished else None


def _data_added(data: PlanData) -> int | None:
    finished = data.backups.last_finished
    if finished is None or finished.summary is None:
        return None
    return finished.summary.data_added


def _duration(data: PlanData) -> float | None:
    finished = data.backups.last_finished
    return finished.duration if finished else None


def _last_error(data: PlanData) -> str | None:
    finished = data.backups.last_finished
    if finished is None or finished.status not in (
        OperationStatus.ERROR,
        OperationStatus.WARNING,
    ):
        return None
    message = finished.display_message or finished.status.name.lower()
    return message[:MAX_STATE_LENGTH]


def _summary(attr: str) -> Callable[[PlanData | RepoData], StateType]:
    def value(data: PlanData | RepoData) -> StateType:
        return getattr(data.summary, attr) if data.summary else None

    return value


def _stats(attr: str) -> Callable[[RepoData], StateType]:
    """Read a repo statistic; unknown until Backrest has collected stats."""

    def value(data: RepoData) -> StateType:
        return getattr(data.stats, attr) if data.stats else None

    return value


@dataclass(frozen=True, kw_only=True)
class BackrestPlanSensorDescription(SensorEntityDescription):
    """Describes a plan sensor."""

    value_fn: Callable[[PlanData], StateType]


@dataclass(frozen=True, kw_only=True)
class BackrestRepoSensorDescription(SensorEntityDescription):
    """Describes a repo sensor."""

    value_fn: Callable[[RepoData], StateType]


PLAN_SENSORS: tuple[BackrestPlanSensorDescription, ...] = (
    BackrestPlanSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=STATUS_OPTIONS,
        value_fn=_status,
    ),
    BackrestPlanSensorDescription(
        key="progress",
        translation_key="progress",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_progress,
    ),
    BackrestPlanSensorDescription(
        key="current_started",
        translation_key="current_started",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_current_started,
    ),
    BackrestPlanSensorDescription(
        key="estimated_end",
        translation_key="estimated_end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_estimated_end,
    ),
    BackrestPlanSensorDescription(
        key="last_backup",
        translation_key="last_backup",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_last_backup,
    ),
    BackrestPlanSensorDescription(
        key="next_backup",
        translation_key="next_backup",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_summary("next_backup"),
    ),
    BackrestPlanSensorDescription(
        key="last_data_added",
        translation_key="last_data_added",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        suggested_display_precision=1,
        value_fn=_data_added,
    ),
    BackrestPlanSensorDescription(
        key="last_duration",
        translation_key="last_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=1,
        value_fn=_duration,
    ),
    BackrestPlanSensorDescription(
        key="last_error",
        translation_key="last_error",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_error,
    ),
    BackrestPlanSensorDescription(
        key="protected_data",
        translation_key="protected_data",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        value_fn=_summary("protected_bytes"),
    ),
    BackrestPlanSensorDescription(
        key="backups_success_30d",
        translation_key="backups_success_30d",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_summary("backups_success_30d"),
    ),
    BackrestPlanSensorDescription(
        key="backups_warning_30d",
        translation_key="backups_warning_30d",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=_summary("backups_warning_30d"),
    ),
    BackrestPlanSensorDescription(
        key="backups_failed_30d",
        translation_key="backups_failed_30d",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_summary("backups_failed_30d"),
    ),
)

REPO_SENSORS: tuple[BackrestRepoSensorDescription, ...] = (
    BackrestRepoSensorDescription(
        key="snapshots",
        translation_key="snapshots",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_stats("snapshot_count"),
    ),
    BackrestRepoSensorDescription(
        key="repo_size",
        translation_key="repo_size",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        value_fn=_stats("total_size"),
    ),
    BackrestRepoSensorDescription(
        key="compression_ratio",
        translation_key="compression_ratio",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_stats("compression_ratio"),
    ),
    BackrestRepoSensorDescription(
        key="data_added_30d",
        translation_key="data_added_30d",
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        suggested_display_precision=2,
        value_fn=_summary("bytes_added_30d"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BackrestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, and add new ones when plans or repos appear."""
    coordinator = entry.runtime_data
    known_plans: set[str] = set()
    known_repos: set[str] = set()

    @callback
    def _add_new() -> None:
        entities: list[SensorEntity] = []
        for plan_id in coordinator.data.plans.keys() - known_plans:
            known_plans.add(plan_id)
            entities.extend(
                BackrestPlanSensor(coordinator, description, plan_id)
                for description in PLAN_SENSORS
            )
        for repo_id in coordinator.data.repos.keys() - known_repos:
            known_repos.add(repo_id)
            repo = coordinator.data.repos[repo_id].repo
            entities.extend(
                BackrestRepoSensor(coordinator, description, repo)
                for description in REPO_SENSORS
            )
        if entities:
            async_add_entities(entities)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class BackrestPlanSensor(BackrestPlanEntity, SensorEntity):
    """A sensor for one plan."""

    entity_description: BackrestPlanSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        data = self.plan_data
        return self.entity_description.value_fn(data) if data else None


class BackrestRepoSensor(BackrestRepoEntity, SensorEntity):
    """A sensor for one repository."""

    entity_description: BackrestRepoSensorDescription

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        data = self.repo_data
        return self.entity_description.value_fn(data) if data else None
