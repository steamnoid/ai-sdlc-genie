"""Typed, resilient access to public GitHub repositories.

The REST API is the primary source of truth. Unauthenticated callers are limited
to a small number of requests per hour, so inventory falls back to the public
archive endpoint, which is not part of that quota. Every call declares a timeout
and a bounded retry budget.
"""

from __future__ import annotations

import io
import logging
import os
import tarfile
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Self

import httpx

from aisdlc.tools.resilience import RETRYABLE_STATUS_CODES, RetryPolicy, retry_async

logger = logging.getLogger(__name__)

GITHUB_API_URL: Final[str] = "https://api.github.com"
GITHUB_RAW_URL: Final[str] = "https://raw.githubusercontent.com"
GITHUB_ARCHIVE_URL: Final[str] = "https://codeload.github.com"

DEFAULT_REF: Final[str] = "HEAD"
DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
DEFAULT_MAX_FILE_BYTES: Final[int] = 512_000
USER_AGENT: Final[str] = "ai-sdlc-genie"


class RepositoryError(RuntimeError):
    """Base error for every repository access failure."""


class RepositoryNotFoundError(RepositoryError):
    """Raised when the repository or the requested file does not exist."""


class GitHubAPIError(RepositoryError):
    """Raised when GitHub answers with an unexpected status code."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class RepositoryListing:
    """Immutable inventory of a repository at a specific revision.

    Attributes:
        repository_id: Canonical ``owner/name`` identifier.
        ref: Git reference the inventory was taken from.
        files: Repository-relative paths of regular files, sorted.
        source: Endpoint that produced the inventory (``api`` or ``archive``).
    """

    repository_id: str
    ref: str
    files: tuple[str, ...]
    source: str


def parse_repository_id(repository_id: str) -> tuple[str, str]:
    """Validate an ``owner/name`` identifier at the system boundary.

    Args:
        repository_id: Candidate identifier.

    Returns:
        The validated ``(owner, name)`` pair.

    Raises:
        ValueError: If the identifier is not exactly ``owner/name``.
    """
    parts = repository_id.strip().strip("/").split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"repository_id must use the 'owner/name' format, got: {repository_id!r}")
    return parts[0], parts[1]


def _build_headers(token: str | None) -> dict[str, str]:
    """Build the request headers, including authorization when a token exists."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _is_transient(error: BaseException) -> bool:
    """Return ``True`` for failures that may succeed on a later attempt."""
    if isinstance(error, httpx.TimeoutException | httpx.TransportError):
        return True
    if isinstance(error, GitHubAPIError):
        return error.status_code in RETRYABLE_STATUS_CODES
    return False


def _archive_members(payload: bytes, *, repository_id: str) -> list[str]:
    """Extract repository-relative file paths from a gzipped tarball.

    Args:
        payload: Raw gzipped tarball bytes.
        repository_id: Repository the archive belongs to, used for errors.

    Returns:
        Repository-relative paths of regular files.

    Raises:
        RepositoryError: If the archive cannot be read.
    """
    try:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            names = [member.name for member in archive if member.isfile()]
    except tarfile.TarError as error:
        raise RepositoryError(f"Could not read the archive for {repository_id}") from error

    if not names:
        return []

    prefix = names[0].split("/", 1)[0]
    relative = [name[len(prefix) + 1 :] if name.startswith(f"{prefix}/") else name for name in names]
    return [name for name in relative if name]


