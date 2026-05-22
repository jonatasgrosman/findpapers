"""Tests for the Paper model."""

import datetime

import pytest

from findpapers.core.author import Author
from findpapers.core.paper import _MAX_FUTURE_DAYS, Paper, PaperType
from findpapers.core.source import Source
from findpapers.exceptions import ModelValidationError


def test_paper_requires_title():
    """Test that paper requires a title."""
    with pytest.raises(ModelValidationError, match="cannot be null"):
        Paper(
            title="",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date.today(),
        )


def test_paper_sanitize_date_nullifies_far_future():
    """Publication dates more than _MAX_FUTURE_DAYS in the future are set to None."""
    far_future = datetime.date.today() + datetime.timedelta(days=_MAX_FUTURE_DAYS + 100)
    paper = Paper(
        title="Future Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=far_future,
    )
    assert paper.publication_date is None


def test_paper_sanitize_date_keeps_near_future():
    """Dates within the grace window are preserved."""
    near_future = datetime.date.today() + datetime.timedelta(days=30)
    paper = Paper(
        title="Near Future Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=near_future,
    )
    assert paper.publication_date == near_future


def test_paper_sanitize_date_keeps_past():
    """Past dates are preserved."""
    past = datetime.date(2020, 6, 15)
    paper = Paper(
        title="Past Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=past,
    )
    assert paper.publication_date == past


def test_paper_sanitize_date_keeps_none():
    """None publication date stays None."""
    paper = Paper(
        title="No Date Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
    )
    assert paper.publication_date is None


def test_paper_url_and_pdf_url():
    """Test that paper accepts url and pdf_url."""
    paper = Paper(
        title="Title",
        abstract="Abstract",
        authors=[Author(name="A")],
        source=None,
        publication_date=None,
        url="https://example.com/paper",
        pdf_url="https://example.com/paper.pdf",
        doi="10.123/abc",
    )
    assert paper.url == "https://example.com/paper"
    assert paper.pdf_url == "https://example.com/paper.pdf"
    assert paper.doi == "10.123/abc"


def test_paper_add_and_merge():
    """Test adding metadata and merging papers."""
    publication = Source(title="Journal")
    paper = Paper(
        title="Title",
        abstract="",
        authors=[Author(name="A")],
        source=publication,
        publication_date=datetime.date(2020, 1, 1),
        url="https://example.com",
    )
    paper.add_database("arxiv")
    assert "arxiv" in paper.databases
    assert paper.url == "https://example.com"

    incoming = Paper(
        title="Longer Title",
        abstract="Abstract",
        authors=[Author(name="A"), Author(name="B")],
        source=Source(title="Journal", publisher="Pub"),
        publication_date=datetime.date(2020, 1, 1),
        url="https://longer-example.com",
        pdf_url="https://example.com/paper.pdf",
        citations=5,
    )
    paper.merge(incoming)
    assert paper.title == "Longer Title"
    assert paper.abstract == "Abstract"
    assert paper.citations == 5
    assert paper.url == "https://longer-example.com"
    assert paper.pdf_url == "https://example.com/paper.pdf"


def test_paper_fields_of_study_and_subjects_defaults():
    """fields_of_study and subjects default to empty sets."""
    paper = Paper(
        title="T",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
    )
    assert paper.fields_of_study == set()
    assert paper.subjects == set()


def test_paper_fields_of_study_and_subjects_set_at_construction():
    """fields_of_study and subjects can be set at construction."""
    paper = Paper(
        title="T",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        fields_of_study={"Computer Science"},
        subjects={"Machine Learning", "Artificial Intelligence"},
    )
    assert paper.fields_of_study == {"Computer Science"}
    assert paper.subjects == {"Machine Learning", "Artificial Intelligence"}


def test_paper_fields_of_study_and_subjects_in_to_dict():
    """to_dict includes fields_of_study and subjects."""
    paper = Paper(
        title="T",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        fields_of_study={"Mathematics", "Computer Science"},
        subjects={"Optimization and Control"},
    )
    d = paper.to_dict()
    assert d["fields_of_study"] == ["Computer Science", "Mathematics"]
    assert d["subjects"] == ["Optimization and Control"]


def test_paper_merge_accumulates_fields_of_study_and_subjects():
    """merge() unions fields_of_study and subjects from both papers."""
    base = Paper(
        title="T",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        fields_of_study={"Computer Science"},
        subjects={"Machine Learning"},
    )
    incoming = Paper(
        title="T",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        fields_of_study={"Mathematics"},
        subjects={"Optimization and Control"},
    )
    base.merge(incoming)
    assert base.fields_of_study == {"Computer Science", "Mathematics"}
    assert base.subjects == {"Machine Learning", "Optimization and Control"}


