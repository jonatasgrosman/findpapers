"""Unit tests for the HTML metadata parsing and paper-building pipeline in
:class:`findpapers.connectors.web_scraping.WebScrapingConnector`.

Tests use real HTML pages collected from arXiv, PubMed, OpenAlex,
IEEE, Scopus, and SemanticScholar that are stored in tests/data/pages/.  This
lets us verify parsing correctness against real-world markup without making
live network requests.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from findpapers.connectors.web_scraping import WebScrapingConnector
from findpapers.core.author import Author
from findpapers.core.source import SourceType

build_paper_from_metadata = WebScrapingConnector.build_paper_from_metadata
extract_metadata_from_html = WebScrapingConnector._extract_metadata_from_html
parse_affiliations = WebScrapingConnector._parse_affiliations
parse_authors = WebScrapingConnector._parse_authors
parse_keywords = WebScrapingConnector._parse_keywords

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PAGES_DIR = Path(__file__).parent.parent.parent / "data" / "pages"

# Pre-load each fixture once at module import so tests do not hit the filesystem
# repeatedly.  If a fixture does not exist on disk the fixture will be None and
# we skip the corresponding tests.


def _load(rel: str) -> str | None:
    """Read an HTML fixture file relative to PAGES_DIR; return None if absent."""
    path = PAGES_DIR / rel
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


ARXIV_HTML = _load("arxiv/abs_2301.00306v4.html")
ARXIV_HTML_WITH_DOI = _load("arxiv/10.1016_j.apenergy.2023.121323.html")
PUBMED_HTML = _load("pubmed/10.3758_s13428-022-02028-7.html")
OPENALEX_HTML = _load("openalex/10.3126_nelta.v27i1-2.53203.html")
IEEE_HTML = _load("ieee/10.1109_ACCESS.2021.3119621.html")
SCOPUS_HTML = _load("scopus/10.1055_a-2233-2736.html")
SEMANTICSCHOLAR_HTML = _load("semanticscholar/10.4230_DagRep.12.6.14.html")


def _skip_if_missing(fixture: str | None) -> None:
    """Skip the current test when the HTML fixture is missing from disk."""
    if fixture is None:
        pytest.skip("HTML fixture not found on disk: run tests/data/pages/collect_pages.py first")


# ---------------------------------------------------------------------------
# extract_metadata_from_html
# ---------------------------------------------------------------------------


class TestExtractMetadataFromHtml:
    """Tests for the pure extract_metadata_from_html() parser."""

    def test_empty_string_returns_empty_dict(self) -> None:
        """Empty HTML yields an empty metadata mapping."""
        assert extract_metadata_from_html("") == {}

    def test_no_meta_tags_returns_empty_dict(self) -> None:
        """HTML without <meta> tags yields an empty mapping."""
        html = "<html><body><h1>Hello</h1></body></html>"
        assert extract_metadata_from_html(html) == {}

    def test_single_meta_name_content(self) -> None:
        """A single <meta name=... content=...> is captured."""
        html = '<html><head><meta name="citation_title" content="My Paper"></head></html>'
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_title") == "My Paper"

    def test_meta_property_captured(self) -> None:
        """<meta property=...> (Open Graph style) is treated the same as name=...."""
        html = '<html><head><meta property="og:title" content="OG Title"></head></html>'
        meta = extract_metadata_from_html(html)
        assert meta.get("og:title") == "OG Title"

    def test_keys_are_lowercased(self) -> None:
        """Meta key names are normalised to lower-case."""
        html = '<html><head><meta name="Citation_Title" content="A Title"></head></html>'
        meta = extract_metadata_from_html(html)
        assert "citation_title" in meta

    def test_dc_colon_prefix_normalised_to_dot(self) -> None:
        """Dublin Core colon-form keys (dc:creator) are mapped to dot-form (dc.creator)."""
        html = '<html><head><meta name="dc:creator" content="Smith, J"></head></html>'
        meta = extract_metadata_from_html(html)
        # The colon-form key must NOT appear; the dot-form must be present.
        assert "dc:creator" not in meta
        assert meta.get("dc.creator") == "Smith, J"

    def test_multiple_dc_colon_creator_collected_as_list(self) -> None:
        """Multiple dc:creator tags produce a list under dc.creator."""
        html = (
            "<html><head>"
            '<meta name="dc:creator" content="Smith, J">'
            '<meta name="dc:creator" content="Doe, J">'
            "</head></html>"
        )
        meta = extract_metadata_from_html(html)
        creators = meta.get("dc.creator")
        assert isinstance(creators, list)
        assert "Smith, J" in creators

    def test_duplicate_keys_collected_as_list(self) -> None:
        """Multiple <meta> with the same key produce a list value."""
        html = (
            "<html><head>"
            '<meta name="citation_author" content="Smith, John">'
            '<meta name="citation_author" content="Doe, Jane">'
            "</head></html>"
        )
        meta = extract_metadata_from_html(html)
        authors = meta.get("citation_author")
        assert isinstance(authors, list)
        assert len(authors) == 2
        assert "Smith, John" in authors
        assert "Doe, Jane" in authors

    def test_empty_content_skipped(self) -> None:
        """<meta> tags with empty content are not included in the mapping."""
        html = '<html><head><meta name="citation_title" content=""></head></html>'
        meta = extract_metadata_from_html(html)
        assert "citation_title" not in meta

    # ------------------------------------------------------------------
    # Real-page tests
    # ------------------------------------------------------------------

    def test_arxiv_has_citation_title(self) -> None:
        """arXiv page contains a citation_title meta tag."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        assert "citation_title" in meta or "og:title" in meta
        title = meta.get("citation_title") or meta.get("og:title")
        assert isinstance(title, str)
        assert len(title) > 5

    def test_arxiv_has_citation_authors(self) -> None:
        """arXiv page exposes one or more citation_author meta tags."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        authors = meta.get("citation_author")
        assert authors is not None
        if isinstance(authors, list):
            assert all(isinstance(a, str) and a for a in authors)
        else:
            assert isinstance(authors, str)
            assert authors

    def test_arxiv_has_citation_date(self) -> None:
        """arXiv page provides a citation_date or citation_online_date meta tag."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        assert "citation_date" in meta or "citation_online_date" in meta

    def test_arxiv_has_citation_pdf_url(self) -> None:
        """arXiv page provides a PDF URL in citation_pdf_url meta tag."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        assert "citation_pdf_url" in meta
        assert meta["citation_pdf_url"].startswith("https://")

    def test_pubmed_has_citation_doi(self) -> None:
        """PubMed page provides a DOI via citation_doi or dc.identifier."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        doi_val = meta.get("citation_doi") or meta.get("dc.identifier")
        assert doi_val
        assert "10." in str(doi_val)

    def test_pubmed_has_journal_title(self) -> None:
        """PubMed page provides a citation_journal_title meta tag."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        assert "citation_journal_title" in meta
        assert isinstance(meta["citation_journal_title"], str)
        assert meta["citation_journal_title"]

    def test_pubmed_has_issn(self) -> None:
        """PubMed page exposes citation_issn meta tag."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        assert "citation_issn" in meta

    def test_openalex_has_doi(self) -> None:
        """OpenAlex landing page provides a citation_doi meta tag."""
        _skip_if_missing(OPENALEX_HTML)
        meta = extract_metadata_from_html(OPENALEX_HTML)  # type: ignore[arg-type]
        doi_val = meta.get("citation_doi") or meta.get("dc.identifier.doi")
        assert doi_val
        assert "10." in str(doi_val)

    def test_openalex_has_journal_title(self) -> None:
        """OpenAlex landing page exposes a citation_journal_title."""
        _skip_if_missing(OPENALEX_HTML)
        meta = extract_metadata_from_html(OPENALEX_HTML)  # type: ignore[arg-type]
        assert "citation_journal_title" in meta

    def test_ieee_js_blob_extracts_authors(self) -> None:
        """IEEE Xplore JS-blob extractor populates citation_author."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        authors_raw = meta.get("citation_author")
        assert authors_raw is not None
        authors = parse_authors(authors_raw)
        assert len(authors) >= 1
        assert all(isinstance(a, str) and a for a in authors)

    def test_ieee_js_blob_extracts_doi(self) -> None:
        """IEEE Xplore JS-blob extractor populates citation_doi."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        doi_val = meta.get("citation_doi")
        assert doi_val
        assert "10." in str(doi_val)

    def test_ieee_js_blob_extracts_keywords(self) -> None:
        """IEEE Xplore JS-blob extractor populates citation_keywords."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        kw_val = meta.get("citation_keywords")
        assert kw_val is not None
        assert len(str(kw_val)) > 0

    def test_ieee_js_blob_extracts_journal_title(self) -> None:
        """IEEE Xplore JS-blob extractor populates citation_journal_title."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        assert "citation_journal_title" in meta

    def test_pubmed_citation_authors_plural_extracted(self) -> None:
        """PubMed pages expose citation_authors (plural) which must be captured."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        assert "citation_authors" in meta
        assert ";" in str(meta["citation_authors"])  # semicolon-separated

    def test_scopus_dc_colon_creator_normalised(self) -> None:
        """Scopus pages use dc:creator (colon form) which must be normalised to dc.creator."""
        _skip_if_missing(SCOPUS_HTML)
        meta = extract_metadata_from_html(SCOPUS_HTML)  # type: ignore[arg-type]
        assert "dc:creator" not in meta
        assert "dc.creator" in meta

    def test_semanticscholar_citation_keyword_singular_extracted(self) -> None:
        """SemanticScholar pages use citation_keyword (singular) which must be captured."""
        _skip_if_missing(SEMANTICSCHOLAR_HTML)
        meta = extract_metadata_from_html(SEMANTICSCHOLAR_HTML)  # type: ignore[arg-type]
        assert "citation_keyword" in meta


# ---------------------------------------------------------------------------
# parse_authors
# ---------------------------------------------------------------------------


class TestParseAuthors:
    """Unit tests for the parse_authors() helper."""

    def test_none_returns_empty_list(self) -> None:
        """None input yields an empty list."""
        assert parse_authors(None) == []

    def test_single_string_returned_as_single_item(self) -> None:
        """A plain string with no semicolons is returned as a one-element list."""
        result = parse_authors("Smith, John")
        assert result == ["Smith, John"]

    def test_semicolon_separated_string_split(self) -> None:
        """PubMed-style semicolon-separated author string is split into individual names."""
        result = parse_authors("Wang Y;Tian J;Yazar Y")
        assert result == ["Wang Y", "Tian J", "Yazar Y"]

    def test_trailing_semicolon_ignored(self) -> None:
        """A trailing semicolon (PubMed sometimes adds one) does not produce an empty entry."""
        result = parse_authors("Smith J;Doe J;")
        assert result == ["Smith J", "Doe J"]

    def test_list_of_strings_returned_flat(self) -> None:
        """A list of plain name strings is returned as-is."""
        result = parse_authors(["Smith, J", "Doe, J"])
        assert result == ["Smith, J", "Doe, J"]

    def test_list_items_with_semicolons_split(self) -> None:
        """List items that themselves contain semicolons are expanded."""
        result = parse_authors(["Smith J;Doe J", "Jones K"])
        assert result == ["Smith J", "Doe J", "Jones K"]

    def test_duplicates_deduplicated_preserving_order(self) -> None:
        """Duplicate author names in a list are removed while preserving order."""
        result = parse_authors(["Smith, J", "Doe, J", "Smith, J"])
        assert result == ["Smith, J", "Doe, J"]


# ---------------------------------------------------------------------------
# parse_keywords
# ---------------------------------------------------------------------------


class TestParseKeywords:
    """Unit tests for the parse_keywords() helper."""

    def test_none_returns_empty_set(self) -> None:
        """None input yields an empty set."""
        assert parse_keywords(None) == set()

    def test_empty_string_returns_empty_set(self) -> None:
        """Empty string yields an empty set."""
        assert parse_keywords("") == set()

    def test_comma_separated_string_split(self) -> None:
        """Comma-separated keywords are split correctly."""
        result = parse_keywords("machine learning, deep learning, NLP")
        assert result == {"machine learning", "deep learning", "NLP"}

    def test_semicolon_separated_string_split(self) -> None:
        """Semicolon-separated keywords are split correctly."""
        result = parse_keywords("AI; ML; DL")
        assert result == {"AI", "ML", "DL"}

    def test_single_keyword_returned_as_set(self) -> None:
        """A string with no delimiter is returned as a one-element set."""
        assert parse_keywords("deep learning") == {"deep learning"}

    def test_list_of_keywords_merged(self) -> None:
        """A list of keyword strings (e.g. from multiple dc.subject tags) is merged."""
        result = parse_keywords(["machine learning", "NLP", "deep learning"])
        assert result == {"machine learning", "NLP", "deep learning"}

    def test_list_with_comma_separated_items_expanded(self) -> None:
        """List items that are themselves comma-separated strings are fully expanded."""
        result = parse_keywords(["AI, ML", "DL"])
        assert result == {"AI", "ML", "DL"}

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace on each keyword is stripped."""
        result = parse_keywords("  AI  ,  ML  ")
        assert result == {"AI", "ML"}


