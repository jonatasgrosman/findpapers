#!/usr/bin/env python3
"""
Collect landing-page HTML for papers extracted from existing sample data.

For each database sample the script parses the raw API response, extracts
DOIs and landing-page URLs, fetches the HTML (or PDF header bytes) and
saves each page to a per-database subdirectory under ``tests/data/pages/``.

These fixtures are used by the enrichment and download runner tests to verify
behaviour without making live network requests.

Usage
-----
    python tests/data/pages/collect_pages.py              # collect all databases
    python tests/data/pages/collect_pages.py arxiv ieee   # collect specific ones

Saved layout
------------
    tests/data/pages/
        <database>/
            <sanitised_doi>.html      : HTML landing page (or empty on error)
            <sanitised_doi>.meta.json : URL, DOI, and HTTP status metadata
        collection_metadata.json      : overall run summary
"""

from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.parse
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent
OUTPUT_DIR = Path(__file__).parent
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.0  # seconds between requests (be polite)
MAX_PAGES_PER_DB = 10  # target number of successfully saved pages per database

ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
DOI_RE = re.compile(r"\b10\.\d{4,}/[^\s\"'<>,;)]+")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise(value: str) -> str:
    """Return a filesystem-safe version of *value*."""
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^\w.\-]", "_", value)[:120]


def _doi_to_url(doi: str) -> str:
    return f"https://doi.org/{doi}"


def _safe_get(url: str, *, timeout: int = REQUEST_TIMEOUT) -> requests.Response | None:
    """GET *url*, returning ``None`` on any error."""
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "findpapers/test-collector (academic research)"},
            allow_redirects=True,
        )
        return resp
    except Exception as exc:
        print(f"    [FAIL] Request error: {exc}")
        return None


