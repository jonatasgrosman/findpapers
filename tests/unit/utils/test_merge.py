"""Tests for merge utilities."""

from findpapers.core.author import Author
from findpapers.utils.merge import merge_authors, merge_value


def _a(name: str, affiliation: str | None = None) -> Author:
    """Shortcut to create an Author with the given name and optional affiliation."""
    return Author(name=name, affiliation=affiliation)


def test_merge_value_prefers_non_null():
    """Test that merge_value prefers non-null values."""
    assert merge_value(None, "value") == "value"
    assert merge_value("value", None) == "value"


def test_merge_value_prefers_longer_strings():
    """Test that merge_value prefers longer strings."""
    assert merge_value("short", "longer string") == "longer string"
    assert merge_value("longer string", "short") == "longer string"


def test_merge_value_prefers_larger_numbers():
    """Test that merge_value prefers larger numbers."""
    assert merge_value(5, 10) == 10
    assert merge_value(10, 5) == 10
    assert merge_value(3.5, 7.2) == 7.2


def test_merge_value_combines_sets():
    """Test that merge_value combines sets."""
    result = merge_value({1, 2}, {3, 4})
    assert result == {1, 2, 3, 4}


def test_merge_value_combines_lists():
    """Test that merge_value combines lists preserving insertion order."""
    result = merge_value([1, 2], [3, 4])
    assert result == [1, 2, 3, 4]


def test_merge_value_combines_lists_deduplicates():
    """Test that merge_value deduplicates list items while preserving order."""
    result = merge_value([1, 2, 3], [2, 3, 4])
    assert result == [1, 2, 3, 4]


def test_merge_value_combines_lists_preserves_base_order():
    """Base items appear first in their original order."""
    result = merge_value(["c", "a"], ["b", "a"])
    assert result == ["c", "a", "b"]


def test_merge_value_combines_lists_unhashable():
    """Test that merge_value handles unhashable items in lists."""
    result = merge_value([{"a": 1}], [{"a": 1}, {"b": 2}])
    assert result == [{"a": 1}, {"b": 2}]


def test_merge_value_combines_tuples_preserves_order():
    """Test that merge_value combines tuples preserving order."""
    result = merge_value((1, 2, 3), (2, 3, 4))
    assert result == (1, 2, 3, 4)


def test_merge_value_combines_tuples_unhashable():
    """Test that merge_value handles unhashable items in tuples."""
    result = merge_value(({"a": 1},), ({"a": 1}, {"b": 2}))
    assert result == ({"a": 1}, {"b": 2})


def test_merge_value_falls_back_to_base_for_unsupported_types():
    """Test that merge_value returns base when types are unsupported or mismatched."""
    sentinel = object()
    assert merge_value(sentinel, "other") is sentinel


def test_merge_value_combines_dicts():
    """Test that merge_value recursively merges dicts."""
    base = {"a": 1, "b": 2}
    incoming = {"b": 3, "c": 4}
    result = merge_value(base, incoming)
    assert result["a"] == 1
    assert result["b"] == 3  # larger value wins
    assert result["c"] == 4


