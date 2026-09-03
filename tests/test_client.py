"""Tests for the HTTP client.

Two behaviours carry most of the risk here. The count endpoints read a total
out of a response header rather than paging, so a missing header has to be an
error and not a silent zero. And three endpoints treat "nothing there" as a
state rather than a failure: a repository with no releases, no Actions runs, or
no commits at all.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest
from aiohttp import web

from forgejo import (
    ForgejoAuthenticationError,
    ForgejoClient,
    ForgejoConnectionError,
    ForgejoNotFoundError,
    ForgejoResponseError,
)

from .conftest import FakeForgejo

VERSION = "/version"
USER = "/user"
NEW = "/notifications/new"
SEARCH = "/repos/issues/search"
REPOS = "/user/repos"
REPO = "/repos/colindv/homelab-nix"
RELEASES = "/repos/colindv/homelab-nix/releases"
TASKS = "/repos/colindv/homelab-nix/actions/tasks"
COMMITS = "/repos/colindv/homelab-nix/commits"


class TestVersion:
    """The one endpoint that answers without a token."""

    async def test_reads_the_version(self, client: ForgejoClient, api: FakeForgejo) -> None:
        api.json(VERSION, {"version": "13.0.1"})
        assert (await client.get_version()).version == "13.0.1"

    async def test_a_payload_without_a_version_is_not_a_forgejo(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        # A 200 from some other service proves nothing. The version key is
        # what distinguishes a Forgejo from anything else answering on /api/v1.
        api.json(VERSION, {"hello": "world"})
        with pytest.raises(ForgejoResponseError, match="not a Forgejo API"):
            await client.get_version()

    async def test_a_list_where_an_object_belongs_is_a_response_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(VERSION, [{"version": "13"}])
        with pytest.raises(ForgejoResponseError):
            await client.get_version()


class TestAuthentication:
    """The token goes in an Authorization header, Forgejo style."""

    async def test_the_token_is_sent_as_a_token_header(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(USER, {"login": "colindv"})
        await client.get_authenticated_user()
        assert api.requests[-1].headers["Authorization"] == "token t0ken"

    async def test_no_token_sends_no_header(
        self, api: FakeForgejo, session: aiohttp.ClientSession
    ) -> None:
        api.json(VERSION, {"version": "13"})
        client = ForgejoClient(api.url, session=session)
        await client.get_version()
        assert "Authorization" not in api.requests[-1].headers

    @pytest.mark.parametrize("status", [401, 403])
    async def test_a_rejected_token_is_an_authentication_error(
        self, client: ForgejoClient, api: FakeForgejo, status: int
    ) -> None:
        api.status(USER, status)
        with pytest.raises(ForgejoAuthenticationError, match="scopes"):
            await client.get_authenticated_user()


class TestErrorMapping:
    """Every failure has exactly one type."""

    async def test_a_missing_endpoint_is_a_not_found_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.status(REPO, 404)
        with pytest.raises(ForgejoNotFoundError):
            await client.get_repository("colindv", "homelab-nix")

    async def test_a_server_error_is_a_response_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.status(VERSION, 500)
        with pytest.raises(ForgejoResponseError, match="500"):
            await client.get_version()

    async def test_a_timeout_is_a_connection_error(
        self, api: FakeForgejo, session: aiohttp.ClientSession
    ) -> None:
        async def slow(_request: web.Request) -> web.StreamResponse:
            await asyncio.sleep(5)
            return web.json_response({})

        api.handle(VERSION, slow)
        client = ForgejoClient(api.url, session=session, timeout=0.1)
        with pytest.raises(ForgejoConnectionError, match="Timeout"):
            await client.get_version()

    async def test_an_unreachable_host_is_a_connection_error(
        self, session: aiohttp.ClientSession, closed_port: str
    ) -> None:
        client = ForgejoClient(closed_port, session=session)
        with pytest.raises(ForgejoConnectionError, match="Cannot reach"):
            await client.get_version()

    async def test_html_behind_a_login_portal_is_a_response_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.text(VERSION, "<html>Sign in</html>", "text/html")
        with pytest.raises(ForgejoResponseError, match="auth proxy"):
            await client.get_version()

    async def test_json_with_the_wrong_content_type_is_still_accepted(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.text(VERSION, '{"version": "13.0.1"}', "text/plain")
        assert (await client.get_version()).version == "13.0.1"


class TestCounting:
    """Counts come from X-Total-Count, not from paging."""

    async def test_the_count_comes_from_the_header(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(SEARCH, [], headers={"X-Total-Count": "17"})
        assert await client.get_assigned_issue_count() == 17

    async def test_only_one_item_is_requested(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        # Paging through everything just to count it would be wasted traffic.
        api.json(SEARCH, [], headers={"X-Total-Count": "500"})
        await client.get_assigned_issue_count()
        assert api.requests[-1].query["limit"] == "1"

    async def test_the_assigned_query_asks_for_open_and_assigned(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(SEARCH, [], headers={"X-Total-Count": "1"})
        await client.get_assigned_issue_count()
        query = api.requests[-1].query
        assert query["state"] == "open"
        assert query["assigned"] == "true"

    async def test_the_review_query_asks_for_pulls_awaiting_review(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(SEARCH, [], headers={"X-Total-Count": "2"})
        assert await client.get_review_request_count() == 2
        query = api.requests[-1].query
        assert query["type"] == "pulls"
        assert query["review_requested"] == "true"

    async def test_a_missing_count_header_reads_as_zero(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(SEARCH, [])
        assert await client.get_assigned_issue_count() == 0

    async def test_an_unparsable_count_header_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(SEARCH, [], headers={"X-Total-Count": "many"})
        with pytest.raises(ForgejoResponseError, match="X-Total-Count"):
            await client.get_assigned_issue_count()

    async def test_notifications_are_read_from_the_body(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(NEW, {"new": 4})
        assert await client.get_new_notification_count() == 4

    async def test_no_new_key_means_no_notifications(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(NEW, {})
        assert await client.get_new_notification_count() == 0


class TestEmptyIsAState:
    """Three endpoints where "nothing there" is an answer, not a failure."""

    async def test_a_repository_with_no_releases_returns_none(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        # /releases/latest answers 404 for this case, which is why the list
        # endpoint is used instead.
        api.json(RELEASES, [])
        assert await client.get_latest_release("colindv", "homelab-nix") is None

    async def test_the_newest_release_is_returned(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(RELEASES, [{"id": 1, "tag_name": "v2.0.0"}])
        release = await client.get_latest_release("colindv", "homelab-nix")
        assert release is not None
        assert release.tag_name == "v2.0.0"

    async def test_a_repository_with_no_workflow_runs_returns_none(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(TASKS, {"workflow_runs": []})
        assert await client.get_latest_workflow_run("colindv", "homelab-nix") is None

    async def test_the_newest_workflow_run_is_returned(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(TASKS, {"workflow_runs": [{"id": 9, "status": "success"}]})
        run = await client.get_latest_workflow_run("colindv", "homelab-nix")
        assert run is not None
        assert run.status == "success"

    async def test_an_empty_repository_has_no_commit_rather_than_a_404(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        # A repository with no commits answers 404 on /commits. That is a
        # state, and turning it into an error would break a fresh repo.
        api.status(COMMITS, 404)
        assert await client.get_latest_commit("colindv", "homelab-nix") is None

    async def test_the_tip_commit_is_returned(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(COMMITS, [{"sha": "abc", "commit": {"message": "Subject\n\nbody"}}])
        commit = await client.get_latest_commit("colindv", "homelab-nix")
        assert commit is not None
        assert commit.message == "Subject"

    async def test_the_commit_request_skips_the_diff_stat(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(COMMITS, [{"sha": "abc"}])
        await client.get_latest_commit("colindv", "homelab-nix")
        assert api.requests[-1].query["stat"] == "false"

    async def test_a_404_on_a_repository_is_still_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        # Only /commits swallows a 404. A missing repository must still raise.
        api.status(REPO, 404)
        with pytest.raises(ForgejoNotFoundError):
            await client.get_repository("colindv", "homelab-nix")


class TestRepositoryListing:
    """The picker's round trip."""

    async def test_lists_repositories(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, [{"name": "a"}, {"name": "b"}])
        assert [r.name for r in await client.list_repositories()] == ["a", "b"]

    async def test_a_non_object_entry_is_skipped(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, [{"name": "a"}, "junk", None])
        assert len(await client.list_repositories()) == 1

    async def test_an_object_where_a_list_belongs_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, {"error": "nope"})
        with pytest.raises(ForgejoResponseError):
            await client.list_repositories()

    async def test_the_default_page_size_is_sent(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, [])
        await client.list_repositories()
        assert api.requests[-1].query["limit"] == "50"

    async def test_a_caller_can_override_the_page_size(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, [])
        await client.list_repositories(limit=5)
        assert api.requests[-1].query["limit"] == "5"


