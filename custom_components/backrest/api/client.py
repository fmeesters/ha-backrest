"""Async client for the Backrest API.

Backrest exposes its gRPC service as Connect RPC: every method is a POST to
``/v1.Backrest/<Method>`` with a JSON body. Authentication is HTTP basic auth.
This module has no Home Assistant imports, so it can move to its own package.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Any

import aiohttp

from .exceptions import (
    BackrestAuthenticationError,
    BackrestConnectionError,
    BackrestResponseError,
)
from .models import (
    BackrestConfig,
    OperationList,
    PlanBackups,
    Repo,
    RepoStats,
    SummaryDashboard,
    latest_repo_stats,
)

SERVICE_PATH = "/v1.Backrest"
DEFAULT_TIMEOUT = 30
# Enough to hold the backup, snapshot index, forget, prune and hook runs of the
# last couple of backup runs, so the newest finished backup is always included.
RECENT_OPERATIONS = 40
# Stats run at most once a day, after a forget or prune. A repo logs a handful
# of operations per backup run, so this covers well over a week of history.
RECENT_REPO_OPERATIONS = 200

_AUTH_CODES = {"unauthenticated", "permission_denied"}


class BackrestClient:
    """Talk to one Backrest instance."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        username: str | None = None,
        password: str | None = None,
        *,
        verify_ssl: bool = True,
        request_timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Set up the client; no request is made yet."""
        self._session = session
        self._base_url = url.rstrip("/")
        self._auth = aiohttp.BasicAuth(username, password or "") if username else None
        self._ssl = verify_ssl
        self._timeout = aiohttp.ClientTimeout(total=request_timeout)

    @property
    def url(self) -> str:
        """Return the base URL of the instance."""
        return self._base_url

    async def _call(self, method: str, payload: dict[str, Any] | None = None) -> Any:
        """Call one unary Connect method and return the decoded JSON."""
        try:
            async with self._session.post(
                f"{self._base_url}{SERVICE_PATH}/{method}",
                json=payload or {},
                auth=self._auth,
                ssl=self._ssl,
                timeout=self._timeout,
                headers={"Connect-Protocol-Version": "1"},
            ) as response:
                if response.status in (401, 403):
                    raise BackrestAuthenticationError(
                        f"Backrest rejected the credentials ({response.status})"
                    )
                try:
                    body = await response.json(content_type=None)
                except ValueError as err:
                    raise BackrestResponseError(
                        f"{method} returned something that is not JSON"
                        f" (HTTP {response.status})"
                    ) from err
                if response.status != 200:
                    code = body.get("code") if isinstance(body, dict) else None
                    message = body.get("message", "") if isinstance(body, dict) else ""
                    if code in _AUTH_CODES:
                        raise BackrestAuthenticationError(message or code)
                    raise BackrestResponseError(
                        f"{method} failed: {code or response.status} {message}".strip(),
                        code=code,
                    )
                return body
        except TimeoutError as err:
            raise BackrestConnectionError(f"Timeout while calling {method}") from err
        except aiohttp.ClientError as err:
            raise BackrestConnectionError(f"Cannot reach Backrest: {err}") from err

    async def get_config(self) -> BackrestConfig:
        """Return the instance name, repos and plans."""
        return BackrestConfig.from_dict(await self._call("GetConfig"))

    async def get_summary_dashboard(self) -> SummaryDashboard:
        """Return the 30-day statistics per plan and repo."""
        return SummaryDashboard.from_dict(await self._call("GetSummaryDashboard"))

    async def get_operations(
        self,
        *,
        plan_id: str | None = None,
        repo_guid: str | None = None,
        last_n: int | None = None,
    ) -> OperationList:
        """Return operations for a plan or repo, optionally only the last N."""
        payload: dict[str, Any] = {}
        selector: dict[str, str] = {}
        if plan_id is not None:
            selector["planId"] = plan_id
        if repo_guid is not None:
            selector["repoGuid"] = repo_guid
        if selector:
            payload["selector"] = selector
        if last_n is not None:
            payload["lastN"] = str(last_n)
        return OperationList.from_dict(await self._call("GetOperations", payload))

    async def get_plan_backups(self, plan_id: str) -> PlanBackups:
        """Return the newest and the newest finished backup of a plan."""
        operations = await self.get_operations(
            plan_id=plan_id, last_n=RECENT_OPERATIONS
        )
        return PlanBackups.from_operations(operations.operations)

    async def get_all_plan_backups(self, plan_ids: list[str]) -> dict[str, PlanBackups]:
        """Fetch the backups of several plans in parallel."""
        results = await asyncio.gather(
            *(self.get_plan_backups(pid) for pid in plan_ids)
        )
        return dict(zip(plan_ids, results, strict=True))

    async def get_repo_stats(self, repo: Repo) -> RepoStats | None:
        """Return the newest repository statistics Backrest collected, if any.

        Backrest runs `restic stats` after a forget or prune, at most once a
        day. The summary dashboard does not fill in its snapshot count, so the
        stats operation is the source for snapshots and repository size.
        """
        if not repo.guid:
            return None
        operations = await self.get_operations(
            repo_guid=repo.guid, last_n=RECENT_REPO_OPERATIONS
        )
        return latest_repo_stats(operations.operations)

    async def get_all_repo_stats(
        self, repos: Sequence[Repo]
    ) -> dict[str, RepoStats | None]:
        """Fetch the statistics of several repos in parallel."""
        results = await asyncio.gather(*(self.get_repo_stats(r) for r in repos))
        return {repo.id: stats for repo, stats in zip(repos, results, strict=True)}
