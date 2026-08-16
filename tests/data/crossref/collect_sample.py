#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from CrossRef.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://api.crossref.org/swagger-ui/index.html

CrossRef API features:
- Free, no authentication required
- Works endpoint for fetching metadata by DOI
- Polite pool with higher rate limits when providing a contact email
- Returns structured JSON with title, authors, abstract, dates, source, etc.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
SAMPLE_RESPONSE_FILE = OUTPUT_DIR / "sample_responses.json"
METADATA_FILE = OUTPUT_DIR / "collection_metadata.json"

BASE_URL = "https://api.crossref.org/works"

# Polite-pool header: provides higher rate limits.
HEADERS = {
    "User-Agent": (
        "findpapers-test-collector/1.0 "
        "(https://github.com/jonatasgrosman/findpapers; "
        "mailto:findpapers@users.noreply.github.com)"
    ),
}

# Curated set of DOIs covering different paper types and publishers.
# Each entry has a DOI and a short description of why it was chosen.
SAMPLE_DOIS: list[dict[str, str]] = [
    {
        "doi": "10.1038/nature12373",
        "reason": "Nature journal article: rich metadata, multiple authors",
    },
    {
        "doi": "10.1145/3292500.3330648",
        "reason": "ACM conference proceedings article (KDD 2019)",
    },
    {
        "doi": "10.1007/978-3-030-58452-8_13",
        "reason": "Springer book chapter (ECCV 2020)",
    },
    {
        "doi": "10.1371/journal.pone.0185542",
        "reason": "PLOS ONE open-access journal article: has abstract",
    },
    {
        "doi": "10.1109/CVPR.2016.90",
        "reason": "IEEE CVPR proceedings article (ResNet): highly cited conference paper",
    },
    {
        "doi": "10.1109/ACCESS.2021.3119621",
        "reason": "IEEE Access journal article",
    },
    {
        "doi": "10.3758/s13428-022-02028-7",
        "reason": "Springer Psychonomic Bulletin: has keywords/subjects",
    },
    {
        "doi": "10.1016/j.apenergy.2023.121323",
        "reason": "Elsevier Applied Energy: publisher-DOI with ISSN and page range",
    },
]

# Delay between requests (seconds) to be polite.
REQUEST_DELAY = 1.0


def fetch_work(doi: str, timeout: float = 30.0) -> dict | None:
    """Fetch a single work record from CrossRef by DOI.

    Parameters
    ----------
    doi : str
        Bare DOI string.
    timeout : float
        HTTP request timeout in seconds.

    Returns
    -------
    dict | None
        Full API response JSON, or None on failure.
    """
    url = f"{BASE_URL}/{quote(doi, safe='')}"
    print(f"  GET {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        if response.status_code == 404:
            print(f"    [FAIL] Not found (404) for {doi}")
            return None
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"    [FAIL] Error: {e}")
        return None


def collect_crossref_samples() -> None:
    """Collect sample data from CrossRef API for each curated DOI."""
    print("=" * 60)
    print("CrossRef API Sample Data Collector")
    print("=" * 60)
    print(f"\nCollecting {len(SAMPLE_DOIS)} DOIs from CrossRef...")

    results: dict[str, dict] = {}
    successes = 0
    failures = 0

    for i, entry in enumerate(SAMPLE_DOIS):
        doi = entry["doi"]
        reason = entry["reason"]
        print(f"\n[{i + 1}/{len(SAMPLE_DOIS)}] {doi}")
        print(f"  Reason: {reason}")

        data = fetch_work(doi)
        if data is not None:
            message = data.get("message", {})
            results[doi] = message

            # Print summary of what was collected.
            title = (message.get("title") or ["(no title)"])[0]
            n_authors = len(message.get("author", []))
            has_abstract = bool(message.get("abstract"))
            cr_type = message.get("type", "unknown")
            container = (message.get("container-title") or ["(none)"])[0]
            citations = message.get("is-referenced-by-count", 0)

            print(f"    [OK] Title: {title[:80]}...")
            print(f"    [OK] Type: {cr_type} | Authors: {n_authors} | Abstract: {has_abstract}")
            print(f"    [OK] Source: {container} | Citations: {citations}")
            successes += 1
        else:
            failures += 1

        # Be polite between requests.
        if i < len(SAMPLE_DOIS) - 1:
            time.sleep(REQUEST_DELAY)

    # Save collected responses.
    SAMPLE_RESPONSE_FILE.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[OK] Saved {successes} work records to: {SAMPLE_RESPONSE_FILE}")

    # Save collection metadata.
    metadata = {
        "collected_at": datetime.now().isoformat(),
        "api_url": BASE_URL,
        "total_dois_requested": len(SAMPLE_DOIS),
        "successful": successes,
        "failed": failures,
        "dois": [e["doi"] for e in SAMPLE_DOIS],
        "descriptions": {e["doi"]: e["reason"] for e in SAMPLE_DOIS},
    }
    METADATA_FILE.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"[OK] Saved collection metadata to: {METADATA_FILE}")

    print(f"\n{'=' * 60}")
    print(f"Collection complete! {successes}/{len(SAMPLE_DOIS)} succeeded, {failures} failed.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    collect_crossref_samples()