class TestSessionOwnership:
    """close() must only close what the client created."""

    async def test_a_borrowed_session_survives_close(
        self, api: FakeForgejo, session: aiohttp.ClientSession
    ) -> None:
        client = ForgejoClient(api.url, session=session)
        await client.close()
        assert session.closed is False

    async def test_an_owned_session_is_closed(self, api: FakeForgejo) -> None:
        api.json(VERSION, {"version": "13"})
        client = ForgejoClient(api.url)
        await client.get_version()
        owned = client._session  # noqa: SLF001  ownership is the thing under test
        assert owned is not None
        await client.close()
        assert owned.closed is True

    async def test_the_context_manager_closes_an_owned_session(
        self, api: FakeForgejo
    ) -> None:
        api.json(VERSION, {"version": "13"})
        async with ForgejoClient(api.url) as client:
            await client.get_version()
            owned = client._session  # noqa: SLF001
        assert owned is not None
        assert owned.closed is True


class TestAddressHandling:
    """The API prefix is added once, whatever the caller passes."""

    @pytest.mark.parametrize("suffix", ["", "/"])
    async def test_a_trailing_slash_does_not_change_the_target(
        self, api: FakeForgejo, session: aiohttp.ClientSession, suffix: str
    ) -> None:
        api.json(VERSION, {"version": "13"})
        client = ForgejoClient(api.url + suffix, session=session)
        await client.get_version()
        assert api.requests[-1].path == "/api/v1/version"

    async def test_a_none_parameter_is_left_out_of_the_query(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPOS, [])
        await client._request("/user/repos", limit=10, sort=None)  # noqa: SLF001
        assert "sort" not in api.requests[-1].query
        assert api.requests[-1].query["limit"] == "10"


