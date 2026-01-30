"""Tests for predatory utility helpers."""

import pytest

from findpapers.utils import predatory_util


def test_normalize_helpers():
    assert predatory_util._normalize(None) is None
    assert predatory_util._normalize("  ABC  ") == "abc"
    assert predatory_util._normalize("   ") is None


def test_get_publication_fields_dict():
    publication = {"title": " Journal ", "publisher": " Pub ", "publisher_host": "Host"}
    name, publisher, host = predatory_util._get_publication_fields(publication)
    assert name == "journal"
    assert publisher == "pub"
    assert host == "host"


def test_get_publication_fields_object():
    class Publication:
        def __init__(self) -> None:
            self.title = " Journal "
            self.publisher = " Pub "
            self.publisher_host = "Host"

    name, publisher, host = predatory_util._get_publication_fields(Publication())
    assert name == "journal"
    assert publisher == "pub"
    assert host == "host"


def test_is_predatory_by_journal_name():
    if not predatory_util.POTENTIAL_PREDATORY_JOURNALS_NAMES:
        pytest.skip("Predatory journal list is empty")
    name = next(iter(predatory_util.POTENTIAL_PREDATORY_JOURNALS_NAMES))
    assert predatory_util.is_predatory_publication({"title": name}) is True


def test_is_predatory_by_publisher_name():
    if not predatory_util.POTENTIAL_PREDATORY_PUBLISHERS_NAMES:
        pytest.skip("Predatory publisher list is empty")
    name = next(iter(predatory_util.POTENTIAL_PREDATORY_PUBLISHERS_NAMES))
    assert predatory_util.is_predatory_publication({"publisher": name}) is True


def test_is_predatory_by_publisher_host():
    if not predatory_util.POTENTIAL_PREDATORY_PUBLISHERS_HOSTS:
        pytest.skip("Predatory publisher hosts list is empty")
    host = next(iter(predatory_util.POTENTIAL_PREDATORY_PUBLISHERS_HOSTS))
    assert predatory_util.is_predatory_publication({"publisher_host": host}) is True


def test_is_predatory_false_for_none():
    assert predatory_util.is_predatory_publication(None) is False


def test_normalize_allowed_types():
    normalized = predatory_util.normalize_allowed_types([" Journal ", "", "Book"])
    assert normalized == {"journal", "book"}
