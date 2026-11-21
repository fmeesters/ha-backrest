"""Binary sensors for the Backrest integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import OperationStatus
from .coordinator import BackrestConfigEntry, PlanData
from .entity import BackrestPlanEntity

PARALLEL_UPDATES = 0


def _running(data: PlanData) -> bool:
    latest = data.backups.latest
    return latest is not None and latest.status.is_running


def _problem(data: PlanData) -> bool:
    """Report a problem when the last backup failed or the plan is overdue."""
    finished = data.backups.last_finished
    failed = finished is not None and finished.status in (
        OperationStatus.ERROR,
        OperationStatus.WARNING,
    )
    overdue = data.summary is not None and data.summary.overdue
    return failed or overdue


@dataclass(frozen=True, kw_only=True)
class BackrestBinarySensorDescription(BinarySensorEntityDescription):
    """Describes a plan binary sensor."""

    value_fn: Callable[[PlanData], bool]


PLAN_BINARY_SENSORS: tuple[BackrestBinarySensorDescription, ...] = (
    BackrestBinarySensorDescription(
        key="running",
        translation_key="running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=_running,
    ),
    BackrestBinarySensorDescription(
        key="problem",
        translation_key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=_problem,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: BackrestConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors, and add new ones when plans appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = coordinator.data.plans.keys() - known
        known.update(new)
        if new:
            async_add_entities(
                BackrestPlanBinarySensor(coordinator, description, plan_id)
                for plan_id in new
                for description in PLAN_BINARY_SENSORS
            )

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))


class BackrestPlanBinarySensor(BackrestPlanEntity, BinarySensorEntity):
    """A binary sensor for one plan."""

    entity_description: BackrestBinarySensorDescription

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        data = self.plan_data
        return self.entity_description.value_fn(data) if data else None
