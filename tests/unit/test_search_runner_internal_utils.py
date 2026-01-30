"""Tests for internal SearchRunner utilities."""

from datetime import date

from findpapers import SearchRunner


def test_publication_type_allowed_from_dict():
    runner = SearchRunner()
    allowed = {"journal"}
    item = {"publication": {"category": "Journal"}}
    assert runner._publication_type_allowed(item, allowed) is True


def test_publication_type_allowed_from_object_publication_category():
    class Publication:
        def __init__(self) -> None:
            self.category = "Conference Proceedings"

    class Paper:
        def __init__(self) -> None:
            self.publication = Publication()

    runner = SearchRunner()
    allowed = {"conference proceedings"}
    assert runner._publication_type_allowed(Paper(), allowed) is True


def test_publication_type_not_allowed_when_missing():
    runner = SearchRunner()
    assert runner._publication_type_allowed({}, {"journal"}) is False


def test_publication_type_allowed_from_publication_category_dict():
    runner = SearchRunner()
    allowed = {"journal"}
    item = {"publication_category": "Journal"}
    assert runner._publication_type_allowed(item, allowed) is True


def test_publication_type_allowed_from_publication_category_object():
    class Paper:
        def __init__(self) -> None:
            self.publication_category = "Journal"

    runner = SearchRunner()
    allowed = {"journal"}
    assert runner._publication_type_allowed(Paper(), allowed) is True


def test_dedupe_key_variants():
    runner = SearchRunner()
    assert runner._dedupe_key({"doi": "10.1/ABC"}) == "doi:10.1/abc"
    assert (
        runner._dedupe_key({"title": "My Title", "publication_date": date(2020, 1, 1)})
        == "title:my title|year:2020"
    )
    assert runner._dedupe_key({"title": "My Title"}) == "title:my title"
    assert runner._dedupe_key({})[:7] == "object:"


def test_dedupe_key_object_date():
    class Paper:
        def __init__(self) -> None:
            self.title = "My Title"
            self.doi = None
            self.publication_date = date(2021, 1, 1)

    runner = SearchRunner()
    assert runner._dedupe_key(Paper()) == "title:my title|year:2021"


def test_merge_values_rules():
    runner = SearchRunner()
    assert runner._merge_values(None, "x") == "x"
    assert runner._merge_values("x", None) == "x"
    assert runner._merge_values("short", "longer") == "longer"
    assert runner._merge_values(1, 2) == 2
    assert runner._merge_values({"a"}, {"b"}) == {"a", "b"}
    assert sorted(runner._merge_values(["a"], ["b"])) == ["a", "b"]
    assert set(runner._merge_values(("a",), ("b",))) == {"a", "b"}
    assert runner._merge_values({"a": 1}, {"a": 2, "b": 3}) == {"a": 2, "b": 3}


def test_merge_items_object():
    class Paper:
        def __init__(self) -> None:
            self.title = "Short"
            self.citations = 1

    runner = SearchRunner()
    base = Paper()
    incoming = Paper()
    incoming.title = "A much longer title"
    incoming.citations = 3

    merged = runner._merge_items(base, incoming)
    assert merged.title == "A much longer title"
    assert merged.citations == 3


def test_merge_items_dict():
    runner = SearchRunner()
    base = {"title": "Short", "citations": 1}
    incoming = {"title": "A much longer title", "citations": 3}
    merged = runner._merge_items(base, incoming)
    assert merged["title"] == "A much longer title"
    assert merged["citations"] == 3


def test_merge_values_fallback():
    runner = SearchRunner()
    obj = object()
    assert runner._merge_values(obj, 123) is obj


def test_get_publication_and_set_predatory_on_object():
    class Publication:
        def __init__(self) -> None:
            self.title = "Journal"
            self.is_potentially_predatory = False

    class Paper:
        def __init__(self) -> None:
            self.publication = Publication()
            self.is_potentially_predatory = False

    runner = SearchRunner()
    paper = Paper()
    publication = runner._get_publication(paper)
    assert publication is paper.publication
    runner._set_predatory_flag(paper, publication)
    assert paper.is_potentially_predatory is True
    assert paper.publication.is_potentially_predatory is True
