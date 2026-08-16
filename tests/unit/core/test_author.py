"""Unit tests for the Author model."""

import pytest

from findpapers.core.author import Author
from findpapers.exceptions import ModelValidationError
from findpapers.utils.merge import merge_authors


class TestAuthorInit:
    """Tests for Author construction."""

    def test_name_only(self):
        """Author can be created with just a name."""
        author = Author(name="Alice Smith")
        assert author.name == "Alice Smith"
        assert author.affiliation is None

    def test_name_and_affiliation(self):
        """Author can be created with name and affiliation."""
        author = Author(name="Alice Smith", affiliation="MIT")
        assert author.name == "Alice Smith"
        assert author.affiliation == "MIT"

    def test_empty_name_raises(self):
        """An empty name raises ModelValidationError."""
        with pytest.raises(ModelValidationError, match="Author name cannot be empty"):
            Author(name="")

    def test_whitespace_name_raises(self):
        """A whitespace-only name raises ModelValidationError."""
        with pytest.raises(ModelValidationError, match="Author name cannot be empty"):
            Author(name="   ")


class TestAuthorStr:
    """Tests for Author.__str__."""

    def test_str_returns_name(self):
        """str(author) returns the author name for backward compatibility."""
        author = Author(name="Alice Smith")
        assert str(author) == "Alice Smith"

    def test_str_ignores_affiliation(self):
        """str(author) does not include affiliation."""
        author = Author(name="Alice Smith", affiliation="MIT")
        assert str(author) == "Alice Smith"


class TestAuthorEquality:
    """Tests for Author.__eq__ and __hash__."""

    def test_equal_same_name(self):
        """Authors with the same name are equal regardless of case."""
        a = Author(name="Alice Smith")
        b = Author(name="alice smith")
        assert a == b

    def test_equal_different_affiliation(self):
        """Authors with same name but different affiliation are still equal."""
        a = Author(name="Alice Smith", affiliation="MIT")
        b = Author(name="Alice Smith", affiliation="Stanford")
        assert a == b

    def test_not_equal_different_name(self):
        """Authors with different names are not equal."""
        a = Author(name="Alice Smith")
        b = Author(name="Bob Jones")
        assert a != b

    def test_hash_same_for_equal(self):
        """Equal authors have the same hash."""
        a = Author(name="Alice Smith")
        b = Author(name="alice smith")
        assert hash(a) == hash(b)

    def test_usable_in_set(self):
        """Authors can be used in sets; duplicates collapse."""
        authors = {Author(name="Alice"), Author(name="alice"), Author(name="Bob")}
        assert len(authors) == 2


class TestAuthorSerialization:
    """Tests for to_dict / from_dict."""

    def test_to_dict(self):
        """to_dict returns name and affiliation."""
        author = Author(name="Alice", affiliation="MIT")
        d = author.to_dict()
        assert d == {"name": "Alice", "affiliation": "MIT"}

    def test_to_dict_no_affiliation(self):
        """to_dict with no affiliation omits the affiliation key."""
        author = Author(name="Alice")
        d = author.to_dict()
        assert d == {"name": "Alice"}
        assert "affiliation" not in d

    def test_from_dict(self):
        """from_dict reconstructs an Author from a dict."""
        data = {"name": "Alice", "affiliation": "MIT"}
        author = Author.from_dict(data)
        assert author.name == "Alice"
        assert author.affiliation == "MIT"

    def test_roundtrip(self):
        """to_dict -> from_dict produces an equal Author."""
        original = Author(name="Alice", affiliation="MIT")
        restored = Author.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.affiliation == original.affiliation


class TestMergeAuthorsAffiliation:
    """Tests for merge_authors affiliation back-fill logic."""

    def test_backfill_affiliation_from_loser(self):
        """Winner list gains affiliations from the loser via name matching."""
        base = [
            Author(name="Alice", affiliation="MIT"),
            Author(name="Bob"),
            Author(name="Charlie", affiliation="Stanford"),
        ]
        incoming = [Author(name="Bob", affiliation="Harvard")]
        result = merge_authors(base, incoming)
        bob = next(a for a in result if a.name == "Bob")
        assert bob.affiliation == "Harvard"

    def test_prefers_list_with_more_affiliations_on_tie(self):
        """On equal length, the list with more affiliations wins."""
        base = [Author(name="Alice"), Author(name="Bob")]
        incoming = [
            Author(name="Alice", affiliation="MIT"),
            Author(name="Bob", affiliation="Stanford"),
        ]
        result = merge_authors(base, incoming)
        assert result[0].affiliation == "MIT"
        assert result[1].affiliation == "Stanford"
