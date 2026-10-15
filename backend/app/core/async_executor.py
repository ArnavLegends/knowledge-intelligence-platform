"""Bounded thread-pool executor for offloading blocking I/O from the async event loop.

Blocking network calls (Gemini embedding/generation, Qdrant search) MUST NOT run
directly inside FastAPI ``async def`` handlers — they freeze the event loop and
prevent concurrent request processing.

This module provides:

- A process-level ``ThreadPoolExecutor`` with a configurable worker ceiling.
- ``run_blocking(fn, *args, timeout=None)`` — an ``await``-able helper that submits
  a callable to the pool and optionally enforces a wall-clock deadline via
  ``asyncio.wait_for``.  TimeoutError from ``asyncio.wait_for`` is propagated to the
  caller as ``asyncio.TimeoutError`` so that endpoint handlers can translate it to
  an appropriate HTTP 504 response.

Usage (inside an ``async def`` FastAPI handler)::

    from app.core.async_executor import run_blocking

    result = await run_blocking(service.search, query, timeout=15.0)
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Process-level executor — created once, reused across all requests.  #
# ------------------------------------------------------------------ #
_executor: ThreadPoolExecutor | None = None


def _get_executor(max_workers: int = 4) -> ThreadPoolExecutor:
    """Return the process-level executor, creating it on first call."""
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="kip-blocking",
        )
        logger.info(
            "Initialized blocking I/O thread pool: max_workers=%d", max_workers
        )
    return _executor


def set_executor(executor: ThreadPoolExecutor | None) -> None:
    """Replace the process-level executor (for testing)."""
    global _executor  # noqa: PLW0603
    _executor = executor


def shutdown_executor(wait: bool = False) -> None:
    """Shut down the process-level thread pool on application shutdown."""
    global _executor  # noqa: PLW0603
    if _executor is not None:
        _executor.shutdown(wait=wait, cancel_futures=True)
        _executor = None
        logger.info("Blocking I/O thread pool shut down.")


async def run_blocking(
    fn: Any,
    *args: Any,
    timeout: float | None = None,
    max_workers: int = 4,
) -> Any:
    """Run a synchronous callable in the thread-pool and await its result.

    Parameters
    ----------
    fn:
        A synchronous callable (no ``await`` inside).
    *args:
        Positional arguments forwarded to ``fn``.
    timeout:
        Optional wall-clock deadline in seconds.  If ``fn`` does not complete
        within this window, ``asyncio.TimeoutError`` is raised.
    max_workers:
        Ignored after the first call (pool is created once).

    Returns
    -------
    The return value of ``fn(*args)``.

    Raises
    ------
    asyncio.TimeoutError
        If the operation exceeds ``timeout``.
    """
    loop = asyncio.get_running_loop()
    executor = _get_executor(max_workers=max_workers)

    future = loop.run_in_executor(executor, fn, *args)

    if timeout is not None:
        return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)

    return await future
