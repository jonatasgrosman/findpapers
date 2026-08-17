"""Unit tests for the fetch_related() connector methods used by Engine.similar()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import requests

from findpapers.connectors.openalex import OpenAlexConnector
from findpapers.connectors.pubmed import PubmedConnector
from findpapers.connectors.semantic_scholar import SemanticScholarConnector

_LSTM_DOI = "10.1162/neco.1997.9.8.1735"
_CRISPR_DOI = "10.1126/science.1225829"


# ---------------------------------------------------------------------------
# Semantic Scholar
# ---------------------------------------------------------------------------


class TestSemanticScholarFetchRelated:
    """Tests for SemanticScholarConnector.fetch_related."""

    def test_returns_empty_for_paper_without_doi(self, make_paper) -> None:
        """Papers without DOI return an empty list without any HTTP call."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=None)

        assert connector.fetch_related(paper) == []

    @patch.object(SemanticScholarConnector, "_get")
    def test_always_requests_from_all_cs(self, mock_get: MagicMock, make_paper) -> None:
        """The 'from=all-cs' pool is always requested, never the 'recent' default.

        This locks down the central finding of the investigation: the
        Recommendations API's own default (from=recent) silently returns an
        empty list for anything not published in the last 60 days.
        """
        connector = SemanticScholarConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = {"recommendedPapers": []}
        mock_get.return_value = response

        connector.fetch_related(paper)

        _, params = mock_get.call_args[0]
        assert params["from"] == "all-cs"

    @patch.object(SemanticScholarConnector, "_request_with_retry")
    def test_sends_api_key_header_when_configured(
        self, mock_request: MagicMock, make_paper
    ) -> None:
        """The x-api-key header is sent normally, like every other request.

        A live-tested, valid key authenticates fine on the Recommendations
        host, the same way it does on the Graph API: an earlier, revoked key
        made this look host-specific (403 everywhere, not just here), which
        this test guards against regressing back into.  ``_request_with_retry``
        is patched (rather than ``_get``) so the real ``_prepare_headers``
        key-injection logic still runs and is observed here.
        """
        connector = SemanticScholarConnector(api_key="a-valid-key")
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = {"recommendedPapers": []}
        mock_request.return_value = response

        connector.fetch_related(paper)

        _, kwargs = mock_request.call_args
        assert kwargs["headers"]["x-api-key"] == "a-valid-key"

    @patch.object(SemanticScholarConnector, "_get")
    def test_parses_real_response(
        self, mock_get: MagicMock, make_paper, similar_samples: dict
    ) -> None:
        """Feed a real recommendations response and verify parsing."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = similar_samples[_LSTM_DOI]["ss_recommendations"]
        mock_get.return_value = response

        related = connector.fetch_related(paper)

        assert len(related) == 100
        for p in related:
            assert p.title
            assert "semantic_scholar" in p.found_in

    @patch.object(SemanticScholarConnector, "_get")
    def test_max_papers_truncates_result(
        self, mock_get: MagicMock, make_paper, similar_samples: dict
    ) -> None:
        """max_papers truncates the parsed result and is forwarded as 'limit'."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = similar_samples[_LSTM_DOI]["ss_recommendations"]
        mock_get.return_value = response

        related = connector.fetch_related(paper, max_papers=5)

        assert len(related) == 5
        _, params = mock_get.call_args[0]
        assert params["limit"] == 5

    @patch.object(SemanticScholarConnector, "_get")
    def test_returns_empty_on_request_failure(self, mock_get: MagicMock, make_paper) -> None:
        """A request failure is swallowed and results in an empty list."""
        connector = SemanticScholarConnector()
        paper = make_paper(doi=_LSTM_DOI)
        mock_get.side_effect = requests.ConnectionError("boom")

        assert connector.fetch_related(paper) == []


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------


