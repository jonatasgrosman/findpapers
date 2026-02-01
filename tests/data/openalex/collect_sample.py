#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from OpenAlex.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://docs.openalex.org/

OpenAlex API features:
- Free, no authentication required (but email/API key recommended for higher rate limits)
- Works endpoint for searching academic papers
- Boolean search support (AND, OR, NOT - must be UPPERCASE)
- Date filtering with from_publication_date and to_publication_date
- Pagination with page/per-page or cursor
"""

import json
import os
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent.parent
LIMIT = 50

# OpenAlex API configuration
# Base URL: https://api.openalex.org/works
# Parameters:
# - search: Full-text search in title, abstract, fulltext
# - filter: Various filters including from_publication_date, to_publication_date
# - page: Page number (1-indexed)
# - per-page: Results per page (max 200)
# - sort: Sort field

BASE_URL = "https://api.openalex.org/works"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# OpenAlex supports Boolean operators (AND, OR, NOT - must be UPPERCASE)
QUERY = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'

# Date range: 2020-2022
DATE_FROM = "2020-01-01"
DATE_TO = "2022-12-31"


def load_api_key() -> str | None:
    """Load OpenAlex API key/email from environment or .env file."""
    # Try both variable names
    api_key = os.environ.get("FINDPAPERS_OPENALEX_API_TOKEN") or os.environ.get("OPENALEX_API_KEY")
    if api_key:
        return api_key

    # Try to load from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_OPENALEX_API_TOKEN=") or line.startswith("OPENALEX_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def collect_openalex_sample() -> None:
    """Collect sample data from OpenAlex API."""
    print("=" * 60)
    print("OpenAlex API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()

    # Build filter string for date range
    filter_str = f"from_publication_date:{DATE_FROM},to_publication_date:{DATE_TO}"

    params = {
        "search": QUERY,
        "filter": filter_str,
        "page": 1,
        "per-page": LIMIT,
        "sort": "publication_date:desc",
    }

    # Add API key as email if available (for polite pool with higher rate limits)
    if api_key:
        params["api_key"] = api_key
        print("✓ Using API key for higher rate limits")
    else:
        print("⚠ No API key found - using anonymous access (lower rate limits)")

    # Build URL for logging
    encoded_params = urllib.parse.urlencode(params)
    full_url = f"{BASE_URL}?{encoded_params}"
    print(f"\nRequest URL: {BASE_URL}")
    print(f"Query: {QUERY}")
    print(f"Date range: {DATE_FROM} to {DATE_TO}")
    print(f"Limit: {LIMIT}")

    print(f"\nFetching {LIMIT} papers from OpenAlex...")

    try:
        response = requests.get(BASE_URL, params=params, timeout=60)
        response.raise_for_status()

        data = response.json()

        # Save JSON response
        json_path = OUTPUT_DIR / "sample_response.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"✓ Saved JSON response to: {json_path}")

        # Extract result counts
        meta = data.get("meta", {})
        total_count = meta.get("count", "N/A")
        results = data.get("results", [])

        # Save metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "api_url": BASE_URL,
            "full_url": full_url,
            "query": QUERY,
            "filter": filter_str,
            "date_range": {"from": DATE_FROM, "to": DATE_TO},
            "limit": LIMIT,
            "response_status": response.status_code,
            "total_results": total_count,
            "results_returned": len(results),
            "api_key_used": api_key is not None,
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"✓ Saved collection metadata to: {metadata_path}")

        print(f"\n✓ Total matching results: {total_count}")
        print(f"✓ Results returned: {len(results)}")

        print("\n" + "=" * 60)
        print("Collection complete!")
        print("=" * 60)

    except requests.RequestException as e:
        print(f"✗ Error fetching data: {e}")
        if hasattr(e, "response") and e.response is not None:
            print(f"Response status: {e.response.status_code}")
            print(f"Response body: {e.response.text[:500]}")
        raise


if __name__ == "__main__":
    collect_openalex_sample()