class TestMergeAuthors:
    """Unit tests for the merge_authors helper."""

    def test_returns_incoming_when_larger(self):
        """Incoming list is returned when it has more authors than base."""
        base = [_a("Alice Smith")]
        incoming = [_a("Bob Jones"), _a("Charlie Brown"), _a("Diana Prince")]
        assert merge_authors(base, incoming) == incoming

    def test_returns_base_when_larger(self):
        """Base list is returned when it has more authors than incoming."""
        base = [_a("Alice Smith"), _a("Bob Jones"), _a("Charlie Brown")]
        incoming = [_a("Diana Prince")]
        assert merge_authors(base, incoming) == base

    def test_returns_base_on_tie(self):
        """Base list is returned when both lists have the same length."""
        base = [_a("Alice Smith"), _a("Bob Jones")]
        incoming = [_a("Charlie Brown"), _a("Diana Prince")]
        assert merge_authors(base, incoming) == base

    def test_empty_base_returns_incoming(self):
        """Empty base returns the incoming list."""
        result = merge_authors([], [_a("Alice Smith")])
        assert result == [_a("Alice Smith")]

    def test_empty_incoming_returns_base(self):
        """Empty incoming returns the base list."""
        result = merge_authors([_a("Alice Smith")], [])
        assert result == [_a("Alice Smith")]

    def test_both_empty(self):
        """Both empty returns empty list."""
        result = merge_authors([], [])
        assert result == []

    def test_returns_copy_not_same_object(self):
        """Returned list is a copy, not the original object."""
        base = [_a("Alice Smith"), _a("Bob Jones")]
        incoming = [_a("Charlie Brown")]
        result = merge_authors(base, incoming)
        assert result is not base
        result.append(_a("extra"))
        assert _a("extra") not in base

    # ------------------------------------------------------------------
    # Affiliation-based tiebreaking
    # ------------------------------------------------------------------

    def test_prefers_incoming_with_more_affiliations_on_tie(self):
        """When lists are same length, prefer the one with more affiliations."""
        base = [_a("Alice"), _a("Bob")]
        incoming = [_a("Alice", affiliation="MIT"), _a("Bob", affiliation="Stanford")]
        result = merge_authors(base, incoming)
        assert result[0].affiliation == "MIT"
        assert result[1].affiliation == "Stanford"

    def test_prefers_base_when_affiliations_tied(self):
        """When lists have same length and same affiliation count, base wins."""
        base = [_a("Alice", affiliation="MIT"), _a("Bob")]
        incoming = [_a("Alice", affiliation="Stanford"), _a("Bob")]
        result = merge_authors(base, incoming)
        assert result[0].affiliation == "MIT"

    # ------------------------------------------------------------------
    # Affiliation back-fill
    # ------------------------------------------------------------------

    def test_backfill_affiliations_from_loser_to_winner(self):
        """Winner authors get affiliations from loser authors with matching names."""
        base = [_a("Alice"), _a("Bob"), _a("Charlie")]
        incoming = [_a("Bob", affiliation="Harvard")]
        # base wins (larger), but Bob's affiliation is back-filled from incoming.
        result = merge_authors(base, incoming)
        assert len(result) == 3
        bob = next(a for a in result if a.name == "Bob")
        assert bob.affiliation == "Harvard"

    def test_backfill_is_case_insensitive(self):
        """Back-fill matches author names case-insensitively."""
        base = [_a("alice smith"), _a("Bob")]
        incoming = [_a("Alice Smith", affiliation="MIT")]
        # base wins (tie -> base), Alice's affiliation is back-filled.
        result = merge_authors(base, incoming)
        alice = next(a for a in result if a.name.lower() == "alice smith")
        assert alice.affiliation == "MIT"

    def test_backfill_does_not_overwrite_existing_affiliation(self):
        """Back-fill only fills in missing affiliations, not overwrites."""
        base = [_a("Alice", affiliation="MIT"), _a("Bob"), _a("Charlie")]
        incoming = [_a("Alice", affiliation="Stanford")]
        result = merge_authors(base, incoming)
        alice = next(a for a in result if a.name == "Alice")
        assert alice.affiliation == "MIT"  # not overwritten

    def test_backfill_when_incoming_wins(self):
        """Back-fill works when incoming list is the winner."""
        base = [_a("Alice", affiliation="MIT")]
        incoming = [_a("Alice"), _a("Bob"), _a("Charlie")]
        # incoming wins (larger), Alice's affiliation back-filled from base.
        result = merge_authors(base, incoming)
        assert len(result) == 3
        alice = next(a for a in result if a.name == "Alice")
        assert alice.affiliation == "MIT"

    def test_no_backfill_when_loser_has_no_affiliations(self):
        """No back-fill occurs when the loser list has no affiliations."""
        base = [_a("Alice"), _a("Bob"), _a("Charlie")]
        incoming = [_a("Alice")]
        result = merge_authors(base, incoming)
        for a in result:
            assert a.affiliation is None
