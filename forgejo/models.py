"""Typed models returned by the client.

Callers never see raw JSON. Every ``from_api`` classmethod is defensive about
missing keys: Forgejo has been through several API generations and a field that
exists on one instance may be absent on an older or newer one. A missing value
becomes ``None`` rather than a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

__all__ = ["Commit", "Repository", "ServerInfo", "User", "WorkflowRun"]


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an API timestamp, tolerating the ``Z`` suffix and junk."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Forgejo returns the zero time for "never happened"; surfacing year 1 as a
    # real timestamp makes template sensors render nonsense dates.
    return None if parsed.year <= 1 else parsed


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """Version banner of the instance."""

    version: str

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ServerInfo:
        """Build from a ``/version`` payload."""
        return cls(version=str(data.get("version", "")))


@dataclass(frozen=True, slots=True)
class User:
    """The account the token belongs to."""

    id: int
    login: str
    full_name: str | None
    is_admin: bool

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> User:
        """Build from a ``/user`` payload."""
        return cls(
            id=int(data.get("id", 0)),
            login=str(data.get("login", "")),
            full_name=data.get("full_name") or None,
            is_admin=bool(data.get("is_admin", False)),
        )


@dataclass(frozen=True, slots=True)
class Repository:
    """A single repository and its counters."""

    id: int
    name: str
    owner: str
    full_name: str
    private: bool
    archived: bool
    fork: bool
    mirror: bool
    default_branch: str | None
    description: str | None
    language: str | None
    html_url: str | None
    has_actions: bool
    open_issues: int
    open_pull_requests: int
    stars: int
    forks: int
    watchers: int
    releases: int
    size_kb: int
    updated_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Repository:
        """Build from a ``/repos/{owner}/{repo}`` payload."""
        owner = data.get("owner") or {}
        return cls(
            id=int(data.get("id", 0)),
            name=str(data.get("name", "")),
            owner=str(owner.get("login", "")),
            full_name=str(data.get("full_name", "")),
            private=bool(data.get("private", False)),
            archived=bool(data.get("archived", False)),
            fork=bool(data.get("fork", False)),
            mirror=bool(data.get("mirror", False)),
            default_branch=data.get("default_branch") or None,
            description=data.get("description") or None,
            language=data.get("language") or None,
            html_url=data.get("html_url") or None,
            has_actions=bool(data.get("has_actions", False)),
            # open_issues_count excludes pull requests on Forgejo and Gitea;
            # open_pr_counter is the separate figure. Adding them together
            # would double-count nothing, but reporting either as "issues"
            # silently changes meaning between forge versions.
            open_issues=int(data.get("open_issues_count", 0)),
            open_pull_requests=int(data.get("open_pr_counter", 0)),
            stars=int(data.get("stars_count", 0)),
            forks=int(data.get("forks_count", 0)),
            watchers=int(data.get("watchers_count", 0)),
            releases=int(data.get("release_counter", 0)),
            size_kb=int(data.get("size", 0)),
            updated_at=_parse_timestamp(data.get("updated_at")),
        )


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """One Forgejo Actions run."""

    id: int
    name: str | None
    workflow_id: str | None
    status: str | None
    event: str | None
    head_branch: str | None
    head_sha: str | None
    run_number: int | None
    display_title: str | None
    url: str | None
    started_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> WorkflowRun:
        """Build from an entry of ``/actions/tasks``."""
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name") or None,
            workflow_id=data.get("workflow_id") or None,
            status=data.get("status") or None,
            event=data.get("event") or None,
            head_branch=data.get("head_branch") or None,
            head_sha=data.get("head_sha") or None,
            run_number=data.get("run_number"),
            display_title=data.get("display_title") or None,
            url=data.get("url") or None,
            started_at=_parse_timestamp(data.get("run_started_at")),
            updated_at=_parse_timestamp(data.get("updated_at")),
        )


@dataclass(frozen=True, slots=True)
class Commit:
    """The tip commit of a branch."""

    sha: str
    message: str | None
    author: str | None
    html_url: str | None
    created_at: datetime | None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> Commit:
        """Build from an entry of ``/commits``."""
        commit = data.get("commit") or {}
        author = commit.get("author") or {}
        message = commit.get("message")
        return cls(
            sha=str(data.get("sha", "")),
            # Only the subject line is useful as a state attribute; the body
            # can run to kilobytes and Home Assistant caps attribute size.
            message=message.strip().splitlines()[0] if message else None,
            author=author.get("name") or None,
            html_url=data.get("html_url") or None,
            created_at=_parse_timestamp(commit.get("created") or data.get("created")),
        )