class TestOpenAlexFetchRelated:
    """Tests for OpenAlexConnector.fetch_related."""

    def test_returns_empty_for_paper_without_doi(self, make_paper) -> None:
        """Papers without DOI return an empty list without any HTTP call."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=None)

        assert connector.fetch_related(paper) == []

    @patch.object(OpenAlexConnector, "_fetch_works_by_ids")
    @patch.object(OpenAlexConnector, "_get")
    def test_resolves_related_works_via_batch_helper(
        self,
        mock_get: MagicMock,
        mock_batch: MagicMock,
        make_paper,
        similar_samples: dict,
    ) -> None:
        """related_works IDs are resolved via the existing batch helper, not N+1 calls."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = similar_samples[_LSTM_DOI]["oa_related_works"]
        mock_get.return_value = response
        mock_batch.return_value = [MagicMock()]

        related = connector.fetch_related(paper)

        assert mock_get.call_count == 1  # only the related_works lookup, no per-ID calls
        related_ids = similar_samples[_LSTM_DOI]["oa_related_works"]["related_works"]
        mock_batch.assert_called_once_with(related_ids)
        assert len(related) == 1

    @patch.object(OpenAlexConnector, "_get")
    def test_returns_empty_when_no_related_works(self, mock_get: MagicMock, make_paper) -> None:
        """No related_works field means no batch call and an empty result."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = {"id": "https://openalex.org/W1", "related_works": []}
        mock_get.return_value = response

        assert connector.fetch_related(paper) == []

    @patch.object(OpenAlexConnector, "_get")
    def test_max_papers_limits_ids_before_batch_fetch(
        self, mock_get: MagicMock, make_paper, similar_samples: dict
    ) -> None:
        """max_papers truncates the ID list before the batch request is issued."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_LSTM_DOI)

        response = MagicMock()
        response.json.return_value = similar_samples[_LSTM_DOI]["oa_related_works"]
        mock_get.return_value = response

        with patch.object(OpenAlexConnector, "_fetch_works_by_ids") as mock_batch:
            mock_batch.return_value = []
            connector.fetch_related(paper, max_papers=2)
            (ids_arg,) = mock_batch.call_args[0]
            assert len(ids_arg) == 2

    @patch.object(OpenAlexConnector, "_get")
    def test_end_to_end_with_real_batch_response(
        self, mock_get: MagicMock, make_paper, similar_samples: dict
    ) -> None:
        """Real related_works + batch responses parse into full Paper objects."""
        connector = OpenAlexConnector()
        paper = make_paper(doi=_LSTM_DOI)

        related_response = MagicMock()
        related_response.json.return_value = similar_samples[_LSTM_DOI]["oa_related_works"]
        batch_response = MagicMock()
        batch_response.json.return_value = similar_samples[_LSTM_DOI]["oa_works_by_ids"]
        mock_get.side_effect = [related_response, batch_response]

        related = connector.fetch_related(paper)

        assert len(related) == len(similar_samples[_LSTM_DOI]["oa_works_by_ids"]["results"])
        for p in related:
            assert p.title
            assert "openalex" in p.found_in


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------


class TestPubmedResolvePmid:
    """Tests for PubmedConnector._resolve_pmid."""

    @patch.object(PubmedConnector, "_search_ids")
    def test_returns_pmid_when_found(self, mock_search: MagicMock) -> None:
        """Returns the first PMID from esearch results."""
        connector = PubmedConnector()
        mock_search.return_value = (["12345"], 1)

        assert connector._resolve_pmid("10.1000/x") == "12345"

    @patch.object(PubmedConnector, "_search_ids")
    def test_returns_none_when_not_found(self, mock_search: MagicMock) -> None:
        """Returns None when the DOI is not indexed by PubMed."""
        connector = PubmedConnector()
        mock_search.return_value = ([], 0)

        assert connector._resolve_pmid("10.1000/not-in-pubmed") is None

    @patch.object(PubmedConnector, "_search_ids")
    def test_returns_none_on_request_failure(self, mock_search: MagicMock) -> None:
        """A request failure is swallowed and results in None."""
        connector = PubmedConnector()
        mock_search.side_effect = requests.ConnectionError("boom")

        assert connector._resolve_pmid("10.1000/x") is None