class TestWrongPayloadShapes:
    """Every endpoint that expects an object must reject a list, and back."""

    async def test_a_list_for_the_current_user_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(USER, [{"login": "colindv"}])
        with pytest.raises(ForgejoResponseError, match="current user"):
            await client.get_authenticated_user()

    async def test_a_list_for_notifications_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(NEW, [])
        with pytest.raises(ForgejoResponseError, match="notifications"):
            await client.get_new_notification_count()

    async def test_a_list_for_one_repository_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPO, [{"name": "homelab-nix"}])
        with pytest.raises(ForgejoResponseError, match="homelab-nix"):
            await client.get_repository("colindv", "homelab-nix")

    async def test_a_list_for_workflow_runs_is_an_error(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(TASKS, [])
        with pytest.raises(ForgejoResponseError, match="runs"):
            await client.get_latest_workflow_run("colindv", "homelab-nix")

    async def test_an_object_where_a_commit_list_belongs_yields_no_commit(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(COMMITS, {"error": "nope"})
        assert await client.get_latest_commit("colindv", "homelab-nix") is None

    async def test_a_non_object_release_entry_yields_no_release(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(RELEASES, ["junk"])
        assert await client.get_latest_release("colindv", "homelab-nix") is None

    async def test_a_non_object_run_entry_yields_no_run(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(TASKS, {"workflow_runs": ["junk"]})
        assert await client.get_latest_workflow_run("colindv", "homelab-nix") is None


class TestReadingOneRepository:
    """The happy path for a single repository."""

    async def test_reads_the_counters(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(
            REPO,
            {
                "id": 4,
                "name": "homelab-nix",
                "full_name": "colindv/homelab-nix",
                "owner": {"login": "colindv"},
                "open_issues_count": 3,
                "open_pr_counter": 1,
                "stars_count": 2,
            },
        )
        repo = await client.get_repository("colindv", "homelab-nix")
        assert repo.full_name == "colindv/homelab-nix"
        assert repo.open_issues == 3
        assert repo.open_pull_requests == 1
        assert repo.stars == 2

    async def test_the_owner_and_name_reach_the_path(
        self, client: ForgejoClient, api: FakeForgejo
    ) -> None:
        api.json(REPO, {"name": "homelab-nix"})
        await client.get_repository("colindv", "homelab-nix")
        assert api.requests[-1].path == "/api/v1/repos/colindv/homelab-nix"
