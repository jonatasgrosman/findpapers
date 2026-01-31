"""Tests for internal SearchRunner utilities."""

from datetime import date

from findpapers import SearchRunner
from findpapers.models import Paper, Publication


def test_publication_type_allowed_from_publication():
    runner = SearchRunner()
    allowed = {"journal"}
    publication = Publication(title="Journal", category="Journal")
    paper = Paper(
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        publication=publication,
        publication_date=None,
        urls=set(),
    )
    assert runner._publication_type_allowed(paper, allowed) is True


def test_publication_type_allowed_from_object_publication_category():
    publication = Publication(title="Conference", category="Conference Proceedings")
    paper = Paper(
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        publication=publication,
        publication_date=None,
        urls=set(),
    )
    runner = SearchRunner()
    allowed = {"conference proceedings"}
    assert runner._publication_type_allowed(paper, allowed) is True


def test_publication_type_not_allowed_when_missing():
    runner = SearchRunner()
    paper = Paper(
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls=set(),
    )
    assert runner._publication_type_allowed(paper, {"journal"}) is False


def test_dedupe_key_variants():
    runner = SearchRunner()
    paper_with_doi = Paper(
        title="My Title",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls=set(),
        doi="10.1/ABC",
    )
    assert runner._dedupe_key(paper_with_doi) == "doi:10.1/abc"

    paper_with_date = Paper(
        title="My Title",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=date(2020, 1, 1),
        urls=set(),
    )
    assert runner._dedupe_key(paper_with_date) == "title:my title|year:2020"

    paper_title_only = Paper(
        title="My Title",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls=set(),
    )
    assert runner._dedupe_key(paper_title_only) == "title:my title"


def test_dedupe_key_object_date():
    runner = SearchRunner()
    paper = Paper(
        title="My Title",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=date(2021, 1, 1),
        urls=set(),
    )
    assert runner._dedupe_key(paper) == "title:my title|year:2021"


def test_paper_urls_have_doi_url_when_available():
    paper = Paper(
        title="Paper",
        abstract="Abstract",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls={"https://a"},
        doi="10.1/abc",
    )
    assert "https://doi.org/10.1/abc" in paper.urls
