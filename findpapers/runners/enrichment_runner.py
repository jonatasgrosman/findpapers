from __future__ import annotations

import logging
from time import perf_counter

from findpapers.exceptions import SearchRunnerNotExecutedError
from findpapers.models import Paper
from findpapers.utils import enrichment_util
from findpapers.utils.parallel_util import execute_tasks

logger = logging.getLogger(__name__)


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

    def run(self, verbose: bool = False) -> None:
        """Enrich the configured papers.

        Parameters
        ----------
        verbose : bool
            Enable verbose logging and detailed output.

        Returns
        -------
        None
        """
        if verbose:
            logging.getLogger().setLevel(logging.INFO)
            logger.info("=== EnrichmentRunner Configuration ===")
            logger.info("Total papers to enrich: %d", len(self._results))
            logger.info("Max workers: %s", self._max_workers or "sequential")
            logger.info("Timeout: %s", self._timeout or "default")
            logger.info("======================================")

        start = perf_counter()
        metrics: dict[str, int | float] = {
            "total_papers": len(self._results),
            "runtime_in_seconds": 0.0,
            "enriched_papers": 0,
        }
        self._enrich_results(metrics, verbose)
        metrics["runtime_in_seconds"] = perf_counter() - start
        self._metrics = metrics
        self._executed = True

        if verbose:
            logger.info("=== Enrichment Summary ===")
            logger.info("Total papers: %d", metrics["total_papers"])
            logger.info("Enriched papers: %d", int(metrics["enriched_papers"]))
            logger.info("Runtime: %.2f seconds", metrics["runtime_in_seconds"])
            logger.info("============================")

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

    def _enrich_results(self, metrics: dict[str, int | float], verbose: bool = False) -> None:
        """Enrich results as the only stage.

        Parameters
        ----------
        metrics : dict[str, int | float]
            Metrics dict to update.
        verbose : bool
            Enable verbose logging.

        Returns
        -------
        None
        """
        max_workers = self._max_workers if isinstance(self._max_workers, int) else None
        timeout = self._timeout
        enriched = 0

        if not self._results:
            return

        # Enrichment task wrapper so the parallel helper can execute per paper.
        def enrich_task(paper: Paper) -> bool:
            return self._enrich_paper(paper, timeout=timeout)

        # Parallel/sequential execution with a single progress bar over papers.
        for _paper, result, error in execute_tasks(
            self._results,
            enrich_task,
            max_workers=max_workers,
            timeout=timeout,
            progress_total=len(self._results),
            progress_unit="paper",
            use_progress=True,
            stop_on_timeout=True,
        ):
            if error is not None:
                if verbose:
                    logger.warning("Error enriching paper: %s", error)
                continue
            if result:
                enriched += 1

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
