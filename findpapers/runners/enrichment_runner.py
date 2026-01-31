from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from time import perf_counter

from findpapers.exceptions import SearchRunnerNotExecutedError
from findpapers.models import Paper
from findpapers.utils import enrichment_util


class EnrichmentRunner:
    """Runner that enriches a provided list of papers."""

    def __init__(
        self,
        papers: list[Paper],
        max_workers: int | None = None,
        timeout: float | None = 10.0,
    ) -> None:
        """Initialize an enrichment run configuration without executing it.

        Parameters
        ----------
        papers : list[Paper]
            Papers to enrich.
        max_workers : int | None
            Maximum workers for parallelism.
        timeout : float | None
            Global timeout in seconds.
        """
        self._executed = False
        self._results = list(papers)
        self._metrics: dict[str, int | float] = {}
        self._max_workers = max_workers
        self._timeout = timeout

    def run(self, verbose: bool = False) -> None:  # noqa: ARG002
        """Enrich the configured papers.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging (placeholder).

        Returns
        -------
        None
        """
        start = perf_counter()
        metrics: dict[str, int | float] = {
            "total_papers": len(self._results),
            "runtime_in_seconds": 0.0,
            "enriched_papers": 0,
        }
        self._enrich_results(metrics)
        metrics["runtime_in_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True

    def get_metrics(self) -> dict[str, int | float]:
        """Return a copy of numeric metrics after `run()`.

        Returns
        -------
        dict[str, int | float]
            Numeric metrics snapshot.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        self._ensure_executed()
        return dict(self._metrics)

    def _ensure_executed(self) -> None:
        """Guard against accessing results before `run()`.

        Raises
        ------
        SearchRunnerNotExecutedError
            If `run()` has not been called.
        """
        if not self._executed:
            raise SearchRunnerNotExecutedError("EnrichmentRunner has not been executed yet.")

    def _enrich_results(self, metrics: dict[str, int | float]) -> None:
        """Enrich results as the only stage.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.

        Returns
        -------
        None
        """
        enrich_start = perf_counter()
        max_workers = self._max_workers if isinstance(self._max_workers, int) else None
        timeout = self._timeout
        enriched = 0
        errors = 0

        if not self._results:
            return

        if max_workers is None or max_workers <= 1:
            for paper in self._results:
                if timeout is not None and (perf_counter() - enrich_start) > timeout:
                    errors += 1
                    break
                try:
                    if self._enrich_paper(paper, timeout=timeout):
                        enriched += 1
                except Exception:
                    errors += 1
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._enrich_paper, paper, timeout=timeout): paper
                    for paper in self._results
                }
                remaining = (
                    None if timeout is None else max(timeout - (perf_counter() - enrich_start), 0)
                )
                try:
                    for future in as_completed(futures, timeout=remaining):
                        try:
                            if future.result():
                                enriched += 1
                        except Exception:
                            errors += 1
                except Exception:
                    errors += len([future for future in futures if not future.done()])

        metrics["enriched_papers"] = enriched

    def _enrich_paper(self, paper: Paper, timeout: float | None = None) -> bool:
        """Enrich a single paper.

        Parameters
        ----------
        paper : Paper
            Paper to enrich.
        timeout : float | None
            Request timeout.

        Returns
        -------
        bool
            True if the paper was enriched, False otherwise.
        """
        urls = [str(url) for url in paper.urls if url]
        if not urls:
            return False
        enriched = enrichment_util.enrich_from_sources(urls=urls, timeout=timeout)
        if enriched is None:
            return False
        paper.merge(enriched)
        return True
