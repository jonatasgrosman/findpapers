"""Unit tests for save utilities."""

from __future__ import annotations

import datetime
import json
import tempfile
from pathlib import Path

import pytest

from findpapers.core.author import Author
from findpapers.core.paper import Paper, PaperType
from findpapers.core.search_result import SearchResult
from findpapers.core.source import Source, SourceType
from findpapers.exceptions import PersistenceError
from findpapers.utils.persistence import (
    _escape_bibtex,
    _extract_papers,
    _normalize_whitespace,
    _sanitize_csv_value,
    _serialize_to_dict,
    _unescape_bibtex,
    _unsanitize_csv_value,
    bibtex_how_published,
    bibtex_note,
    citation_key_for,
    load_from_bibtex,
    load_from_csv,
    load_from_json,
    paper_to_bibtex,
    save_to_bibtex,
    save_to_csv,
    save_to_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def journal_publication() -> Source:
    """Return a journal publication."""
    return Source(
        title="Nature Machine Intelligence",
        issn="2522-5839",
        publisher="Springer Nature",
    )


@pytest.fixture
def conference_publication() -> Source:
    """Return a conference proceedings publication."""
    return Source(
        title="NeurIPS 2023",
        isbn="978-0-000-00000-0",
        publisher="Curran Associates",
    )


@pytest.fixture
def minimal_paper() -> Paper:
    """Return a paper with the minimum required fields."""
    return Paper(
        title="Minimal Paper",
        abstract="An abstract.",
        authors=[Author(name="Alice, A.")],
        source=None,
        publication_date=None,
    )


@pytest.fixture
def full_paper(journal_publication: Source) -> Paper:
    """Return a paper with all fields populated."""
    return Paper(
        title="Deep Learning Survey",
        abstract="A survey on deep learning techniques.",
        authors=[Author(name="LeCun, Y."), Author(name="Bengio, Y."), Author(name="Hinton, G.")],
        source=journal_publication,
        publication_date=datetime.date(2022, 6, 15),
        url="https://example.com/paper",
        pdf_url="https://example.com/paper.pdf",
        doi="10.1234/example.doi",
        citations=500,
        keywords={"neural networks", "deep learning", "AI"},
        comments="Highly cited review.",
        page_count=42,
        page_range="1-42",
        found_in={"arxiv", "semantic_scholar"},
        funders={"NIH", "NSF"},
    )


@pytest.fixture
def conference_paper(conference_publication: Source) -> Paper:
    """Return a paper in a conference proceedings."""
    return Paper(
        title="Attention is All You Need",
        abstract="Transformers intro.",
        authors=[Author(name="Vaswani, A.")],
        source=conference_publication,
        publication_date=datetime.date(2017, 12, 1),
        url="https://arxiv.org/abs/1706.03762",
        doi="10.48550/arXiv.1706.03762",
        found_in={"arxiv"},
    )


@pytest.fixture
def sample_search(full_paper: Paper, minimal_paper: Paper) -> SearchResult:
    """Return a SearchResult with two papers."""
    search = SearchResult(query="[deep learning]", databases=["arxiv"])
    search.add_paper(full_paper)
    search.add_paper(minimal_paper)
    return search


# ---------------------------------------------------------------------------
# _extract_papers
# ---------------------------------------------------------------------------


class TestExtractPapers:
    """Tests for _extract_papers()."""

    def test_from_list(self, full_paper: Paper, minimal_paper: Paper) -> None:
        """Extracts papers from a plain list."""
        papers = [full_paper, minimal_paper]
        assert _extract_papers(papers) is papers

    def test_from_search_result(self, sample_search: SearchResult) -> None:
        """Extracts papers from a SearchResult."""
        papers = _extract_papers(sample_search)
        assert len(papers) == 2

    def test_raises_for_unsupported_type(self) -> None:
        """Raises PersistenceError for unsupported input."""
        with pytest.raises(PersistenceError, match="Expected"):
            _extract_papers("not a valid input")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _serialize_to_dict
# ---------------------------------------------------------------------------


class TestSerializeToDict:
    """Tests for _serialize_to_dict()."""

    def test_search_result_has_type(self, sample_search: SearchResult) -> None:
        """SearchResult serialization includes type discriminator."""
        result = _serialize_to_dict(sample_search)
        assert result["type"] == "search_result"
        assert "papers" in result

    def test_paper_list_has_type(self, full_paper: Paper) -> None:
        """Paper list serialization includes type discriminator."""
        result = _serialize_to_dict([full_paper])
        assert result["type"] == "paper_list"
        assert len(result["papers"]) == 1

    def test_raises_for_unsupported_type(self) -> None:
        """Raises PersistenceError for unsupported input."""
        with pytest.raises(PersistenceError, match="Expected"):
            _serialize_to_dict("not valid")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# citation_key_for
# ---------------------------------------------------------------------------


class TestCitationKeyFor:
    """Tests for citation_key_for()."""

    def test_basic_key(self, full_paper: Paper) -> None:
        """Key includes first author, year, and first title word."""
        key = citation_key_for(full_paper)
        assert "lecun" in key.lower()
        assert "2022" in key
        assert "deep" in key.lower()

    def test_no_author_fallback(self) -> None:
        """Paper with no authors uses 'unknown' as author part."""
        paper = Paper(
            title="Some Title",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date(2020, 1, 1),
        )
        key = citation_key_for(paper)
        assert "unknown" in key

    def test_no_date_fallback(self) -> None:
        """Paper with no date uses 'XXXX' as year part."""
        paper = Paper(
            title="Some Title",
            abstract="",
            authors=[Author(name="Smith, J.")],
            source=None,
            publication_date=None,
        )
        key = citation_key_for(paper)
        assert "XXXX" in key

    def test_only_alphanumeric(self) -> None:
        """Key contains only alphanumeric characters."""
        paper = Paper(
            title="A-Title: With, Punctuation!",
            abstract="",
            authors=[Author(name="O'Brien, T.")],
            source=None,
            publication_date=datetime.date(2021, 3, 10),
        )
        key = citation_key_for(paper)
        assert key.isalnum()


# ---------------------------------------------------------------------------
# bibtex_note
# ---------------------------------------------------------------------------


class TestBibtexNote:
    """Tests for bibtex_note()."""

    def test_with_all_fields(self, full_paper: Paper) -> None:
        """Note contains URL, date, and comments when all are present."""
        note = bibtex_note(full_paper)
        assert "https://example.com/paper" in note
        assert "2022" in note
        assert "Highly cited review." in note

    def test_without_url(self) -> None:
        """Note omits URL part when paper.url is None."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date(2020, 1, 1),
            url=None,
        )
        note = bibtex_note(paper)
        assert "Available at" not in note

    def test_empty_for_no_content(self) -> None:
        """Note is empty string when URL and date are both absent."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            url=None,
        )
        assert bibtex_note(paper) == ""