def test_paper_merge_keeps_larger_author_list():
    """Paper.merge keeps whichever author list is longer.

    This covers the enrichment scenario where different sources return
    different numbers of authors (e.g. one source lists all co-authors while
    another lists only the first few).
    """
    # base has fewer authors than incoming → incoming wins
    base = Paper(
        title="Test Paper",
        abstract="Abstract",
        authors=[Author(name="Alice Smith"), Author(name="Bob Jones")],
        source=None,
        publication_date=None,
    )
    incoming = Paper(
        title="Test Paper",
        abstract="Abstract",
        authors=[
            Author(name="Alice Smith"),
            Author(name="Bob Jones"),
            Author(name="Charlie Brown"),
            Author(name="Diana Prince"),
        ],
        source=None,
        publication_date=None,
    )
    base.merge(incoming)
    assert base.authors == [
        Author(name="Alice Smith"),
        Author(name="Bob Jones"),
        Author(name="Charlie Brown"),
        Author(name="Diana Prince"),
    ]

    # base has more authors than incoming → base wins
    base2 = Paper(
        title="Test Paper",
        abstract="Abstract",
        authors=[
            Author(name="Alice Smith"),
            Author(name="Bob Jones"),
            Author(name="Charlie Brown"),
        ],
        source=None,
        publication_date=None,
    )
    incoming2 = Paper(
        title="Test Paper",
        abstract="Abstract",
        authors=[Author(name="Alice Smith")],
        source=None,
        publication_date=None,
    )
    base2.merge(incoming2)
    assert base2.authors == [
        Author(name="Alice Smith"),
        Author(name="Bob Jones"),
        Author(name="Charlie Brown"),
    ]


def test_paper_merge_doi_first_wins():
    """Paper.merge never overwrites an existing DOI — the first source wins."""
    base = Paper(
        title="Attention is All You Need",
        abstract="",
        authors=[Author(name="Vaswani")],
        source=None,
        publication_date=datetime.date(2017, 6, 12),
        doi="10.48550/arxiv.1706.03762",
    )
    incoming = Paper(
        title="Attention is All You Need",
        abstract="The dominant sequence...",
        authors=[Author(name="Vaswani")],
        source=None,
        publication_date=datetime.date(2017, 6, 12),
        doi="10.5555/3295222.3295349",
    )
    base.merge(incoming)
    # Base DOI must be preserved regardless of which one is a preprint.
    assert base.doi == "10.48550/arxiv.1706.03762"


def test_paper_merge_doi_filled_from_incoming_when_base_has_none():
    """Paper.merge fills a missing DOI from the incoming paper."""
    base = Paper(
        title="Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        doi=None,
    )
    incoming = Paper(
        title="Paper",
        abstract="",
        authors=[],
        source=None,
        publication_date=None,
        doi="10.5555/3295222.3295349",
    )
    base.merge(incoming)
    assert base.doi == "10.5555/3295222.3295349"


# ---------------------------------------------------------------------------
# PaperType on Paper
# ---------------------------------------------------------------------------


