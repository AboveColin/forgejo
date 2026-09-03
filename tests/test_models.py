"""Tests for the typed models.

Forgejo has been through several API generations, so every from_api has to
survive a missing field. The cases below cover the ones where a wrong guess
would be visible to a user: the zero timestamp meaning "never", the separate
issue and pull-request counters, and a commit body that must not reach a state
attribute whole.
"""

from __future__ import annotations

from forgejo import Commit, Release, Repository, ServerInfo, User, WorkflowRun
from forgejo.constants import TERMINAL_RUN_STATUSES


class TestServerInfo:
    """The version banner."""

    def test_reads_the_version(self) -> None:
        assert ServerInfo.from_api({"version": "13.0.1"}).version == "13.0.1"

    def test_a_missing_version_is_empty_not_an_error(self) -> None:
        assert ServerInfo.from_api({}).version == ""


class TestUser:
    """The authenticated account."""

    def test_reads_the_account(self) -> None:
        user = User.from_api(
            {"id": 7, "login": "colindv", "full_name": "Colin", "is_admin": True}
        )
        assert (user.id, user.login, user.full_name, user.is_admin) == (
            7,
            "colindv",
            "Colin",
            True,
        )

    def test_an_empty_full_name_becomes_none(self) -> None:
        # Forgejo sends "" rather than omitting the key when it is unset.
        assert User.from_api({"login": "a", "full_name": ""}).full_name is None

    def test_missing_fields_do_not_raise(self) -> None:
        user = User.from_api({})
        assert user.id == 0
        assert user.is_admin is False


class TestRepository:
    """Repository counters, where the naming is the trap."""

    def test_issues_and_pull_requests_are_separate_counters(self) -> None:
        # open_issues_count excludes pull requests on Forgejo and Gitea.
        # Reporting either one as "issues" changes meaning between versions.
        repo = Repository.from_api({"open_issues_count": 4, "open_pr_counter": 2})
        assert repo.open_issues == 4
        assert repo.open_pull_requests == 2

    def test_the_owner_comes_out_of_the_nested_object(self) -> None:
        repo = Repository.from_api(
            {"name": "homelab-nix", "owner": {"login": "colindv"}}
        )
        assert repo.owner == "colindv"
        assert repo.name == "homelab-nix"

    def test_a_missing_owner_object_does_not_raise(self) -> None:
        assert Repository.from_api({"name": "x"}).owner == ""

    def test_the_flags_default_to_false(self) -> None:
        repo = Repository.from_api({})
        assert (repo.private, repo.archived, repo.fork, repo.mirror) == (
            False,
            False,
            False,
            False,
        )

    def test_the_counters_default_to_zero(self) -> None:
        repo = Repository.from_api({})
        assert (repo.stars, repo.forks, repo.watchers, repo.releases) == (0, 0, 0, 0)

    def test_a_timestamp_with_a_z_suffix_parses(self) -> None:
        repo = Repository.from_api({"updated_at": "2026-08-28T09:14:02Z"})
        assert repo.updated_at is not None
        assert repo.updated_at.year == 2026

    def test_the_zero_time_means_never_not_year_one(self) -> None:
        repo = Repository.from_api({"updated_at": "0001-01-01T00:00:00Z"})
        assert repo.updated_at is None

    def test_an_unparsable_timestamp_is_dropped(self) -> None:
        assert Repository.from_api({"updated_at": "soon"}).updated_at is None


class TestWorkflowRun:
    """Actions runs."""

    def test_reads_a_run(self) -> None:
        run = WorkflowRun.from_api(
            {
                "id": 12,
                "status": "success",
                "event": "push",
                "head_branch": "main",
                "run_started_at": "2026-09-01T10:00:00Z",
            }
        )
        assert run.id == 12
        assert run.status == "success"
        assert run.started_at is not None

    def test_an_empty_status_becomes_none(self) -> None:
        assert WorkflowRun.from_api({"status": ""}).status is None

    def test_a_running_status_is_not_terminal(self) -> None:
        # "running" is not "did not succeed"; the caller has to be able to
        # tell those apart, which is what the terminal set is for.
        assert "running" not in TERMINAL_RUN_STATUSES
        assert "success" in TERMINAL_RUN_STATUSES
        assert "failure" in TERMINAL_RUN_STATUSES
        assert "cancelled" in TERMINAL_RUN_STATUSES
        assert "skipped" in TERMINAL_RUN_STATUSES


class TestRelease:
    """Releases, including drafts."""

    def test_reads_a_release(self) -> None:
        release = Release.from_api(
            {"id": 3, "tag_name": "v1.2.0", "name": "1.2.0", "published_at": "2026-09-02T14:18:09Z"}
        )
        assert release.tag_name == "v1.2.0"
        assert release.draft is False
        assert release.published_at is not None

    def test_draft_and_prerelease_are_read(self) -> None:
        release = Release.from_api({"tag_name": "v2", "draft": True, "prerelease": True})
        assert release.draft is True
        assert release.prerelease is True


class TestCommit:
    """Commit subjects, which must stay short."""

    def test_only_the_subject_line_is_kept(self) -> None:
        # A commit body can run to kilobytes, and Home Assistant caps the size
        # of a state attribute.
        commit = Commit.from_api(
            {"sha": "abc123", "commit": {"message": "Fix the thing\n\nLong body\nmore body"}}
        )
        assert commit.message == "Fix the thing"

    def test_the_author_comes_out_of_the_nested_object(self) -> None:
        commit = Commit.from_api({"commit": {"author": {"name": "Colin"}}})
        assert commit.author == "Colin"

    def test_a_commit_with_no_message_has_none(self) -> None:
        assert Commit.from_api({"sha": "a", "commit": {}}).message is None

    def test_a_missing_commit_object_does_not_raise(self) -> None:
        commit = Commit.from_api({"sha": "a"})
        assert commit.sha == "a"
        assert commit.author is None

    def test_the_created_timestamp_is_read_from_either_place(self) -> None:
        nested = Commit.from_api({"commit": {"created": "2026-01-02T03:04:05Z"}})
        top = Commit.from_api({"created": "2026-01-02T03:04:05Z"})
        assert nested.created_at == top.created_at
        assert nested.created_at is not None