# ---------------------------------------------------------------------------
# bibtex_how_published
# ---------------------------------------------------------------------------


class TestBibtexHowPublished:
    """Tests for bibtex_how_published()."""

    def test_with_url_and_date(self) -> None:
        """howPublished contains URL and formatted date."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date(2023, 5, 20),
            url="https://example.org",
        )
        result = bibtex_how_published(paper)
        assert "https://example.org" in result
        assert "2023/05/20" in result

    def test_returns_empty_without_url(self) -> None:
        """Returns empty string when URL is missing."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date(2023, 1, 1),
            url=None,
        )
        assert bibtex_how_published(paper) == ""

    def test_returns_empty_without_date(self) -> None:
        """Returns empty string when date is missing."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            url="https://example.org",
        )
        assert bibtex_how_published(paper) == ""


# ---------------------------------------------------------------------------
# _escape_bibtex
# ---------------------------------------------------------------------------


class TestEscapeBibtex:
    """Tests for _escape_bibtex()."""

    def test_plain_text_unchanged(self) -> None:
        """Text without special characters passes through unchanged."""
        assert _escape_bibtex("Hello World 123") == "Hello World 123"

    def test_ampersand_escaped(self) -> None:
        """Ampersand is escaped to \\&."""
        assert _escape_bibtex("A & B") == r"A \& B"

    def test_percent_escaped(self) -> None:
        """Percent sign is escaped to \\%."""
        assert _escape_bibtex("100% effective") == r"100\% effective"

    def test_dollar_escaped(self) -> None:
        """Dollar sign is escaped to \\$."""
        assert _escape_bibtex("costs $5") == r"costs \$5"

    def test_hash_escaped(self) -> None:
        """Hash sign is escaped to \\#."""
        assert _escape_bibtex("item #1") == r"item \#1"

    def test_underscore_escaped(self) -> None:
        """Underscore is escaped to \\_."""
        assert _escape_bibtex("my_var") == r"my\_var"

    def test_tilde_escaped(self) -> None:
        """Tilde is escaped to \\textasciitilde{}."""
        assert _escape_bibtex("approx~value") == r"approx\textasciitilde{}value"

    def test_caret_escaped(self) -> None:
        """Caret is escaped to \\textasciicircum{}."""
        assert _escape_bibtex("x^2") == r"x\textasciicircum{}2"

    def test_backslash_escaped(self) -> None:
        """Backslash is escaped to \\textbackslash{}."""
        assert _escape_bibtex("a\\b") == r"a\textbackslash{}b"

    def test_multiple_special_characters(self) -> None:
        """Multiple different special chars are all escaped."""
        result = _escape_bibtex("A & B: 100% of $x_i^2")
        assert r"\&" in result
        assert r"\%" in result
        assert r"\$" in result
        assert r"\_" in result
        assert r"\textasciicircum{}" in result

    def test_backslash_escaped_before_others(self) -> None:
        """Backslash is escaped first, so replacements aren't double-escaped."""
        # A literal backslash followed by & should produce \textbackslash{}\&
        result = _escape_bibtex("\\&")
        assert result == r"\textbackslash{}\&"

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _escape_bibtex("") == ""

    def test_newlines_collapsed_to_spaces(self) -> None:
        """Newlines within text are collapsed to single spaces."""
        assert _escape_bibtex("line one\nline two") == "line one line two"

    def test_multiple_newlines_collapsed(self) -> None:
        """Multiple consecutive newlines are collapsed to a single space."""
        assert _escape_bibtex("a\n\n\nb") == "a b"

    def test_newlines_with_surrounding_whitespace(self) -> None:
        """Whitespace around newlines is also collapsed."""
        assert _escape_bibtex("a  \n  b") == "a b"