class TestPaperType:
    """Tests for the paper_type attribute on Paper."""

    def test_paper_type_defaults_to_none(self) -> None:
        """Paper without explicit paper_type has None."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.paper_type is None

    def test_paper_type_set_at_construction(self) -> None:
        """Paper can be constructed with a paper_type."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.ARTICLE,
        )
        assert paper.paper_type is PaperType.ARTICLE

    def test_paper_type_serialized_in_to_dict(self) -> None:
        """to_dict includes paper_type when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.INPROCEEDINGS,
        )
        d = paper.to_dict()
        assert d["paper_type"] == "inproceedings"

    def test_paper_type_none_serialized_as_none(self) -> None:
        """to_dict serializes missing paper_type as None."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        d = paper.to_dict()
        assert d["paper_type"] is None

    def test_paper_type_deserialized_from_dict(self) -> None:
        """from_dict restores paper_type from string value."""
        d = {"title": "T", "paper_type": "phdthesis"}
        paper = Paper.from_dict(d)
        assert paper.paper_type is PaperType.PHDTHESIS

    def test_paper_type_invalid_string_ignored(self) -> None:
        """from_dict ignores invalid paper_type strings."""
        d = {"title": "T", "paper_type": "not_a_type"}
        paper = Paper.from_dict(d)
        assert paper.paper_type is None

    def test_paper_type_none_in_dict(self) -> None:
        """from_dict handles paper_type being None."""
        d = {"title": "T", "paper_type": None}
        paper = Paper.from_dict(d)
        assert paper.paper_type is None

    def test_paper_type_missing_from_dict(self) -> None:
        """from_dict handles paper_type key missing."""
        d = {"title": "T"}
        paper = Paper.from_dict(d)
        assert paper.paper_type is None

    def test_paper_type_merge_fills_none(self) -> None:
        """Merge fills paper_type when base is None."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.ARTICLE,
        )
        base.merge(incoming)
        assert base.paper_type is PaperType.ARTICLE

    def test_paper_type_merge_keeps_existing(self) -> None:
        """Merge preserves existing paper_type when incoming also has one."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.INPROCEEDINGS,
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.ARTICLE,
        )
        base.merge(incoming)
        assert base.paper_type is PaperType.INPROCEEDINGS

    def test_all_bibtex_types_present(self) -> None:
        """PaperType enum covers the agreed BibTeX entry types."""
        expected = {
            "article",
            "inproceedings",
            "inbook",
            "incollection",
            "book",
            "phdthesis",
            "mastersthesis",
            "techreport",
            "unpublished",
            "misc",
        }
        actual = {pt.value for pt in PaperType}
        assert actual == expected

    def test_paper_type_round_trip(self) -> None:
        """to_dict → from_dict preserves paper_type."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            paper_type=PaperType.TECHREPORT,
        )
        restored = Paper.from_dict(paper.to_dict())
        assert restored.paper_type is PaperType.TECHREPORT


class TestPaperLanguage:
    """Tests for the language attribute on Paper."""

    def test_language_defaults_to_none(self) -> None:
        """Paper without explicit language has None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.language is None

    def test_language_set_at_construction(self) -> None:
        """Paper can be constructed with a language."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="en",
        )
        assert paper.language == "en"

    def test_language_serialized_in_to_dict(self) -> None:
        """to_dict includes language when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="pt",
        )
        assert paper.to_dict()["language"] == "pt"

    def test_language_none_serialized_as_none(self) -> None:
        """to_dict serializes missing language as None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.to_dict()["language"] is None

    def test_language_deserialized_from_dict(self) -> None:
        """from_dict restores language from string value."""
        paper = Paper.from_dict({"title": "T", "language": "fr"})
        assert paper.language == "fr"

    def test_language_none_in_dict(self) -> None:
        """from_dict handles language being None."""
        paper = Paper.from_dict({"title": "T", "language": None})
        assert paper.language is None

    def test_language_missing_from_dict(self) -> None:
        """from_dict handles language key missing."""
        paper = Paper.from_dict({"title": "T"})
        assert paper.language is None

    def test_language_round_trip(self) -> None:
        """to_dict → from_dict preserves language."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="de",
        )
        assert Paper.from_dict(paper.to_dict()).language == "de"

    def test_language_merge_fills_none(self) -> None:
        """merge() fills language when base has None."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="en",
        )
        base.merge(incoming)
        assert base.language == "en"

    def test_language_merge_keeps_existing(self) -> None:
        """merge() preserves existing language value."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="en",
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            language="fr",
        )
        base.merge(incoming)
        assert base.language == "en"


class TestPaperIsOpenAccess:
    """Tests for the is_open_access attribute on Paper."""

    def test_is_open_access_defaults_to_none(self) -> None:
        """Paper without explicit is_open_access has None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.is_open_access is None

    def test_is_open_access_set_true_at_construction(self) -> None:
        """Paper can be constructed with is_open_access=True."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=True,
        )
        assert paper.is_open_access is True

    def test_is_open_access_set_false_at_construction(self) -> None:
        """Paper can be constructed with is_open_access=False."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=False,
        )
        assert paper.is_open_access is False

    def test_is_open_access_serialized_true_in_to_dict(self) -> None:
        """to_dict includes is_open_access=True when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=True,
        )
        assert paper.to_dict()["is_open_access"] is True

    def test_is_open_access_serialized_false_in_to_dict(self) -> None:
        """to_dict includes is_open_access=False when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=False,
        )
        assert paper.to_dict()["is_open_access"] is False

    def test_is_open_access_none_serialized_as_none(self) -> None:
        """to_dict serializes missing is_open_access as None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.to_dict()["is_open_access"] is None

    def test_is_open_access_deserialized_from_dict_true(self) -> None:
        """from_dict restores is_open_access=True."""
        paper = Paper.from_dict({"title": "T", "is_open_access": True})
        assert paper.is_open_access is True

    def test_is_open_access_deserialized_from_dict_false(self) -> None:
        """from_dict restores is_open_access=False."""
        paper = Paper.from_dict({"title": "T", "is_open_access": False})
        assert paper.is_open_access is False

    def test_is_open_access_none_in_dict(self) -> None:
        """from_dict handles is_open_access being None."""
        paper = Paper.from_dict({"title": "T", "is_open_access": None})
        assert paper.is_open_access is None

    def test_is_open_access_missing_from_dict(self) -> None:
        """from_dict handles is_open_access key missing."""
        paper = Paper.from_dict({"title": "T"})
        assert paper.is_open_access is None

    def test_is_open_access_round_trip(self) -> None:
        """to_dict → from_dict preserves is_open_access."""
        for value in (True, False, None):
            paper = Paper(
                title="T",
                abstract="",
                authors=[],
                source=None,
                publication_date=None,
                is_open_access=value,
            )
            assert Paper.from_dict(paper.to_dict()).is_open_access is value

    def test_is_open_access_merge_fills_none_with_true(self) -> None:
        """merge() fills is_open_access when base has None and incoming has True."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=True,
        )
        base.merge(incoming)
        assert base.is_open_access is True

    def test_is_open_access_merge_fills_none_with_false(self) -> None:
        """merge() fills is_open_access when base has None and incoming has False."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=False,
        )
        base.merge(incoming)
        assert base.is_open_access is False

    def test_is_open_access_merge_true_wins_over_false(self) -> None:
        """merge() honours merge_value semantics: True beats False (bool is int subtype)."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=False,
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=True,
        )
        base.merge(incoming)
        assert base.is_open_access is True

    def test_is_open_access_merge_keeps_existing_true(self) -> None:
        """merge() keeps is_open_access=True when incoming has None."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_open_access=True,
        )
        incoming = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        base.merge(incoming)
        assert base.is_open_access is True


