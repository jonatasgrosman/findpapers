"""Tests for merge utility helpers."""

from findpapers.utils.merge_util import merge_value


def test_merge_value_prefers_non_null() -> None:
    assert merge_value(None, "x") == "x"
    assert merge_value("x", None) == "x"


def test_merge_value_prefers_longer_text() -> None:
    assert merge_value("short", "longer") == "longer"


def test_merge_value_prefers_larger_numeric() -> None:
    assert merge_value(1, 2) == 2


def test_merge_value_merges_collections() -> None:
    assert merge_value({"a"}, {"b"}) == {"a", "b"}
    assert sorted(merge_value(["a"], ["b"])) == ["a", "b"]
    assert set(merge_value(("a",), ("b",))) == {"a", "b"}
    assert merge_value({"a": 1}, {"a": 2, "b": 3}) == {"a": 2, "b": 3}


def test_merge_value_fallback() -> None:
    obj = object()
    assert merge_value(obj, 123) is obj