class GitHubClient:
    """Async client for the read-only GitHub operations this project needs.

    Use as an async context manager so the connection pool is always released::

        async with GitHubClient() as client:
            listing = await client.list_files("owner/name")
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        policy: RetryPolicy | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Create a client.

        Args:
            token: Optional personal access token; raises the API rate limit.
            timeout_seconds: Per-request timeout.
            policy: Bounded retry budget shared by every request.
            client: Pre-built transport, mainly for deterministic tests.
        """
        self._headers = _build_headers(token)
        self._policy = policy if policy is not None else RetryPolicy()
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=self._headers,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release the connection pool when this client owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def _get(
        self,
        url: str,
        *,
        description: str,
        params: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        """Perform a GET request with a bounded retry budget.

        Args:
            url: Absolute request URL.
            description: Label used in log records.
            params: Optional query parameters.

        Returns:
            The last response, whatever its status code.
        """
        return await retry_async(
            lambda: self._client.get(url, params=dict(params) if params else None),
            policy=self._policy,
            is_retryable=_is_transient,
            description=description,
        )

    @staticmethod
    def _raise_for_status(response: httpx.Response, description: str) -> None:
        """Translate an error status into a typed domain exception."""
        if response.is_success:
            return
        if response.status_code in {401, 403, 404}:
            raise RepositoryNotFoundError(
                f"{description} failed with status {response.status_code}; "
                "check the repository name or set GITHUB_TOKEN"
            )
        raise GitHubAPIError(f"{description} failed with status {response.status_code}", response.status_code)

    async def list_files(self, repository_id: str, *, ref: str = DEFAULT_REF) -> RepositoryListing:
        """List the regular files of a repository.

        Uses the REST tree endpoint, which needs authentication or a generous
        rate-limit allowance. On quota exhaustion it falls back to the public
        archive endpoint so unauthenticated environments keep working.

        Args:
            repository_id: Repository in ``owner/name`` format.
            ref: Branch name, tag, or commit SHA.

        Returns:
            A sorted, immutable inventory of repository-relative paths.

        Raises:
            ValueError: If ``repository_id`` is malformed.
            RepositoryError: If neither source can serve the request.
        """
        owner, name = parse_repository_id(repository_id)
        url = f"{GITHUB_API_URL}/repos/{owner}/{name}/git/trees/{ref}"
        response = await self._get(
            url,
            description=f"list_files({repository_id})",
            params={"recursive": "1"},
        )

        if response.status_code in {401, 403, 429}:
            logger.info(
                "REST inventory unavailable for %s; falling back to the public archive endpoint",
                repository_id,
            )
            return await self._list_files_from_archive(repository_id, ref=ref)

        self._raise_for_status(response, f"list_files({repository_id})")

        payload = response.json()
        if payload.get("truncated"):
            logger.warning("GitHub returned a truncated tree for %s; inventory is incomplete", repository_id)
        files = tuple(sorted(item["path"] for item in payload.get("tree", []) if item.get("type") == "blob"))
        return RepositoryListing(repository_id=repository_id, ref=ref, files=files, source="api")

    async def _list_files_from_archive(self, repository_id: str, *, ref: str) -> RepositoryListing:
        """Build an inventory from the public archive endpoint."""
        response = await self._get(
            f"{GITHUB_ARCHIVE_URL}/{repository_id}/tar.gz/{ref}",
            description=f"archive({repository_id})",
        )
        self._raise_for_status(response, f"archive({repository_id})")
        files = tuple(sorted(_archive_members(response.content, repository_id=repository_id)))
        return RepositoryListing(repository_id=repository_id, ref=ref, files=files, source="archive")

    async def read_file(
        self,
        repository_id: str,
        path: str,
        *,
        ref: str = DEFAULT_REF,
        max_bytes: int = DEFAULT_MAX_FILE_BYTES,
    ) -> str:
        """Read a single file through the public raw endpoint.

        Args:
            repository_id: Repository in ``owner/name`` format.
            path: Repository-relative file path.
            ref: Branch name, tag, or commit SHA.
            max_bytes: Upper bound on the decoded response size.

        Returns:
            File content decoded as UTF-8, with undecodable bytes replaced.

        Raises:
            ValueError: If the arguments are malformed.
            RepositoryError: If the file is missing or GitHub misbehaves.
        """
        owner, name = parse_repository_id(repository_id)
        normalized_path = path.strip().lstrip("/")
        if not normalized_path:
            raise ValueError("path must not be empty")

        response = await self._get(
            f"{GITHUB_RAW_URL}/{owner}/{name}/{ref}/{normalized_path}",
            description=f"read_file({repository_id}/{normalized_path})",
        )
        self._raise_for_status(response, f"read_file({repository_id}/{normalized_path})")

        if len(response.content) > max_bytes:
            logger.warning("Truncating %s/%s to %d bytes", repository_id, normalized_path, max_bytes)
        return response.content[:max_bytes].decode("utf-8", errors="replace")


def _env_token() -> str | None:
    """Read the optional GitHub token from the environment."""
    return os.getenv("GITHUB_TOKEN")


async def list_files(repository_id: str, *, ref: str = DEFAULT_REF) -> RepositoryListing:
    """List repository files with a short-lived client.

    Args:
        repository_id: Repository in ``owner/name`` format.
        ref: Branch name, tag, or commit SHA.

    Returns:
        The repository inventory.
    """
    async with GitHubClient(token=_env_token()) as client:
        return await client.list_files(repository_id, ref=ref)


async def read_file(
    repository_id: str,
    path: str,
    *,
    ref: str = DEFAULT_REF,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> str:
    """Read one repository file with a short-lived client.

    Args:
        repository_id: Repository in ``owner/name`` format.
        path: Repository-relative file path.
        ref: Branch name, tag, or commit SHA.
        max_bytes: Upper bound on the decoded response size.

    Returns:
        File content as text.
    """
    async with GitHubClient(token=_env_token()) as client:
        return await client.read_file(repository_id, path, ref=ref, max_bytes=max_bytes)
