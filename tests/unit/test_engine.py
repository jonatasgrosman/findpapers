"""Unit tests for the Engine facade."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

import findpapers
from findpapers.core.paper import Paper
from findpapers.core.search_result import SearchResult
from findpapers.engine import Engine
from findpapers.runners.snowball_runner import SnowballRunner

_FINDPAPERS_ENV_VARS = {
    "FINDPAPERS_IEEE_API_TOKEN": "",
    "FINDPAPERS_SCOPUS_API_TOKEN": "",
    "FINDPAPERS_PUBMED_API_TOKEN": "",
    "FINDPAPERS_OPENALEX_API_TOKEN": "",
    "FINDPAPERS_EMAIL": "",
    "FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN": "",
    "FINDPAPERS_WOS_API_TOKEN": "",
    "FINDPAPERS_PROXY": "",
    "FINDPAPERS_SSL_VERIFY": "",
}


@pytest.fixture(autouse=True)
def _clear_findpapers_env():
    """Clear FINDPAPERS_* environment variables for every test in this module."""
    with patch.dict(os.environ, _FINDPAPERS_ENV_VARS, clear=False):
        yield


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


class TestEngineInit:
    """Tests for Engine initialisation and stored configuration."""

    def test_default_values(self):
        """Engine defaults all API keys to None, ssl_verify to True."""
        # Ensure no FINDPAPERS_* env vars leak from other tests.
        env_clear = {
            "FINDPAPERS_IEEE_API_TOKEN": "",
            "FINDPAPERS_SCOPUS_API_TOKEN": "",
            "FINDPAPERS_PUBMED_API_TOKEN": "",
            "FINDPAPERS_OPENALEX_API_TOKEN": "",
            "FINDPAPERS_EMAIL": "",
            "FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN": "",
            "FINDPAPERS_WOS_API_TOKEN": "",
            "FINDPAPERS_PROXY": "",
            "FINDPAPERS_SSL_VERIFY": "",
        }
        with patch.dict(os.environ, env_clear, clear=False):
            engine = Engine()

        assert engine._ieee_api_key is None
        assert engine._scopus_api_key is None
        assert engine._pubmed_api_key is None
        assert engine._openalex_api_key is None
        assert engine._email is None
        assert engine._semantic_scholar_api_key is None
        assert engine._proxy is None
        assert engine._ssl_verify is True

    def test_custom_values(self):
        """Engine stores the supplied configuration values."""
        engine = Engine(
            ieee_api_key="ieee-k",
            scopus_api_key="scopus-k",
            pubmed_api_key="pubmed-k",
            openalex_api_key="oalex-k",
            email="me@example.com",
            semantic_scholar_api_key="s2-k",
            proxy="http://proxy:8080",
            ssl_verify=False,
        )

        assert engine._ieee_api_key == "ieee-k"
        assert engine._scopus_api_key == "scopus-k"
        assert engine._pubmed_api_key == "pubmed-k"
        assert engine._openalex_api_key == "oalex-k"
        assert engine._email == "me@example.com"
        assert engine._semantic_scholar_api_key == "s2-k"
        assert engine._proxy == "http://proxy:8080"
        assert engine._ssl_verify is False

    def test_keyword_only_arguments(self):
        """Engine constructor only accepts keyword arguments."""
        with pytest.raises(TypeError):
            Engine("ieee-key")  # type: ignore[misc]

    def test_env_var_fallbacks(self):
        """Engine reads missing values from FINDPAPERS_* env vars."""
        env = {
            "FINDPAPERS_IEEE_API_TOKEN": "env-ieee",
            "FINDPAPERS_SCOPUS_API_TOKEN": "env-scopus",
            "FINDPAPERS_PUBMED_API_TOKEN": "env-pubmed",
            "FINDPAPERS_OPENALEX_API_TOKEN": "env-oalex",
            "FINDPAPERS_EMAIL": "env@example.com",
            "FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN": "env-s2",
            "FINDPAPERS_WOS_API_TOKEN": "env-wos",
            "FINDPAPERS_PROXY": "http://env-proxy:8080",
        }
        with patch.dict(os.environ, env, clear=False):
            engine = Engine()

        assert engine._ieee_api_key == "env-ieee"
        assert engine._scopus_api_key == "env-scopus"
        assert engine._pubmed_api_key == "env-pubmed"
        assert engine._openalex_api_key == "env-oalex"
        assert engine._email == "env@example.com"
        assert engine._semantic_scholar_api_key == "env-s2"
        assert engine._wos_api_key == "env-wos"
        assert engine._proxy == "http://env-proxy:8080"

    def test_explicit_values_override_env(self):
        """Explicit arguments take precedence over environment variables."""
        env = {
            "FINDPAPERS_IEEE_API_TOKEN": "env-ieee",
            "FINDPAPERS_EMAIL": "env@example.com",
        }
        with patch.dict(os.environ, env, clear=False):
            engine = Engine(ieee_api_key="explicit-ieee", email="explicit@example.com")

        assert engine._ieee_api_key == "explicit-ieee"
        assert engine._email == "explicit@example.com"

    def test_ssl_verify_env_false(self):
        """FINDPAPERS_SSL_VERIFY=false disables SSL verification."""
        for val in ("false", "0", "no", "False", "NO"):
            with patch.dict(os.environ, {"FINDPAPERS_SSL_VERIFY": val}, clear=False):
                engine = Engine()
            assert engine._ssl_verify is False, f"Expected False for SSL_VERIFY={val!r}"

    def test_ssl_verify_env_true(self):
        """FINDPAPERS_SSL_VERIFY=true keeps SSL verification enabled."""
        with patch.dict(os.environ, {"FINDPAPERS_SSL_VERIFY": "true"}, clear=False):
            engine = Engine()
        assert engine._ssl_verify is True

    def test_ssl_verify_explicit_overrides_env(self):
        """Explicit ssl_verify=False overrides the environment variable."""
        with patch.dict(os.environ, {"FINDPAPERS_SSL_VERIFY": "true"}, clear=False):
            engine = Engine(ssl_verify=False)
        assert engine._ssl_verify is False

    def test_ssl_verify_false_logs_warning(self, caplog):
        """Engine logs a security warning when SSL verification is disabled."""
        with caplog.at_level("WARNING", logger="findpapers.engine"):
            Engine(ssl_verify=False)
        assert any("SSL certificate verification is disabled" in msg for msg in caplog.messages)

    def test_ssl_verify_true_no_warning(self, caplog):
        """Engine does not log a warning when SSL verification is enabled."""
        env_clear = {"FINDPAPERS_SSL_VERIFY": ""}
        with (
            patch.dict(os.environ, env_clear, clear=False),
            caplog.at_level("WARNING", logger="findpapers.engine"),
        ):
            Engine(ssl_verify=True)
        assert not any("SSL certificate verification" in msg for msg in caplog.messages)

    def test_ssl_verify_env_false_logs_warning(self, caplog):
        """Engine logs a warning when SSL is disabled via environment variable."""
        with (
            patch.dict(os.environ, {"FINDPAPERS_SSL_VERIFY": "false"}, clear=False),
            caplog.at_level("WARNING", logger="findpapers.engine"),
        ):
            Engine()
        assert any("SSL certificate verification is disabled" in msg for msg in caplog.messages)


# ---------------------------------------------------------------------------
# search()
# ---------------------------------------------------------------------------


class TestEngineSearch:
    """Tests for Engine.search()."""

    def test_search_delegates_to_runner_with_engine_keys(self):
        """search() passes engine API keys and per-call params to SearchRunner."""
        engine = Engine(
            ieee_api_key="ieee-k",
            scopus_api_key="scopus-k",
            pubmed_api_key="pubmed-k",
            openalex_api_key="oalex-k",
            email="me@example.com",
            semantic_scholar_api_key="s2-k",
        )
        fake_search = MagicMock(spec=SearchResult)
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = fake_search
            mock_cls.return_value = mock_runner

            result = engine.search(
                "ti[ml]",
                databases=["arxiv"],
                max_papers_per_database=50,
                num_workers=3,
                verbose=True,
            )

        mock_cls.assert_called_once_with(
            query="ti[ml]",
            databases=["arxiv"],
            max_papers_per_database=50,
            ieee_api_key="ieee-k",
            scopus_api_key="scopus-k",
            pubmed_api_key="pubmed-k",
            openalex_api_key="oalex-k",
            email="me@example.com",
            semantic_scholar_api_key="s2-k",
            wos_api_key=None,
            num_workers=3,
            since=None,
            until=None,
            enrichment_databases=["crossref", "web_scraping"],
            max_cited_by=100,
            proxy=None,
            ssl_verify=True,
        )
        mock_runner.run.assert_called_once_with(verbose=True, show_progress=True)
        assert result is fake_search

    def test_search_default_per_call_params(self):
        """num_workers defaults to 1, verbose to False."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]")

        _, kwargs = mock_cls.call_args
        assert kwargs["num_workers"] == 1
        mock_runner.run.assert_called_once_with(verbose=False, show_progress=True)

    def test_search_show_progress_false(self):
        """show_progress=False is forwarded to SearchRunner.run()."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]", show_progress=False)

        mock_runner.run.assert_called_once_with(verbose=False, show_progress=False)


# ---------------------------------------------------------------------------
# download()
# ---------------------------------------------------------------------------


class TestEngineDownload:
    """Tests for Engine.download()."""

    def test_download_uses_engine_proxy_and_ssl(self, make_paper):
        """download() forwards engine proxy and ssl_verify to DownloadRunner."""
        engine = Engine(
            proxy="http://proxy:8080",
            ssl_verify=False,
        )
        fake_metrics = {"total_papers": 1, "downloaded_papers": 1}
        with patch("findpapers.engine.DownloadRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = fake_metrics
            mock_cls.return_value = mock_runner

            papers = [make_paper()]
            result = engine.download(
                papers,
                "/tmp/pdfs",
                num_workers=2,
                timeout=20.0,
                verbose=True,
            )

        mock_cls.assert_called_once_with(
            papers=papers,
            output_directory="/tmp/pdfs",
            num_workers=2,
            timeout=20.0,
            proxy="http://proxy:8080",
            ssl_verify=False,
        )
        mock_runner.run.assert_called_once_with(verbose=True, show_progress=True)
        assert result == fake_metrics

    def test_download_default_per_call_params(self):
        """num_workers defaults to 1, verbose to False, timeout to 30.0."""
        engine = Engine()
        with patch("findpapers.engine.DownloadRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {}
            mock_cls.return_value = mock_runner

            engine.download([], "/tmp/out")

        _, kwargs = mock_cls.call_args
        assert kwargs["num_workers"] == 1
        assert kwargs["timeout"] == 30.0
        mock_runner.run.assert_called_once_with(verbose=False, show_progress=True)

    def test_download_show_progress_false(self):
        """show_progress=False is forwarded to DownloadRunner.run()."""
        engine = Engine()
        with patch("findpapers.engine.DownloadRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = {}
            mock_cls.return_value = mock_runner

            engine.download([], "/tmp/out", show_progress=False)

        mock_runner.run.assert_called_once_with(verbose=False, show_progress=False)


# ---------------------------------------------------------------------------
# search() enrichment_databases forwarding
# ---------------------------------------------------------------------------


class TestEngineSearchEnrichmentDatabases:
    """Tests that Engine.search() forwards enrichment_databases to SearchRunner."""

    def test_enrichment_databases_forwarded(self):
        """enrichment_databases is passed through to SearchRunner."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]", enrichment_databases=["arxiv", "pubmed"])

        _, kwargs = mock_cls.call_args
        assert kwargs["enrichment_databases"] == ["arxiv", "pubmed"]

    def test_enrichment_databases_default_is_list(self):
        """enrichment_databases defaults to DEFAULT_ENRICHMENT_DATABASES (not None)."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]")

        _, kwargs = mock_cls.call_args
        assert kwargs["enrichment_databases"] == ["crossref", "web_scraping"]

    def test_enrichment_databases_none_disables_enrichment(self):
        """enrichment_databases=None is forwarded to SearchRunner (disables enrichment)."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]", enrichment_databases=None)

        _, kwargs = mock_cls.call_args
        assert kwargs["enrichment_databases"] is None

    def test_enrichment_databases_empty_list_disables_enrichment(self):
        """enrichment_databases=[] is forwarded to SearchRunner to disable enrichment."""
        engine = Engine()
        with patch("findpapers.engine.SearchRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock(spec=SearchResult)
            mock_cls.return_value = mock_runner

            engine.search("[ml]", enrichment_databases=[])

        _, kwargs = mock_cls.call_args
        assert kwargs["enrichment_databases"] == []


# ---------------------------------------------------------------------------
# get()
# ---------------------------------------------------------------------------


class TestEngineGet:
    """Tests for Engine.get()."""

    def test_fetch_forwards_timeout(self):
        """get() forwards per-call timeout to GetRunner."""
        engine = Engine()
        fake_paper = MagicMock(spec=Paper)
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = fake_paper
            mock_cls.return_value = mock_runner

            result = engine.get("10.1234/test", timeout=30.0, verbose=True)

        _, call_kwargs = mock_cls.call_args
        assert call_kwargs["identifier"] == "10.1234/test"
        assert call_kwargs["timeout"] == 30.0
        mock_runner.run.assert_called_once_with(verbose=True, max_cited_by=100)
        assert result is fake_paper

    def test_fetch_returns_none_when_not_found(self):
        """get() returns None when the identifier cannot be resolved."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            result = engine.get("10.9999/nonexistent")

        assert result is None

    def test_fetch_default_per_call_params(self):
        """get() verbose defaults to False, timeout to 10.0."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("10.1234/test")

        _, kwargs = mock_cls.call_args
        assert kwargs["timeout"] == 10.0
        mock_runner.run.assert_called_once_with(verbose=False, max_cited_by=100)

    def test_get_forwards_doi_org_url(self):
        """get() passes doi.org URLs to GetRunner as the identifier."""
        engine = Engine()
        fake_paper = MagicMock(spec=Paper)
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = fake_paper
            mock_cls.return_value = mock_runner

            result = engine.get("https://doi.org/10.1038/nature12373")

        _, kwargs = mock_cls.call_args
        assert kwargs["identifier"] == "https://doi.org/10.1038/nature12373"
        assert result is fake_paper

    def test_get_forwards_landing_page_url(self):
        """get() passes landing-page URLs to GetRunner as the identifier."""
        engine = Engine()
        fake_paper = MagicMock(spec=Paper)
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = fake_paper
            mock_cls.return_value = mock_runner

            result = engine.get("https://arxiv.org/abs/1706.03762")

        _, kwargs = mock_cls.call_args
        assert kwargs["identifier"] == "https://arxiv.org/abs/1706.03762"
        assert result is fake_paper

    def test_get_forwards_proxy_and_ssl(self):
        """get() passes proxy and ssl_verify from the Engine to GetRunner."""
        engine = Engine(proxy="http://proxy:8080", ssl_verify=False)
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("https://arxiv.org/abs/1706.03762")

        _, kwargs = mock_cls.call_args
        assert kwargs["proxy"] == "http://proxy:8080"
        assert kwargs["ssl_verify"] is False

    def test_get_forwards_databases_param(self):
        """get() passes the databases list to GetRunner."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("10.1234/test", databases=["arxiv", "pubmed"])

        _, kwargs = mock_cls.call_args
        assert kwargs["databases"] == ["arxiv", "pubmed"]

    def test_get_databases_defaults_to_none(self):
        """get() passes databases=None to GetRunner when not specified."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("10.1234/test")

        _, kwargs = mock_cls.call_args
        assert kwargs["databases"] is None

    def test_get_forwards_crossref_in_databases(self):
        """get() forwards databases list including 'crossref' to GetRunner."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("10.1234/test", databases=["crossref"])

        _, kwargs = mock_cls.call_args
        assert kwargs["databases"] == ["crossref"]

    def test_get_forwards_web_scraping_in_databases(self):
        """get() forwards databases list including 'web_scraping' to GetRunner."""
        engine = Engine()
        with patch("findpapers.engine.GetRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = None
            mock_cls.return_value = mock_runner

            engine.get("https://arxiv.org/abs/1706.03762", databases=["web_scraping"])

        _, kwargs = mock_cls.call_args
        assert kwargs["databases"] == ["web_scraping"]


# ---------------------------------------------------------------------------
# Top-level import
# ---------------------------------------------------------------------------


class TestEngineImport:
    """Verify that Engine is accessible from the findpapers namespace."""

    def test_engine_importable(self):
        """findpapers.Engine is the Engine class."""

        assert findpapers.Engine is Engine


# ---------------------------------------------------------------------------
# Snowball
# ---------------------------------------------------------------------------


class TestEngineSnowball:
    """Tests for Engine.snowball()."""

    def test_snowball_delegates_to_runner(self, make_paper):
        """snowball() creates a SnowballRunner and calls run()."""
        engine = Engine()
        seed = make_paper("Seed", doi="10.1000/seed")

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_graph = MagicMock()
            mock_runner.run.return_value = mock_graph
            mock_cls.return_value = mock_runner

            result = engine.snowball(seed)

        mock_cls.assert_called_once()
        mock_runner.run.assert_called_once_with(verbose=False, show_progress=True)
        assert result is mock_graph

    def test_snowball_passes_parameters(self, make_paper):
        """snowball() passes configuration to SnowballRunner."""
        engine = Engine(openalex_api_key="oakey", email="me@test.com")
        seed = make_paper("Seed", doi="10.1000/seed")

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock()
            mock_cls.return_value = mock_runner

            engine.snowball(
                seed,
                max_depth=2,
                direction="backward",
                num_workers=3,
                verbose=True,
            )

        _, kwargs = mock_cls.call_args
        assert kwargs["max_depth"] == 2
        assert kwargs["direction"] == "backward"
        assert kwargs["num_workers"] == 3
        assert kwargs["openalex_api_key"] == "oakey"
        assert kwargs["email"] == "me@test.com"
        mock_runner.run.assert_called_once_with(verbose=True, show_progress=True)

    def test_snowball_since_until_forwarded(self, make_paper):
        """snowball() forwards since and until to SnowballRunner."""
        import datetime as _dt

        engine = Engine()
        seed = make_paper("Seed", doi="10.1000/seed")
        since = _dt.date(2020, 1, 1)
        until = _dt.date(2023, 12, 31)

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock()
            mock_cls.return_value = mock_runner

            engine.snowball(seed, since=since, until=until)

        _, kwargs = mock_cls.call_args
        assert kwargs["since"] is since
        assert kwargs["until"] is until

    def test_snowball_since_until_none_by_default(self, make_paper):
        """snowball() passes None for since and until when not provided."""
        engine = Engine()
        seed = make_paper("Seed", doi="10.1000/seed")

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock()
            mock_cls.return_value = mock_runner

            engine.snowball(seed)

        _, kwargs = mock_cls.call_args
        assert kwargs["since"] is None
        assert kwargs["until"] is None

    def test_snowball_accepts_list_of_papers(self, make_paper):
        """snowball() accepts a list of papers."""
        engine = Engine()
        seeds = [
            make_paper("Seed 1", doi="10.1000/s1"),
            make_paper("Seed 2", doi="10.1000/s2"),
        ]

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock()
            mock_cls.return_value = mock_runner

            engine.snowball(seeds)

        call_args = mock_cls.call_args
        assert call_args[1]["seed_papers"] is seeds

    def test_snowball_show_progress_false(self, make_paper):
        """show_progress=False is forwarded to SnowballRunner.run()."""
        engine = Engine()
        seed = make_paper("Seed", doi="10.1000/seed")

        with patch("findpapers.engine.SnowballRunner") as mock_cls:
            mock_runner = MagicMock()
            mock_runner.run.return_value = MagicMock()
            mock_cls.return_value = mock_runner

            engine.snowball(seed, show_progress=False)

        mock_runner.run.assert_called_once_with(verbose=False, show_progress=False)


class TestSnowballImport:
    """Verify snowball-related classes are accessible from findpapers namespace."""

    def test_snowball_runner_importable(self):
        """findpapers.SnowballRunner is accessible."""

        assert findpapers.SnowballRunner is SnowballRunner


class TestSaveFunctionsImport:
    """Verify persistence functions are accessible from findpapers namespace."""

    def test_save_to_json_importable(self):
        """findpapers.save_to_json is accessible."""

        assert callable(findpapers.save_to_json)

    def test_load_from_json_importable(self):
        """findpapers.load_from_json is accessible."""

        assert callable(findpapers.load_from_json)

    def test_save_to_bibtex_importable(self):
        """findpapers.save_to_bibtex is accessible."""

        assert callable(findpapers.save_to_bibtex)

    def test_load_from_bibtex_importable(self):
        """findpapers.load_from_bibtex is accessible."""

        assert callable(findpapers.load_from_bibtex)

    def test_save_to_csv_importable(self):
        """findpapers.save_to_csv is accessible."""

        assert callable(findpapers.save_to_csv)

    def test_load_from_csv_importable(self):
        """findpapers.load_from_csv is accessible."""

        assert callable(findpapers.load_from_csv)


# ---------------------------------------------------------------------------
# Save / Load (top-level functions)
# ---------------------------------------------------------------------------


class TestSaveToJson:
    """Tests for findpapers.save_to_json top-level function."""

    def test_save_search_result(self, make_paper, tmp_path):
        """SearchResult is saved to a JSON file."""

        search = SearchResult(query="[test]", databases=["arxiv"])
        search.add_paper(make_paper(doi="10.1/a"))
        path = str(tmp_path / "search.json")
        findpapers.save_to_json(search, path)
        assert os.path.exists(path)

    def test_save_paper_list(self, make_paper, tmp_path):
        """A plain list of papers is saved to a JSON file."""

        papers = [make_paper(doi="10.1/a"), make_paper(title="Paper B", doi="10.1/b")]
        path = str(tmp_path / "papers.json")
        findpapers.save_to_json(papers, path)
        assert os.path.exists(path)


class TestSaveToBibtex:
    """Tests for findpapers.save_to_bibtex top-level function."""

    def test_save_paper_list(self, make_paper, tmp_path):
        """A plain list of papers is saved to a BibTeX file."""

        papers = [make_paper(doi="10.1/a")]
        path = str(tmp_path / "refs.bib")
        findpapers.save_to_bibtex(papers, path)
        with open(path, encoding="utf-8") as file_handle:
            content = file_handle.read()
        assert "@" in content

    def test_empty_list_produces_empty_file(self, tmp_path):
        """An empty paper list creates an empty file."""

        path = str(tmp_path / "empty.bib")
        findpapers.save_to_bibtex([], path)
        with open(path, encoding="utf-8") as file_handle:
            content = file_handle.read()
        assert content == ""


class TestLoadFromBibtex:
    """Tests for findpapers.load_from_bibtex top-level function."""

    def test_round_trip(self, make_paper, tmp_path):
        """Papers survive save -> load round-trip."""

        papers = [make_paper(doi="10.1/a")]
        path = str(tmp_path / "refs.bib")
        findpapers.save_to_bibtex(papers, path)
        loaded = findpapers.load_from_bibtex(path)
        assert len(loaded) == 1
        assert loaded[0].title == papers[0].title


class TestLoadFromJson:
    """Tests for findpapers.load_from_json top-level function."""

    def test_round_trip_search_result(self, make_paper, tmp_path):
        """SearchResult survives save -> load round-trip."""

        search = SearchResult(query="[test]", databases=["arxiv"])
        search.add_paper(make_paper(doi="10.1/a"))
        path = str(tmp_path / "search.json")
        findpapers.save_to_json(search, path)

        loaded = findpapers.load_from_json(path)
        assert isinstance(loaded, SearchResult)
        assert len(loaded.papers) == 1

    def test_round_trip_paper_list(self, make_paper, tmp_path):
        """Paper list survives save -> load round-trip."""

        papers = [make_paper(doi="10.1/a")]
        path = str(tmp_path / "papers.json")
        findpapers.save_to_json(papers, path)

        loaded = findpapers.load_from_json(path)
        assert isinstance(loaded, list)
        assert len(loaded) == 1
        assert loaded[0].title == "Test Paper"


class TestSaveToCsv:
    """Tests for findpapers.save_to_csv top-level function."""

    def test_save_paper_list(self, make_paper, tmp_path):
        """A plain list of papers is saved to a CSV file."""

        papers = [make_paper(doi="10.1/a")]
        path = str(tmp_path / "papers.csv")
        findpapers.save_to_csv(papers, path)
        with open(path, encoding="utf-8") as fh:
            content = fh.read()
        assert "title" in content
        assert "Test Paper" in content

    def test_empty_list_produces_header_only(self, tmp_path):
        """An empty paper list creates a CSV with only the header."""

        path = str(tmp_path / "empty.csv")
        findpapers.save_to_csv([], path)
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().strip().splitlines()
        assert len(lines) == 1


class TestLoadFromCsv:
    """Tests for findpapers.load_from_csv top-level function."""

    def test_round_trip(self, make_paper, tmp_path):
        """Papers survive save -> load round-trip."""

        papers = [make_paper(doi="10.1/a")]
        path = str(tmp_path / "papers.csv")
        findpapers.save_to_csv(papers, path)
        loaded = findpapers.load_from_csv(path)
        assert len(loaded) == 1
        assert loaded[0].title == papers[0].title
