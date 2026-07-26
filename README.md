# forgejo

Async Python client for the [Forgejo](https://forgejo.org/) REST API. Forgejo
keeps API compatibility with Gitea, so this works against Gitea instances too.

The library covers the read-only surface needed to monitor a forge: version,
account, unread notifications, repository counters, the latest Actions run, and
the tip commit. It has no Home Assistant dependency — if that is what you are
after, see [HA-Forgejo](https://github.com/AboveColin/HA-Forgejo).

## Install

```bash
pip install forgejo
```

Requires Python 3.12+.

## Use

```python
import asyncio

from forgejo import ForgejoClient


async def main() -> None:
    async with ForgejoClient("https://git.example.com", token="your-api-token") as client:
        server = await client.get_version()
        print(f"Forgejo {server.version}")

        me = await client.get_authenticated_user()
        print(f"Signed in as {me.login}")

        print(f"{await client.get_new_notification_count()} unread notifications")

        repo = await client.get_repository("example-user", "example-repo")
        print(f"{repo.full_name}: {repo.open_issues} issues, {repo.open_pull_requests} PRs")

        run = await client.get_latest_workflow_run("example-user", "example-repo")
        if run is not None:
            print(f"Last CI run: {run.name} -> {run.status}")


asyncio.run(main())
```

### Bring your own session

Pass an existing `aiohttp.ClientSession` and the client will use it and leave it
open. This is what you want inside a larger application that already pools
connections.

```python
async with aiohttp.ClientSession() as session:
    client = ForgejoClient("https://git.example.com", token="...", session=session)
```

### Self-signed certificates

Instances on a private network often use a certificate the system trust store
does not know about.

```python
client = ForgejoClient("https://git.internal", token="...", verify_ssl=False)
```

Turning verification off means the connection is encrypted but unauthenticated.
Prefer installing the CA certificate where possible.

## Getting a token

In the web UI: **Settings → Applications → Generate New Token**. Read-only
scopes are enough:

- `read:repository` — repository counters, Actions runs, commits
- `read:issue` — issue and pull-request counts
- `read:notification` — unread notification count
- `read:user` — the account the token belongs to

Everything except `get_version()` needs a token.

## API

| Method | Returns |
|---|---|
| `get_version()` | `ServerInfo` |
| `get_authenticated_user()` | `User` |
| `get_new_notification_count()` | `int` |
| `list_repositories(limit=50)` | `list[Repository]` |
| `get_repository(owner, repo)` | `Repository` |
| `get_latest_workflow_run(owner, repo)` | `WorkflowRun \| None` |
| `get_latest_commit(owner, repo)` | `Commit \| None` |

Methods return dataclasses, never raw dictionaries. `None` means the thing does
not exist — a repository with no workflows, or an empty repository with no
commits — which is different from an error.

## Errors

All exceptions derive from `ForgejoError`:

- `ForgejoConnectionError` — unreachable or timed out
- `ForgejoAuthenticationError` — token rejected or missing a scope
- `ForgejoNotFoundError` — no such repository or endpoint
- `ForgejoResponseError` — answered, but not with usable JSON

A common cause of `ForgejoResponseError` is an auth proxy in front of the
instance returning its own login page with HTTP 200.

## Notes on the API

- `open_issues` excludes pull requests. Pull requests are counted separately in
  `open_pull_requests`. This surprises people coming from the GitHub API, where
  the equivalent field includes both.
- A workflow run status is only meaningful once it reaches a terminal state.
  `TERMINAL_RUN_STATUSES` holds the set; anything else means still running,
  which is not the same as failing.

## License

MIT
