"""Unit tests for SnowballRunner."""

from __future__ import annotations

import datetime
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from findpapers.core.paper import Paper
from findpapers.core.snowball_result import SnowballResult
from findpapers.exceptions import InvalidParameterError
from findpapers.runners.snowball_runner import (
    SNOWBALL_DATABASES,
    SNOWBALL_ENRICHMENT_DATABASES,
    SnowballRunner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_get_runner_class(
    paper_map: dict[str, Paper | None],
    call_log: list[dict] | None = None,
):
    """Return a drop-in replacement for GetRunner backed by *paper_map*.

    When instantiated with ``identifier=doi``, the returned object's
    ``.run()`` method looks up the normalised DOI in *paper_map* and
    returns the corresponding :class:`~findpapers.core.paper.Paper` or
    ``None``.

    Parameters
    ----------
    paper_map : dict[str, Paper | None]
        Mapping from *normalised* DOI (lowercase, stripped) to the paper
        that should be returned when that DOI is fetched.
    call_log : list[dict] | None
        When provided, each GetRunner instantiation appends a dict with
        ``{"identifier": str, "databases": ...}`` for later inspection.

    Returns
    -------
    type
        A class with the same public interface as
        :class:`~findpapers.runners.get_runner.GetRunner`.
    """

    class _MockGetRunner:
        def __init__(self, identifier: str, **kwargs: object) -> None:
            """Store the requested identifier.

            Parameters
            ----------
            identifier : str
                DOI to be resolved.
            **kwargs : object
                Ignored credential / config kwargs (except ``databases``,
                which is recorded in *call_log* when provided).
            """
            self._identifier = identifier.strip().lower()
            if call_log is not None:
                call_log.append(
                    {"identifier": self._identifier, "databases": kwargs.get("databases")}
                )

        def run(self, verbose: bool = False, max_cited_by: int | None = None) -> Paper | None:
            """Return the paper registered for the stored DOI.

            Parameters
            ----------
            verbose : bool
                Ignored.

            Returns
            -------
            Paper | None
                Pre-configured result from *paper_map*.
            """
            return paper_map.get(self._identifier)

    return _MockGetRunner


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seed(make_paper) -> Paper:
    """A single seed paper with a DOI."""
    return cast(Paper, make_paper("Seed", doi="10.1000/seed"))


# ---------------------------------------------------------------------------
# TestSnowballRunnerInit
# ---------------------------------------------------------------------------


class TestSnowballRunnerInit:
    """Tests for SnowballRunner.__init__ validation."""

    def test_single_paper_seed_is_accepted(self, seed: Paper) -> None:
        """A single Paper (not wrapped in a list) is accepted as seed_papers."""
        runner = SnowballRunner(seed_papers=seed)
        assert len(runner._seed_papers) == 1

    def test_papers_without_doi_are_skipped(self, make_paper) -> None:
        """Papers without a DOI are silently skipped; counter is incremented."""
        with_doi = make_paper("With DOI", doi="10.1000/ok")
        without_doi = make_paper("No DOI")
        runner = SnowballRunner(seed_papers=[with_doi, without_doi])

        assert len(runner._seed_papers) == 1
        assert runner._skipped_seeds == 1

    def test_default_parameters(self, seed: Paper) -> None:
        """Defaults: max_depth=1, direction='both', num_workers=1."""
        runner = SnowballRunner(seed_papers=seed)

        assert runner._max_depth == 1
        assert runner._direction == "both"
        assert runner._num_workers == 1
        assert runner._max_papers_per_level is None
        assert runner._max_expansion_per_level is None
        # With direction='both' (default), databases defaults to all SNOWBALL_DATABASES.
        assert runner._databases == list(SNOWBALL_DATABASES)
        # Enrichment defaults to crossref + web_scraping.
        assert runner._enrichment_databases == list(SNOWBALL_ENRICHMENT_DATABASES)

    def test_max_depth_zero_raises(self, seed: Paper) -> None:
        """max_depth=0 raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_depth must be >= 1"):
            SnowballRunner(seed_papers=seed, max_depth=0)

    def test_max_depth_negative_raises(self, seed: Paper) -> None:
        """Negative max_depth raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_depth must be >= 1"):
            SnowballRunner(seed_papers=seed, max_depth=-3)

    def test_top_n_zero_raises(self, seed: Paper) -> None:
        """max_papers_per_level=0 raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_papers_per_level must be >= 1"):
            SnowballRunner(seed_papers=seed, max_papers_per_level=0)

    def test_top_n_negative_raises(self, seed: Paper) -> None:
        """Negative max_papers_per_level raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_papers_per_level must be >= 1"):
            SnowballRunner(seed_papers=seed, max_papers_per_level=-5)

    def test_top_n_positive_stored(self, seed: Paper) -> None:
        """A positive max_papers_per_level value is stored on the runner."""
        runner = SnowballRunner(seed_papers=seed, max_papers_per_level=10)
        assert runner._max_papers_per_level == 10

    def test_max_expansion_zero_raises(self, seed: Paper) -> None:
        """max_expansion_per_level=0 raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_expansion_per_level must be >= 1"):
            SnowballRunner(seed_papers=seed, max_expansion_per_level=0)

    def test_max_expansion_negative_raises(self, seed: Paper) -> None:
        """Negative max_expansion_per_level raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_expansion_per_level must be >= 1"):
            SnowballRunner(seed_papers=seed, max_expansion_per_level=-3)

    def test_max_expansion_positive_stored(self, seed: Paper) -> None:
        """A positive max_expansion_per_level value is stored on the runner."""
        runner = SnowballRunner(seed_papers=seed, max_expansion_per_level=5)
        assert runner._max_expansion_per_level == 5

    def test_max_cited_by_zero_raises(self, seed: Paper) -> None:
        """max_cited_by=0 raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_cited_by must be >= 1"):
            SnowballRunner(seed_papers=seed, max_cited_by=0)

    def test_max_cited_by_negative_raises(self, seed: Paper) -> None:
        """Negative max_cited_by raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="max_cited_by must be >= 1"):
            SnowballRunner(seed_papers=seed, max_cited_by=-1)

    def test_max_cited_by_positive_stored(self, seed: Paper) -> None:
        """A positive max_cited_by value is stored on the runner."""
        runner = SnowballRunner(seed_papers=seed, max_cited_by=500)
        assert runner._max_cited_by == 500

    def test_max_cited_by_none_stored(self, seed: Paper) -> None:
        """max_cited_by=None disables the limit when passed explicitly."""
        runner = SnowballRunner(seed_papers=seed, max_cited_by=None)
        assert runner._max_cited_by is None

    def test_max_cited_by_default_is_100(self, seed: Paper) -> None:
        """max_cited_by defaults to 100 when not supplied."""
        runner = SnowballRunner(seed_papers=seed)
        assert runner._max_cited_by == 100

    def test_databases_empty_list_raises(self, seed: Paper) -> None:
        """An empty databases list raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="databases must not be an empty list"):
            SnowballRunner(seed_papers=seed, databases=[])

    def test_databases_unknown_value_raises(self, seed: Paper) -> None:
        """An unknown database name raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="Unknown or unsupported database"):
            SnowballRunner(seed_papers=seed, databases=["no_such_db"])

    def test_databases_known_values_accepted(self, seed: Paper) -> None:
        """All values from SNOWBALL_DATABASES are accepted without raising."""
        for db in SNOWBALL_DATABASES:
            runner = SnowballRunner(seed_papers=seed, databases=[db], direction="backward")
            assert runner._databases == [db]

    def test_databases_multiple_known_values_stored(self, seed: Paper) -> None:
        """Multiple valid database names are stored normalised."""
        runner = SnowballRunner(seed_papers=seed, databases=["crossref", "openalex"])
        assert runner._databases is not None
        assert set(runner._databases) == {"crossref", "openalex"}

    def test_databases_none_expanded_to_all_snowball_databases(self, seed: Paper) -> None:
        """databases=None expands to all SNOWBALL_DATABASES."""
        runner = SnowballRunner(seed_papers=seed, databases=None)
        assert runner._databases == list(SNOWBALL_DATABASES)

    def test_databases_normalised_to_lowercase(self, seed: Paper) -> None:
        """Database names are normalised to lowercase."""
        runner = SnowballRunner(seed_papers=seed, databases=["CrossRef"], direction="backward")
        assert runner._databases == ["crossref"]

    def test_num_workers_clamped_to_one(self, seed: Paper) -> None:
        """num_workers=0 is clamped to 1."""
        runner = SnowballRunner(seed_papers=seed, num_workers=0)
        assert runner._num_workers == 1

    def test_forward_direction_incompatible_databases_raises(self, seed: Paper) -> None:
        """forward direction with crossref-only raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="forward"):
            SnowballRunner(seed_papers=seed, direction="forward", databases=["crossref"])

    def test_both_direction_incompatible_databases_raises(self, seed: Paper) -> None:
        """both direction with crossref-only raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="both"):
            SnowballRunner(seed_papers=seed, direction="both", databases=["crossref"])

    def test_backward_direction_crossref_only_valid(self, seed: Paper) -> None:
        """backward direction with crossref-only is valid."""
        runner = SnowballRunner(seed_papers=seed, direction="backward", databases=["crossref"])
        assert runner._databases == ["crossref"]

    def test_forward_direction_openalex_valid(self, seed: Paper) -> None:
        """forward direction with openalex is valid."""
        runner = SnowballRunner(seed_papers=seed, direction="forward", databases=["openalex"])
        assert runner._databases == ["openalex"]


