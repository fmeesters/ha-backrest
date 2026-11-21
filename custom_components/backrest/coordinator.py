"""Data update coordinator for the Backrest integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import (
    BackrestAuthenticationError,
    BackrestClient,
    BackrestConfig,
    BackrestError,
    Plan,
    PlanBackups,
    Repo,
    Summary,
)
from .const import DOMAIN, LOGGER, SCAN_INTERVAL

type BackrestConfigEntry = ConfigEntry[BackrestCoordinator]


@dataclass(slots=True)
class PlanData:
    """Everything known about one plan."""

    plan: Plan
    summary: Summary | None
    backups: PlanBackups


@dataclass(slots=True)
class RepoData:
    """Everything known about one repository."""

    repo: Repo
    summary: Summary | None


@dataclass(slots=True)
class BackrestData:
    """A snapshot of one Backrest instance."""

    config: BackrestConfig
    plans: dict[str, PlanData] = field(default_factory=dict)
    repos: dict[str, RepoData] = field(default_factory=dict)


class BackrestCoordinator(DataUpdateCoordinator[BackrestData]):
    """Fetch configuration, statistics and recent backups from Backrest."""

    config_entry: BackrestConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: BackrestConfigEntry,
        client: BackrestClient,
    ) -> None:
        """Set up the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=SCAN_INTERVAL,
            # Skip state writes when nothing changed (all data are dataclasses).
            always_update=False,
        )
        self.client = client

    @property
    def instance(self) -> str:
        """Return the Backrest instance name, the stable ID of this entry."""
        return str(self.config_entry.unique_id)

    async def _async_update_data(self) -> BackrestData:
        """Fetch the latest state from Backrest."""
        try:
            config = await self.client.get_config()
            summary, backups = await asyncio.gather(
                self.client.get_summary_dashboard(),
                self.client.get_all_plan_backups([plan.id for plan in config.plans]),
            )
        except BackrestAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except BackrestError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err

        return BackrestData(
            config=config,
            plans={
                plan.id: PlanData(
                    plan=plan,
                    summary=summary.plans.get(plan.id),
                    backups=backups[plan.id],
                )
                for plan in config.plans
            },
            repos={
                repo.id: RepoData(repo=repo, summary=summary.repos.get(repo.id))
                for repo in config.repos
            },
        )
