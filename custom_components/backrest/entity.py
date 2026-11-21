"""Base entities for the Backrest integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import Repo
from .const import DOMAIN, MANUFACTURER
from .coordinator import BackrestCoordinator, PlanData, RepoData


def plan_identifier(instance: str, plan_id: str) -> tuple[str, str]:
    """Return the device identifier of a plan."""
    return (DOMAIN, f"{instance}_plan_{plan_id}")


def repo_identifier(instance: str, repo: Repo) -> tuple[str, str]:
    """Return the device identifier of a repo (its GUID survives a rename)."""
    return (DOMAIN, f"{instance}_repo_{repo.guid or repo.id}")


class BackrestPlanEntity(CoordinatorEntity[BackrestCoordinator]):
    """An entity that belongs to one backup plan."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BackrestCoordinator,
        description: EntityDescription,
        plan_id: str,
    ) -> None:
        """Bind the entity to a plan."""
        super().__init__(coordinator)
        self.entity_description = description
        self.plan_id = plan_id
        instance = coordinator.instance
        self._attr_unique_id = f"{instance}_plan_{plan_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={plan_identifier(instance, plan_id)},
            name=f"{instance} {plan_id}",
            manufacturer=MANUFACTURER,
            model="Backup plan",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, instance),
            configuration_url=coordinator.client.url,
        )

    @property
    def plan_data(self) -> PlanData | None:
        """Return the current data of this plan, if it still exists."""
        return self.coordinator.data.plans.get(self.plan_id)

    @property
    def available(self) -> bool:
        """Return False once the plan is removed from Backrest."""
        return super().available and self.plan_data is not None


class BackrestRepoEntity(CoordinatorEntity[BackrestCoordinator]):
    """An entity that belongs to one repository."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: BackrestCoordinator,
        description: EntityDescription,
        repo: Repo,
    ) -> None:
        """Bind the entity to a repo."""
        super().__init__(coordinator)
        self.entity_description = description
        self.repo_id = repo.id
        instance = coordinator.instance
        self._attr_unique_id = (
            f"{instance}_repo_{repo.guid or repo.id}_{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={repo_identifier(instance, repo)},
            name=f"{instance} {repo.id}",
            manufacturer=MANUFACTURER,
            model="Repository",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, instance),
            configuration_url=coordinator.client.url,
        )

    @property
    def repo_data(self) -> RepoData | None:
        """Return the current data of this repo, if it still exists."""
        return self.coordinator.data.repos.get(self.repo_id)

    @property
    def available(self) -> bool:
        """Return False once the repo is removed from Backrest."""
        return super().available and self.repo_data is not None