class TestPaperIsRetracted:
    """Tests for the is_retracted attribute on Paper."""

    def test_is_retracted_defaults_to_none(self) -> None:
        """Paper without explicit is_retracted has None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.is_retracted is None

    def test_is_retracted_set_true_at_construction(self) -> None:
        """Paper can be constructed with is_retracted=True."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=True,
        )
        assert paper.is_retracted is True

    def test_is_retracted_set_false_at_construction(self) -> None:
        """Paper can be constructed with is_retracted=False."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=False,
        )
        assert paper.is_retracted is False

    def test_is_retracted_serialized_true_in_to_dict(self) -> None:
        """to_dict includes is_retracted=True when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=True,
        )
        assert paper.to_dict()["is_retracted"] is True

    def test_is_retracted_serialized_false_in_to_dict(self) -> None:
        """to_dict includes is_retracted=False when set."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=False,
        )
        assert paper.to_dict()["is_retracted"] is False

    def test_is_retracted_none_serialized_as_none(self) -> None:
        """to_dict serializes missing is_retracted as None."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.to_dict()["is_retracted"] is None

    def test_is_retracted_deserialized_from_dict_true(self) -> None:
        """from_dict restores is_retracted=True."""
        paper = Paper.from_dict({"title": "T", "is_retracted": True})
        assert paper.is_retracted is True

    def test_is_retracted_deserialized_from_dict_false(self) -> None:
        """from_dict restores is_retracted=False."""
        paper = Paper.from_dict({"title": "T", "is_retracted": False})
        assert paper.is_retracted is False

    def test_is_retracted_none_in_dict(self) -> None:
        """from_dict handles is_retracted being None."""
        paper = Paper.from_dict({"title": "T", "is_retracted": None})
        assert paper.is_retracted is None

    def test_is_retracted_missing_from_dict(self) -> None:
        """from_dict handles is_retracted key missing."""
        paper = Paper.from_dict({"title": "T"})
        assert paper.is_retracted is None

    def test_is_retracted_round_trip(self) -> None:
        """to_dict → from_dict preserves is_retracted."""
        for value in (True, False, None):
            paper = Paper(
                title="T",
                abstract="",
                authors=[],
                source=None,
                publication_date=None,
                is_retracted=value,
            )
            assert Paper.from_dict(paper.to_dict()).is_retracted is value

    def test_is_retracted_merge_fills_none_with_true(self) -> None:
        """merge() fills is_retracted when base has None and incoming has True."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=True,
        )
        base.merge(incoming)
        assert base.is_retracted is True

    def test_is_retracted_merge_fills_none_with_false(self) -> None:
        """merge() fills is_retracted when base has None and incoming has False."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=False,
        )
        base.merge(incoming)
        assert base.is_retracted is False

    def test_is_retracted_merge_true_wins_over_false(self) -> None:
        """merge() honours merge_value semantics: True beats False (bool is int subtype)."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=False,
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=True,
        )
        base.merge(incoming)
        assert base.is_retracted is True

    def test_is_retracted_merge_keeps_existing_true(self) -> None:
        """merge() keeps is_retracted=True when incoming has None."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            is_retracted=True,
        )
        incoming = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        base.merge(incoming)
        assert base.is_retracted is True