class TestPubmedFetchRelated:
    """Tests for PubmedConnector.fetch_related."""

    def test_returns_empty_for_paper_without_doi(self, make_paper) -> None:
        """Papers without DOI return an empty list without any HTTP call."""
        connector = PubmedConnector()
        paper = make_paper(doi=None)

        assert connector.fetch_related(paper) == []

    @patch.object(PubmedConnector, "_resolve_pmid")
    def test_returns_empty_when_pmid_not_resolvable(
        self, mock_resolve: MagicMock, make_paper
    ) -> None:
        """No resolvable PMID (non-biomedical paper) yields an empty list."""
        connector = PubmedConnector()
        paper = make_paper(doi="10.1000/not-biomedical")
        mock_resolve.return_value = None

        assert connector.fetch_related(paper) == []

    @patch.object(PubmedConnector, "_fetch_details")
    @patch.object(PubmedConnector, "_get")
    @patch.object(PubmedConnector, "_resolve_pmid")
    def test_end_to_end_with_real_elink_response(
        self,
        mock_resolve: MagicMock,
        mock_get: MagicMock,
        mock_details: MagicMock,
        make_paper,
        similar_samples: dict,
        pubmed_efetch_xml: str,
    ) -> None:
        """Real elink response is sorted by score and truncated before efetch."""
        from defusedxml import ElementTree as ET

        connector = PubmedConnector()
        paper = make_paper(doi=_CRISPR_DOI)
        mock_resolve.return_value = "22745249"

        response = MagicMock()
        response.json.return_value = similar_samples[_CRISPR_DOI]["pm_elink_neighbor_score"]
        mock_get.return_value = response

        tree = ET.fromstring(pubmed_efetch_xml)
        articles = tree.findall(".//PubmedArticle")
        mock_details.return_value = articles[:3]

        related = connector.fetch_related(paper, max_papers=3)

        assert len(related) <= 3
        (pmids_arg,) = mock_details.call_args[0]
        assert len(pmids_arg) == 3
        for p in related:
            assert "pubmed" in p.found_in

    @patch.object(PubmedConnector, "_get")
    @patch.object(PubmedConnector, "_resolve_pmid")
    def test_returns_empty_on_elink_failure(
        self, mock_resolve: MagicMock, mock_get: MagicMock, make_paper
    ) -> None:
        """An elink request failure is swallowed and results in an empty list."""
        connector = PubmedConnector()
        paper = make_paper(doi=_CRISPR_DOI)
        mock_resolve.return_value = "22745249"
        mock_get.side_effect = requests.ConnectionError("boom")

        assert connector.fetch_related(paper) == []

    @patch.object(PubmedConnector, "_get")
    @patch.object(PubmedConnector, "_resolve_pmid")
    def test_excludes_seed_pmid_from_scored_candidates(
        self, mock_resolve: MagicMock, mock_get: MagicMock, make_paper
    ) -> None:
        """The seed's own PMID is never included among the candidates."""
        connector = PubmedConnector()
        paper = make_paper(doi=_CRISPR_DOI)
        mock_resolve.return_value = "999"

        response = MagicMock()
        response.json.return_value = {
            "linksets": [
                {
                    "linksetdbs": [
                        {
                            "linkname": "pubmed_pubmed",
                            "links": [
                                {"id": "999", "score": 100},
                                {"id": "111", "score": 50},
                            ],
                        }
                    ]
                }
            ]
        }
        mock_get.return_value = response

        with patch.object(PubmedConnector, "_fetch_details", return_value=[]) as mock_details:
            connector.fetch_related(paper)
            (pmids_arg,) = mock_details.call_args[0]
            assert "999" not in pmids_arg
            assert pmids_arg == ["111"]
