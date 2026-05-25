"""Unit tests for OpenAlexConnector citation methods (fetch_references, fetch_cited_by)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from findpapers.connectors.openalex import OpenAlexConnector


def _make_openalex_work(
    openalex_id: str = "https://openalex.org/W111",
    doi: str = "10.1000/ref",
    title: str = "Referenced Paper",
) -> dict:
    """Create a minimal OpenAlex work record for mocking."""
    return {
        "id": openalex_id,
        "doi": f"https://doi.org/{doi}",
        "title": title,
        "display_name": title,
        "abstract_inverted_index": None,
        "authorships": [
            {
                "author": {"display_name": "Author One"},
                "institutions": [],
            }
        ],
        "publication_date": "2024-01-15",
        "cited_by_count": 5,
        "open_access": {},
        "primary_location": {"landing_page_url": f"https://example.com/{doi}"},
        "locations": [],
        "concepts": [],
        "keywords": [],
        "type": "article",
        "biblio": {},
    }


# ---------------------------------------------------------------------------
# Tests: fetch_cited_by
# ---------------------------------------------------------------------------


class TestOpenAlexFetchCitedBy:
    """Tests for OpenAlexConnector.fetch_cited_by."""

    def test_returns_empty_for_paper_without_doi(self, make_paper) -> None:
        """Papers without DOI cannot be resolved; return empty list."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=None)

        result = connector.fetch_cited_by(paper)

        assert result == []

    @patch.object(OpenAlexConnector, "_get")
    def test_fetches_citing_papers(self, mock_get: MagicMock, make_paper) -> None:
        """Resolves the OpenAlex ID and fetches citing papers."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/cited")

        # First call: resolve DOI → OpenAlex ID
        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W888"}

        # Second call: cites filter → one page of results
        cite_response = MagicMock()
        cite_response.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W300", "10.1000/c1", "Citing 1"),
            ],
            "meta": {"next_cursor": None},
        }

        mock_get.side_effect = [id_response, cite_response]

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 1
        assert cited_by[0].title == "Citing 1"

    @patch.object(OpenAlexConnector, "_get")
    def test_paginates_through_multiple_pages(self, mock_get: MagicMock, make_paper) -> None:
        """Follows cursor pagination until exhausted."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/popular")

        # Resolve ID
        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W777"}

        # Page 1: has next_cursor and full page (simulate _PAGE_SIZE results)
        page1 = MagicMock()
        page1.json.return_value = {
            "results": [
                _make_openalex_work(f"https://openalex.org/W{i}", f"10.1000/p{i}", f"Paper {i}")
                for i in range(200)
            ],
            "meta": {"next_cursor": "cursor_2"},
        }

        # Page 2: last page, fewer results
        page2 = MagicMock()
        page2.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W999", "10.1000/last", "Last Paper"),
            ],
            "meta": {"next_cursor": None},
        }

        mock_get.side_effect = [id_response, page1, page2]

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 201  # 200 + 1
        assert mock_get.call_count == 3  # id resolve + 2 pages

    @patch.object(OpenAlexConnector, "_get")
    def test_returns_empty_when_id_not_resolved(self, mock_get: MagicMock, make_paper) -> None:
        """Returns empty list when OpenAlex ID cannot be resolved."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/unknown")

        id_response = MagicMock()
        id_response.json.return_value = {"id": ""}
        mock_get.return_value = id_response

        cited_by = connector.fetch_cited_by(paper)

        assert cited_by == []

    @patch.object(OpenAlexConnector, "_get")
    def test_handles_api_error_during_id_resolve(self, mock_get: MagicMock, make_paper) -> None:
        """Returns empty list when ID resolution fails."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/error")

        mock_get.side_effect = requests.RequestException("Network error")

        cited_by = connector.fetch_cited_by(paper)

        assert cited_by == []

    @patch.object(OpenAlexConnector, "_get")
    def test_max_papers_stops_pagination_early(self, mock_get: MagicMock, make_paper) -> None:
        """Pagination stops once max_papers is reached; no further API calls are made."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/popular")

        # Resolve ID
        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W777"}

        # Page 1: full page of 200 results with a next_cursor (more pages exist)
        page1 = MagicMock()
        page1.json.return_value = {
            "results": [
                _make_openalex_work(f"https://openalex.org/W{i}", f"10.1000/p{i}", f"Paper {i}")
                for i in range(200)
            ],
            "meta": {"next_cursor": "cursor_2"},
        }

        mock_get.side_effect = [id_response, page1]

        # Request only 5 papers — pagination must stop after page 1
        cited_by = connector.fetch_cited_by(paper, max_papers=5)

        assert len(cited_by) == 5
        # Only id resolve + 1 page fetched; cursor_2 page never requested
        assert mock_get.call_count == 2

    @patch.object(OpenAlexConnector, "_get")
    def test_max_papers_requests_sort_by_citations(self, mock_get: MagicMock, make_paper) -> None:
        """When max_papers is set, sort=cited_by_count:desc is added to the request."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/popular")

        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W777"}

        page1 = MagicMock()
        page1.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W1", "10.1000/c1", "Citing 1"),
            ],
            "meta": {"next_cursor": None},
        }
        mock_get.side_effect = [id_response, page1]

        connector.fetch_cited_by(paper, max_papers=10)

        # The second call (cites page) must include sort=cited_by_count:desc
        page_call_kwargs = mock_get.call_args_list[1][0][1]  # second positional arg = params dict
        assert page_call_kwargs.get("sort") == "cited_by_count:desc"

    @patch.object(OpenAlexConnector, "_get")
    def test_no_sort_when_max_papers_is_none(self, mock_get: MagicMock, make_paper) -> None:
        """When max_papers is None, sort param is NOT added to the request."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/cited")

        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W888"}

        cite_response = MagicMock()
        cite_response.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W300", "10.1000/c1", "Citing 1"),
            ],
            "meta": {"next_cursor": None},
        }
        mock_get.side_effect = [id_response, cite_response]

        connector.fetch_cited_by(paper, max_papers=None)

        page_call_kwargs = mock_get.call_args_list[1][0][1]
        assert "sort" not in page_call_kwargs

    @patch.object(OpenAlexConnector, "_get")
    def test_max_papers_none_fetches_all(self, mock_get: MagicMock, make_paper) -> None:
        """Default (None) max_papers fetches all pages without truncation."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/cited")

        id_response = MagicMock()
        id_response.json.return_value = {"id": "https://openalex.org/W888"}

        cite_response = MagicMock()
        cite_response.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W300", "10.1000/c1", "Citing 1"),
                _make_openalex_work("https://openalex.org/W301", "10.1000/c2", "Citing 2"),
            ],
            "meta": {"next_cursor": None},
        }

        mock_get.side_effect = [id_response, cite_response]

        cited_by = connector.fetch_cited_by(paper, max_papers=None)

        assert len(cited_by) == 2