# ---------------------------------------------------------------------------
# TestSnowballRunnerRun
# ---------------------------------------------------------------------------


class TestSnowballRunnerRun:
    """Tests for SnowballRunner.run() behaviour."""

    def test_returns_snowball_result(self, make_paper) -> None:
        """run() always returns a SnowballResult instance."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(show_progress=False)

        assert isinstance(result, SnowballResult)

    def test_result_contains_seed_paper(self, make_paper) -> None:
        """Seed paper is always present in result.seed_papers."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(show_progress=False)

        seed_dois = {p.doi for p in result.seed_papers if p.doi}
        assert "10.1000/seed" in seed_dois

    def test_backward_direction_follows_references(self, make_paper) -> None:
        """Backward snowballing follows paper.references to discover new DOIs."""
        # Enriched seed has a reference pointing to ref_paper.
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/ref"]

        ref_paper = make_paper("Ref", doi="10.1000/ref")

        paper_map = {"10.1000/seed": enriched_seed, "10.1000/ref": ref_paper}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/ref" in dois

    def test_forward_direction_follows_cited_by(self, make_paper) -> None:
        """Forward snowballing follows paper.cited_by to discover new DOIs."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.cited_by = ["10.1000/citing"]

        citing_paper = make_paper("Citing", doi="10.1000/citing")

        paper_map = {"10.1000/seed": enriched_seed, "10.1000/citing": citing_paper}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="forward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/citing" in dois

    def test_both_directions_follows_references_and_cited_by(self, make_paper) -> None:
        """Both directions: references AND cited_by are followed."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/ref"]
        enriched_seed.cited_by = ["10.1000/citing"]

        ref_paper = make_paper("Ref", doi="10.1000/ref")
        citing_paper = make_paper("Citing", doi="10.1000/citing")

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/ref": ref_paper,
            "10.1000/citing": citing_paper,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="both",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/ref" in dois
        assert "10.1000/citing" in dois

    def test_backward_only_does_not_follow_cited_by(self, make_paper) -> None:
        """Backward direction does NOT follow paper.cited_by."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/ref"]
        enriched_seed.cited_by = ["10.1000/citing"]

        ref_paper = make_paper("Ref", doi="10.1000/ref")
        citing_paper = make_paper("Citing", doi="10.1000/citing")

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/ref": ref_paper,
            "10.1000/citing": citing_paper,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/ref" in dois
        assert "10.1000/citing" not in dois

    def test_forward_only_does_not_follow_references(self, make_paper) -> None:
        """Forward direction does NOT follow paper.references."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/ref"]
        enriched_seed.cited_by = ["10.1000/citing"]

        ref_paper = make_paper("Ref", doi="10.1000/ref")
        citing_paper = make_paper("Citing", doi="10.1000/citing")

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/ref": ref_paper,
            "10.1000/citing": citing_paper,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="forward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/citing" in dois
        assert "10.1000/ref" not in dois

    def test_depth_2_expands_second_level(self, make_paper) -> None:
        """At max_depth=2, papers discovered at level 1 are also expanded."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/l1"]

        level1 = make_paper("Level1", doi="10.1000/l1")
        level1.references = ["10.1000/l2"]

        level2 = make_paper("Level2", doi="10.1000/l2")

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/l1": level1,
            "10.1000/l2": level2,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/l1" in dois
        assert "10.1000/l2" in dois

    def test_doi_deduplication(self, make_paper) -> None:
        """The same DOI discovered via multiple paths appears only once."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        # Both references AND cited_by contain the same DOI.
        enriched_seed.references = ["10.1000/shared"]
        enriched_seed.cited_by = ["10.1000/shared"]

        shared_paper = make_paper("Shared", doi="10.1000/shared")

        paper_map = {"10.1000/seed": enriched_seed, "10.1000/shared": shared_paper}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="both",
            )
            result = runner.run(show_progress=False)

        dois = [p.doi for p in result.papers if p.doi]
        assert dois.count("10.1000/shared") == 1

    def test_already_visited_doi_is_not_fetched_twice(self, make_paper) -> None:
        """DOIs already in the visited set are not re-fetched at deeper levels via BFS discovery."""
        # Seed references l1; l1 references seed (cycle).
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/l1"]

        l1_paper = make_paper("L1", doi="10.1000/l1")
        l1_paper.references = ["10.1000/seed"]  # cycle back to seed

        call_counts: dict[str, int] = {}

        class _CountingGetRunner:
            def __init__(self, identifier: str, **kwargs: object) -> None:
                self._doi = identifier.strip().lower()

            def run(self, verbose: bool = False, max_cited_by: int | None = None) -> Paper | None:
                call_counts[self._doi] = call_counts.get(self._doi, 0) + 1
                return {"10.1000/seed": enriched_seed, "10.1000/l1": l1_paper}.get(self._doi)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=_CountingGetRunner):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        # seed should be fetched exactly once at level 0 (BFS never revisits it).
        assert call_counts.get("10.1000/seed", 0) == 1
        seed_dois = {p.doi for p in result.seed_papers if p.doi}
        assert "10.1000/seed" in seed_dois
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/l1" in dois

    def test_no_references_yields_only_seed(self, make_paper) -> None:
        """When a seed has no references/cited_by, result.papers is empty and seed is in seed_papers."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        # No references or cited_by populated.

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=3,
            )
            result = runner.run(show_progress=False)

        assert result.papers == []
        assert len(result.seed_papers) == 1

    def test_get_runner_returning_none_is_skipped(self, make_paper) -> None:
        """When GetRunner.run() returns None, that DOI is silently skipped."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/missing"]

        paper_map = {"10.1000/seed": enriched_seed, "10.1000/missing": None}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/missing" not in dois

    def test_multiple_seeds_all_expanded(self, make_paper) -> None:
        """All provided seed papers are fetched and expanded."""
        seed1 = make_paper("Seed 1", doi="10.1000/s1")
        seed2 = make_paper("Seed 2", doi="10.1000/s2")

        enriched_s1 = make_paper("Seed 1", doi="10.1000/s1")
        enriched_s1.references = ["10.1000/r1"]
        enriched_s2 = make_paper("Seed 2", doi="10.1000/s2")
        enriched_s2.references = ["10.1000/r2"]

        r1 = make_paper("Ref 1", doi="10.1000/r1")
        r2 = make_paper("Ref 2", doi="10.1000/r2")

        paper_map = {
            "10.1000/s1": enriched_s1,
            "10.1000/s2": enriched_s2,
            "10.1000/r1": r1,
            "10.1000/r2": r2,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=[seed1, seed2],
                max_depth=1,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        paper_dois = {p.doi for p in result.papers if p.doi}
        seed_dois = {p.doi for p in result.seed_papers if p.doi}
        assert {"10.1000/r1", "10.1000/r2"}.issubset(paper_dois)
        assert {"10.1000/s1", "10.1000/s2"}.issubset(seed_dois)

    def test_seeds_without_doi_are_skipped_and_counted(self, make_paper) -> None:
        """Seed papers without DOI are excluded and the skip count is correct."""
        seed_no_doi = make_paper("No DOI")
        runner = SnowballRunner(seed_papers=[seed_no_doi], max_depth=1)

        with patch("findpapers.runners.snowball_runner.GetRunner") as mock_cls:
            mock_cls.return_value = MagicMock()
            result = runner.run(show_progress=False)

        assert result.skipped_seeds_without_doi == 1
        # GetRunner should not have been called for the seedless paper.
        mock_cls.assert_not_called()


# ---------------------------------------------------------------------------
# TestSnowballRunnerMaxPerLevel
# ---------------------------------------------------------------------------


class TestSnowballRunnerMaxPerLevel:
    """Tests for the max_papers_per_level parameter (per-level result cap)."""

    def test_max_papers_per_level_filters_result_not_frontier(self, make_paper) -> None:
        """max_papers_per_level limits result papers per level; all papers still expand."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/high", "10.1000/mid", "10.1000/low"]

        high = make_paper("High", doi="10.1000/high", citations=100)
        mid = make_paper("Mid", doi="10.1000/mid", citations=50)
        low = make_paper("Low", doi="10.1000/low", citations=5)

        # level2 is reachable only via low
        level2_via_low = make_paper("L2-via-low", doi="10.1000/l2low")
        low.references = ["10.1000/l2low"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/high": high,
            "10.1000/mid": mid,
            "10.1000/low": low,
            "10.1000/l2low": level2_via_low,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_papers_per_level=2,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        # high and mid are top-2 by citations: they are in the result.
        assert "10.1000/high" in dois
        assert "10.1000/mid" in dois
        # low is filtered out of the result (rank 3, cap is 2).
        assert "10.1000/low" not in dois
        # low is still in the frontier, so l2low IS fetched and in the result.
        assert "10.1000/l2low" in dois

    def test_max_papers_per_level_1_keeps_only_highest_cited(self, make_paper) -> None:
        """max_papers_per_level=1 keeps only the single most-cited paper in the result."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/winner", "10.1000/loser"]

        winner = make_paper("Winner", doi="10.1000/winner", citations=999)
        loser = make_paper("Loser", doi="10.1000/loser", citations=1)

        level2_via_loser = make_paper("L2-Loser", doi="10.1000/l2loser")
        loser.references = ["10.1000/l2loser"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/winner": winner,
            "10.1000/loser": loser,
            "10.1000/l2loser": level2_via_loser,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_papers_per_level=1,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/winner" in dois
        # loser filtered from result (rank 2, cap is 1).
        assert "10.1000/loser" not in dois
        # loser is still in frontier; l2loser IS fetched and in result.
        assert "10.1000/l2loser" in dois

    def test_none_citations_ranked_below_known(self, make_paper) -> None:
        """Papers with citations=None rank below papers with known citation counts."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/known", "10.1000/unknown"]

        known_cited = make_paper("Known", doi="10.1000/known", citations=10)
        unknown_cited = make_paper("Unknown", doi="10.1000/unknown", citations=None)

        deep_via_unknown = make_paper("DeepUnknown", doi="10.1000/deepunknown")
        unknown_cited.references = ["10.1000/deepunknown"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/known": known_cited,
            "10.1000/unknown": unknown_cited,
            "10.1000/deepunknown": deep_via_unknown,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_papers_per_level=1,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        # known (citations=10) ranks above unknown (citations=None treated as 0).
        assert "10.1000/known" in dois
        # unknown filtered from result (rank 2, cap is 1).
        assert "10.1000/unknown" not in dois
        # unknown is still in frontier; deepunknown IS fetched and in result.
        assert "10.1000/deepunknown" in dois

    def test_max_papers_per_level_none_keeps_all_papers(self, make_paper) -> None:
        """Without max_papers_per_level, all discovered papers are in the result."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1", "10.1000/p2"]

        p1 = make_paper("P1", doi="10.1000/p1", citations=1)
        p2 = make_paper("P2", doi="10.1000/p2", citations=0)
        deep_via_p2 = make_paper("Deep", doi="10.1000/deep")
        p2.references = ["10.1000/deep"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/p1": p1,
            "10.1000/p2": p2,
            "10.1000/deep": deep_via_p2,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/p1" in dois
        assert "10.1000/p2" in dois
        assert "10.1000/deep" in dois


# ---------------------------------------------------------------------------
# TestSnowballRunnerMaxExpansion
# ---------------------------------------------------------------------------


class TestSnowballRunnerMaxExpansion:
    """Tests for the max_expansion_per_level parameter (per-level frontier cap)."""

    def test_max_expansion_limits_frontier_not_result(self, make_paper) -> None:
        """max_expansion_per_level limits the frontier; all fetched papers stay in result."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/high", "10.1000/mid", "10.1000/low"]

        high = make_paper("High", doi="10.1000/high", citations=100)
        mid = make_paper("Mid", doi="10.1000/mid", citations=50)
        low = make_paper("Low", doi="10.1000/low", citations=5)

        level2_via_low = make_paper("L2-via-low", doi="10.1000/l2low")
        low.references = ["10.1000/l2low"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/high": high,
            "10.1000/mid": mid,
            "10.1000/low": low,
            "10.1000/l2low": level2_via_low,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_expansion_per_level=2,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        # All 3 level-1 papers are in the result (no max_papers_per_level).
        assert "10.1000/high" in dois
        assert "10.1000/mid" in dois
        assert "10.1000/low" in dois
        # low is NOT in the frontier (frontier = top-2 = high, mid).
        # Therefore l2low is never fetched.
        assert "10.1000/l2low" not in dois

    def test_max_expansion_1_only_most_cited_expanded(self, make_paper) -> None:
        """max_expansion_per_level=1 drives the next level from only the top paper."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/winner", "10.1000/loser"]

        winner = make_paper("Winner", doi="10.1000/winner", citations=999)
        loser = make_paper("Loser", doi="10.1000/loser", citations=1)

        level2_via_loser = make_paper("L2-Loser", doi="10.1000/l2loser")
        loser.references = ["10.1000/l2loser"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/winner": winner,
            "10.1000/loser": loser,
            "10.1000/l2loser": level2_via_loser,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_expansion_per_level=1,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/winner" in dois
        assert "10.1000/loser" in dois  # in result but not in frontier
        assert "10.1000/l2loser" not in dois  # loser not expanded

    def test_max_expansion_none_citations_ranked_below_known(self, make_paper) -> None:
        """Papers with citations=None are treated as 0 when ranking the frontier."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/known", "10.1000/unknown"]

        known_cited = make_paper("Known", doi="10.1000/known", citations=10)
        unknown_cited = make_paper("Unknown", doi="10.1000/unknown", citations=None)

        deep_via_unknown = make_paper("DeepUnknown", doi="10.1000/deepunknown")
        unknown_cited.references = ["10.1000/deepunknown"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/known": known_cited,
            "10.1000/unknown": unknown_cited,
            "10.1000/deepunknown": deep_via_unknown,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                max_expansion_per_level=1,
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        # Both level-1 papers are in the result.
        assert "10.1000/known" in dois
        assert "10.1000/unknown" in dois
        # unknown not in frontier (citations=None < known=10); deepunknown not fetched.
        assert "10.1000/deepunknown" not in dois

    def test_max_expansion_none_expands_all(self, make_paper) -> None:
        """Without max_expansion_per_level, all papers drive the next level."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1", "10.1000/p2"]

        p1 = make_paper("P1", doi="10.1000/p1", citations=1)
        p2 = make_paper("P2", doi="10.1000/p2", citations=0)
        deep_via_p2 = make_paper("Deep", doi="10.1000/deep")
        p2.references = ["10.1000/deep"]

        paper_map = {
            "10.1000/seed": enriched_seed,
            "10.1000/p1": p1,
            "10.1000/p2": p2,
            "10.1000/deep": deep_via_p2,
        }
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
            )
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/deep" in dois


