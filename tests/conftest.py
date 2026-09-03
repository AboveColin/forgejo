"""Shared fixtures for the Forgejo client tests.

The client is exercised against a real aiohttp server on a loopback port
rather than a mocking library. Mocking libraries for aiohttp lag its releases
and break the suite on an unrelated bump; a real server does not, and it also
exercises status codes, headers and connection failures for real.
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator, Callable

import pytest
import pytest_asyncio
from aiohttp import ClientSession, web

from forgejo import ForgejoClient

API = "/api/v1"


class FakeForgejo:
    """A loopback server that answers whatever a test tells it to.

    ``requests`` records every request that arrived, so a test can assert on
    the query string and headers the client sent.
    """

    def __init__(self) -> None:
        self.app = web.Application()
        self.requests: list[web.Request] = []
        self._routes: dict[str, Callable[[web.Request], web.StreamResponse]] = {}
        self.app.router.add_route("*", "/{tail:.*}", self._dispatch)
        self.url = ""

    def handle(self, path: str, handler: Callable[[web.Request], web.StreamResponse]) -> None:
        """Answer the API path ``path`` with ``handler``."""
        self._routes[API + path] = handler

    def json(
        self, path: str, payload: object, status: int = 200, headers: dict | None = None
    ) -> None:
        """Answer ``path`` with a JSON body, and optional response headers."""
        self.handle(
            path, lambda _r: web.json_response(payload, status=status, headers=headers)
        )

    def text(self, path: str, body: str, content_type: str = "text/plain") -> None:
        """Answer ``path`` with a text body."""
        self.handle(path, lambda _r: web.Response(text=body, content_type=content_type))

    def status(self, path: str, code: int) -> None:
        """Answer ``path`` with a bare status code."""
        self.handle(path, lambda _r: web.Response(status=code))

    async def _dispatch(self, request: web.Request) -> web.StreamResponse:
        self.requests.append(request)
        handler = self._routes.get(request.path)
        if handler is None:
            return web.Response(status=404)
        result = handler(request)
        return await result if hasattr(result, "__await__") else result


@pytest_asyncio.fixture
async def api() -> AsyncIterator[FakeForgejo]:
    """A running fake Forgejo, with its address filled in."""
    fake = FakeForgejo()
    runner = web.AppRunner(fake.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    fake.url = f"http://127.0.0.1:{runner.addresses[0][1]}"
    try:
        yield fake
    finally:
        await runner.cleanup()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[ClientSession]:
    """A session the test owns, so client.close() must leave it open."""
    async with ClientSession() as open_session:
        yield open_session


@pytest_asyncio.fixture
async def client(api: FakeForgejo, session: ClientSession) -> AsyncIterator[ForgejoClient]:
    """A client pointed at the fake, carrying a token."""
    instance = ForgejoClient(api.url, "t0ken", session=session)
    yield instance
    await instance.close()


@pytest.fixture(name="closed_port")
def fixture_closed_port() -> str:
    """An address on loopback with nothing listening behind it."""
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture(autouse=True)
def no_outbound_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test that tries to resolve a name outside loopback.

    This is a tripwire, not a limit: every test here talks to a fake on
    127.0.0.1, so correct tests never notice it exists. It is here because a
    test that points a client at a real host looks exactly like a test that
    points it at a fake, right up until the suite is talking to production.

    The guard sits on getaddrinfo rather than on connect, because that is where
    every outbound connection starts and it is the last point at which the
    hostname is still readable. Guarding the socket instead reports an empty
    address list, which says nothing about what went wrong.
    """
    import socket

    allowed = {"127.0.0.1", "::1", "localhost", ""}
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        if host is not None and str(host) not in allowed:
            raise AssertionError(
                f"a test tried to reach {host!r}. Tests must only talk to the "
                "local fake: point the client at the api fixture, not a real "
                "host."
            )
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
