"""Async client library for the Forgejo (and Gitea) REST API."""

from __future__ import annotations

from .client import ForgejoClient
from .constants import TERMINAL_RUN_STATUSES
from .exceptions import (
    ForgejoAuthenticationError,
    ForgejoConnectionError,
    ForgejoError,
    ForgejoNotFoundError,
    ForgejoResponseError,
)
from .models import Commit, Release, Repository, ServerInfo, User, WorkflowRun

__version__ = "1.0.0"

__all__ = [
    "TERMINAL_RUN_STATUSES",
    "Commit",
    "ForgejoAuthenticationError",
    "ForgejoClient",
    "ForgejoConnectionError",
    "ForgejoError",
    "ForgejoNotFoundError",
    "ForgejoResponseError",
    "Release",
    "Repository",
    "ServerInfo",
    "User",
    "WorkflowRun",
    "__version__",
]
