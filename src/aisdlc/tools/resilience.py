"""Bounded retry helpers for outbound I/O.

Every external call in this project must declare an explicit timeout and a
bounded retry strategy with exponential backoff. This module keeps that policy
in one place so individual tools stay small and deterministic.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Final

logger = logging.getLogger(__name__)

#: HTTP outcomes that justify another attempt. Anything else fails fast.
RETRYABLE_STATUS_CODES: Final[frozenset[int]] = frozenset({408, 425, 429, 500, 502, 503, 504})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Immutable description of how often, and how fast, an operation is retried.

    Attributes:
        attempts: Total number of attempts, including the first one.
        backoff_seconds: Delay before the second attempt.
        backoff_multiplier: Growth factor applied to each subsequent delay.
        max_backoff_seconds: Upper bound for a single delay.
    """

    attempts: int = 3
    backoff_seconds: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 8.0

    def __post_init__(self) -> None:
        if self.attempts < 1:
            raise ValueError("RetryPolicy.attempts must be at least 1")
        if self.backoff_seconds < 0:
            raise ValueError("RetryPolicy.backoff_seconds must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("RetryPolicy.backoff_multiplier must be at least 1")
        if self.max_backoff_seconds < self.backoff_seconds:
            raise ValueError("RetryPolicy.max_backoff_seconds must not be below backoff_seconds")

    def delay_before(self, attempt: int) -> float:
        """Return the delay preceding ``attempt`` (1-based, first attempt waits 0s)."""
        if attempt <= 1:
            return 0.0
        delay = self.backoff_seconds * (self.backoff_multiplier ** (attempt - 2))
        return min(delay, self.max_backoff_seconds)


class RetryExhaustedError(RuntimeError):
    """Raised when an operation keeps failing with a retryable outcome."""


async def retry_async[T](
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    is_retryable: Callable[[BaseException], bool] | None = None,
    description: str = "operation",
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> T:
    """Execute ``operation`` with bounded retries and exponential backoff.

    Args:
        operation: Zero-argument coroutine factory; called once per attempt.
        policy: Retry budget. Defaults to :class:`RetryPolicy`.
        is_retryable: Decides whether a given failure deserves another attempt.
            Defaults to retrying every exception.
        description: Human-readable label used in log records.
        sleep: Awaitable delay implementation, injectable for deterministic tests.

    Returns:
        The first successful result of ``operation``.

    Raises:
        The last error, once the budget is exhausted or the error is not retryable.
    """
    active_policy = policy if policy is not None else RetryPolicy()
    retryable = is_retryable if is_retryable is not None else lambda _: True

    last_error: BaseException | None = None
    for attempt in range(1, active_policy.attempts + 1):
        try:
            return await operation()
        except Exception as error:  # re-raised below with the policy applied
            last_error = error
            if attempt >= active_policy.attempts or not retryable(error):
                raise
            delay = active_policy.delay_before(attempt + 1)
            logger.warning(
                "Retrying %s after failure (attempt %d/%d, delay %.2fs): %s",
                description,
                attempt,
                active_policy.attempts,
                delay,
                error,
            )
            if delay:
                await sleep(delay)

    raise RetryExhaustedError(
        f"{description} failed after {active_policy.attempts} attempts"
    ) from last_error