# ---------------------------------------------------------------------------
# TestSnowballRunnerFilters
# ---------------------------------------------------------------------------


class TestSnowballRunnerFilters:
    """Tests for since/until publication-date filters."""

    def _run(
        self,
        make_paper,
        seed_doi: str,
        enriched_seed: Paper,
        paper_map: dict[str, Paper | None],
        **runner_kwargs,
    ) -> SnowballResult:
        """Helper: run SnowballRunner with given seed and paper_map."""
        mock_cls = _mock_get_runner_class(paper_map)
        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi=seed_doi),
                max_depth=1,
                direction="backward",
                **runner_kwargs,
            )
            return runner.run(show_progress=False)

    def test_since_excludes_old_papers(self, make_paper) -> None:
        """Papers published before 'since' are excluded from the result."""
        enriched_seed = make_paper("Seed", doi="10.1/seed")
        enriched_seed.references = ["10.1/old", "10.1/new"]

        old = make_paper("Old", doi="10.1/old", publication_date=datetime.date(2020, 1, 1))
        new = make_paper("New", doi="10.1/new", publication_date=datetime.date(2023, 6, 1))

        paper_map = {"10.1/seed": enriched_seed, "10.1/old": old, "10.1/new": new}

        result = self._run(
            make_paper, "10.1/seed", enriched_seed, paper_map, since=datetime.date(2022, 1, 1)
        )
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1/new" in dois
        assert "10.1/old" not in dois

    def test_until_excludes_new_papers(self, make_paper) -> None:
        """Papers published after 'until' are excluded from the result."""
        enriched_seed = make_paper("Seed", doi="10.1/seed")
        enriched_seed.references = ["10.1/old", "10.1/new"]

        old = make_paper("Old", doi="10.1/old", publication_date=datetime.date(2019, 3, 1))
        new = make_paper("New", doi="10.1/new", publication_date=datetime.date(2024, 1, 1))

        paper_map = {"10.1/seed": enriched_seed, "10.1/old": old, "10.1/new": new}

        result = self._run(
            make_paper, "10.1/seed", enriched_seed, paper_map, until=datetime.date(2020, 12, 31)
        )
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1/old" in dois
        assert "10.1/new" not in dois

    def test_since_and_until_combined(self, make_paper) -> None:
        """Only papers within [since, until] are included."""
        enriched_seed = make_paper("Seed", doi="10.1/seed")
        enriched_seed.references = ["10.1/ir", "10.1/to", "10.1/tn"]

        in_range = make_paper("IR", doi="10.1/ir", publication_date=datetime.date(2021, 6, 1))
        too_old = make_paper("TO", doi="10.1/to", publication_date=datetime.date(2019, 1, 1))
        too_new = make_paper("TN", doi="10.1/tn", publication_date=datetime.date(2024, 1, 1))

        paper_map = {
            "10.1/seed": enriched_seed,
            "10.1/ir": in_range,
            "10.1/to": too_old,
            "10.1/tn": too_new,
        }
        result = self._run(
            make_paper,
            "10.1/seed",
            enriched_seed,
            paper_map,
            since=datetime.date(2020, 1, 1),
            until=datetime.date(2023, 12, 31),
        )
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1/ir" in dois
        assert "10.1/to" not in dois
        assert "10.1/tn" not in dois

    def test_no_filters_accepts_all(self, make_paper) -> None:
        """Without date filters, all discovered papers are included."""
        enriched_seed = make_paper("Seed", doi="10.1/seed")
        enriched_seed.references = ["10.1/dated", "10.1/nodate"]

        dated = make_paper("Dated", doi="10.1/dated", publication_date=datetime.date(2021, 1, 1))
        no_date = make_paper("NoDate", doi="10.1/nodate", publication_date=None)

        paper_map = {"10.1/seed": enriched_seed, "10.1/dated": dated, "10.1/nodate": no_date}

        result = self._run(make_paper, "10.1/seed", enriched_seed, paper_map)
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1/dated" in dois
        assert "10.1/nodate" in dois


