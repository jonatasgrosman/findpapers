"""Tests for enrichment utilities."""

from findpapers.utils import enrichment_util


def test_extract_metadata_from_html():
    html = """
    <html>
      <head>
        <meta name="citation_title" content="My Paper" />
        <meta name="citation_author" content="Alice" />
        <meta name="citation_author" content="Bob" />
        <meta name="citation_doi" content="10.1/abc" />
        <meta name="citation_abstract" content="Abstract" />
        <meta name="citation_journal_title" content="Journal" />
        <meta name="citation_publisher" content="Publisher" />
      </head>
    </html>
    """
    metadata = enrichment_util.extract_metadata_from_html(html)
    assert metadata["citation_title"] == "My Paper"
    assert metadata["citation_doi"] == "10.1/abc"
    assert metadata["citation_abstract"] == "Abstract"
    assert metadata["citation_journal_title"] == "Journal"
    assert metadata["citation_publisher"] == "Publisher"
    assert metadata["citation_author"] == ["Alice", "Bob"]


def test_build_paper_from_metadata():
    metadata = {
        "citation_title": "My Paper",
        "citation_author": ["Alice", "Bob"],
        "citation_doi": "10.1/abc",
        "citation_abstract": "Abstract",
        "citation_journal_title": "Journal",
        "citation_publisher": "Publisher",
        "citation_publication_date": "2022-01-15",
        "citation_pdf_url": "https://example.com/paper.pdf",
        "citation_keywords": "AI, ML",
    }
    paper = enrichment_util.build_paper_from_metadata(metadata, "https://example.com")
    assert paper is not None
    assert paper.title == "My Paper"
    assert paper.abstract == "Abstract"
    assert paper.doi == "10.1/abc"
    assert paper.publication is not None
    assert paper.publication.title == "Journal"
    assert paper.publication.publisher == "Publisher"
    assert paper.publication_date is not None
    assert "https://example.com" in paper.urls
    assert "https://example.com/paper.pdf" in paper.urls
    assert paper.keywords == {"AI", "ML"}


def test_enrich_from_sources_skips_pdf(monkeypatch):
    metadata = {"citation_title": "My Paper"}

    def mock_fetch(url, timeout=None):
        return metadata

    monkeypatch.setattr(enrichment_util, "fetch_metadata", mock_fetch)
    paper = enrichment_util.enrich_from_sources(
        urls=["https://example.com/paper.pdf", "https://example.com"],
        timeout=1.0,
    )
    assert paper is not None
    assert paper.title == "My Paper"
