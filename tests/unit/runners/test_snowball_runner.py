"""Unit tests for SnowballRunner."""

from __future__ import annotations

import datetime
from collections.abc import Callable
from unittest.mock import patch

import pytest

from findpapers.connectors.citation_base import CitationConnectorBase
from findpapers.core.citation_graph import CitationGraph
from findpapers.core.paper import Paper
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.snowball_runner import SnowballRunner


@pytest.fixture(autouse=True)
def _no_enrichment():
    """Patch out enrichment so unit tests do not make real HTTP requests."""
    with patch(
        "findpapers.runners.discovery_runner.DiscoveryRunner._enrich_papers",
        return_value=None,
    ):
        yield


class FakeCitationConnector(CitationConnectorBase):
    """A fake connector that returns pre-configured references and citations."""

    def __init__(
        self,
        references: dict[str, list[Paper]] | None = None,
        cited_by: dict[str, list[Paper]] | None = None,
    ) -> None:
        """Create a FakeCitationConnector.

        Parameters
        ----------
        references : dict[str, list[Paper]] | None
            Mapping from DOI to list of referenced papers.
        cited_by : dict[str, list[Paper]] | None
            Mapping from DOI to list of citing papers.
        """
        super().__init__()
        self._references = references or {}
        self._cited_by = cited_by or {}

    @property
    def name(self) -> str:
        """Return connector name.

        Returns
        -------
        str
            Connector identifier.
        """
        return "fake"

    @property
    def min_request_interval(self) -> float:
        """Return minimum request interval.

        Returns
        -------
        float
            Zero for tests.
        """
        return 0.0

    def fetch_references(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Return pre-configured references for the given paper.

        Parameters
        ----------
        paper : Paper
            Paper to look up.
        progress_callback : Callable[[int], None] | None
            Ignored in fake connector.

        Returns
        -------
        list[Paper]
            List of referenced papers.
        """
        return list(self._references.get(paper.doi or "", []))

    def fetch_cited_by(
        self,
        paper: Paper,
        progress_callback: Callable[[int], None] | None = None,
    ) -> list[Paper]:
        """Return pre-configured citing papers.

        Parameters
        ----------
        paper : Paper
            Paper to look up.
        progress_callback : Callable[[int], None] | None
            Ignored in fake connector.

        Returns
        -------
        list[Paper]
            List of citing papers.
        """
        return list(self._cited_by.get(paper.doi or "", []))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSnowballRunnerInit:
    """Tests for SnowballRunner initialisation."""

    def test_single_paper_seed(self, make_paper) -> None:
        """Accepts a single Paper as seed_papers."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=seed, max_depth=1)

        assert len(runner._seed_papers) == 1

    def test_skips_papers_without_doi(self, make_paper) -> None:
        """Papers without DOI are silently skipped."""
        seed_with_doi = make_paper("With DOI", doi="10.1000/ok")
        seed_without_doi = make_paper("No DOI")
        runner = SnowballRunner(seed_papers=[seed_with_doi, seed_without_doi])

        assert len(runner._seed_papers) == 1
        assert runner._skipped_seeds == 1

    def test_default_parameters(self, make_paper) -> None:
        """Default max_depth is 1, direction is 'both', num_workers is 1."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed])

        assert runner._max_depth == 1
        assert runner._direction == "both"
        assert runner._num_workers == 1

    def test_max_depth_zero_raises(self, make_paper) -> None:
        """max_depth of zero raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="max_depth must be >= 1"):
            SnowballRunner(seed_papers=[seed], max_depth=0)

    def test_max_depth_negative_raises(self, make_paper) -> None:
        """Negative max_depth raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="max_depth must be >= 1"):
            SnowballRunner(seed_papers=[seed], max_depth=-1)

    def test_top_n_per_level_zero_raises(self, make_paper) -> None:
        """top_n_per_level of zero raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="top_n_per_level must be >= 1"):
            SnowballRunner(seed_papers=[seed], top_n_per_level=0)

    def test_top_n_per_level_negative_raises(self, make_paper) -> None:
        """Negative top_n_per_level raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="top_n_per_level must be >= 1"):
            SnowballRunner(seed_papers=[seed], top_n_per_level=-5)

    def test_top_n_per_level_none_is_valid(self, make_paper) -> None:
        """top_n_per_level=None (default) does not raise."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed])
        assert runner._top_n_per_level is None

    def test_top_n_per_level_positive_is_stored(self, make_paper) -> None:
        """A positive top_n_per_level value is stored on the runner."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed], top_n_per_level=10)
        assert runner._top_n_per_level == 10

    def test_databases_none_uses_all_connectors(self, make_paper) -> None:
        """databases=None (default) builds all citation connectors."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed])
        assert len(runner._connectors) == 3

    def test_databases_single_value_filters_connectors(self, make_paper) -> None:
        """Passing a single database restricts the connectors to that one."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed], databases=["openalex"])
        assert len(runner._connectors) == 1
        assert runner._connectors[0].name == "openalex"

    def test_databases_multiple_values_filters_connectors(self, make_paper) -> None:
        """Passing multiple databases restricts connectors to those databases."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed], databases=["crossref", "semantic_scholar"])
        connector_names = {c.name for c in runner._connectors}
        assert connector_names == {"crossref", "semantic_scholar"}

    def test_databases_empty_list_raises(self, make_paper) -> None:
        """An empty databases list raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="databases must not be an empty list"):
            SnowballRunner(seed_papers=[seed], databases=[])

    def test_databases_unknown_value_raises(self, make_paper) -> None:
        """An unknown database identifier raises InvalidParameterError."""
        seed = make_paper("Seed", doi="10.1000/seed")
        with pytest.raises(InvalidParameterError, match="Unknown citation database"):
            SnowballRunner(seed_papers=[seed], databases=["no_such_db"])


class TestSnowballRunnerRun:
    """Tests for the snowball execution logic."""

    def test_depth_one_returns_immediate_neighbours(self, make_paper) -> None:
        """With max_depth=1 only immediate neighbours are fetched."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        connector = FakeCitationConnector(
            references={"10.1000/seed": [ref]},
        )
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 2
        assert graph.edge_count == 1

    def test_backward_snowball_depth_1(self, make_paper) -> None:
        """Backward snowballing collects references of the seed."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref1 = make_paper("Ref 1", doi="10.1000/r1")
        ref2 = make_paper("Ref 2", doi="10.1000/r2")

        connector = FakeCitationConnector(
            references={"10.1000/seed": [ref1, ref2]},
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="backward",
        )
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 3  # seed + 2 refs
        assert graph.edge_count == 2  # seed -> ref1, seed -> ref2
        refs = graph.get_references(seed)
        assert len(refs) == 2

    def test_forward_snowball_depth_1(self, make_paper) -> None:
        """Forward snowballing collects papers that cite the seed."""
        seed = make_paper("Seed", doi="10.1000/seed")
        citing1 = make_paper("Citing 1", doi="10.1000/c1")
        citing2 = make_paper("Citing 2", doi="10.1000/c2")

        connector = FakeCitationConnector(
            cited_by={"10.1000/seed": [citing1, citing2]},
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="forward",
        )
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 3  # seed + 2 citing
        assert graph.edge_count == 2
        cited_by = graph.get_cited_by(seed)
        assert len(cited_by) == 2

    def test_both_directions_depth_1(self, make_paper) -> None:
        """Snowballing in both directions collects refs and citing papers."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        citing = make_paper("Citing", doi="10.1000/citing")

        connector = FakeCitationConnector(
            references={"10.1000/seed": [ref]},
            cited_by={"10.1000/seed": [citing]},
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="both",
        )
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 3
        assert graph.edge_count == 2

    def test_depth_2_expands_second_level(self, make_paper) -> None:
        """At max_depth=2, papers found at level 1 are also expanded."""
        seed = make_paper("Seed", doi="10.1000/seed")
        level1 = make_paper("Level 1", doi="10.1000/l1")
        level2 = make_paper("Level 2", doi="10.1000/l2")

        connector = FakeCitationConnector(
            references={
                "10.1000/seed": [level1],
                "10.1000/l1": [level2],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
        )
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 3  # seed + l1 + l2
        assert graph.edge_count == 2  # seed->l1, l1->l2
        assert graph.get_node_depth(seed) == 0
        assert graph.get_node_depth(level1) == 1
        assert graph.get_node_depth(level2) == 2

    def test_deduplication_across_connectors(self, make_paper) -> None:
        """Same paper found by different connectors is not duplicated."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        ref_dup = make_paper("Ref (duplicate)", doi="10.1000/ref")

        connector1 = FakeCitationConnector(references={"10.1000/seed": [ref]})
        connector2 = FakeCitationConnector(references={"10.1000/seed": [ref_dup]})

        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="backward",
        )
        runner._connectors = [connector1, connector2]

        graph = runner.run()

        assert graph.node_count == 2  # seed + ref (deduplicated)
        assert graph.edge_count == 1  # one edge seed -> ref

    def test_cycle_detection(self, make_paper) -> None:
        """Papers already in the graph are not expanded again."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")

        # ref cites seed back — creates a cycle.
        connector = FakeCitationConnector(
            references={
                "10.1000/seed": [ref],
                "10.1000/ref": [seed],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
        )
        runner._connectors = [connector]

        graph = runner.run()

        # Only 2 papers; the seed is not re-added.
        assert graph.node_count == 2
        # seed -> ref AND ref -> seed (but ref -> seed is only added
        # at depth 2 when ref is expanded).
        assert graph.edge_count == 2

    def test_connector_error_does_not_crash(self, make_paper) -> None:
        """If a connector raises, the runner logs and continues."""
        seed = make_paper("Seed", doi="10.1000/seed")

        class ErrorConnector(CitationConnectorBase):
            """Connector that always raises."""

            @property
            def name(self) -> str:
                """Return name.

                Returns
                -------
                str
                    Connector name.
                """
                return "error"

            @property
            def min_request_interval(self) -> float:
                """Return interval.

                Returns
                -------
                float
                    Zero.
                """
                return 0.0

            def fetch_references(
                self,
                paper: Paper,
                progress_callback: Callable[[int], None] | None = None,
            ) -> list[Paper]:
                """Always raise.

                Parameters
                ----------
                paper : Paper
                    Ignored.
                progress_callback : Callable[[int], None] | None
                    Ignored.

                Raises
                ------
                RuntimeError
                    Always.
                """
                raise RuntimeError("boom")

            def fetch_cited_by(
                self,
                paper: Paper,
                progress_callback: Callable[[int], None] | None = None,
            ) -> list[Paper]:
                """Always raise.

                Parameters
                ----------
                paper : Paper
                    Ignored.
                progress_callback : Callable[[int], None] | None
                    Ignored.

                Raises
                ------
                RuntimeError
                    Always.
                """
                raise RuntimeError("boom")

        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="both",
        )
        runner._connectors = [ErrorConnector()]

        # Should not raise.
        graph = runner.run()

        assert graph.node_count == 1  # only the seed
        assert graph.edge_count == 0

    def test_multiple_seeds(self, make_paper) -> None:
        """Multiple seed papers are all expanded at depth 1."""
        seed1 = make_paper("Seed 1", doi="10.1000/s1")
        seed2 = make_paper("Seed 2", doi="10.1000/s2")
        ref1 = make_paper("Ref 1", doi="10.1000/r1")
        ref2 = make_paper("Ref 2", doi="10.1000/r2")

        connector = FakeCitationConnector(
            references={
                "10.1000/s1": [ref1],
                "10.1000/s2": [ref2],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed1, seed2],
            max_depth=1,
            direction="backward",
        )
        runner._connectors = [connector]

        graph = runner.run()

        assert graph.node_count == 4
        assert graph.edge_count == 2

    def test_parallel_connectors(self, make_paper) -> None:
        """With num_workers > 1, connectors are queried in parallel."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref1 = make_paper("Ref C1", doi="10.1000/rc1")
        ref2 = make_paper("Ref C2", doi="10.1000/rc2")

        connector1 = FakeCitationConnector(references={"10.1000/seed": [ref1]})
        connector2 = FakeCitationConnector(references={"10.1000/seed": [ref2]})

        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="backward",
            num_workers=3,
        )
        runner._connectors = [connector1, connector2]

        graph = runner.run()

        # Both connectors should have been queried.
        assert graph.node_count == 3  # seed + rc1 + rc2
        assert graph.edge_count == 2

    def test_top_n_per_level_limits_next_frontier(self, make_paper) -> None:
        """top_n_per_level keeps only the N most-cited papers in the graph per level."""
        seed = make_paper("Seed", doi="10.1000/seed")
        # Three papers at level 1 with distinct citation counts.
        high = make_paper("High", doi="10.1000/high", citations=100)
        mid = make_paper("Mid", doi="10.1000/mid", citations=50)
        low = make_paper("Low", doi="10.1000/low", citations=5)

        connector = FakeCitationConnector(
            references={"10.1000/seed": [high, mid, low]},
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
            top_n_per_level=2,
        )
        runner._connectors = [connector]

        graph = runner.run()

        # Only the top 2 (high, mid) are added to the graph; "low" is discarded.
        assert graph.contains(high)
        assert graph.contains(mid)
        assert not graph.contains(low)

    def test_top_n_per_level_selects_by_citation_count(self, make_paper) -> None:
        """Papers are ranked by citations descending; lower-cited ones are not added to the graph."""
        seed = make_paper("Seed", doi="10.1000/seed")
        high = make_paper("High", doi="10.1000/high", citations=200)
        low = make_paper("Low", doi="10.1000/low", citations=1)
        # Level 2 papers reachable only via "low" — should NOT appear.
        deep = make_paper("Deep", doi="10.1000/deep", citations=999)

        connector = FakeCitationConnector(
            references={
                "10.1000/seed": [high, low],
                "10.1000/low": [deep],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
            top_n_per_level=1,
        )
        runner._connectors = [connector]

        graph = runner.run()

        # Only "high" (top 1) is added; "low" is discarded and "deep" is never discovered.
        assert graph.contains(high)
        assert not graph.contains(low)
        assert not graph.contains(deep)

    def test_top_n_per_level_none_expands_all(self, make_paper) -> None:
        """Without top_n_per_level all discovered papers are expanded."""
        seed = make_paper("Seed", doi="10.1000/seed")
        p1 = make_paper("P1", doi="10.1000/p1", citations=10)
        p2 = make_paper("P2", doi="10.1000/p2", citations=1)
        deep = make_paper("Deep", doi="10.1000/deep")

        connector = FakeCitationConnector(
            references={
                "10.1000/seed": [p1, p2],
                "10.1000/p2": [deep],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
            # top_n_per_level not set (default None)
        )
        runner._connectors = [connector]

        graph = runner.run()

        # p2 is expanded so deep should be discovered.
        assert graph.contains(deep)

    def test_top_n_per_level_none_citations_treated_as_zero(self, make_paper) -> None:
        """Papers with citations=None are ranked below papers with known counts."""
        seed = make_paper("Seed", doi="10.1000/seed")
        cited = make_paper("Cited", doi="10.1000/cited", citations=10)
        unknown = make_paper("Unknown", doi="10.1000/unknown", citations=None)
        deep_via_unknown = make_paper("DeepUnknown", doi="10.1000/deepunknown")

        connector = FakeCitationConnector(
            references={
                "10.1000/seed": [cited, unknown],
                "10.1000/unknown": [deep_via_unknown],
            },
        )
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=2,
            direction="backward",
            top_n_per_level=1,
        )
        runner._connectors = [connector]

        graph = runner.run()

        # Only "cited" (top 1 by citation count) is added; "unknown" is discarded
        # and "deep_via_unknown" is never discovered.
        assert graph.contains(cited)
        assert not graph.contains(unknown)
        assert not graph.contains(deep_via_unknown)


class TestSnowballRunnerMetrics:
    """Tests for metrics after execution."""

    def test_metrics_after_run(self, make_paper) -> None:
        """Graph contains expected data after run()."""
        seed = make_paper("Seed", doi="10.1000/seed")
        runner = SnowballRunner(seed_papers=[seed], max_depth=1)
        runner._connectors = [FakeCitationConnector()]

        graph = runner.run()

        assert graph.node_count == 1
        assert graph.edge_count == 0

    def test_show_progress_false_disables_progress_bar(self, make_paper) -> None:
        """show_progress=False suppresses the tqdm progress bar."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.2000/ref")
        connector = FakeCitationConnector(references={"10.1000/seed": [ref]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1)
        runner._connectors = [connector]

        with patch("findpapers.runners.snowball_runner.make_progress_bar") as mock_pbar:
            mock_ctx = type(
                "MockCtx",
                (),
                {
                    "__enter__": lambda self: self,
                    "__exit__": lambda self, *args: False,
                    "update": lambda self, n=1: None,
                    "reset": lambda self, total=None: None,
                    "set_description": lambda self, desc="": None,
                    "refresh": lambda self: None,
                    "n": 0,
                    "total": None,
                },
            )()
            mock_pbar.return_value = mock_ctx
            runner.run(show_progress=False)
            assert mock_pbar.called
            for call in mock_pbar.call_args_list:
                assert call.kwargs.get("disable") is True


class TestCollectCandidates:
    """Tests for the _collect_candidates helper method."""

    def test_returns_reference_tuples_with_is_ref_true(self, make_paper) -> None:
        """Backward citations are returned with is_reference=True."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        connector = FakeCitationConnector(references={"10.1000/seed": [ref]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        candidates = runner._collect_candidates(seed)

        assert len(candidates) == 1
        candidate, source, is_ref = candidates[0]
        assert candidate.doi == "10.1000/ref"
        assert source is seed
        assert is_ref is True

    def test_returns_citing_tuples_with_is_ref_false(self, make_paper) -> None:
        """Forward citations are returned with is_reference=False."""
        seed = make_paper("Seed", doi="10.1000/seed")
        citing = make_paper("Citing", doi="10.1000/citing")
        connector = FakeCitationConnector(cited_by={"10.1000/seed": [citing]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="forward")
        runner._connectors = [connector]

        candidates = runner._collect_candidates(seed)

        assert len(candidates) == 1
        candidate, source, is_ref = candidates[0]
        assert candidate.doi == "10.1000/citing"
        assert source is seed
        assert is_ref is False

    def test_does_not_modify_graph(self, make_paper) -> None:
        """_collect_candidates must not add any paper to the graph."""
        from findpapers.core.citation_graph import CitationGraph

        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        connector = FakeCitationConnector(references={"10.1000/seed": [ref]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        graph = CitationGraph(seed_papers=[seed], max_depth=1, direction="backward")
        node_count_before = graph.node_count

        runner._collect_candidates(seed)

        assert graph.node_count == node_count_before


class TestSnowballRunnerVerbose:
    """Tests for verbose logging branches."""

    def test_verbose_logs_configuration_and_results(self, make_paper) -> None:
        """verbose=True logs configuration, per-level info, and results."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        connector = FakeCitationConnector(references={"10.1000/seed": [ref]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        graph = runner.run(verbose=True, show_progress=False)

        assert graph.node_count == 2

    def test_verbose_multi_level(self, make_paper) -> None:
        """verbose=True logs at each depth level."""
        seed = make_paper("Seed", doi="10.1000/seed")
        l1 = make_paper("L1", doi="10.1000/l1")
        l2 = make_paper("L2", doi="10.1000/l2")
        connector = FakeCitationConnector(
            references={"10.1000/seed": [l1], "10.1000/l1": [l2]},
        )
        runner = SnowballRunner(seed_papers=[seed], max_depth=2, direction="backward")
        runner._connectors = [connector]

        graph = runner.run(verbose=True, show_progress=False)

        assert graph.node_count == 3

    def test_verbose_true_restores_root_logger_level(self, make_paper) -> None:
        """run(verbose=True) restores the root logger level on exit."""
        import logging

        seed = make_paper("Seed", doi="10.1000/seed")
        connector = FakeCitationConnector(references={})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        root_logger = logging.getLogger()
        original_level = root_logger.level
        root_logger.setLevel(logging.WARNING)
        try:
            runner.run(verbose=True, show_progress=False)
            assert root_logger.level == logging.WARNING
        finally:
            root_logger.setLevel(original_level)


class TestSnowballRunnerParallelErrors:
    """Tests for error handling in parallel connector execution."""

    def test_parallel_connector_exception_is_caught(self, make_paper) -> None:
        """Exception in a parallel connector is caught; other results survive."""

        class BoomConnector(CitationConnectorBase):
            """Connector whose future raises."""

            @property
            def name(self) -> str:
                """Return name.

                Returns
                -------
                str
                    Connector name.
                """
                return "boom"

            @property
            def min_request_interval(self) -> float:
                """Return interval.

                Returns
                -------
                float
                    Zero.
                """
                return 0.0

            def fetch_references(
                self,
                paper: Paper,
                progress_callback: Callable[[int], None] | None = None,
            ) -> list[Paper]:
                """Always raise.

                Parameters
                ----------
                paper : Paper
                    Ignored.
                progress_callback : Callable[[int], None] | None
                    Ignored.

                Raises
                ------
                RuntimeError
                    Always.
                """
                raise RuntimeError("boom")

            def fetch_cited_by(
                self,
                paper: Paper,
                progress_callback: Callable[[int], None] | None = None,
            ) -> list[Paper]:
                """Always raise.

                Parameters
                ----------
                paper : Paper
                    Ignored.
                progress_callback : Callable[[int], None] | None
                    Ignored.

                Raises
                ------
                RuntimeError
                    Always.
                """
                raise RuntimeError("boom")

        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        good = FakeCitationConnector(references={"10.1000/seed": [ref]})
        bad = BoomConnector()

        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="backward",
            num_workers=4,
        )
        runner._connectors = [good, bad]

        graph = runner.run(show_progress=False)

        # The good connector's result should still be present.
        assert graph.node_count == 2  # seed + ref
        assert graph.edge_count == 1

    def test_parallel_future_exception_is_caught(self, make_paper) -> None:
        """When _query_single_connector itself raises, the future exception is caught."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        good = FakeCitationConnector(references={"10.1000/seed": [ref]})
        bad = FakeCitationConnector()

        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=1,
            direction="backward",
            num_workers=4,
        )
        runner._connectors = [good, bad]

        original = runner._query_single_connector

        def patched(
            connector: CitationConnectorBase,
            paper: Paper,
            *,
            show_progress: bool = True,
        ) -> tuple[str, list[Paper] | None, list[Paper] | None]:
            """Raise for the 'bad' connector, delegate otherwise."""
            if connector is bad:
                raise RuntimeError("unexpected crash")
            return original(connector, paper, show_progress=show_progress)

        with patch.object(runner, "_query_single_connector", side_effect=patched):
            graph = runner.run(show_progress=False)

        # The good connector result survives; the bad one is logged & skipped.
        assert graph.node_count == 2  # seed + ref
        assert graph.edge_count == 1


class TestSnowballRunnerEmptyFrontier:
    """Tests for early termination when frontier is empty."""

    def test_empty_frontier_breaks_early(self, make_paper) -> None:
        """When no new papers are discovered, deeper levels are skipped."""
        seed = make_paper("Seed", doi="10.1000/seed")
        # Connector returns no references at any level.
        connector = FakeCitationConnector(references={})
        runner = SnowballRunner(
            seed_papers=[seed],
            max_depth=3,
            direction="backward",
        )
        runner._connectors = [connector]

        graph = runner.run(show_progress=False)

        assert graph.node_count == 1  # only the seed
        assert graph.edge_count == 0


class TestSnowballRunnerFilters:
    """Tests for the since and until date filters in SnowballRunner."""

    def _run_with_refs(
        self,
        make_paper,
        seed_doi: str,
        refs: list[Paper],
        **runner_kwargs,
    ) -> CitationGraph:
        """Helper: run SnowballRunner with a single seed and given references."""
        seed = make_paper("Seed", doi=seed_doi)
        connector = FakeCitationConnector(references={seed_doi: refs})
        runner = SnowballRunner(
            seed_papers=[seed], max_depth=1, direction="backward", **runner_kwargs
        )
        runner._connectors = [connector]
        return runner.run(show_progress=False)

    # ------------------------------------------------------------------
    # since / until date filters
    # ------------------------------------------------------------------

    def test_since_filter_excludes_older_papers(self, make_paper) -> None:
        """Papers published before `since` are not added to the graph."""
        old = make_paper("Old", doi="10.1/old", publication_date=datetime.date(2020, 1, 1))
        new = make_paper("New", doi="10.1/new", publication_date=datetime.date(2023, 6, 1))
        graph = self._run_with_refs(
            make_paper,
            "10.1/seed",
            [old, new],
            since=datetime.date(2022, 1, 1),
        )
        titles = {n.title for n in graph.nodes}
        assert "New" in titles
        assert "Old" not in titles

    def test_until_filter_excludes_newer_papers(self, make_paper) -> None:
        """Papers published after `until` are not added to the graph."""
        old = make_paper("Old", doi="10.1/old", publication_date=datetime.date(2019, 3, 1))
        new = make_paper("New", doi="10.1/new", publication_date=datetime.date(2024, 1, 1))
        graph = self._run_with_refs(
            make_paper,
            "10.1/seed",
            [old, new],
            until=datetime.date(2020, 12, 31),
        )
        titles = {n.title for n in graph.nodes}
        assert "Old" in titles
        assert "New" not in titles

    def test_since_filter_excludes_papers_with_no_date(self, make_paper) -> None:
        """Papers without a publication date are excluded when since is set."""
        no_date = Paper(
            title="NoDate",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi="10.1/nd",
        )
        graph = self._run_with_refs(
            make_paper,
            "10.1/seed",
            [no_date],
            since=datetime.date(2020, 1, 1),
        )
        titles = {n.title for n in graph.nodes}
        assert "NoDate" not in titles

    def test_until_filter_excludes_papers_with_no_date(self, make_paper) -> None:
        """Papers without a publication date are excluded when until is set."""
        no_date = Paper(
            title="NoDate",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            doi="10.1/nd",
        )
        graph = self._run_with_refs(
            make_paper,
            "10.1/seed",
            [no_date],
            until=datetime.date(2025, 1, 1),
        )
        titles = {n.title for n in graph.nodes}
        assert "NoDate" not in titles

    def test_since_and_until_combined(self, make_paper) -> None:
        """Only papers within the [since, until] range are accepted."""
        in_range = make_paper("InRange", doi="10.1/ir", publication_date=datetime.date(2021, 6, 1))
        too_old = make_paper("TooOld", doi="10.1/to", publication_date=datetime.date(2019, 1, 1))
        too_new = make_paper("TooNew", doi="10.1/tn", publication_date=datetime.date(2024, 1, 1))
        graph = self._run_with_refs(
            make_paper,
            "10.1/seed",
            [in_range, too_old, too_new],
            since=datetime.date(2020, 1, 1),
            until=datetime.date(2023, 12, 31),
        )
        titles = {n.title for n in graph.nodes}
        assert "InRange" in titles
        assert "TooOld" not in titles
        assert "TooNew" not in titles

    def test_no_filters_adds_all_papers(self, make_paper) -> None:
        """Without any filters, papers with or without dates are all added."""
        dated = make_paper("Dated", doi="10.1/d", publication_date=datetime.date(2021, 1, 1))
        no_date = make_paper("NoDate", doi="10.1/nd", publication_date=None)
        graph = self._run_with_refs(make_paper, "10.1/seed", [dated, no_date])
        titles = {n.title for n in graph.nodes}
        assert "Dated" in titles
        assert "NoDate" in titles


# ---------------------------------------------------------------------------
# cited_by population
# ---------------------------------------------------------------------------


class TestSnowballCitedByPopulation:
    """Tests that cited_by is populated on papers during snowballing."""

    def test_backward_snowball_populates_cited_by_on_reference(self, make_paper) -> None:
        """Backward snowballing sets cited_by on reference papers with the seed DOI."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")

        connector = FakeCitationConnector(references={"10.1000/seed": [ref]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector]

        graph = runner.run()

        canonical_ref = next(n for n in graph.nodes if n.doi == "10.1000/ref")
        assert "10.1000/seed" in canonical_ref.cited_by

    def test_forward_snowball_populates_cited_by_on_source(self, make_paper) -> None:
        """Forward snowballing adds citing paper DOIs to the source's cited_by."""
        seed = make_paper("Seed", doi="10.1000/seed")
        citing = make_paper("Citing", doi="10.1000/citing")

        connector = FakeCitationConnector(cited_by={"10.1000/seed": [citing]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="forward")
        runner._connectors = [connector]

        graph = runner.run()

        canonical_seed = next(n for n in graph.nodes if n.doi == "10.1000/seed")
        assert "10.1000/citing" in canonical_seed.cited_by

    def test_both_directions_populate_cited_by_correctly(self, make_paper) -> None:
        """Snowballing in both directions populates cited_by in both cases."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        citing = make_paper("Citing", doi="10.1000/citing")

        connector = FakeCitationConnector(
            references={"10.1000/seed": [ref]},
            cited_by={"10.1000/seed": [citing]},
        )
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="both")
        runner._connectors = [connector]

        graph = runner.run()

        canonical_seed = next(n for n in graph.nodes if n.doi == "10.1000/seed")
        canonical_ref = next(n for n in graph.nodes if n.doi == "10.1000/ref")

        # Citing paper should appear in seed.cited_by
        assert "10.1000/citing" in canonical_seed.cited_by
        # Seed should appear in ref.cited_by
        assert "10.1000/seed" in canonical_ref.cited_by

    def test_cited_by_not_duplicated_across_connectors(self, make_paper) -> None:
        """When two connectors return the same reference, cited_by is not duplicated."""
        seed = make_paper("Seed", doi="10.1000/seed")
        ref = make_paper("Ref", doi="10.1000/ref")
        ref_dup = make_paper("Ref dup", doi="10.1000/ref")

        connector1 = FakeCitationConnector(references={"10.1000/seed": [ref]})
        connector2 = FakeCitationConnector(references={"10.1000/seed": [ref_dup]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="backward")
        runner._connectors = [connector1, connector2]

        graph = runner.run()

        canonical_ref = next(n for n in graph.nodes if n.doi == "10.1000/ref")
        # Seed DOI must appear exactly once in cited_by
        assert canonical_ref.cited_by.count("10.1000/seed") == 1

    def test_cited_by_skips_papers_without_doi(self, make_paper) -> None:
        """Forward snowball: citing paper without DOI is not added to cited_by."""
        seed = make_paper("Seed", doi="10.1000/seed")
        citing_no_doi = make_paper("NoDoi")  # no DOI

        connector = FakeCitationConnector(cited_by={"10.1000/seed": [citing_no_doi]})
        runner = SnowballRunner(seed_papers=[seed], max_depth=1, direction="forward")
        runner._connectors = [connector]

        graph = runner.run()

        canonical_seed = next(n for n in graph.nodes if n.doi == "10.1000/seed")
        assert canonical_seed.cited_by == []