# ---------------------------------------------------------------------------
# Tests: _resolve_openalex_id
# ---------------------------------------------------------------------------


class TestResolveOpenalexId:
    """Tests for the internal _resolve_openalex_id helper."""

    @patch.object(OpenAlexConnector, "_get")
    def test_resolves_by_doi(self, mock_get: MagicMock, make_paper) -> None:
        """Returns the OpenAlex ID from the API response."""
        connector = OpenAlexConnector()
        paper = make_paper(doi="10.1000/ok")

        response = MagicMock()
        response.json.return_value = {"id": "https://openalex.org/W12345"}
        mock_get.return_value = response

        oa_id = connector._resolve_openalex_id(paper)

        assert oa_id == "https://openalex.org/W12345"

    def test_returns_none_without_doi(self, make_paper) -> None:
        """Returns None when paper has no DOI."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=None)

        assert connector._resolve_openalex_id(paper) is None


# ---------------------------------------------------------------------------
# Tests: _fetch_works_by_ids
# ---------------------------------------------------------------------------


class TestFetchWorksByIds:
    """Tests for batch-fetching works by OpenAlex IDs."""

    @patch.object(OpenAlexConnector, "_get")
    def test_empty_ids_returns_empty(self, mock_get: MagicMock) -> None:
        """Empty ID list returns empty result without making API calls."""
        connector = OpenAlexConnector()

        result = connector._fetch_works_by_ids([])

        assert result == []
        mock_get.assert_not_called()

    @patch.object(OpenAlexConnector, "_get")
    def test_batch_fetches_ids(self, mock_get: MagicMock) -> None:
        """Fetches works using pipe-separated ID filter."""
        connector = OpenAlexConnector()

        response = MagicMock()
        response.json.return_value = {
            "results": [
                _make_openalex_work("https://openalex.org/W1", "10.1000/a", "Paper A"),
                _make_openalex_work("https://openalex.org/W2", "10.1000/b", "Paper B"),
            ]
        }
        mock_get.return_value = response

        result = connector._fetch_works_by_ids(
            [
                "https://openalex.org/W1",
                "https://openalex.org/W2",
            ]
        )

        assert len(result) == 2
        assert mock_get.call_count == 1


# ---------------------------------------------------------------------------
# Tests with real API response data
# ---------------------------------------------------------------------------

_SPRINGER_DOI = "10.3758/s13428-022-02028-7"


class TestOpenAlexRealDataParsing:
    """Tests using real OpenAlex API responses."""

    @patch.object(OpenAlexConnector, "_get")
    def test_resolve_openalex_id_with_real_data(
        self,
        mock_get: MagicMock,
        make_paper,
        oa_citation_samples: dict,
    ) -> None:
        """Resolve DOI to OpenAlex ID using real API response."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_SPRINGER_DOI)
        doi_data = oa_citation_samples[_SPRINGER_DOI]["doi_resolution"]

        response = MagicMock()
        response.json.return_value = doi_data
        mock_get.return_value = response

        oa_id = connector._resolve_openalex_id(paper)

        assert oa_id == "https://openalex.org/W4312081276"

    @patch.object(OpenAlexConnector, "_get")
    def test_fetch_works_by_ids_with_real_data(
        self,
        mock_get: MagicMock,
        oa_citation_samples: dict,
    ) -> None:
        """Batch-fetch works using real API response."""
        connector = OpenAlexConnector()
        sample = oa_citation_samples[_SPRINGER_DOI]
        ref_ids = sample["referenced_works"]["referenced_works"]

        response = MagicMock()
        response.json.return_value = sample["works_by_ids"]
        mock_get.return_value = response

        papers = connector._fetch_works_by_ids(ref_ids)

        assert len(papers) == 13
        titles = {p.title for p in papers}
        # Verify a known paper from the reference list is present.
        assert any("GloVe" in t or "Global Vectors" in t for t in titles)

    @patch.object(OpenAlexConnector, "_get")
    def test_fetch_cited_by_with_real_data(
        self,
        mock_get: MagicMock,
        make_paper,
        oa_citation_samples: dict,
    ) -> None:
        """Full fetch_cited_by with real ID resolution + cited-by page."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_SPRINGER_DOI)
        sample = oa_citation_samples[_SPRINGER_DOI]

        # First call: resolve DOI → OpenAlex ID
        id_response = MagicMock()
        id_response.json.return_value = sample["doi_resolution"]

        # Second call: cited-by results
        cite_response = MagicMock()
        cite_response.json.return_value = sample["cited_by"]

        mock_get.side_effect = [id_response, cite_response]

        cited_by = connector.fetch_cited_by(paper)

        assert len(cited_by) == 2
        for p in cited_by:
            assert p.title
            assert "openalex" in p.found_in