# ---------------------------------------------------------------------------
# _normalize_whitespace
# ---------------------------------------------------------------------------


class TestNormalizeWhitespace:
    """Tests for _normalize_whitespace()."""

    def test_no_newlines(self) -> None:
        """Text without newlines passes through unchanged."""
        assert _normalize_whitespace("hello world") == "hello world"

    def test_single_newline(self) -> None:
        """A single newline is replaced with a space."""
        assert _normalize_whitespace("hello\nworld") == "hello world"

    def test_crlf_newline(self) -> None:
        """Windows-style CRLF is also collapsed."""
        assert _normalize_whitespace("hello\r\nworld") == "hello world"

    def test_multiple_newlines(self) -> None:
        """Multiple consecutive newlines collapse to one space."""
        assert _normalize_whitespace("a\n\n\nb") == "a b"

    def test_surrounding_whitespace_collapsed(self) -> None:
        """Whitespace around newlines is included in the collapse."""
        assert _normalize_whitespace("a  \n  b") == "a b"

    def test_leading_trailing_stripped(self) -> None:
        """Leading and trailing newlines are stripped."""
        assert _normalize_whitespace("\nhello\n") == "hello"

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert _normalize_whitespace("") == ""


# ---------------------------------------------------------------------------
# paper_to_bibtex
# ---------------------------------------------------------------------------


