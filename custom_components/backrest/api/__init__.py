"""Backrest API client, kept free of Home Assistant imports."""

from .client import BackrestClient
from .exceptions import (
    BackrestAuthenticationError,
    BackrestConnectionError,
    BackrestError,
    BackrestResponseError,
)
from .models import (
    BackrestConfig,
    BackupProgress,
    BackupSummary,
    Operation,
    OperationKind,
    OperationList,
    OperationStatus,
    Plan,
    PlanBackups,
    Repo,
    RepoStats,
    Summary,
    SummaryDashboard,
)

__all__ = [
    "BackrestAuthenticationError",
    "BackrestClient",
    "BackrestConfig",
    "BackrestConnectionError",
    "BackrestError",
    "BackrestResponseError",
    "BackupProgress",
    "BackupSummary",
    "Operation",
    "OperationKind",
    "OperationList",
    "OperationStatus",
    "Plan",
    "PlanBackups",
    "Repo",
    "RepoStats",
    "Summary",
    "SummaryDashboard",
]