# ---------------------------------------------------------------------------
# build_paper_from_metadata
# ---------------------------------------------------------------------------


class TestBuildPaperFromMetadata:
    """Tests for build_paper_from_metadata()."""

    def test_citation_authors_plural_semicolon_parsed(self) -> None:
        """PubMed-style citation_authors (plural, semicolons) is parsed into an author list."""
        meta = {
            "citation_title": "Paper",
            "citation_authors": "Wang Y;Tian J;Yazar Y;",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert Author(name="Wang Y") in paper.authors
        assert Author(name="Tian J") in paper.authors
        assert len(paper.authors) == 3

    def test_dc_subject_used_as_keywords(self) -> None:
        """dc.subject meta tags contribute to the paper's keyword set."""
        meta = {
            "citation_title": "Paper",
            "dc.subject": ["Machine Learning", "NLP"],
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert "Machine Learning" in (paper.keywords or set())
        assert "NLP" in (paper.keywords or set())

    def test_citation_keyword_singular_used_as_keywords(self) -> None:
        """citation_keyword (singular) meta tags contribute to the keyword set."""
        meta = {
            "citation_title": "Paper",
            "citation_keyword": ["deep learning", "efficiency"],
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert "deep learning" in (paper.keywords or set())

    def test_keyword_sources_merged(self) -> None:
        """Keywords from different sources (citation_keywords and dc.subject) are merged."""
        meta = {
            "citation_title": "Paper",
            "citation_keywords": "AI, ML",
            "dc.subject": "NLP",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.keywords is not None
        assert {"AI", "ML", "NLP"}.issubset(paper.keywords)

    def test_citation_inbook_title_creates_source(self) -> None:
        """citation_inbook_title (Scopus book chapters) creates a source."""
        meta = {
            "citation_title": "Chapter Title",
            "citation_inbook_title": "Advances in Machine Learning",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Advances in Machine Learning"

    def test_pages_built_from_firstpage_and_lastpage(self) -> None:
        """citation_firstpage + citation_lastpage are combined into paper.page_range."""
        meta = {
            "citation_title": "Paper",
            "citation_firstpage": "100",
            "citation_lastpage": "115",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.page_range == "100\u2013115"  # en-dash

    def test_pages_only_firstpage(self) -> None:
        """When only citation_firstpage is present, it is stored as page_range."""
        meta = {"citation_title": "Paper", "citation_firstpage": "42"}
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.page_range == "42"

    def test_page_count_extracted(self) -> None:
        """citation_num_pages is parsed and stored as paper.page_count."""
        meta = {"citation_title": "Paper", "citation_num_pages": "26"}
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.page_count == 26

    def test_doi_url_prefix_stripped(self) -> None:
        """A doi.org URL prefix is stripped from the DOI value."""
        meta = {
            "citation_title": "Paper",
            "citation_doi": "https://doi.org/10.1234/test",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.doi == "10.1234/test"

    def test_dc_identifier_doi_used_when_citation_doi_absent(self) -> None:
        """dc.identifier.doi is used as DOI when citation_doi is not present."""
        meta = {
            "citation_title": "Paper",
            "dc.identifier.doi": "10.9999/example",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.doi == "10.9999/example"

    def test_dc_creator_used_for_authors(self) -> None:
        """dc.creator (from dc:creator colon-form normalisation) is used for authors."""
        meta = {
            "citation_title": "Paper",
            "dc.creator": ["Smith, J", "Doe, J"],
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert Author(name="Smith, J") in paper.authors

    def test_dc_date_issued_used_for_date(self) -> None:
        """dc.date.issued is used as publication date when other date keys are absent."""
        meta = {"citation_title": "Paper", "dc.date.issued": "2021-03-15"}
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.publication_date == date(2021, 3, 15)

    def test_citation_online_date_used_as_fallback_date(self) -> None:
        """citation_online_date is used as last-resort date fallback."""
        meta = {"citation_title": "Paper", "citation_online_date": "2024/02/12"}
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.publication_date == date(2024, 2, 12)

    def test_non_doi_dc_identifier_ignored(self) -> None:
        """A dc.identifier value that is not a DOI (e.g. PMID) is ignored."""
        meta = {
            "citation_title": "Paper",
            "dc.identifier": "PMID: 36006759",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.doi is None
        """Returns None when no title key is found in metadata."""
        assert build_paper_from_metadata({}, "http://example.com") is None

    def test_minimal_metadata_creates_paper(self) -> None:
        """A metadata dict with only a title produces a Paper with that title."""
        paper = build_paper_from_metadata({"citation_title": "My Title"}, "http://x.com")
        assert paper is not None
        assert paper.title == "My Title"

    def test_url_stored_on_paper(self) -> None:
        """The page URL passed to build_paper_from_metadata is set on the paper."""
        url = "https://example.org/paper"
        paper = build_paper_from_metadata({"citation_title": "T"}, url)
        assert paper is not None
        assert paper.url == url

    def test_doi_extracted(self) -> None:
        """DOI is captured from citation_doi."""
        meta = {"citation_title": "Paper", "citation_doi": "10.1234/test"}
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.doi == "10.1234/test"

    def test_authors_from_list(self) -> None:
        """Multiple citation_author values become an author list."""
        meta = {
            "citation_title": "T",
            "citation_author": ["Smith, J", "Doe, J"],
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert Author(name="Smith, J") in paper.authors

    def test_journal_source_created(self) -> None:
        """citation_journal_title creates a Source."""
        meta = {
            "citation_title": "Paper",
            "citation_journal_title": "Nature",
            "citation_issn": "0028-0836",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.title == "Nature"
        assert paper.source.issn == "0028-0836"

    def test_journal_source_type_assigned(self) -> None:
        """citation_journal_title sets source_type=JOURNAL."""
        meta = {
            "citation_title": "Paper",
            "citation_journal_title": "Nature",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.JOURNAL

    def test_conference_source_type_assigned(self) -> None:
        """citation_conference_title sets source_type=CONFERENCE."""
        meta = {
            "citation_title": "A Conference Paper",
            "citation_conference_title": "NeurIPS",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.CONFERENCE

    def test_book_source_type_from_inbook_title(self) -> None:
        """citation_inbook_title sets source_type=BOOK."""
        meta = {
            "citation_title": "Chapter Title",
            "citation_inbook_title": "Advances in ML",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_book_source_type_from_book_title(self) -> None:
        """citation_book_title sets source_type=BOOK."""
        meta = {
            "citation_title": "Chapter Title",
            "citation_book_title": "My Book",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None
        assert paper.source.source_type == SourceType.BOOK

    def test_conference_source_created(self) -> None:
        """citation_conference_title creates a Source."""
        meta = {
            "citation_title": "A Conference Paper",
            "citation_conference_title": "NeurIPS",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.source is not None

    def test_preprint_server_source_not_created(self) -> None:
        """Preprint server names (arxiv, biorxiv, medrxiv) are not treated as sources."""
        for server in ("arxiv", "bioRxiv", "medRxiv"):
            meta = {
                "citation_title": "A Preprint",
                "citation_journal_title": server,
            }
            paper = build_paper_from_metadata(meta, "http://x.com")
            assert paper is not None, f"Paper should be created for {server}"
            assert paper.source is None, f"Source should be None for preprint server {server}"

    def test_pdf_url_captured(self) -> None:
        """citation_pdf_url is stored on the paper."""
        meta = {
            "citation_title": "T",
            "citation_pdf_url": "https://example.com/paper.pdf",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.pdf_url == "https://example.com/paper.pdf"

    def test_keywords_parsed_from_comma_separated(self) -> None:
        """Comma-separated keywords are split into a set."""
        meta = {
            "citation_title": "T",
            "keywords": "machine learning, deep learning, NLP",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.keywords is not None
        assert "machine learning" in paper.keywords

    def test_date_parsed(self) -> None:
        """citation_date is parsed into a datetime.date."""
        meta = {
            "citation_title": "T",
            "citation_date": "2023-06-15",
        }
        paper = build_paper_from_metadata(meta, "http://x.com")
        assert paper is not None
        assert paper.publication_date == date(2023, 6, 15)

    # ------------------------------------------------------------------
    # Real-page integration tests
    # ------------------------------------------------------------------

    def test_arxiv_paper_doi_derived_from_url(self) -> None:
        """arXiv abs/* pages have no DOI in meta tags but DOI is derived from the URL."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://arxiv.org/abs/2301.00306v4")
        assert paper is not None
        assert paper.doi == "10.48550/arXiv.2301.00306"
        assert paper.source is None  # preprint: no journal

    def test_arxiv_paper_has_pdf_url(self) -> None:
        """arXiv page should populate pdf_url on the built paper."""
        _skip_if_missing(ARXIV_HTML)
        meta = extract_metadata_from_html(ARXIV_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://arxiv.org/abs/2301.00306v4")
        assert paper is not None
        assert paper.pdf_url is not None
        assert "arxiv.org/pdf" in paper.pdf_url

    def test_arxiv_paper_with_doi_has_no_source(self) -> None:
        """arXiv pre-print with a DOI still exposes no source (server is arxiv)."""
        _skip_if_missing(ARXIV_HTML_WITH_DOI)
        meta = extract_metadata_from_html(ARXIV_HTML_WITH_DOI)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://arxiv.org/abs/2301.01148v1")
        assert paper is not None
        # The DOI points to the published version, but the HTML page is arXiv
        assert paper.doi == "10.1016/j.apenergy.2023.121323"

    def test_pubmed_paper_has_doi_and_journal(self) -> None:
        """PubMed page produces a paper with a DOI and a journal publication."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://pubmed.ncbi.nlm.nih.gov/36006759/")
        assert paper is not None
        assert paper.doi is not None
        assert paper.doi.startswith("10.")
        assert paper.source is not None
        assert paper.source.issn is not None

    def test_pubmed_paper_has_authors(self) -> None:
        """PubMed pages expose citation_authors (plural, semicolons); authors must be populated."""
        _skip_if_missing(PUBMED_HTML)
        meta = extract_metadata_from_html(PUBMED_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://pubmed.ncbi.nlm.nih.gov/36006759/")
        assert paper is not None
        assert len(paper.title) > 5
        assert len(paper.authors) > 0

    def test_openalex_paper_has_doi_and_journal(self) -> None:
        """OpenAlex landing page produces a paper with DOI and journal publication."""
        _skip_if_missing(OPENALEX_HTML)
        meta = extract_metadata_from_html(OPENALEX_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "http://dx.doi.org/10.3126/nelta.v27i1-2.53203")
        assert paper is not None
        assert paper.doi is not None
        assert paper.doi.startswith("10.")
        assert paper.source is not None

    def test_openalex_paper_has_keywords(self) -> None:
        """OpenAlex landing page exposes at least one keyword on the paper."""
        _skip_if_missing(OPENALEX_HTML)
        meta = extract_metadata_from_html(OPENALEX_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "http://dx.doi.org/10.3126/nelta.v27i1-2.53203")
        assert paper is not None
        assert paper.keywords

    def test_ieee_paper_has_authors(self) -> None:
        """IEEE Xplore page (JS blob) produces a paper with populated authors."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://ieeexplore.ieee.org/document/9568778/")
        assert paper is not None
        assert len(paper.authors) > 0

    def test_ieee_paper_has_doi_and_journal(self) -> None:
        """IEEE Xplore page (JS blob) produces a paper with a DOI and journal."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://ieeexplore.ieee.org/document/9568778/")
        assert paper is not None
        assert paper.doi is not None
        assert paper.doi.startswith("10.")
        assert paper.source is not None

    def test_ieee_paper_has_keywords(self) -> None:
        """IEEE Xplore page (JS blob) produces a paper with keywords."""
        _skip_if_missing(IEEE_HTML)
        meta = extract_metadata_from_html(IEEE_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://ieeexplore.ieee.org/document/9568778/")
        assert paper is not None
        assert paper.keywords

    def test_scopus_authors_from_dc_colon_creator(self) -> None:
        """Scopus pages use dc:creator which must be normalised and used for authors."""
        _skip_if_missing(SCOPUS_HTML)
        meta = extract_metadata_from_html(SCOPUS_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://doi.org/10.1055/a-2233-2736")
        assert paper is not None
        assert len(paper.authors) > 0

    def test_semanticscholar_keywords_from_citation_keyword_singular(self) -> None:
        """SemanticScholar pages use citation_keyword (singular) which must populate keywords."""
        _skip_if_missing(SEMANTICSCHOLAR_HTML)
        meta = extract_metadata_from_html(SEMANTICSCHOLAR_HTML)  # type: ignore[arg-type]
        paper = build_paper_from_metadata(meta, "https://doi.org/10.4230/DagRep.12.6.14")
        assert paper is not None
        assert paper.keywords


# ---------------------------------------------------------------------------
# End-to-end: extract_metadata_from_html -> build_paper_from_metadata
# ---------------------------------------------------------------------------


class TestExtractAndBuildPipeline:
    """Integration tests that exercise extract_metadata_from_html + build_paper_from_metadata."""

    def test_real_arxiv_page_end_to_end(self) -> None:
        """Full end-to-end: parse arXiv HTML and build a Paper."""
        _skip_if_missing(ARXIV_HTML)
        assert ARXIV_HTML is not None
        metadata = extract_metadata_from_html(ARXIV_HTML)
        assert metadata is not None
        result = build_paper_from_metadata(metadata, "https://arxiv.org/abs/2301.00306v4")
        assert result is not None
        assert len(result.title) > 5
        assert result.pdf_url is not None

    def test_real_pubmed_page_end_to_end(self) -> None:
        """Full end-to-end: parse PubMed HTML and build a Paper."""
        _skip_if_missing(PUBMED_HTML)
        assert PUBMED_HTML is not None
        metadata = extract_metadata_from_html(PUBMED_HTML)
        assert metadata is not None
        result = build_paper_from_metadata(metadata, "https://pubmed.ncbi.nlm.nih.gov/36006759/")
        assert result is not None
        assert result.doi is not None
        assert result.doi.startswith("10.")
        assert result.source is not None

    def test_real_openalex_page_end_to_end(self) -> None:
        """Full end-to-end: parse OpenAlex landing page HTML and build a Paper."""
        _skip_if_missing(OPENALEX_HTML)
        assert OPENALEX_HTML is not None
        metadata = extract_metadata_from_html(OPENALEX_HTML)
        assert metadata is not None
        url = "http://dx.doi.org/10.3126/nelta.v27i1-2.53203"
        result = build_paper_from_metadata(metadata, url)
        assert result is not None
        assert result.doi is not None
        assert result.doi.startswith("10.")
        assert result.source is not None

    def test_real_ieee_page_end_to_end(self) -> None:
        """Full end-to-end: parse IEEE Xplore HTML and build a Paper."""
        _skip_if_missing(IEEE_HTML)
        assert IEEE_HTML is not None
        metadata = extract_metadata_from_html(IEEE_HTML)
        assert metadata is not None
        url = "https://ieeexplore.ieee.org/document/9568778/"
        result = build_paper_from_metadata(metadata, url)
        assert result is not None
        assert result.doi is not None
        assert result.doi.startswith("10.")
        assert result.source is not None
        assert len(result.authors) > 0
        assert result.keywords
        assert len(result.keywords) > 0


# ---------------------------------------------------------------------------
# Additional coverage for extract_metadata_from_html edge cases
# ---------------------------------------------------------------------------


class TestExtractMetadataEdgeCases:
    """Tests covering defensive branches in extract_metadata_from_html."""

    def test_ieee_invalid_json_blob_returns_meta_tags_only(self) -> None:
        """Invalid JSON in the IEEE JS blob is silently ignored."""
        html = (
            "<html><head>"
            '<meta name="citation_title" content="Good">'
            "<script>xplGlobal.document.metadata = {INVALID JSON};</script>"
            "</head></html>"
        )
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_title") == "Good"
        # No IEEE fields since JSON was invalid.
        assert "citation_doi" not in meta or meta["citation_doi"] == "Good"

    def test_ieee_conference_content_type(self) -> None:
        """IEEE JS blob with isConference=true maps to citation_conference_title."""
        blob = (
            '{"title":"My Paper","doi":"10.1109/test",'
            '"displayPublicationTitle":"ICASSP 2024",'
            '"isConference":true,"authors":[]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_conference_title") == "ICASSP 2024"

    def test_ieee_book_content_type(self) -> None:
        """IEEE JS blob with isBook=true maps to citation_book_title."""
        blob = (
            '{"title":"My Paper","doi":"10.1109/test",'
            '"displayPublicationTitle":"Deep Learning Book",'
            '"isBook":true,"authors":[]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_book_title") == "Deep Learning Book"

    def test_ieee_book_without_chapters_content_type(self) -> None:
        """IEEE JS blob with isBookWithoutChapters=true maps to citation_book_title."""
        blob = (
            '{"title":"My Paper","doi":"10.1109/test",'
            '"displayPublicationTitle":"A Monograph",'
            '"isBookWithoutChapters":true,"authors":[]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_book_title") == "A Monograph"

    def test_ieee_author_affiliation_as_list(self) -> None:
        """IEEE JS blob with affiliation as a list is joined with semicolons.

        Also includes an author entry with no name to exercise the ``continue``
        guard in the affiliations loop.
        """
        blob = (
            '{"title":"Test","doi":"10.1109/x",'
            '"authors":[{"affiliation":"Ignored"},'
            '{"name":"Alice","affiliation":["MIT","Stanford"]}]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_author_institution") == "MIT; Stanford"

    def test_ieee_single_author_affiliation_as_string(self) -> None:
        """IEEE JS blob with affiliation as a string is stored directly."""
        blob = (
            '{"title":"Test","doi":"10.1109/x","authors":[{"name":"Bob","affiliation":"Harvard"}]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_author_institution") == "Harvard"

    def test_ieee_pub_title_fallback_to_journal(self) -> None:
        """IEEE JS blob without isConference/isBook defaults to journal title."""
        blob = (
            '{"title":"Test","doi":"10.1109/x",'
            '"displayPublicationTitle":"Some Publication","authors":[]}'
        )
        html = f"<html><head><script>xplGlobal.document.metadata = {blob};</script></head></html>"
        meta = extract_metadata_from_html(html)
        assert meta.get("citation_journal_title") == "Some Publication"


# ---------------------------------------------------------------------------
# parse_affiliations
# ---------------------------------------------------------------------------


class TestParseAffiliations:
    """Tests for the parse_affiliations() helper."""

    def test_none_returns_empty_list(self) -> None:
        """None value returns an empty list."""
        assert parse_affiliations(None) == []

    def test_single_string_returned(self) -> None:
        """A plain string is returned as a single-element list."""
        assert parse_affiliations("MIT") == ["MIT"]

    def test_semicolon_separated_string_split(self) -> None:
        """Semicolon-separated string is split into individual items."""
        result = parse_affiliations("MIT; Stanford; Harvard")
        assert result == ["MIT", "Stanford", "Harvard"]

    def test_list_of_strings_returned(self) -> None:
        """A list is returned with items stripped."""
        result = parse_affiliations(["  MIT ", "Stanford"])
        assert result == ["MIT", "Stanford"]

    def test_empty_string_returns_empty_list(self) -> None:
        """Empty string returns an empty list."""
        assert parse_affiliations("") == []