class TestPaperToBibtex:
    """Tests for paper_to_bibtex()."""

    def test_article_type_from_journal_source_without_paper_type(self) -> None:
        """Paper with JOURNAL source but no paper_type falls back to @misc."""
        pub = Source(title="Nature", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@misc{")

    def test_inproceedings_type_from_conference_source_without_paper_type(self) -> None:
        """Paper with CONFERENCE source but no paper_type falls back to @misc."""
        pub = Source(title="NeurIPS", source_type=SourceType.CONFERENCE)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@misc{")

    def test_inbook_type_from_book_source_without_paper_type(self) -> None:
        """Paper with BOOK source but no paper_type falls back to @misc."""
        pub = Source(title="Advances", source_type=SourceType.BOOK)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@misc{")

    def test_misc_type_without_source_type(self, full_paper: Paper) -> None:
        """Paper without source_type still produces @misc entry."""
        assert full_paper.source is not None
        full_paper.source.source_type = None
        entry = paper_to_bibtex(full_paper)
        assert entry.startswith("@misc{")

    def test_misc_type_without_source(self, minimal_paper: Paper) -> None:
        """Paper without source produces @misc entry."""
        entry = paper_to_bibtex(minimal_paper)
        assert entry.startswith("@misc{")

    def test_contains_title(self, full_paper: Paper) -> None:
        """Entry contains the paper title."""
        entry = paper_to_bibtex(full_paper)
        assert "Deep Learning Survey" in entry

    def test_contains_authors(self, full_paper: Paper) -> None:
        """Entry contains authors joined with ' and '."""
        entry = paper_to_bibtex(full_paper)
        assert "LeCun, Y. and Bengio, Y. and Hinton, G." in entry

    def test_contains_year(self, full_paper: Paper) -> None:
        """Entry contains the publication year."""
        entry = paper_to_bibtex(full_paper)
        assert "year = {2022}" in entry

    def test_contains_publisher(self, full_paper: Paper) -> None:
        """Entry contains publisher field when available."""
        entry = paper_to_bibtex(full_paper)
        assert "publisher = {Springer Nature}" in entry

    def test_contains_howpublished(self, conference_paper: Paper) -> None:
        """Entry contains howpublished field when URL and date are present."""
        entry = paper_to_bibtex(conference_paper)
        assert "howpublished" in entry

    def test_repository_source_type_falls_back_to_misc(self) -> None:
        """A paper with REPOSITORY source_type falls back to @misc."""
        pub = Source(title="arXiv", source_type=SourceType.REPOSITORY)
        paper = Paper(
            title="W Paper",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@misc{")

    def test_entry_ends_with_closing_brace(self, full_paper: Paper) -> None:
        """BibTeX entry ends with closing brace."""
        entry = paper_to_bibtex(full_paper)
        assert entry.rstrip().endswith("}")

    def test_paper_type_overrides_source_type(self) -> None:
        """paper_type takes precedence over source_type for BibTeX entry type."""
        pub = Source(title="Nature", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.TECHREPORT,
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@techreport{")

    def test_paper_type_article_produces_at_article(self) -> None:
        """Paper with ARTICLE paper_type produces @article entry."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.ARTICLE,
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@article{")

    def test_paper_type_unpublished_produces_at_unpublished(self) -> None:
        """Paper with UNPUBLISHED paper_type produces @unpublished entry."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.UNPUBLISHED,
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@unpublished{")

    def test_unpublished_includes_note_field(self) -> None:
        """@unpublished entry includes a note field built from URL, date, and comments."""
        paper = Paper(
            title="Preprint",
            abstract="",
            authors=[Author(name="Smith, J.")],
            source=None,
            publication_date=datetime.date(2024, 3, 1),
            url="https://arxiv.org/abs/2401.00001",
            comments="Submitted to ICML",
            paper_type=PaperType.UNPUBLISHED,
        )
        entry = paper_to_bibtex(paper)
        assert "note = {" in entry
        assert "arxiv.org" in entry
        assert "2024" in entry
        assert "Submitted to ICML" in entry

    def test_paper_type_none_falls_back_to_misc(self) -> None:
        """Without paper_type, BibTeX type defaults to @misc."""
        pub = Source(title="NeurIPS", source_type=SourceType.CONFERENCE)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert entry.startswith("@misc{")

    def test_article_contains_journal_field(self) -> None:
        """@article entry includes journal field from source title."""
        pub = Source(title="Nature Machine Intelligence", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.ARTICLE,
        )
        entry = paper_to_bibtex(paper)
        assert "journal = {Nature Machine Intelligence}" in entry

    def test_inproceedings_contains_booktitle_field(self) -> None:
        """@inproceedings entry includes booktitle field from source title."""
        pub = Source(title="NeurIPS 2023", source_type=SourceType.CONFERENCE)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.INPROCEEDINGS,
        )
        entry = paper_to_bibtex(paper)
        assert "booktitle = {NeurIPS 2023}" in entry

    def test_incollection_contains_booktitle_field(self) -> None:
        """@incollection entry includes booktitle field from source title."""
        pub = Source(title="Advances in AI", source_type=SourceType.BOOK)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.INCOLLECTION,
        )
        entry = paper_to_bibtex(paper)
        assert "booktitle = {Advances in AI}" in entry

    def test_techreport_contains_institution_field(self) -> None:
        """@techreport entry includes institution field from source publisher."""
        pub = Source(title="Tech Reports", publisher="MIT", source_type=SourceType.OTHER)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.TECHREPORT,
        )
        entry = paper_to_bibtex(paper)
        assert "institution = {MIT}" in entry

    def test_contains_doi_field(self) -> None:
        """Entry includes doi field when paper has DOI."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            doi="10.1234/example.doi",
        )
        entry = paper_to_bibtex(paper)
        assert "doi = {10.1234/example.doi}" in entry

    def test_no_doi_field_when_none(self) -> None:
        """Entry omits doi field when paper has no DOI."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert "doi" not in entry

    def test_contains_abstract_field(self) -> None:
        """Entry includes abstract field when paper has abstract."""
        paper = Paper(
            title="T",
            abstract="A deep survey.",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert "abstract = {A deep survey.}" in entry

    def test_no_abstract_field_when_empty(self) -> None:
        """Entry omits abstract field when abstract is empty."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert "abstract" not in entry

    def test_contains_keywords_field(self) -> None:
        """Entry includes keywords field sorted alphabetically."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            keywords={"deep learning", "AI"},
        )
        entry = paper_to_bibtex(paper)
        assert "keywords = {AI, deep learning}" in entry

    def test_contains_url_field(self) -> None:
        """Entry includes url field when paper has URL."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            url="https://example.com/paper",
        )
        entry = paper_to_bibtex(paper)
        assert "url = {https://example.com/paper}" in entry

    def test_no_journal_when_not_article(self) -> None:
        """Non-article entries do not include journal field."""
        pub = Source(title="NeurIPS 2023", source_type=SourceType.CONFERENCE)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.INPROCEEDINGS,
        )
        entry = paper_to_bibtex(paper)
        assert "journal" not in entry

    def test_no_booktitle_when_article(self) -> None:
        """@article entries do not include booktitle field."""
        pub = Source(title="Nature", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.ARTICLE,
        )
        entry = paper_to_bibtex(paper)
        assert "booktitle" not in entry

    def test_title_special_chars_escaped(self) -> None:
        """Special characters in title are LaTeX-escaped."""
        paper = Paper(
            title="A & B: 100% of $x_i",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert r"A \& B: 100\% of \$x\_i" in entry

    def test_author_special_chars_escaped(self) -> None:
        """Special characters in author names are LaTeX-escaped."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="O'Neil & Co_Lab")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert r"O'Neil \& Co\_Lab" in entry

    def test_abstract_special_chars_escaped(self) -> None:
        """Special characters in abstract are LaTeX-escaped."""
        paper = Paper(
            title="T",
            abstract="We report 50% improvement & $x^2$ gain",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert r"50\% improvement \& \$x\textasciicircum{}2\$ gain" in entry

    def test_journal_special_chars_escaped(self) -> None:
        """Special characters in journal field are LaTeX-escaped."""
        pub = Source(title="Science & Nature", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.ARTICLE,
        )
        entry = paper_to_bibtex(paper)
        assert r"journal = {Science \& Nature}" in entry

    def test_publisher_special_chars_escaped(self) -> None:
        """Special characters in publisher field are LaTeX-escaped."""
        pub = Source(title="J", publisher="Smith & Sons", source_type=SourceType.JOURNAL)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
        )
        entry = paper_to_bibtex(paper)
        assert r"publisher = {Smith \& Sons}" in entry

    def test_keywords_special_chars_escaped(self) -> None:
        """Special characters in keywords are LaTeX-escaped."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            keywords={"C# programming", "100%"},
        )
        entry = paper_to_bibtex(paper)
        assert r"100\%" in entry
        assert r"C\# programming" in entry

    def test_doi_not_escaped(self) -> None:
        """DOI field is not escaped (special chars are part of the identifier)."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            doi="10.1000/test_doi#1",
        )
        entry = paper_to_bibtex(paper)
        assert "doi = {10.1000/test_doi#1}" in entry

    def test_url_not_escaped(self) -> None:
        """URL field is not escaped (special chars are part of the URL)."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
            url="https://example.com/~user/path%20file",
        )
        entry = paper_to_bibtex(paper)
        assert "url = {https://example.com/~user/path%20file}" in entry

    def test_institution_special_chars_escaped(self) -> None:
        """Special characters in institution field are LaTeX-escaped."""
        pub = Source(title="Reports", publisher="AT&T Labs", source_type=SourceType.OTHER)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.TECHREPORT,
        )
        entry = paper_to_bibtex(paper)
        assert r"institution = {AT\&T Labs}" in entry

    def test_booktitle_special_chars_escaped(self) -> None:
        """Special characters in booktitle field are LaTeX-escaped."""
        pub = Source(title="Proc. A&B 2023", source_type=SourceType.CONFERENCE)
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="X, Y.")],
            source=pub,
            publication_date=datetime.date(2021, 1, 1),
            paper_type=PaperType.INPROCEEDINGS,
        )
        entry = paper_to_bibtex(paper)
        assert r"booktitle = {Proc. A\&B 2023}" in entry


# ---------------------------------------------------------------------------
# save_to_json
# ---------------------------------------------------------------------------


class TestSaveToJson:
    """Tests for save_to_json()."""

    def test_creates_file_from_search(self, sample_search: SearchResult) -> None:
        """File is created from a SearchResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.json")
            save_to_json(sample_search, path)
            assert Path(path).exists()

    def test_creates_file_from_paper_list(self, full_paper: Paper) -> None:
        """File is created from a list of papers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.json")
            save_to_json([full_paper], path)
            assert Path(path).exists()

    def test_search_result_valid_json(self, sample_search: SearchResult) -> None:
        """SearchResult save creates valid JSON with type discriminator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.json")
            save_to_json(sample_search, path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            assert data["type"] == "search_result"
            assert len(data["papers"]) == 2

    def test_paper_list_valid_json(self, full_paper: Paper, minimal_paper: Paper) -> None:
        """Paper list save creates valid JSON with type discriminator."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.json")
            save_to_json([full_paper, minimal_paper], path)
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            assert data["type"] == "paper_list"
            assert len(data["papers"]) == 2


# ---------------------------------------------------------------------------
# save_to_bibtex
# ---------------------------------------------------------------------------


class TestSaveToBibtex:
    """Tests for save_to_bibtex()."""

    def test_creates_file_from_paper_list(self, full_paper: Paper) -> None:
        """File is created from a list of papers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([full_paper], path)
            content = Path(path).read_text(encoding="utf-8")
            assert "@" in content

    def test_entry_count(self, sample_search: SearchResult) -> None:
        """Number of '@' entry markers equals the number of papers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex(sample_search.papers, path)
            content = Path(path).read_text(encoding="utf-8")
            entries = [line for line in content.splitlines() if line.startswith("@")]
            assert len(entries) == len(sample_search.papers)

    def test_empty_paper_list(self) -> None:
        """Empty paper list produces an empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([], path)
            content = Path(path).read_text(encoding="utf-8")
            assert content == ""

    def test_abstract_newlines_collapsed(self) -> None:
        """Newlines in abstract are collapsed to spaces in BibTeX output."""
        paper = Paper(
            title="Test",
            abstract="BACKGROUND\nSome text.\n\nMETHODS\nMore text.",
            authors=[Author(name="A, B.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([paper], path)
            content = Path(path).read_text(encoding="utf-8")
            # No literal newlines inside the abstract field value
            for line in content.splitlines():
                if "abstract" in line.lower():
                    assert "\n" not in line.split("{", 1)[1]


# ---------------------------------------------------------------------------
# load_from_bibtex
# ---------------------------------------------------------------------------


class TestLoadFromBibtex:
    """Tests for load_from_bibtex()."""

    def test_round_trip(self, full_paper: Paper) -> None:
        """Papers survive save -> load round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([full_paper], path)
            loaded = load_from_bibtex(path)
            assert len(loaded) == 1
            assert loaded[0].title == full_paper.title

    def test_preserves_authors(self, full_paper: Paper) -> None:
        """Author names are preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([full_paper], path)
            loaded = load_from_bibtex(path)
            original_names = [a.name for a in full_paper.authors]
            loaded_names = [a.name for a in loaded[0].authors]
            assert loaded_names == original_names

    def test_preserves_doi(self, full_paper: Paper) -> None:
        """DOI is preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([full_paper], path)
            loaded = load_from_bibtex(path)
            assert loaded[0].doi == full_paper.doi

    def test_preserves_year(self, full_paper: Paper) -> None:
        """Publication year is preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([full_paper], path)
            loaded = load_from_bibtex(path)
            assert loaded[0].publication_date is not None
            assert full_paper.publication_date is not None
            assert loaded[0].publication_date.year == full_paper.publication_date.year

    def test_preserves_paper_type(self) -> None:
        """Paper type is preserved across the round-trip."""
        paper = Paper(
            title="Test Article",
            abstract="",
            authors=[Author("Smith, John")],
            source=None,
            publication_date=datetime.date(2023, 6, 15),
            paper_type=PaperType.ARTICLE,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.bib")
            save_to_bibtex([paper], path)
            loaded = load_from_bibtex(path)
            assert loaded[0].paper_type == PaperType.ARTICLE

    def test_empty_file(self) -> None:
        """Loading an empty file returns an empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "empty.bib")
            Path(path).write_text("", encoding="utf-8")
            loaded = load_from_bibtex(path)
            assert loaded == []

    def test_unescape_special_characters(self) -> None:
        """Special LaTeX characters are unescaped during load."""
        bib_content = (
            "@article{test2023foo,\n"
            "    title = {Deep Learning \\& Neural Networks},\n"
            "    author = {Smith, John},\n"
            "    year = {2023},\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "special.bib")
            Path(path).write_text(bib_content, encoding="utf-8")
            loaded = load_from_bibtex(path)
            assert len(loaded) == 1
            assert loaded[0].title == "Deep Learning & Neural Networks"

    def test_multiple_entries(self) -> None:
        """Multiple BibTeX entries produce multiple papers."""
        bib_content = (
            "@article{a2020x,\n    title = {Paper One},\n    year = {2020},\n}\n\n"
            "@inproceedings{b2021y,\n    title = {Paper Two},\n    year = {2021},\n}\n"
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "multi.bib")
            Path(path).write_text(bib_content, encoding="utf-8")
            loaded = load_from_bibtex(path)
            assert len(loaded) == 2
            assert loaded[0].title == "Paper One"
            assert loaded[1].title == "Paper Two"

    def test_skips_entries_without_title(self) -> None:
        """Entries without a title field are skipped."""
        bib_content = "@misc{nokey,\n    author = {Test},\n    year = {2020},\n}\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "notitle.bib")
            Path(path).write_text(bib_content, encoding="utf-8")
            loaded = load_from_bibtex(path)
            assert loaded == []

    def test_file_not_found(self) -> None:
        """FileNotFoundError is raised for non-existent paths."""
        with pytest.raises(FileNotFoundError):
            load_from_bibtex("/tmp/nonexistent_bibtex_file.bib")


# ---------------------------------------------------------------------------
# _unescape_bibtex
# ---------------------------------------------------------------------------


class TestUnescapeBibtex:
    """Tests for _unescape_bibtex()."""

    def test_unescape_ampersand(self) -> None:
        """LaTeX ampersand is unescaped."""
        assert _unescape_bibtex(r"\&") == "&"

    def test_unescape_percent(self) -> None:
        """LaTeX percent is unescaped."""
        assert _unescape_bibtex(r"\%") == "%"

    def test_unescape_underscore(self) -> None:
        """LaTeX underscore is unescaped."""
        assert _unescape_bibtex(r"\_") == "_"

    def test_unescape_backslash(self) -> None:
        r"""LaTeX backslash command is unescaped."""
        assert _unescape_bibtex(r"\textbackslash{}") == "\\"

    def test_round_trip_with_escape(self) -> None:
        """Escaping then unescaping returns the original text."""
        original = "R&D costs: 100% of $budget #1 for A_B"
        assert _unescape_bibtex(_escape_bibtex(original)) == original

    def test_empty_string(self) -> None:
        """Empty string is returned unchanged."""
        assert _unescape_bibtex("") == ""


# ---------------------------------------------------------------------------
# load_from_json
# ---------------------------------------------------------------------------


class TestLoadFromJson:
    """Tests for load_from_json()."""

    def test_round_trip_search_result(self, sample_search: SearchResult) -> None:
        """SearchResult survives save -> load round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "search.json")
            save_to_json(sample_search, path)
            loaded = load_from_json(path)

        assert isinstance(loaded, SearchResult)
        assert len(loaded.papers) == 2
        assert loaded.query == "[deep learning]"

    def test_round_trip_paper_list(self, full_paper: Paper, minimal_paper: Paper) -> None:
        """Paper list survives save -> load round-trip."""
        papers = [full_paper, minimal_paper]
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "papers.json")
            save_to_json(papers, path)
            loaded = load_from_json(path)

        assert isinstance(loaded, list)
        assert len(loaded) == 2
        assert loaded[0].title == full_paper.title

    def test_legacy_search_result_auto_detection(self, sample_search: SearchResult) -> None:
        """Files without 'type' but with 'papers' are loaded as SearchResult."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "legacy.json")
            # Write a payload without "type" key.
            payload = sample_search.to_dict()
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh)

            loaded = load_from_json(path)

        assert isinstance(loaded, SearchResult)
        assert len(loaded.papers) == 2

    def test_unrecognised_format_raises(self) -> None:
        """Files with unrecognised structure cause PersistenceError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "bad.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"foo": "bar"}, fh)

            with pytest.raises(PersistenceError, match="Unrecognised"):
                load_from_json(path)


# ---------------------------------------------------------------------------
# save_to_csv
# ---------------------------------------------------------------------------


class TestSaveToCsv:
    """Tests for save_to_csv()."""

    def test_creates_file(self, full_paper: Paper) -> None:
        """CSV file is created from a list of papers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            assert Path(path).exists()
            content = Path(path).read_text(encoding="utf-8")
            assert "title" in content
            assert full_paper.title in content

    def test_row_count(self, sample_search: SearchResult) -> None:
        """Number of data rows equals the number of papers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv(sample_search.papers, path)
            lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
            # header + one row per paper
            assert len(lines) == len(sample_search.papers) + 1

    def test_empty_list(self) -> None:
        """Empty paper list produces a CSV with only the header."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([], path)
            lines = Path(path).read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1  # header only

    def test_authors_semicolon_separated(self, full_paper: Paper) -> None:
        """Multiple authors are joined with '; '."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            content = Path(path).read_text(encoding="utf-8")
            assert "LeCun, Y.; Bengio, Y.; Hinton, G." in content

    def test_keywords_semicolon_separated(self, full_paper: Paper) -> None:
        """Keywords are joined with '; ' and sorted."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            content = Path(path).read_text(encoding="utf-8")
            assert "AI; deep learning; neural networks" in content


# ---------------------------------------------------------------------------
# load_from_csv
# ---------------------------------------------------------------------------


class TestLoadFromCsv:
    """Tests for load_from_csv()."""

    def test_round_trip(self, full_paper: Paper) -> None:
        """Papers survive save -> load round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert len(loaded) == 1
            assert loaded[0].title == full_paper.title

    def test_preserves_authors(self, full_paper: Paper) -> None:
        """Author names are preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            original_names = [a.name for a in full_paper.authors]
            loaded_names = [a.name for a in loaded[0].authors]
            assert loaded_names == original_names

    def test_preserves_doi(self, full_paper: Paper) -> None:
        """DOI is preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].doi == full_paper.doi

    def test_preserves_publication_date(self, full_paper: Paper) -> None:
        """Publication date is preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].publication_date == full_paper.publication_date

    def test_preserves_paper_type(self) -> None:
        """Paper type is preserved across the round-trip."""
        paper = Paper(
            title="Test Article",
            abstract="",
            authors=[Author("Smith, John")],
            source=None,
            publication_date=datetime.date(2023, 6, 15),
            paper_type=PaperType.ARTICLE,
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].paper_type == PaperType.ARTICLE

    def test_preserves_keywords(self, full_paper: Paper) -> None:
        """Keywords are preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].keywords == full_paper.keywords

    def test_preserves_citations(self, full_paper: Paper) -> None:
        """Citations count is preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].citations == full_paper.citations

    def test_preserves_source(self, full_paper: Paper) -> None:
        """Source title and publisher are preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].source is not None
            assert full_paper.source is not None
            assert loaded[0].source.title == full_paper.source.title
            assert loaded[0].source.publisher == full_paper.source.publisher

    def test_preserves_databases(self, full_paper: Paper) -> None:
        """Databases are preserved across the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].found_in == full_paper.found_in

    def test_multiple_papers(self, sample_search: SearchResult) -> None:
        """Multiple papers survive the round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv(sample_search.papers, path)
            loaded = load_from_csv(path)
            assert len(loaded) == len(sample_search.papers)

    def test_empty_file_returns_empty_list(self) -> None:
        """A CSV with only a header produces an empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "empty.csv")
            save_to_csv([], path)
            loaded = load_from_csv(path)
            assert loaded == []

    def test_skips_rows_without_title(self) -> None:
        """Rows without a title are skipped."""
        csv_content = "title,authors,abstract\n,John,Some abstract\n"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "notitle.csv")
            Path(path).write_text(csv_content, encoding="utf-8")
            loaded = load_from_csv(path)
            assert loaded == []

    def test_file_not_found(self) -> None:
        """FileNotFoundError is raised for non-existent paths."""
        with pytest.raises(FileNotFoundError):
            load_from_csv("/tmp/nonexistent_csv_file.csv")

    def test_preserves_funders(self, full_paper: Paper) -> None:
        """Funders are preserved across the CSV save->load round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([full_paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].funders == full_paper.funders

    def test_preserves_language(self) -> None:
        """Language is preserved across the CSV save->load round-trip."""
        paper = Paper(
            title="Test",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="pt",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].language == "pt"

    def test_preserves_is_open_access(self) -> None:
        """is_open_access is preserved across the CSV save->load round-trip."""
        for value in (True, False, None):
            paper = Paper(
                title="Test",
                abstract="",
                authors=[],
                source=None,
                publication_date=None,
                is_open_access=value,
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                path = str(Path(tmpdir) / "out.csv")
                save_to_csv([paper], path)
                loaded = load_from_csv(path)
                assert loaded[0].is_open_access == value

    def test_preserves_is_retracted(self) -> None:
        """is_retracted is preserved across the CSV save->load round-trip."""
        for value in (True, False, None):
            paper = Paper(
                title="Test",
                abstract="",
                authors=[],
                source=None,
                publication_date=None,
                is_retracted=value,
            )
            with tempfile.TemporaryDirectory() as tmpdir:
                path = str(Path(tmpdir) / "out.csv")
                save_to_csv([paper], path)
                loaded = load_from_csv(path)
                assert loaded[0].is_retracted == value


# ---------------------------------------------------------------------------
# CSV formula injection sanitization
# ---------------------------------------------------------------------------


class TestSanitizeCsvValue:
    """Tests for _sanitize_csv_value()."""

    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
    def test_prefixes_dangerous_characters(self, prefix):
        """Values starting with formula-trigger characters get a quote prefix."""
        value = f"{prefix}SUM(A1:A10)"
        assert _sanitize_csv_value(value) == f"'{value}"

    def test_leaves_safe_values_unchanged(self):
        """Regular text is not modified."""
        assert _sanitize_csv_value("Deep Learning Survey") == "Deep Learning Survey"

    def test_leaves_empty_string_unchanged(self):
        """Empty strings pass through unchanged."""
        assert _sanitize_csv_value("") == ""

    def test_leaves_numeric_string_unchanged(self):
        """Numeric strings that don't start with formula chars are untouched."""
        assert _sanitize_csv_value("10.1038/nature12373") == "10.1038/nature12373"

    def test_newlines_collapsed_to_spaces(self):
        """Newlines within a value are collapsed to single spaces."""
        assert _sanitize_csv_value("line one\nline two") == "line one line two"

    def test_newlines_before_formula_prefix(self):
        """Newlines are collapsed before formula-prefix check."""
        # A leading newline followed by '=' should result in the text
        # being stripped, then the '=' prefix triggers the quote.
        assert _sanitize_csv_value("\n=cmd") == "'=cmd"


class TestCsvNewlineNormalization:
    """Newlines in CSV cell values are collapsed to spaces."""

    def test_abstract_newlines_collapsed_in_csv(self) -> None:
        """Newlines in abstract are collapsed in CSV output."""
        paper = Paper(
            title="Test",
            abstract="BACKGROUND\nSome text.\n\nMETHODS\nMore text.",
            authors=[Author(name="A, B.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([paper], path)
            raw = Path(path).read_text(encoding="utf-8")
            # Header + exactly one data line (no extra lines from newlines)
            lines = raw.strip().splitlines()
            assert len(lines) == 2

    def test_round_trip_preserves_content(self) -> None:
        """Abstract with newlines survives save->load with content intact."""
        paper = Paper(
            title="Test",
            abstract="Line one\nLine two",
            authors=[Author(name="A, B.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([paper], path)
            loaded = load_from_csv(path)
            assert loaded[0].abstract == "Line one Line two"


class TestUnsanitizeCsvValue:
    """Tests for _unsanitize_csv_value()."""

    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
    def test_removes_quote_before_dangerous_characters(self, prefix):
        """Strip the protective quote prefix added by _sanitize_csv_value."""
        sanitized = f"'{prefix}SUM(A1:A10)"
        assert _unsanitize_csv_value(sanitized) == f"{prefix}SUM(A1:A10)"

    def test_leaves_safe_values_unchanged(self):
        """Regular text that happens to start with a quote is left as-is if not a formula char."""
        assert _unsanitize_csv_value("'Hello") == "'Hello"

    def test_leaves_empty_string_unchanged(self):
        """Empty strings pass through unchanged."""
        assert _unsanitize_csv_value("") == ""

    def test_round_trip(self):
        """Sanitize then unsanitize restores the original value."""
        for value in ["=cmd|'calc'", "+1-2", "-negative", "@mention", "safe", ""]:
            assert _unsanitize_csv_value(_sanitize_csv_value(value)) == value


class TestCsvFormulaInjectionRoundTrip:
    """End-to-end CSV round-trip with formula-trigger values."""

    def test_dangerous_title_survives_round_trip(self):
        """A title starting with '=' survives save->load without formula injection."""
        paper = Paper(
            title="=SUM(A1:A10)",
            abstract="+abstract with plus",
            authors=[Author("-Author, A.")],
            source=None,
            publication_date=datetime.date(2023, 1, 1),
            comments="@dangerous comment",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "out.csv")
            save_to_csv([paper], path)

            # Verify the raw CSV does not contain unsanitized formula triggers
            raw = Path(path).read_text(encoding="utf-8")
            lines = raw.strip().splitlines()
            # The data line should not start a cell with '=' directly
            data_line = lines[1]
            assert not data_line.startswith("=")

            loaded = load_from_csv(path)
            assert len(loaded) == 1
            assert loaded[0].title == paper.title
            assert loaded[0].abstract == paper.abstract
            assert loaded[0].comments == paper.comments
