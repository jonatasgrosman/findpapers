from findpapers import SearchRunner
from findpapers.searchers import ArxivSearcher, PubmedSearcher


def test_fetch_stage_collects_results_and_keeps_partial_on_error(monkeypatch):
    def mock_arxiv_search(self):
        return [{"id": 1}, {"id": 2}]

    def mock_pubmed_search(self):
        raise RuntimeError("boom")

    monkeypatch.setattr(ArxivSearcher, "search", mock_arxiv_search)
    monkeypatch.setattr(PubmedSearcher, "search", mock_pubmed_search)

    runner = SearchRunner(databases=["arxiv", "pubmed"])
    runner.run()

    metrics = runner.get_metrics()
    assert metrics["papers_count"] == 2
    assert metrics["errors_total"] == 1
    assert metrics["searcher.arxiv.count"] == 2
    assert metrics["searcher.pubmed.errors"] == 1
    assert metrics["stage.fetch.runtime_seconds"] >= 0
