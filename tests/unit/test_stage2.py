import pytest

from findpapers import SearchRunner


def test_search_runner_raises_for_unknown_database():
    with pytest.raises(ValueError):
        SearchRunner(databases=["unknown"]).run()
