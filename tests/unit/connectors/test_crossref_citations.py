"""Unit tests for CrossRefConnector citation methods."""

from __future__ import annotations

from findpapers.connectors.crossref import CrossRefConnector


def _make_crossref_work(
    doi: str = "10.1000/ref",
    title: str = "Referenced Paper",
    references: list[dict] | None = None,
) -> dict:
    """Create a minimal CrossRef work record for mocking."""
    work: dict = {
        "DOI": doi,
        "title": [title],
        "abstract": "<jats:p>An abstract.</jats:p>",
        "author": [{"given": "Author", "family": "One", "affiliation": []}],
        "issued": {"date-parts": [[2024, 1, 15]]},
        "container-title": ["Test Journal"],
        "type": "journal-article",
        "is-referenced-by-count": 5,
        "URL": f"https://doi.org/{doi}",
    }
    if references is not None:
        work["reference"] = references
    return work


# ---------------------------------------------------------------------------
# Tests with real API response data
# ---------------------------------------------------------------------------

_NATURE_DOI = "10.1038/nature12373"


class TestCrossRefRealDataParsing:
    """Tests using real CrossRef API responses from sample_responses.json."""

    def test_real_work_has_references(self, crossref_sample_json: dict) -> None:
        """Verify real CrossRef work contains a non-empty reference array."""
        work = crossref_sample_json[_NATURE_DOI]
        refs = work.get("reference", [])

        assert len(refs) == 30
        # Most references in this paper have DOIs.
        with_doi = [r for r in refs if r.get("DOI")]
        assert len(with_doi) == 29

    def test_build_paper_with_real_work(self, crossref_sample_json: dict) -> None:
        """build_paper converts a real CrossRef work record to a Paper."""
        connector = CrossRefConnector()
        work = crossref_sample_json[_NATURE_DOI]

        paper = connector.build_paper(work)

        assert paper is not None
        assert paper.title
        assert paper.doi == _NATURE_DOI
        assert paper.authors
