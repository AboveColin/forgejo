"""Endpoints and magic values for the Forgejo/Gitea REST API."""

from __future__ import annotations

from typing import Final

API_PREFIX: Final = "/api/v1"

DEFAULT_TIMEOUT: Final = 10.0

# The version endpoint is the only one that answers without a token on a
# default install, which makes it the cheapest way to prove a URL points at a
# Forgejo instance before we ask the user for credentials.
EP_VERSION: Final = "/version"
EP_USER: Final = "/user"
EP_USER_REPOS: Final = "/user/repos"
EP_NEW_NOTIFICATIONS: Final = "/notifications/new"
EP_REPO: Final = "/repos/{owner}/{repo}"
EP_REPO_TASKS: Final = "/repos/{owner}/{repo}/actions/tasks"
EP_REPO_COMMITS: Final = "/repos/{owner}/{repo}/commits"
EP_REPO_RELEASES: Final = "/repos/{owner}/{repo}/releases"
EP_ISSUE_SEARCH: Final = "/repos/issues/search"

# Counting endpoints report the total in a header, so asking for a single item
# is enough to learn how many there are.
COUNT_HEADER: Final = "X-Total-Count"

# Forgejo pages repository listings; 50 is the server-side default maximum on
# most instances and keeps the picker in a config flow to one round trip.
REPO_PAGE_SIZE: Final = 50

# Terminal states reported by the Actions API. Anything else means the run is
# still going, which is not the same thing as a run that succeeded.
RUN_STATUS_SUCCESS: Final = "success"
RUN_STATUS_FAILURE: Final = "failure"
RUN_STATUS_CANCELLED: Final = "cancelled"
RUN_STATUS_SKIPPED: Final = "skipped"

TERMINAL_RUN_STATUSES: Final = frozenset(
    {
        RUN_STATUS_SUCCESS,
        RUN_STATUS_FAILURE,
        RUN_STATUS_CANCELLED,
        RUN_STATUS_SKIPPED,
    }
)