# ---------------------------------------------------------------------------
# TestSnowballResultMetadata
# ---------------------------------------------------------------------------


class TestSnowballResultMetadata:
    """Tests verifying SnowballResult metadata fields after run()."""

    def test_result_seed_papers(self, make_paper) -> None:
        """result.seed_papers matches the seeds passed to SnowballRunner."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(show_progress=False)

        assert len(result.seed_papers) == 1

    def test_result_max_depth(self, make_paper) -> None:
        """result.max_depth matches the configured max_depth."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=3)
            result = runner.run(show_progress=False)

        assert result.max_depth == 3

    def test_result_direction(self, make_paper) -> None:
        """result.direction matches the configured direction."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1, direction="forward")
            result = runner.run(show_progress=False)

        assert result.direction == "forward"

    def test_result_skipped_seeds(self, make_paper) -> None:
        """result.skipped_seeds_without_doi reflects seeds skipped due to missing DOI."""
        seed_with = make_paper("With DOI", doi="10.1000/ok")
        seed_without = make_paper("No DOI")
        enriched = make_paper("With DOI", doi="10.1000/ok")

        paper_map = {"10.1000/ok": enriched}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=[seed_with, seed_without], max_depth=1)
            result = runner.run(show_progress=False)

        assert result.skipped_seeds_without_doi == 1

    def test_result_runtime_seconds_positive(self, make_paper) -> None:
        """result.runtime_seconds is a non-negative float."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(show_progress=False)

        assert result.runtime_seconds is not None
        assert result.runtime_seconds >= 0.0

    def test_result_processed_at_is_utc(self, make_paper) -> None:
        """result.processed_at is a timezone-aware UTC datetime."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(show_progress=False)

        assert result.processed_at.tzinfo is not None


# ---------------------------------------------------------------------------
# TestSnowballRunnerVerboseAndProgress
# ---------------------------------------------------------------------------


class TestSnowballRunnerVerboseAndProgress:
    """Tests for verbose and show_progress flags."""

    def test_verbose_run_returns_result(self, make_paper) -> None:
        """verbose=True does not raise and still returns a SnowballResult."""
        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(seed_papers=seed, max_depth=1)
            result = runner.run(verbose=True, show_progress=False)

        assert isinstance(result, SnowballResult)

    def test_verbose_restores_root_logger_level(self, make_paper) -> None:
        """run(verbose=True) restores the root logger to its original level."""
        import logging

        seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map)

        root = logging.getLogger()
        saved = root.level
        root.setLevel(logging.WARNING)
        try:
            with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
                runner = SnowballRunner(seed_papers=seed, max_depth=1)
                runner.run(verbose=True, show_progress=False)

            assert root.level == logging.WARNING
        finally:
            root.setLevel(saved)


# ---------------------------------------------------------------------------
# TestFetchDoisError
# ---------------------------------------------------------------------------


class TestFetchDoisError:
    """Tests for error handling in _fetch_dois."""

    def test_get_runner_exception_is_logged_and_skipped(self, make_paper) -> None:
        """When GetRunner.run() raises, the DOI is skipped and no crash occurs."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/bad"]

        class _ErrorGetRunner:
            def __init__(self, identifier: str, **kwargs: object) -> None:
                self._doi = identifier.strip().lower()

            def run(self, verbose: bool = False, max_cited_by: int | None = None) -> Paper | None:
                if self._doi == "10.1000/bad":
                    raise RuntimeError("network failure")
                return {"10.1000/seed": enriched_seed}.get(self._doi)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=_ErrorGetRunner):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
            )
            # Must not raise.
            result = runner.run(show_progress=False)

        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/bad" not in dois


