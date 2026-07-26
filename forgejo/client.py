"""Async client for the Forgejo (and Gitea) REST API."""

from __future__ import annotations

import asyncio
import socket
from types import TracebackType
from typing import Any, Self

import aiohttp
from yarl import URL

from .constants import (
    API_PREFIX,
    DEFAULT_TIMEOUT,
    EP_NEW_NOTIFICATIONS,
    EP_REPO,
    EP_REPO_COMMITS,
    EP_REPO_TASKS,
    EP_USER,
    EP_USER_REPOS,
    EP_VERSION,
    REPO_PAGE_SIZE,
)
from .exceptions import (
    ForgejoAuthenticationError,
    ForgejoConnectionError,
    ForgejoNotFoundError,
    ForgejoResponseError,
)
from .models import Commit, Repository, ServerInfo, User, WorkflowRun

__all__ = ["ForgejoClient"]


class ForgejoClient:
    """Talk to one Forgejo instance.

    The client is safe to reuse across many requests and holds no state beyond
    the session and credentials.
    """

    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        verify_ssl: bool = True,
    ) -> None:
        """Configure the client.

        Pass ``session`` to reuse an existing one; the caller keeps ownership of
        it and ``close()`` will leave it open.
        """
        self._base = URL(base_url.rstrip("/") + API_PREFIX + "/")
        self._token = token
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._verify_ssl = verify_ssl

    async def __aenter__(self) -> Self:
        """Enter the context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Leave the context manager, closing an owned session."""
        await self.close()

    async def close(self) -> None:
        """Close the session, but only if this client created it."""
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    async def _request(self, path: str, **params: Any) -> Any:
        """Perform one GET and return decoded JSON."""
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._owns_session = True

        headers = {"Accept": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"

        url = self._base.join(URL(path.lstrip("/")))
        try:
            response = await self._session.get(
                url,
                headers=headers,
                params={k: str(v) for k, v in params.items() if v is not None},
                timeout=self._timeout,
                ssl=self._verify_ssl,
            )
        except asyncio.TimeoutError as err:
            raise ForgejoConnectionError(f"Timeout talking to {url.host}") from err
        except (aiohttp.ClientError, socket.gaierror) as err:
            raise ForgejoConnectionError(f"Cannot reach {url.host}: {err}") from err

        async with response:
            if response.status in (401, 403):
                raise ForgejoAuthenticationError(
                    "Forgejo rejected the token; check that it is valid and has "
                    "the required read scopes"
                )
            if response.status == 404:
                raise ForgejoNotFoundError(f"Not found: {path}")
            if response.status >= 400:
                raise ForgejoResponseError(
                    f"Forgejo returned HTTP {response.status} for {path}"
                )
            # A reverse proxy that intercepts the request (an auth portal, a
            # captive login page) answers 200 with HTML. Decoding rather than
            # trusting Content-Type keeps the error message honest.
            try:
                return await response.json(content_type=None)
            except ValueError as err:
                raise ForgejoResponseError(
                    f"Expected JSON from {path}; got something else. Is this URL "
                    "really a Forgejo instance, and is it behind an auth proxy?"
                ) from err

    async def get_version(self) -> ServerInfo:
        """Read the instance version. Works without a token on most installs."""
        data = await self._request(EP_VERSION)
        if not isinstance(data, dict) or "version" not in data:
            raise ForgejoResponseError("No version in response; not a Forgejo API")
        return ServerInfo.from_api(data)

    async def get_authenticated_user(self) -> User:
        """Read the account the token belongs to."""
        data = await self._request(EP_USER)
        if not isinstance(data, dict):
            raise ForgejoResponseError("Unexpected payload for the current user")
        return User.from_api(data)

    async def get_new_notification_count(self) -> int:
        """Count unread notifications for the authenticated user."""
        data = await self._request(EP_NEW_NOTIFICATIONS)
        if not isinstance(data, dict):
            raise ForgejoResponseError("Unexpected payload for notifications")
        return int(data.get("new", 0))

    async def list_repositories(self, limit: int = REPO_PAGE_SIZE) -> list[Repository]:
        """List repositories the token can see, newest activity first."""
        data = await self._request(EP_USER_REPOS, limit=limit)
        if not isinstance(data, list):
            raise ForgejoResponseError("Unexpected payload for the repository list")
        return [Repository.from_api(item) for item in data if isinstance(item, dict)]

    async def get_repository(self, owner: str, repo: str) -> Repository:
        """Read one repository and its counters."""
        data = await self._request(EP_REPO.format(owner=owner, repo=repo))
        if not isinstance(data, dict):
            raise ForgejoResponseError(f"Unexpected payload for {owner}/{repo}")
        return Repository.from_api(data)

    async def get_latest_workflow_run(
        self, owner: str, repo: str
    ) -> WorkflowRun | None:
        """Return the most recent Actions run, or ``None`` if there are none.

        No runs is a legitimate answer for a repository without workflows, so
        it is not an error.
        """
        data = await self._request(
            EP_REPO_TASKS.format(owner=owner, repo=repo), limit=1
        )
        if not isinstance(data, dict):
            raise ForgejoResponseError(f"Unexpected payload for {owner}/{repo} runs")
        runs = data.get("workflow_runs") or []
        if not runs or not isinstance(runs[0], dict):
            return None
        return WorkflowRun.from_api(runs[0])

    async def get_latest_commit(self, owner: str, repo: str) -> Commit | None:
        """Return the tip commit of the default branch, if the repo has one."""
        try:
            data = await self._request(
                EP_REPO_COMMITS.format(owner=owner, repo=repo), limit=1, stat="false"
            )
        except ForgejoNotFoundError:
            # An empty repository has no commits and answers 404 here. That is
            # a state, not a failure.
            return None
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            return None
        return Commit.from_api(data[0])
