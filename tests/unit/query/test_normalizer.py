"""Tests for QueryNormalizer."""

from __future__ import annotations

import pytest

from findpapers.query.normalizer import QueryNormalizer


class TestQueryNormalizer:
    """Test query normalization."""

    @pytest.fixture
    def normalizer(self) -> QueryNormalizer:
        """Return a QueryNormalizer instance."""
        return QueryNormalizer()

    # ------------------------------------------------------------------
    # Already-canonical queries: must pass through unchanged

    def test_canonical_single_term_unchanged(self, normalizer: QueryNormalizer) -> None:
        """Test that a canonical single-term query is returned unchanged."""
        assert normalizer.normalize("[machine learning]") == "[machine learning]"

    def test_canonical_two_terms_unchanged(self, normalizer: QueryNormalizer) -> None:
        """Test that a canonical two-term query is returned unchanged."""
        assert normalizer.normalize("[DL] OR [ML]") == "[DL] OR [ML]"

    def test_canonical_with_filter_unchanged(self, normalizer: QueryNormalizer) -> None:
        """Test that a canonical query with filter code is returned unchanged."""
        assert normalizer.normalize("ti[neural network]") == "ti[neural network]"

    def test_canonical_complex_query_unchanged(self, normalizer: QueryNormalizer) -> None:
        """Test that a complex canonical query is returned unchanged."""
        query = "[deep learning] AND ([image classification] OR [object detection])"
        assert normalizer.normalize(query) == query

    # ------------------------------------------------------------------
    # Double-quote conversions

    def test_single_quoted_term_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that a single double-quoted term is converted to brackets."""
        assert normalizer.normalize('"machine learning"') == "[machine learning]"

    def test_two_quoted_terms_or_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that double-quoted terms with OR connector are converted."""
        assert normalizer.normalize('"DL" OR "ML"') == "[DL] OR [ML]"

    def test_two_quoted_terms_and_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that double-quoted terms with AND connector are converted."""
        assert (
            normalizer.normalize('"deep learning" AND "healthcare"')
            == "[deep learning] AND [healthcare]"
        )

    def test_quoted_term_with_filter_prefix_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that a double-quoted term preceded by a filter code is converted."""
        assert normalizer.normalize('ti"neural network"') == "ti[neural network]"

    def test_quoted_terms_mixed_operators_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that multiple quoted terms with mixed operators are converted."""
        result = normalizer.normalize('"deep learning" AND NOT "shallow learning"')
        assert result == "[deep learning] AND NOT [shallow learning]"

    def test_quoted_terms_with_grouping_converted(self, normalizer: QueryNormalizer) -> None:
        """Test that quoted terms inside parentheses are converted."""
        result = normalizer.normalize('"AI" AND ("ML" OR "DL")')
        assert result == "[AI] AND ([ML] OR [DL])"

    def test_quoted_terms_nested_groups(self, normalizer: QueryNormalizer) -> None:
        """Test quoted terms in nested groups are all converted."""
        result = normalizer.normalize(
            '"transformer" AND ("vision" OR ("detection" AND "segmentation"))'
        )
        assert result == "[transformer] AND ([vision] OR ([detection] AND [segmentation]))"

    def test_quoted_terms_multiple_groups_with_and_not(self, normalizer: QueryNormalizer) -> None:
        """Test quoted terms across multiple groups including AND NOT."""
        result = normalizer.normalize(
            '("deep learning" OR "machine learning") AND NOT ("survey" OR "review")'
        )
        assert result == "([deep learning] OR [machine learning]) AND NOT ([survey] OR [review])"

    def test_quoted_terms_filter_on_group(self, normalizer: QueryNormalizer) -> None:
        """Test that a filter code preceding a group with quoted terms is preserved."""
        result = normalizer.normalize('ti("neural network" OR "deep learning") AND abs"healthcare"')
        assert result == "ti([neural network] OR [deep learning]) AND abs[healthcare]"

    def test_quoted_terms_complex_boolean_with_subgroups(self, normalizer: QueryNormalizer) -> None:
        """Test a realistic multi-group query with double-quoted terms."""
        result = normalizer.normalize(
            '("natural language processing" OR "computational linguistics")'
            ' AND ("sentiment analysis" OR "text classification")'
            ' AND NOT "social media"'
        )
        assert result == (
            "([natural language processing] OR [computational linguistics])"
            " AND ([sentiment analysis] OR [text classification])"
            " AND NOT [social media]"
        )

    def test_quoted_terms_deeply_nested_subgroups(self, normalizer: QueryNormalizer) -> None:
        """Test quoted terms in three levels of nesting."""
        result = normalizer.normalize('"AI" OR ("ML" AND ("DL" OR ("CNN" AND "RNN")))')
        assert result == "[AI] OR ([ML] AND ([DL] OR ([CNN] AND [RNN])))"

    def test_quoted_terms_filter_codes_in_subgroups(self, normalizer: QueryNormalizer) -> None:
        """Test filter codes applied to quoted terms inside nested groups."""
        result = normalizer.normalize(
            'ti("BERT" OR "GPT") AND (abs"fine-tuning" OR key"transfer learning")'
        )
        assert result == "ti([BERT] OR [GPT]) AND (abs[fine-tuning] OR key[transfer learning])"

    # ------------------------------------------------------------------
    # Bare-text conversions

    def test_bare_single_word_wrapped(self, normalizer: QueryNormalizer) -> None:
        """Test that a bare single word is wrapped in brackets."""
        assert normalizer.normalize("AI") == "[AI]"

    def test_bare_multi_word_wrapped_as_single_term(self, normalizer: QueryNormalizer) -> None:
        """Test that bare multi-word text is treated as a single term."""
        assert normalizer.normalize("Deep learning") == "[Deep learning]"

    def test_bare_text_with_surrounding_whitespace(self, normalizer: QueryNormalizer) -> None:
        """Test that surrounding whitespace is stripped before wrapping."""
        assert normalizer.normalize("  Deep learning  ") == "[Deep learning]"

    # ------------------------------------------------------------------
    # Edge cases

    def test_empty_string_returned_unchanged(self, normalizer: QueryNormalizer) -> None:
        """Test that an empty string is returned as-is (validator will handle it)."""
        assert normalizer.normalize("") == ""

    def test_whitespace_only_returned_stripped(self, normalizer: QueryNormalizer) -> None:
        """Test that a whitespace-only string is stripped and returned as-is."""
        assert normalizer.normalize("   ") == ""

    def test_mixed_brackets_and_quotes_uses_bracket_path(self, normalizer: QueryNormalizer) -> None:
        """Test that a query with brackets passes through even if it also has quotes."""
        # Once a [ is detected the query is assumed canonical and returned as-is
        query = '[DL] OR "ML"'
        assert normalizer.normalize(query) == query

    def test_bare_text_with_unbalanced_parens_passes_through(
        self, normalizer: QueryNormalizer
    ) -> None:
        """Test that bare text containing parentheses is not wrapped.

        A string like ``((bad query`` looks like a broken structured expression,
        so it is returned unchanged to let the validator raise the appropriate
        unbalanced-parentheses error.
        """
        assert normalizer.normalize("((bad query") == "((bad query"

    def test_bare_text_with_balanced_parens_passes_through(
        self, normalizer: QueryNormalizer
    ) -> None:
        """Test that bare text with balanced parentheses is not wrapped.

        Balanced parentheses still signal the caller intended a grouped query,
        so the string is returned as-is for the validator to process.
        """
        assert normalizer.normalize("(term a OR term b)") == "(term a OR term b)"
