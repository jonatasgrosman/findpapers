"""Unit tests for SemanticScholarConnector citation methods."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from findpapers.connectors.semantic_scholar import SemanticScholarConnector


def _make_ss_paper_record(
    paper_id: str = "abc123",
    doi: str = "10.1000/ref",
    title: str = "Referenced Paper",
) -> dict:
    """Create a minimal Semantic Scholar paper record for mocking."""
    return {
        "paperId": paper_id,
        "externalIds": {"DOI": doi},
        "title": title,
        "abstract": "An abstract.",
        "authors": [{"name": "Author One", "authorId": "111"}],
        "year": 2024,
        "publicationDate": "2024-01-15",
        "journal": {"name": "Test Journal"},
        "venue": "",
        "citationCount": 10,
        "openAccessPdf": None,
        "url": f"https://semanticscholar.org/paper/{paper_id}",
        "fieldsOfStudy": [],
        "publicationTypes": ["JournalArticle"],
        "publicationVenue": None,
    }


# ---------------------------------------------------------------------------
# Tests: fetch_cited_by
# ---------------------------------------------------------------------------


class TestSemanticScholarFetchCitedBy:
    """Tests for SemanticScholarConnector.fetch_cited_by."""

    def test_returns_empty_for_paper_without_doi(self, make_paper) -> None:
        """Papers without DOI return empty list."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=None)

        result = connector.fetch_cited_by(paper)

        assert result == []

    @patch.object(SemanticScholarConnector, "_get")
    def test_fetches_citing_papers(self, mock_get: MagicMock, make_paper) -> None:
        """Fetches citations using the /paper/{id}/citations endpoint."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi="10.1000/cited")

        response = MagicMock()
        response.json.return_value = {
            "data": [
                {"citingPaper": _make_ss_paper_record("c1", "10.1000/c1", "Citing 1")},
            ],
            "next": None,
        }
        mock_get.return_value = response

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 1
        assert cited_by[0].title == "Citing 1"
        call_url = mock_get.call_args[0][0]
        assert "citations" in call_url

    @patch.object(SemanticScholarConnector, "_get")
    def test_paginates_through_multiple_pages(self, mock_get: MagicMock, make_paper) -> None:
        """Follows offset-based pagination until exhausted."""
        connector = SemanticScholarConnector()
        # Set citations so _fetch_paper_counts is skipped (uses local count).
        paper = make_paper(doi="10.1000/popular", citations=1001)

        # Page 1: returns 1000 items (full page) with next offset
        page1 = MagicMock()
        page1.json.return_value = {
            "data": [
                {"citingPaper": _make_ss_paper_record(f"p{i}", f"10.1000/p{i}", f"Paper {i}")}
                for i in range(1000)
            ],
            "next": 1000,
        }

        # Page 2: returns fewer items (last page)
        page2 = MagicMock()
        page2.json.return_value = {
            "data": [
                {"citingPaper": _make_ss_paper_record("last", "10.1000/last", "Last Paper")},
            ],
            "next": None,
        }

        mock_get.side_effect = [page1, page2]

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 1001
        assert mock_get.call_count == 2

    @patch.object(SemanticScholarConnector, "_get")
    def test_handles_api_error(self, mock_get: MagicMock, make_paper) -> None:
        """Returns empty list on API error."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi="10.1000/error")

        mock_get.side_effect = requests.RequestException("Network error")

        cited_by = connector.fetch_cited_by(paper)

        assert cited_by == []

    @patch.object(SemanticScholarConnector, "_get")
    def test_skips_unparseable_entries(self, mock_get: MagicMock, make_paper) -> None:
        """Entries without a title are skipped silently."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi="10.1000/mixed")

        bad_record = _make_ss_paper_record("bad", "10.1000/bad", "")
        good_record = _make_ss_paper_record("good", "10.1000/good", "Good Paper")

        response = MagicMock()
        response.json.return_value = {
            "data": [
                {"citingPaper": bad_record},
                {"citingPaper": good_record},
            ],
            "next": None,
        }
        mock_get.return_value = response

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 1
        assert cited_by[0].title == "Good Paper"

    @patch.object(SemanticScholarConnector, "_get")
    def test_max_papers_stops_pagination_early(self, mock_get: MagicMock, make_paper) -> None:
        """Pagination stops once max_papers is reached; no further pages are fetched."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi="10.1000/popular", citations=2000)

        # Page 1: full page (1000 items) with next offset
        page1 = MagicMock()
        page1.json.return_value = {
            "data": [
                {"citingPaper": _make_ss_paper_record(f"p{i}", f"10.1000/p{i}", f"Paper {i}")}
                for i in range(1000)
            ],
            "next": 1000,
        }

        mock_get.side_effect = [page1]

        # Request only 3 papers — only 1 page fetched, result is trimmed
        cited_by = connector.fetch_cited_by(paper, max_papers=3)

        assert len(cited_by) == 3
        assert mock_get.call_count == 1

    @patch.object(SemanticScholarConnector, "_get")
    def test_max_papers_none_fetches_all(self, mock_get: MagicMock, make_paper) -> None:
        """Default (None) max_papers fetches all pages."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi="10.1000/normal")

        page = MagicMock()
        page.json.return_value = {
            "data": [
                {"citingPaper": _make_ss_paper_record("a", "10.1000/a", "Paper A")},
                {"citingPaper": _make_ss_paper_record("b", "10.1000/b", "Paper B")},
            ],
            "next": None,
        }
        mock_get.return_value = page

        cited_by = connector.fetch_cited_by(paper, max_papers=None)

        assert len(cited_by) == 2


# ---------------------------------------------------------------------------
# Tests with real API response data
# ---------------------------------------------------------------------------

_SPRINGER_DOI = "10.3758/s13428-022-02028-7"


class TestSemanticScholarRealDataParsing:
    """Tests using real Semantic Scholar API responses."""

    def test_parse_paper_counts(self, ss_citation_samples: dict) -> None:
        """Parse real paper-counts response for reference/citation counts."""
        counts = ss_citation_samples[_SPRINGER_DOI]["paper_counts"]

        assert counts["referenceCount"] == 40
        assert counts["citationCount"] == 3

    @patch.object(SemanticScholarConnector, "_get")
    def test_fetch_cited_by_with_real_data(
        self,
        mock_get: MagicMock,
        make_paper,
        ss_citation_samples: dict,
    ) -> None:
        """Feed real citations response to fetch_cited_by and verify parsing."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=_SPRINGER_DOI)
        cits_response = ss_citation_samples[_SPRINGER_DOI]["citations"]

        response = MagicMock()
        response.json.return_value = cits_response
        mock_get.return_value = response

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 3
        for p in cited_by:
            assert p.title
            assert "semantic_scholar" in p.found_in
