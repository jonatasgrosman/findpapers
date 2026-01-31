"""Tests for Paper, Publication, and Search models."""

import datetime

import pytest

from findpapers.models import Paper, Publication, Search


def test_publication_category_normalization():
    publication = Publication(title="My Journal")
    publication.category = "journal of tests"
    assert publication.category == "Journal"


def test_publication_merge():
    base = Publication(title="A", publisher=None)
    incoming = Publication(title="Longer", publisher="Pub")
    base.merge(incoming)
    assert base.title == "Longer"
    assert base.publisher == "Pub"


def test_publication_to_from_dict():
    data = {
        "title": "T",
        "isbn": "1",
        "issn": "2",
        "publisher": "Pub",
        "category": "Journal",
        "cite_score": 1.0,
        "sjr": 2.0,
        "snip": 3.0,
        "subject_areas": ["A"],
        "is_potentially_predatory": True,
    }
    publication = Publication.from_dict(data)
    assert Publication.to_dict(publication)["title"] == "T"


def test_paper_requires_title():
    with pytest.raises(ValueError):
        Paper(
            title="",
            abstract="",
            authors=[],
            publication=None,
            publication_date=datetime.date.today(),
            urls=set(),
        )


def test_paper_adds_doi_url_when_missing_urls():
    paper = Paper(
        title="Title",
        abstract="",
        authors=["A"],
        publication=None,
        publication_date=None,
        urls=set(),
        doi="10.123/abc",
    )
    assert "https://doi.org/10.123/abc" in paper.urls


def test_paper_add_and_merge():
    publication = Publication(title="Journal")
    paper = Paper(
        title="Title",
        abstract="",
        authors=["A"],
        publication=publication,
        publication_date=datetime.date(2020, 1, 1),
        urls=set(),
    )
    paper.add_database("arxiv")
    paper.add_url("https://example.com")
    assert "arxiv" in paper.databases
    assert "https://example.com" in paper.urls

    incoming = Paper(
        title="Longer Title",
        abstract="Abstract",
        authors=["A", "B"],
        publication=Publication(title="Journal", publisher="Pub"),
        publication_date=datetime.date(2020, 1, 1),
        urls={"https://b"},
        citations=5,
    )
    paper.merge(incoming)
    assert paper.title == "Longer Title"
    assert paper.abstract == "Abstract"
    assert paper.citations == 5
    assert "https://b" in paper.urls


def test_search_add_paper():
    search = Search(query="q", databases=["arxiv"])
    paper = Paper(
        title="Title",
        abstract="",
        authors=[],
        publication=None,
        publication_date=datetime.date(2020, 1, 1),
        urls=set(),
    )
    search.add_paper(paper)
    assert search.papers == [paper]