def _save_page(
    db_dir: Path,
    key: str,
    url: str,
    doi: str | None,
    resp: requests.Response | None,
) -> dict:
    """Persist the response body and return a metadata dict."""
    db_dir.mkdir(parents=True, exist_ok=True)
    safe_key = _sanitise(key)

    meta: dict = {
        "key": key,
        "url": url,
        "doi": doi,
        "final_url": None,
        "status": None,
        "content_type": None,
        "size_bytes": 0,
        "error": None,
    }

    if resp is None:
        meta["error"] = "request_failed"
        (db_dir / f"{safe_key}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return meta

    meta["final_url"] = resp.url
    meta["status"] = resp.status_code
    content_type = resp.headers.get("content-type", "").lower()
    meta["content_type"] = content_type
    meta["size_bytes"] = len(resp.content)

    if "text/html" in content_type:
        (db_dir / f"{safe_key}.html").write_text(resp.text, encoding="utf-8", errors="replace")
    elif "application/pdf" in content_type:
        # Save only the first 4 KB of bytes: enough for tests, avoids large files
        (db_dir / f"{safe_key}.pdf.bin").write_bytes(resp.content[:4096])
        meta["truncated"] = True

    (db_dir / f"{safe_key}.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


# ---------------------------------------------------------------------------
# Per-database extractors
# ---------------------------------------------------------------------------


def _extract_arxiv(sample_path: Path) -> Iterator[tuple[str, str | None]]:
    """Yield (url, doi) for every entry in an arXiv XML sample."""
    tree = ET.parse(sample_path)
    root = tree.getroot()
    for entry in root.findall("atom:entry", ARXIV_NS):
        # Prefer alternate (HTML) link
        url = None
        for link in entry.findall("atom:link", ARXIV_NS):
            if link.get("rel") == "alternate":
                url = link.get("href")
                break
        if url is None:
            id_el = entry.find("atom:id", ARXIV_NS)
            url = id_el.text.strip() if id_el is not None and id_el.text else None
        doi_el = entry.find("arxiv:doi", ARXIV_NS)
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None
        if url:
            yield url, doi


def _extract_json_dois(
    sample_path: Path, url_fields: list[str], doi_fields: list[str]
) -> Iterator[tuple[str, str | None]]:
    """Generic extractor for JSON responses: yield (url, doi) for every item."""
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Various APIs wrap the list: OpenAlex -> "results", WoS -> "hits", etc.
        for key in ("results", "collection", "hits", "items", "papers", "data", "articles"):
            if isinstance(data.get(key), list):
                items = data[key]
                break

    for item in items:
        url = None
        for f in url_fields:
            parts = f.split(".")
            val = item
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if val and isinstance(val, str):
                url = val
                break
        doi = None
        for f in doi_fields:
            parts = f.split(".")
            val = item
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            if val and isinstance(val, str):
                raw = val.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                if raw.startswith("10."):
                    doi = raw
                break
        if url is None and doi:
            url = _doi_to_url(doi)
        if url:
            yield url, doi


def _extract_pubmed(sample_path: Path) -> Iterator[tuple[str, str | None]]:
    """Yield (url, doi) for every article in a PubMed XML file."""
    tree = ET.parse(sample_path)
    root = tree.getroot()
    for article in root.iter("PubmedArticle"):
        pmid_el = article.find(".//PMID")
        pmid = pmid_el.text.strip() if pmid_el is not None and pmid_el.text else None
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None
        doi = None
        for id_el in article.findall(".//ArticleId"):
            if id_el.get("IdType") == "doi" and id_el.text:
                doi = id_el.text.strip()
                break
        if url:
            yield url, doi


def _extract_scopus(sample_path: Path) -> Iterator[tuple[str, str | None]]:
    """Yield (url, doi) for every entry in a Scopus JSON response.

    Scopus wraps results in ``search-results.entry``.  The ``prism:url`` field
    is an internal API URL, so we construct a doi.org URL from ``prism:doi``.
    """
    data = json.loads(sample_path.read_text(encoding="utf-8"))
    entries = data.get("search-results", {}).get("entry", [])
    for entry in entries:
        doi = entry.get("prism:doi")
        if doi and str(doi).startswith("10."):
            yield _doi_to_url(doi), doi


# ---------------------------------------------------------------------------
# Database configurations
# ---------------------------------------------------------------------------

DB_CONFIGS: dict[str, dict] = {
    "arxiv": {
        "sample": "arxiv/sample_response.xml",
        "extractor": _extract_arxiv,
    },
    "ieee": {
        "sample": "ieee/sample_response.json",
        "extractor": lambda p: _extract_json_dois(
            p,
            url_fields=["html_url"],
            doi_fields=["doi"],
        ),
    },
    "pubmed": {
        "sample": "pubmed/efetch_response.xml",
        "extractor": _extract_pubmed,
    },
    "scopus": {
        "sample": "scopus/sample_response.json",
        "extractor": _extract_scopus,
    },
    "openalex": {
        "sample": "openalex/sample_response.json",
        "extractor": lambda p: _extract_json_dois(
            p,
            url_fields=["primary_location.landing_page_url", "open_access.oa_url"],
            doi_fields=["doi"],
        ),
    },
    "semanticscholar": {
        "sample": "semanticscholar/bulk_search_response.json",
        # S2 paper pages are JS-rendered; use the DOI to hit the publisher page.
        "extractor": lambda p: _extract_json_dois(
            p,
            url_fields=[],
            doi_fields=["externalIds.DOI"],
        ),
    },
    "wos": {
        "sample": "wos/sample_response.json",
        # WoS Starter wraps hits in a top-level "hits" key.
        # The record URL is in links.record and the DOI in identifiers.doi.
        "extractor": lambda p: _extract_json_dois(
            p,
            url_fields=["links.record"],
            doi_fields=["identifiers.doi"],
        ),
    },
}


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def collect_db(db_name: str, config: dict) -> dict:
    """Collect pages for a single database, return summary dict."""
    print(f"\n{'=' * 60}")
    print(f"  {db_name.upper()} page collector")
    print(f"{'=' * 60}")

    sample_path = DATA_DIR / config["sample"]
    if not sample_path.exists():
        print(f"  [FAIL] Sample file not found: {sample_path}")
        return {"db": db_name, "collected": 0, "errors": 0, "skipped": True}

    db_output_dir = OUTPUT_DIR / db_name
    db_output_dir.mkdir(parents=True, exist_ok=True)

    extractor = config["extractor"]
    collected, errors = 0, 0
    pages_meta = []

    for url, doi in extractor(sample_path):
        if collected >= MAX_PAGES_PER_DB:
            break
        key = doi if doi else urllib.parse.urlsplit(url).path.strip("/").replace("/", "_")
        print(f"  -> {url}")
        resp = _safe_get(url)
        meta = _save_page(db_output_dir, key, url, doi, resp)
        if resp and resp.ok:
            print(
                f"    [OK] {resp.status_code} {meta.get('content_type', '')} ({meta['size_bytes']} B)"
            )
            pages_meta.append(meta)
            collected += 1
        else:
            print("    [FAIL] failed: trying next candidate")
            errors += 1
        time.sleep(REQUEST_DELAY)

    # Save per-db index
    (db_output_dir / "index.json").write_text(json.dumps(pages_meta, indent=2), encoding="utf-8")
    print(f"\n  Collected: {collected}  Errors: {errors}")
    return {"db": db_name, "collected": collected, "errors": errors, "skipped": False}


def main() -> int:
    """Entry point."""
    print("=" * 60)
    print("  Paper Landing-Page Collector")
    print("=" * 60)

    if len(sys.argv) > 1:
        selected = sys.argv[1:]
        invalid = [s for s in selected if s not in DB_CONFIGS]
        if invalid:
            print(f"\n[FAIL] Unknown database(s): {', '.join(invalid)}")
            print(f"Available: {', '.join(DB_CONFIGS.keys())}")
            return 1
    else:
        selected = list(DB_CONFIGS.keys())

    print(f"\nDatabases: {', '.join(selected)}")
    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Max pages per DB: {MAX_PAGES_PER_DB}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for db_name in selected:
        results.append(collect_db(db_name, DB_CONFIGS[db_name]))

    # Overall metadata
    (OUTPUT_DIR / "collection_metadata.json").write_text(
        json.dumps(
            {
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "databases": results,
                "total_collected": sum(r["collected"] for r in results),
                "total_errors": sum(r["errors"] for r in results),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"\n{'=' * 60}")
    print("  Summary")
    print(f"{'=' * 60}")
    for r in results:
        if r.get("skipped"):
            print(f"  {r['db']:14} SKIPPED (no sample file)")
        else:
            print(f"  {r['db']:14} collected={r['collected']}  errors={r['errors']}")

    total_ok = sum(r["collected"] for r in results)
    print(f"\n  Total pages saved: {total_ok}")
    return 0 if all(r.get("skipped") or r["errors"] == 0 for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