# ---------------------------------------------------------------------------
# TestSnowballRunnerEnrichmentStrategy
# ---------------------------------------------------------------------------


class TestSnowballRunnerEnrichmentStrategy:
    """Tests for the three-tier fetch strategy (discovery / enrichment / scraping)."""

    # ------------------------------------------------------------------
    # enrichment_databases parameter validation
    # ------------------------------------------------------------------

    def test_enrichment_databases_empty_list_disables_enrichment(self, seed: Paper) -> None:
        """An empty enrichment_databases list disables enrichment (stored as [])."""
        runner = SnowballRunner(seed_papers=seed, enrichment_databases=[])
        assert runner._enrichment_databases == []

    def test_enrichment_databases_unknown_value_raises(self, seed: Paper) -> None:
        """An unknown value in enrichment_databases raises InvalidParameterError."""
        with pytest.raises(InvalidParameterError, match="Unknown database"):
            SnowballRunner(seed_papers=seed, enrichment_databases=["no_such_db"])

    def test_enrichment_databases_none_uses_default(self, seed: Paper) -> None:
        """enrichment_databases=None stores the module-level default."""
        runner = SnowballRunner(seed_papers=seed, enrichment_databases=None)
        assert runner._enrichment_databases == list(SNOWBALL_ENRICHMENT_DATABASES)

    def test_enrichment_databases_custom_stored(self, seed: Paper) -> None:
        """An explicit enrichment_databases list is stored on the runner."""
        runner = SnowballRunner(seed_papers=seed, enrichment_databases=["crossref", "openalex"])
        assert set(runner._enrichment_databases) == {"crossref", "openalex"}

    # ------------------------------------------------------------------
    # Seeds are fetched with union of databases + enrichment_databases
    # ------------------------------------------------------------------

    def test_seeds_fetched_with_union_databases(self, make_paper) -> None:
        """Seeds are fetched with union(databases, enrichment_databases)."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        call_log: list[dict] = []
        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map, call_log=call_log)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
                databases=["crossref"],
                enrichment_databases=["openalex"],
            )
            runner.run(show_progress=False)

        seed_calls = [c for c in call_log if c["identifier"] == "10.1000/seed"]
        # At least one call should have both databases.
        union_dbs = sorted({"crossref", "openalex"})
        assert any(sorted(c["databases"]) == union_dbs for c in seed_calls), (
            f"Expected at least one seed call with databases={union_dbs!r}. Calls: {seed_calls}"
        )

    # ------------------------------------------------------------------
    # Frontier enrichment between BFS levels
    # ------------------------------------------------------------------

    def test_frontier_enriched_before_next_level(self, make_paper) -> None:
        """Papers driving the next BFS level are re-fetched with union(databases, enrichment_databases)."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1"]

        # p1 from discovery has no references; enriched p1 has references to p2.
        p1_discovery = make_paper("P1", doi="10.1000/p1")
        p1_enriched = make_paper("P1 enriched", doi="10.1000/p1")
        p1_enriched.references = ["10.1000/p2"]

        p2 = make_paper("P2", doi="10.1000/p2")

        union_dbs = sorted({"crossref", "openalex"})

        class _SmartMock:
            def __init__(self, identifier: str, **kwargs: object) -> None:
                self._doi = identifier.strip().lower()
                raw_dbs = kwargs.get("databases")
                self._dbs: list[str] | None = list(raw_dbs) if isinstance(raw_dbs, list) else None

            def run(self, verbose: bool = False, max_cited_by: int | None = None) -> Paper | None:
                if self._doi == "10.1000/seed":
                    return enriched_seed  # type: ignore[no-any-return]
                if self._doi == "10.1000/p1":
                    # Return enriched version when called with the union.
                    dbs: list[str] = self._dbs if self._dbs is not None else []
                    return p1_enriched if sorted(dbs) == union_dbs else p1_discovery  # type: ignore[no-any-return]
                if self._doi == "10.1000/p2":
                    return p2  # type: ignore[no-any-return]
                return None

        with patch("findpapers.runners.snowball_runner.GetRunner", new=_SmartMock):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=2,
                direction="backward",
                databases=["crossref"],
                enrichment_databases=["openalex"],
            )
            result = runner.run(show_progress=False)

        # p2 is only reachable if p1 was enriched before level 2.
        dois = {p.doi for p in result.papers if p.doi}
        assert "10.1000/p2" in dois, "p2 should be discovered via enriched p1"

    def test_frontier_not_enriched_at_last_level(self, make_paper) -> None:
        """Papers at the last BFS level are NOT re-enriched (no next level to expand)."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1"]

        p1 = make_paper("P1", doi="10.1000/p1")

        call_log: list[dict] = []
        paper_map = {"10.1000/seed": enriched_seed, "10.1000/p1": p1}
        mock_cls = _mock_get_runner_class(paper_map, call_log=call_log)

        union_dbs = sorted({"crossref", "openalex"})

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
                databases=["crossref"],
                enrichment_databases=["openalex"],
            )
            runner.run(show_progress=False)

        # p1 is at the last (and only) BFS level: no union-enrichment call expected.
        p1_union_calls = [
            c
            for c in call_log
            if c["identifier"] == "10.1000/p1" and sorted(c["databases"] or []) == union_dbs
        ]
        assert p1_union_calls == [], "No frontier enrichment expected at the last BFS level"

    # ------------------------------------------------------------------
    # Final enrichment enriches non-seed papers only
    # ------------------------------------------------------------------

    def test_final_enrichment_enriches_non_seed_papers(self, make_paper) -> None:
        """After BFS, non-seed papers are re-enriched with enrichment-only databases."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1"]

        p1 = make_paper("P1", doi="10.1000/p1")

        call_log: list[dict] = []
        paper_map = {"10.1000/seed": enriched_seed, "10.1000/p1": p1}
        mock_cls = _mock_get_runner_class(paper_map, call_log=call_log)

        enrichment_only = ["web_scraping"]
        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
                databases=["crossref"],
                enrichment_databases=enrichment_only,
            )
            runner.run(show_progress=False)

        # p1 (non-seed) should get a final-enrichment call with enrichment_only databases.
        p1_final_calls = [
            c
            for c in call_log
            if c["identifier"] == "10.1000/p1" and c["databases"] == enrichment_only
        ]
        assert len(p1_final_calls) >= 1, (
            f"Expected final enrichment call for p1 with {enrichment_only!r}. Calls: {call_log}"
        )

    def test_final_enrichment_skips_seeds(self, make_paper) -> None:
        """Seed DOIs are excluded from the final enrichment pass."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")

        call_log: list[dict] = []
        paper_map = {"10.1000/seed": enriched_seed}
        mock_cls = _mock_get_runner_class(paper_map, call_log=call_log)

        enrichment_only = ["web_scraping"]
        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
                databases=["crossref"],
                enrichment_databases=enrichment_only,
            )
            runner.run(show_progress=False)

        # The seed DOI should NOT appear in final-enrichment calls.
        seed_final_calls = [
            c
            for c in call_log
            if c["identifier"] == "10.1000/seed" and c["databases"] == enrichment_only
        ]
        assert seed_final_calls == [], (
            f"Seed should be excluded from final enrichment. Calls: {call_log}"
        )

    def test_final_enrichment_uses_enrichment_minus_discovery_databases(self, make_paper) -> None:
        """Final enrichment only uses databases not already used during BFS discovery."""
        enriched_seed = make_paper("Seed", doi="10.1000/seed")
        enriched_seed.references = ["10.1000/p1"]

        p1 = make_paper("P1", doi="10.1000/p1")

        call_log: list[dict] = []
        paper_map = {"10.1000/seed": enriched_seed, "10.1000/p1": p1}
        mock_cls = _mock_get_runner_class(paper_map, call_log=call_log)

        with patch("findpapers.runners.snowball_runner.GetRunner", new=mock_cls):
            runner = SnowballRunner(
                seed_papers=make_paper("Seed", doi="10.1000/seed"),
                max_depth=1,
                direction="backward",
                # crossref used in both discovery and enrichment; web_scraping is enrichment-only.
                databases=["crossref"],
                enrichment_databases=["crossref", "web_scraping"],
            )
            runner.run(show_progress=False)

        # Final enrichment of p1 should use only web_scraping (crossref was already used).
        p1_final_calls = [
            c
            for c in call_log
            if c["identifier"] == "10.1000/p1" and c["databases"] == ["web_scraping"]
        ]
        assert len(p1_final_calls) >= 1, (
            f"Expected final enrichment with web_scraping only. Calls: {call_log}"
        )
