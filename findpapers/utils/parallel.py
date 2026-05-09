"""Utilities for parallel and sequential task execution with optional progress tracking."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from time import perf_counter
from typing import TypeVar

from tqdm.contrib.logging import logging_redirect_tqdm

from findpapers.utils.progress import make_progress_bar

T = TypeVar("T")
R = TypeVar("R")

ProgressUpdate = Callable[[T, R | None, Exception | None], int]


def _iter_sequential(
    items: Iterable[T],
    task: Callable[[T], R],
    timeout: float | None,
    start: float,
    stop_on_timeout: bool,
) -> Iterator[tuple[T, R | None, Exception | None]]:
    """Yield task results one at a time, optionally respecting a global timeout.

    Parameters
    ----------
    items : Iterable[T]
        Items to process.
    task : Callable[[T], R]
        Task to run for each item.
    timeout : float | None
        Global deadline (seconds since *start*). ``None`` disables the check.
    start : float
        Reference timestamp from :func:`time.perf_counter`.
    stop_on_timeout : bool
        When ``True``, stop yielding after the first timeout error.

    Yields
    ------
    tuple[T, R | None, Exception | None]
        ``(item, result, error)`` for each processed item.
    """
    for item in items:
        if timeout is not None and (perf_counter() - start) > timeout:
            yield item, None, TimeoutError("Global timeout exceeded.")
            if stop_on_timeout:
                return
            continue
        try:
            result: R | None = task(item)
            error: Exception | None = None
        except Exception as exc:
            result = None
            error = exc
        yield item, result, error


def _iter_parallel(
    items: Iterable[T],
    task: Callable[[T], R],
    timeout: float | None,
    start: float,
    num_workers: int,
    stop_on_timeout: bool,  # kept for API symmetry with _iter_sequential
) -> Iterator[tuple[T, R | None, Exception | None]]:
    """Yield task results from a thread pool, handling global timeouts.

    Parameters
    ----------
    items : Iterable[T]
        Items to process.
    task : Callable[[T], R]
        Task to run for each item.
    timeout : float | None
        Global deadline (seconds since *start*). ``None`` disables the check.
    start : float
        Reference timestamp from :func:`time.perf_counter`.
    num_workers : int
        Maximum thread-pool size.
    stop_on_timeout : bool
        Reserved for API symmetry — parallel execution always stops on timeout.

    Yields
    ------
    tuple[T, R | None, Exception | None]
        ``(item, result, error)`` for each completed or cancelled task.
    """
    # logging_redirect_tqdm ensures log records emitted by worker threads
    # are written via tqdm.write() instead of directly to stderr, preventing
    # them from corrupting active progress bars.
    with logging_redirect_tqdm(), ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = {executor.submit(task, item): item for item in items}
        remaining = None if timeout is None else max(timeout - (perf_counter() - start), 0)
        yielded_futures: set[Future[R]] = set()
        try:
            for future in as_completed(futures, timeout=remaining):
                item = futures[future]
                yielded_futures.add(future)
                try:
                    fut_result: R | None = future.result()
                    fut_error: Exception | None = None
                except Exception as exc:
                    fut_result = None
                    fut_error = exc
                yield item, fut_result, fut_error
        except FuturesTimeoutError:
            yield from _handle_parallel_timeout(futures, yielded_futures)
            executor.shutdown(wait=False, cancel_futures=True)


def _handle_parallel_timeout(
    futures: dict[Future[R], T],
    yielded_futures: set[Future[R]],
) -> Iterator[tuple[T, R | None, Exception | None]]:
    """Yield results for futures remaining after a global parallel timeout.

    Cancels pending (not-yet-started) futures and drains completed ones so
    callers receive an entry for every submitted task.

    Parameters
    ----------
    futures : dict
        Mapping of future → original item.
    yielded_futures : set
        Futures already yielded before the timeout.

    Yields
    ------
    tuple[T, None, Exception | None]
        ``(item, None, error)`` for each remaining future.
    """
    timeout_error: Exception = TimeoutError("Global timeout exceeded.")
    for future, item in futures.items():
        if future in yielded_futures:
            continue
        if not future.done():
            future.cancel()
            yield item, None, timeout_error
            continue
        try:
            result: R | None = future.result()
            error = None
        except Exception as exc:
            result = None
            error = exc
        yield item, result, error


def execute_tasks(
    items: Iterable[T],
    task: Callable[[T], R],
    *,
    num_workers: int | None,
    timeout: float | None,
    progress_total: int | None = None,
    progress_unit: str = "item",
    progress_desc: str | None = None,
    progress_update: ProgressUpdate | None = None,
    use_progress: bool = True,
    stop_on_timeout: bool = True,
) -> Iterator[tuple[T, R | None, Exception | None]]:
    """Execute tasks sequentially or in parallel with optional progress tracking.

    Parameters
    ----------
    items : Iterable[T]
        Items to process.
    task : Callable[[T], R]
        Task function to execute for each item.
    num_workers : int | None
        Number of workers. ``None`` or ``1`` runs sequentially.
    timeout : float | None
        Global timeout in seconds. ``None`` means no timeout.
    progress_total : int | None
        Total number of progress units for the progress bar.
    progress_unit : str
        Unit label displayed in the progress bar.
    progress_desc : str | None
        Short description label shown before the progress bar.  ``None``
        omits the label.
    progress_update : ProgressUpdate | None
        Optional callback returning the progress increment per completed item.
        When ``None``, each completed item counts as 1.
    use_progress : bool
        Whether to display a tqdm progress bar.
    stop_on_timeout : bool
        When ``True``, stop processing remaining items after a timeout.

    Yields
    ------
    Iterator[tuple[T, R | None, Exception | None]]
        ``(item, result, error)`` tuples for each completed task.
        *result* is ``None`` and *error* is set on failure.

    Raises
    ------
    None
        Errors are surfaced as the third element of the yielded tuple, never
        raised directly.
    """
    total = progress_total
    if total is None and hasattr(items, "__len__"):
        total = len(items)  # type: ignore[arg-type]

    progress_bar = (
        make_progress_bar(
            desc=progress_desc,
            total=total,
            unit=progress_unit,
            disable=not use_progress,
        )
        if total is not None
        else None
    )

    def _update_progress(item: T, result: R | None, error: Exception | None) -> None:
        if progress_bar is None:
            return
        increment = 1 if progress_update is None else progress_update(item, result, error)
        if increment:
            progress_bar.update(increment)

    start = perf_counter()
    try:
        if num_workers is None or num_workers <= 1:
            gen = _iter_sequential(items, task, timeout, start, stop_on_timeout)
        else:
            gen = _iter_parallel(items, task, timeout, start, num_workers, stop_on_timeout)

        for item, result, error in gen:
            _update_progress(item, result, error)
            yield item, result, error
    finally:
        if progress_bar is not None:
            progress_bar.close()
