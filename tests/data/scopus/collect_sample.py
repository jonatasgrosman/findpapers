#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from Scopus.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://dev.elsevier.com/documentation/ScopusSearchAPI.wadl

IMPORTANT: This script requires a Scopus/Elsevier API key.
Set the SCOPUS_API_KEY environment variable or create a .env file in the project root.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent.parent
LIMIT = 50


def load_api_key() -> str | None:
    """Load Scopus API key from environment or .env file."""
    # Try both variable names
    api_key = os.environ.get("FINDPAPERS_SCOPUS_API_TOKEN") or os.environ.get("SCOPUS_API_KEY")
    if api_key:
        return api_key

    # Try to load from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_SCOPUS_API_TOKEN=") or line.startswith(
                "SCOPUS_API_KEY="
            ):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


# Scopus API configuration
# Base URL: https://api.elsevier.com/content/search/scopus
# Parameters:
# - query: Boolean search query using Scopus syntax
# - start: Offset for pagination (0-based)
# - count: Number of results to return
# - date: Date range in format YYYY-YYYY
# - sort: Sort field (e.g., -coverDate for descending by date)
# Headers:
# - X-ELS-APIKey: API key (required)
# - Accept: application/json

BASE_URL = "https://api.elsevier.com/content/search/scopus"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# Scopus uses TITLE-ABS-KEY for searching title, abstract, and keywords
QUERY = 'TITLE-ABS-KEY(("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing"))'

# Date range: 2020-2022
DATE_RANGE = "2020-2022"


def collect_scopus_sample() -> None:
    """Collect sample data from Scopus API.

    The Scopus API returns at most 25 entries per request, so we paginate
    until we reach ``LIMIT`` entries or exhaust the result set.
    """
    print("=" * 60)
    print("Scopus API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        print("\n[FAIL] ERROR: SCOPUS_API_KEY not found!")
        print("Please set the SCOPUS_API_KEY environment variable or add it to .env file")
        print("You can get an API key at: https://dev.elsevier.com/")
        return

    headers = {
        "X-ELS-APIKey": api_key,
        "Accept": "application/json",
    }

    page_size = 25  # Scopus API maximum per request
    all_entries: list[dict] = []
    start = 0

    print(f"\nRequest URL: {BASE_URL}")
    print(f"Query: {QUERY}")
    print(f"Date range: {DATE_RANGE}")
    print(f"Target: {LIMIT} papers (page size {page_size})\n")

    print(f"Fetching up to {LIMIT} papers from Scopus...")

    try:
        while len(all_entries) < LIMIT:
            params = {
                "query": QUERY,
                "start": start,
                "count": page_size,
                "date": DATE_RANGE,
                "sort": "-coverDate",
                "view": "STANDARD",
            }

            response = requests.get(BASE_URL, headers=headers, params=params, timeout=60)
            response.raise_for_status()

            data = response.json()
            search_results = data.get("search-results", {})
            entries = search_results.get("entry", [])

            if not isinstance(entries, list) or len(entries) == 0:
                break

            all_entries.extend(entries)
            print(
                f"  Page {start // page_size + 1}: got {len(entries)} entries "
                f"(total so far: {len(all_entries)})"
            )

            # Stop if we got fewer than a full page (no more results)
            if len(entries) < page_size:
                break

            start += page_size

            # Be polite between pages
            if len(all_entries) < LIMIT:
                time.sleep(1.0)

        # Trim to exact LIMIT
        all_entries = all_entries[:LIMIT]

        # Build a single combined response structure
        combined_data = data.copy()
        combined_data["search-results"] = dict(search_results)
        combined_data["search-results"]["entry"] = all_entries

        # Save JSON response
        json_path = OUTPUT_DIR / "sample_response.json"
        json_path.write_text(json.dumps(combined_data, indent=2), encoding="utf-8")
        print(f"\n[OK] Saved JSON response to: {json_path}")

        # Extract result counts
        total_results = search_results.get("opensearch:totalResults", "N/A")

        # Save metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "api_url": BASE_URL,
            "query": QUERY,
            "date_range": DATE_RANGE,
            "limit": LIMIT,
            "page_size": page_size,
            "pages_fetched": (start // page_size) + 1,
            "response_status": response.status_code,
            "total_results": total_results,
            "entries_returned": len(all_entries),
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[OK] Saved collection metadata to: {metadata_path}")

        print(f"\n[OK] Total matching results: {total_results}")
        print(f"[OK] Entries returned: {len(all_entries)}")

        print("\n" + "=" * 60)
        print("Collection complete!")
        print("=" * 60)

    except requests.RequestException as e:
        print(f"[FAIL] Error fetching data: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text[:500]}")
        raise


if __name__ == "__main__":
    collect_scopus_sample()