class TestInferPageCount:
    """Tests for Paper._infer_page_count and its integration."""

    def test_simple_range(self) -> None:
        """A valid page range like '223-230' yields 8 pages."""
        assert Paper._infer_page_count("223-230") == 8

    def test_single_page(self) -> None:
        """When start equals end (e.g. '5-5'), the result is 1."""
        assert Paper._infer_page_count("5-5") == 1

    def test_none_input(self) -> None:
        """None page_range returns None."""
        assert Paper._infer_page_count(None) is None

    def test_empty_string(self) -> None:
        """Empty string returns None."""
        assert Paper._infer_page_count("") is None

    def test_non_numeric(self) -> None:
        """Non-numeric page_range (e.g. 'e123') return None."""
        assert Paper._infer_page_count("e123") is None

    def test_non_numeric_range(self) -> None:
        """Non-numeric range (e.g. 'A1-B2') returns None."""
        assert Paper._infer_page_count("A1-B2") is None

    def test_reversed_range(self) -> None:
        """Reversed range (end < start) returns None."""
        assert Paper._infer_page_count("230-223") is None

    def test_single_number_no_hyphen(self) -> None:
        """A single number without hyphen returns None (not a range)."""
        assert Paper._infer_page_count("56") is None

    def test_multiple_hyphens(self) -> None:
        """More than one hyphen returns None."""
        assert Paper._infer_page_count("1-2-3") is None

    def test_spaces_around_numbers(self) -> None:
        """Spaces around numbers are trimmed correctly."""
        assert Paper._infer_page_count(" 10 - 20 ") == 11

    def test_init_infers_when_absent(self) -> None:
        """Paper.__init__ auto-fills page_count from page_range when absent."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            page_range="100-110",
        )
        assert paper.page_count == 11

    def test_init_preserves_explicit_value(self) -> None:
        """Explicit page_count is never overridden by inference."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            page_count=5,
            page_range="100-110",
        )
        assert paper.page_count == 5

    def test_merge_infers_after_page_range_acquired(self) -> None:
        """Merging fills page_count if page_range becomes available."""
        paper_a = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        paper_b = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            page_range="50-60",
        )
        # paper_b already has inferred page_count, but test merge path
        # by resetting it to None to force inference in merge.
        paper_b.page_count = None
        paper_a.merge(paper_b)
        assert paper_a.page_count == 11

    def test_from_dict_infers(self) -> None:
        """from_dict auto-fills page_count when absent."""
        data = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            page_range="1-15",
        ).to_dict()
        # Force page_count to None to test inference via from_dict.
        data["page_count"] = None
        restored = Paper.from_dict(data)
        assert restored.page_count == 15


# ------------------------------------------------------------------
# Paper.__eq__ / __hash__
# ------------------------------------------------------------------


class TestPaperEquality:
    """Tests for Paper.__eq__ and __hash__."""

    def test_same_doi_means_equal(self) -> None:
        """Papers with matching DOIs are equal regardless of title."""
        a = Paper(
            title="A", abstract="", authors=[], source=None, publication_date=None, doi="10.1/x"
        )
        b = Paper(
            title="B", abstract="", authors=[], source=None, publication_date=None, doi="10.1/x"
        )
        assert a == b
        assert hash(a) == hash(b)

    def test_doi_case_insensitive(self) -> None:
        """DOI comparison is case-insensitive."""
        a = Paper(
            title="A", abstract="", authors=[], source=None, publication_date=None, doi="10.1/X"
        )
        b = Paper(
            title="B", abstract="", authors=[], source=None, publication_date=None, doi="10.1/x"
        )
        assert a == b

    def test_same_title_no_doi_means_equal(self) -> None:
        """Papers without DOI but with the same title are equal."""
        a = Paper(title="Same", abstract="a", authors=[], source=None, publication_date=None)
        b = Paper(title="Same", abstract="b", authors=[], source=None, publication_date=None)
        assert a == b
        assert hash(a) == hash(b)

    def test_title_case_insensitive(self) -> None:
        """Title comparison is case-insensitive when no DOI is present."""
        a = Paper(title="HELLO", abstract="", authors=[], source=None, publication_date=None)
        b = Paper(title="hello", abstract="", authors=[], source=None, publication_date=None)
        assert a == b

    def test_different_doi_not_equal(self) -> None:
        """Papers with different DOIs are not equal."""
        a = Paper(
            title="A", abstract="", authors=[], source=None, publication_date=None, doi="10.1/x"
        )
        b = Paper(
            title="A", abstract="", authors=[], source=None, publication_date=None, doi="10.2/y"
        )
        assert a != b

    def test_different_title_no_doi_not_equal(self) -> None:
        """Papers without DOI and different titles are not equal."""
        a = Paper(title="Alpha", abstract="", authors=[], source=None, publication_date=None)
        b = Paper(title="Beta", abstract="", authors=[], source=None, publication_date=None)
        assert a != b

    def test_not_equal_to_non_paper(self) -> None:
        """Comparison with non-Paper returns NotImplemented."""
        p = Paper(title="A", abstract="", authors=[], source=None, publication_date=None)
        assert p != "not a paper"

    def test_paper_usable_in_set(self) -> None:
        """Papers with same identity can be deduplicated in a set."""
        a = Paper(
            title="X", abstract="", authors=[], source=None, publication_date=None, doi="10.1/z"
        )
        b = Paper(
            title="Y", abstract="", authors=[], source=None, publication_date=None, doi="10.1/z"
        )
        assert len({a, b}) == 1

    def test_paper_in_list_after_deserialization(self) -> None:
        """Paper created from dict is found via 'in' operator on a list."""
        original = Paper(
            title="T", abstract="", authors=[], source=None, publication_date=None, doi="10.1/abc"
        )
        data = original.to_dict()
        restored = Paper.from_dict(data)
        assert restored in [original]


