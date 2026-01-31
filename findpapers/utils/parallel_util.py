from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import (
    ThreadPoolExecutor,
)
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import (
    as_completed,
)
from time import perf_counter
from typing import TypeVar

from tqdm import tqdm

T = TypeVar("T")
R = TypeVar("R")

ProgressUpdate = Callable[[T, R | None, Exception | None], int]


def execute_tasks(
    items: Iterable[T],
    task: Callable[[T], R],
    *,
    max_workers: int | None,
    timeout: float | None,
    progress_total: int | None = None,
    progress_unit: str = "item",
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
    max_workers : int | None
        Maximum number of workers for parallel execution.
    timeout : float | None
        Global timeout in seconds.
    progress_total : int | None
        Total number of progress units.
    progress_unit : str
        Unit label for the progress bar.
    progress_update : ProgressUpdate | None
        Callback returning progress increments per completed item.
    use_progress : bool
        Whether to display a progress bar.
    stop_on_timeout : bool
        Whether to stop processing when the timeout is exceeded.

    Yields
    ------
    Iterator[tuple[T, R | None, Exception | None]]
        (item, result, error) tuples for completed tasks.
    """
    # Prefer an explicit total when provided to avoid exhausting iterables.
    total = progress_total
    if total is None and hasattr(items, "__len__"):
        total = len(items)  # type: ignore[arg-type]

    progress_bar = (
        tqdm(total=total, unit=progress_unit) if use_progress and total is not None else None
    )

    def update_progress(item: T, result: R | None, error: Exception | None) -> None:
        if progress_bar is None:
            return
        if progress_update is None:
            increment = 1
        else:
            increment = progress_update(item, result, error)
        if increment:
            progress_bar.update(increment)

    # Measure a global timeout across the entire run, not per-item.
    start = perf_counter()
    try:
        # Sequential path (also used when max_workers is None or 1).
        if max_workers is None or max_workers <= 1:
            for item in items:
                if timeout is not None and (perf_counter() - start) > timeout:
                    timeout_error = TimeoutError("Global timeout exceeded.")
                    update_progress(item, None, timeout_error)
                    yield item, None, timeout_error
                    if stop_on_timeout:
                        break
                    continue
                try:
                    result = task(item)
                except Exception as exc:  # noqa: BLE001
                    update_progress(item, None, exc)
                    yield item, None, exc
                    continue
                update_progress(item, result, None)
                yield item, result, None
        else:
            # Parallel path: submit all tasks and iterate results as they complete.
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(task, item): item for item in items}
                remaining = None if timeout is None else max(timeout - (perf_counter() - start), 0)
                yielded_futures: set[object] = set()
                try:
                    for future in as_completed(futures, timeout=remaining):
                        item = futures[future]
                        yielded_futures.add(future)
                        try:
                            result = future.result()
                            error = None
                        except Exception as exc:  # noqa: BLE001
                            result = None
                            error = exc
                        update_progress(item, result, error)
                        yield item, result, error
                except FuturesTimeoutError:
                    # Global timeout reached: yield remaining futures as timed out.
                    timeout_error = TimeoutError("Global timeout exceeded.")
                    for future, item in futures.items():
                        if future in yielded_futures:
                            continue
                        if not future.done():
                            update_progress(item, None, timeout_error)
                            yield item, None, timeout_error
                            continue
                        try:
                            result = future.result()
                            error = None
                        except Exception as exc:  # noqa: BLE001
                            result = None
                            error = exc
                        update_progress(item, result, error)
                        yield item, result, error
    finally:
        if progress_bar is not None:
            progress_bar.close()
