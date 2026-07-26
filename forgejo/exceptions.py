"""Exceptions raised by the Forgejo client."""

from __future__ import annotations

__all__ = [
    "ForgejoAuthenticationError",
    "ForgejoConnectionError",
    "ForgejoError",
    "ForgejoNotFoundError",
    "ForgejoResponseError",
]


class ForgejoError(Exception):
    """Base class for every error raised by this library."""


class ForgejoConnectionError(ForgejoError):
    """The server could not be reached, or it did not answer in time."""


class ForgejoAuthenticationError(ForgejoError):
    """The token was rejected, or it lacks the scope for this request."""


class ForgejoNotFoundError(ForgejoError):
    """The requested repository, user or endpoint does not exist."""


class ForgejoResponseError(ForgejoError):
    """The server answered, but not with something we can use."""