# ---------------------------------------------------------------------------
# Paper.__str__
# ---------------------------------------------------------------------------


class TestPaperStr:
    """Tests for Paper.__str__."""

    def test_str_full(self) -> None:
        """str(paper) with authors and date looks like a citation."""
        paper = Paper(
            title="Deep Learning",
            abstract="",
            authors=[Author(name="LeCun, Y."), Author(name="Bengio, Y.")],
            source=None,
            publication_date=datetime.date(2015, 5, 1),
        )
        assert str(paper) == "LeCun, Y. et al. (2015) Deep Learning."

    def test_str_single_author(self) -> None:
        """str(paper) with a single author omits 'et al.'."""
        paper = Paper(
            title="A Survey",
            abstract="",
            authors=[Author(name="Smith, J.")],
            source=None,
            publication_date=datetime.date(2020, 1, 1),
        )
        assert str(paper) == "Smith, J. (2020) A Survey."

    def test_str_no_authors(self) -> None:
        """str(paper) without authors starts with year."""
        paper = Paper(
            title="Anonymous Work",
            abstract="",
            authors=[],
            source=None,
            publication_date=datetime.date(2021, 6, 1),
        )
        assert str(paper) == "(2021) Anonymous Work."

    def test_str_no_date(self) -> None:
        """str(paper) without date omits year."""
        paper = Paper(
            title="Timeless",
            abstract="",
            authors=[Author(name="Doe, J.")],
            source=None,
            publication_date=None,
        )
        assert str(paper) == "Doe, J. Timeless."

    def test_str_minimal(self) -> None:
        """str(paper) with no authors and no date returns just the title."""
        paper = Paper(
            title="Only Title",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert str(paper) == "Only Title."

    def test_str_title_trailing_dot_not_duplicated(self) -> None:
        """A title already ending with '.' does not get a double period."""
        paper = Paper(
            title="Ends with dot.",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert str(paper) == "Ends with dot."

    def test_str_differs_from_repr(self) -> None:
        """__str__ and __repr__ produce different output."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[Author(name="A, B.")],
            source=None,
            publication_date=datetime.date(2021, 1, 1),
        )
        assert str(paper) != repr(paper)


class TestPaperIdentityEdgeCases:
    """Tests for __eq__, __hash__, and _identity_key edge cases."""

    def test_eq_identity_fallback_when_no_doi_no_title(self) -> None:
        """__eq__ falls back to `is` when _identity_key returns None for either paper."""
        # Paper with empty title and no DOI → _identity_key returns None
        p1 = Paper(title="A", abstract="", authors=[], source=None, publication_date=None)
        p2 = Paper(title="A", abstract="", authors=[], source=None, publication_date=None)
        # Both have a title so they compare via key
        assert p1 == p2
        # Now remove keys: monkeypatch _identity_key to return None
        p1._Paper__doi = None  # type: ignore[attr-defined]
        p1.title = ""
        # With empty title and no DOI, _identity_key returns None
        assert p1._identity_key() is None
        # Identity comparison: p1 is only equal to itself
        assert p1 == p1
        assert p1 != p2

    def test_hash_uses_id_when_no_key(self) -> None:
        """__hash__ returns id(self) when _identity_key is None."""
        p = Paper(title="temp", abstract="", authors=[], source=None, publication_date=None)
        p.title = ""
        p.doi = None
        assert p._identity_key() is None
        assert hash(p) == id(p)

    def test_identity_key_returns_none_without_doi_or_title(self) -> None:
        """_identity_key returns None when both doi and title are falsy."""
        p = Paper(title="temp", abstract="", authors=[], source=None, publication_date=None)
        p.title = ""
        p.doi = None
        assert p._identity_key() is None


class TestPaperFromDictEdgeCases:
    """Tests for from_dict coercion and edge-case handling."""

    def test_missing_title_raises(self) -> None:
        """from_dict raises ModelValidationError when title is missing."""
        with pytest.raises(ModelValidationError, match="title"):
            Paper.from_dict({})

    def test_non_string_abstract_coerced(self) -> None:
        """Non-string abstract is converted to str."""
        d = {"title": "T", "abstract": 42, "authors": []}
        paper = Paper.from_dict(d)
        assert paper.abstract == "42"

    def test_single_author_dict_not_list(self) -> None:
        """A single author dict (not in a list) is wrapped into a list."""
        d = {"title": "T", "authors": {"name": "J. Doe"}}
        paper = Paper.from_dict(d)
        assert len(paper.authors) == 1
        assert paper.authors[0].name == "J. Doe"

    def test_invalid_iso_date_becomes_none(self) -> None:
        """A malformed date string is coerced to None."""
        d = {"title": "T", "publication_date": "not-a-date"}
        paper = Paper.from_dict(d)
        assert paper.publication_date is None

    def test_non_string_url_coerced(self) -> None:
        """Non-string url is converted to str."""
        d = {"title": "T", "url": 123}
        paper = Paper.from_dict(d)
        assert paper.url == "123"

    def test_non_string_pdf_url_coerced(self) -> None:
        """Non-string pdf_url is converted to str."""
        d = {"title": "T", "pdf_url": 456}
        paper = Paper.from_dict(d)
        assert paper.pdf_url == "456"

    def test_non_string_doi_coerced(self) -> None:
        """Non-string doi is converted to str."""
        d = {"title": "T", "doi": 789}
        paper = Paper.from_dict(d)
        assert paper.doi == "789"

    def test_scalar_keywords_wrapped(self) -> None:
        """A single scalar keyword (not a list) is wrapped into a set."""
        d = {"title": "T", "keywords": "machine-learning"}
        paper = Paper.from_dict(d)
        assert paper.keywords == {"machine-learning"}

    def test_scalar_databases_wrapped(self) -> None:
        """A single scalar database (not a list) is wrapped into a set."""
        d = {"title": "T", "databases": "scopus"}
        paper = Paper.from_dict(d)
        assert paper.databases == {"scopus"}

    def test_fields_of_study_deserialized(self) -> None:
        """from_dict restores fields_of_study from a list."""
        d = {"title": "T", "fields_of_study": ["Computer Science", "Mathematics"]}
        paper = Paper.from_dict(d)
        assert paper.fields_of_study == {"Computer Science", "Mathematics"}

    def test_subjects_deserialized(self) -> None:
        """from_dict restores subjects from a list."""
        d = {"title": "T", "subjects": ["Artificial Intelligence", "Machine Learning"]}
        paper = Paper.from_dict(d)
        assert paper.subjects == {"Artificial Intelligence", "Machine Learning"}

    def test_fields_of_study_missing_defaults_empty(self) -> None:
        """from_dict defaults fields_of_study to empty set."""
        d = {"title": "T"}
        paper = Paper.from_dict(d)
        assert paper.fields_of_study == set()

    def test_subjects_missing_defaults_empty(self) -> None:
        """from_dict defaults subjects to empty set."""
        d = {"title": "T"}
        paper = Paper.from_dict(d)
        assert paper.subjects == set()

    def test_scalar_fields_of_study_wrapped(self) -> None:
        """A single scalar fields_of_study is wrapped into a set."""
        d = {"title": "T", "fields_of_study": "Computer Science"}
        paper = Paper.from_dict(d)
        assert paper.fields_of_study == {"Computer Science"}

    def test_scalar_subjects_wrapped(self) -> None:
        """A single scalar subjects is wrapped into a set."""
        d = {"title": "T", "subjects": "Artificial Intelligence"}
        paper = Paper.from_dict(d)
        assert paper.subjects == {"Artificial Intelligence"}


# ------------------------------------------------------------------
# Paper.funders
# ------------------------------------------------------------------


class TestPaperFunders:
    """Tests for the funders attribute on Paper."""

    def test_funders_defaults_to_empty_set(self) -> None:
        """Paper without explicit funders has an empty set."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.funders == set()

    def test_funders_set_at_construction(self) -> None:
        """funders can be populated at construction time."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"NSF", "NIH"},
        )
        assert paper.funders == {"NSF", "NIH"}

    def test_funders_serialized_in_to_dict(self) -> None:
        """to_dict includes funders as a sorted list."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"Wellcome Trust", "FAPESP"},
        )
        d = paper.to_dict()
        assert d["funders"] == ["FAPESP", "Wellcome Trust"]

    def test_funders_empty_serialized_as_empty_list(self) -> None:
        """to_dict serializes an empty funders set as an empty list."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.to_dict()["funders"] == []

    def test_funders_deserialized_from_dict_list(self) -> None:
        """from_dict restores funders from a list."""
        paper = Paper.from_dict({"title": "T", "funders": ["NSF", "NIH"]})
        assert paper.funders == {"NSF", "NIH"}

    def test_funders_missing_from_dict_defaults_empty(self) -> None:
        """from_dict defaults funders to empty set when key is absent."""
        paper = Paper.from_dict({"title": "T"})
        assert paper.funders == set()

    def test_funders_none_in_dict_defaults_empty(self) -> None:
        """from_dict treats None funders as an empty set."""
        paper = Paper.from_dict({"title": "T", "funders": None})
        assert paper.funders == set()

    def test_funders_round_trip(self) -> None:
        """to_dict → from_dict preserves funders."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"European Commission", "CAPES"},
        )
        restored = Paper.from_dict(paper.to_dict())
        assert restored.funders == {"European Commission", "CAPES"}

    def test_funders_merge_unions_both_sets(self) -> None:
        """merge() unions funders from both papers."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"NSF"},
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"NIH"},
        )
        base.merge(incoming)
        assert base.funders == {"NSF", "NIH"}

    def test_funders_merge_empty_base_with_populated_incoming(self) -> None:
        """merge() fills funders when base has none."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"Wellcome Trust"},
        )
        base.merge(incoming)
        assert base.funders == {"Wellcome Trust"}

    def test_funders_merge_keeps_existing_when_incoming_empty(self) -> None:
        """merge() keeps existing funders when incoming has none."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            funders={"CNPQ"},
        )
        incoming = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        base.merge(incoming)
        assert base.funders == {"CNPQ"}

    def test_scalar_funder_wrapped_in_set(self) -> None:
        """A single scalar funder string is wrapped into a set by from_dict."""
        paper = Paper.from_dict({"title": "T", "funders": "NSF"})
        assert paper.funders == {"NSF"}


class TestPaperTitleNormalization:
    """Tests for title HTML-stripping and whitespace normalization in Paper.__init__."""

    def test_html_tags_stripped_from_title(self) -> None:
        """HTML tags are removed from the title at construction time."""
        paper = Paper(
            title="400/50 V <i>LLC</i> Module",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.title == "400/50 V LLC Module"

    def test_newlines_in_title_collapsed(self) -> None:
        """Embedded newlines in the title are collapsed to a single space."""
        paper = Paper(
            title="Part One\nPart Two\n  Part Three",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.title == "Part One Part Two Part Three"

    def test_html_and_newlines_combined(self) -> None:
        """HTML tags and newlines are both cleaned from a title."""
        paper = Paper(
            title="Vertically Mounted\n  <i>LLC</i>\n  Module for Datacenters",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.title == "Vertically Mounted LLC Module for Datacenters"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Leading and trailing whitespace is stripped from the title."""
        paper = Paper(
            title="   My Paper   ",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.title == "My Paper"

    def test_plain_title_unchanged(self) -> None:
        """A plain title without HTML or extra whitespace is left unchanged."""
        paper = Paper(
            title="Deep Learning: A Survey",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
        )
        assert paper.title == "Deep Learning: A Survey"


# ---------------------------------------------------------------------------
# Paper.references
# ---------------------------------------------------------------------------


class TestPaperReferences:
    """Tests for the references attribute on Paper."""

    def test_references_defaults_to_empty_list(self) -> None:
        """Paper without explicit references has an empty list."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.references == []

    def test_references_set_at_construction(self) -> None:
        """references can be populated at construction time."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/a", "10.1000/b"],
        )
        assert paper.references == ["10.1000/a", "10.1000/b"]

    def test_references_none_at_construction_defaults_empty(self) -> None:
        """Passing None for references defaults to an empty list."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=None,
        )
        assert paper.references == []

    def test_references_serialized_in_to_dict(self) -> None:
        """to_dict includes references as a sorted list."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/z", "10.1000/a"],
        )
        assert paper.to_dict()["references"] == ["10.1000/a", "10.1000/z"]

    def test_references_empty_serialized_as_empty_list(self) -> None:
        """to_dict serializes an empty references list as an empty list."""
        paper = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        assert paper.to_dict()["references"] == []

    def test_references_deserialized_from_dict_list(self) -> None:
        """from_dict restores references from a list."""
        paper = Paper.from_dict({"title": "T", "references": ["10.1000/a", "10.1000/b"]})
        assert paper.references == ["10.1000/a", "10.1000/b"]

    def test_references_missing_from_dict_defaults_empty(self) -> None:
        """from_dict defaults references to empty list when key is absent."""
        paper = Paper.from_dict({"title": "T"})
        assert paper.references == []

    def test_references_none_in_dict_defaults_empty(self) -> None:
        """from_dict treats None references as an empty list."""
        paper = Paper.from_dict({"title": "T", "references": None})
        assert paper.references == []

    def test_references_round_trip(self) -> None:
        """to_dict → from_dict preserves references."""
        paper = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/a", "10.1000/b"],
        )
        restored = Paper.from_dict(paper.to_dict())
        assert restored.references == ["10.1000/a", "10.1000/b"]

    def test_references_merge_unions_preserving_order(self) -> None:
        """merge() unions references from both papers without duplicates."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/a", "10.1000/b"],
        )
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/b", "10.1000/c"],
        )
        base.merge(incoming)
        # "b" already present — should not be duplicated; "c" appended.
        assert base.references == ["10.1000/a", "10.1000/b", "10.1000/c"]

    def test_references_merge_empty_base_with_populated_incoming(self) -> None:
        """merge() fills references when base has none."""
        base = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        incoming = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/x"],
        )
        base.merge(incoming)
        assert base.references == ["10.1000/x"]

    def test_references_merge_keeps_existing_when_incoming_empty(self) -> None:
        """merge() keeps existing references when incoming has none."""
        base = Paper(
            title="T",
            abstract="",
            authors=[],
            source=None,
            publication_date=None,
            references=["10.1000/a"],
        )
        incoming = Paper(title="T", abstract="", authors=[], source=None, publication_date=None)
        base.merge(incoming)
        assert base.references == ["10.1000/a"]
