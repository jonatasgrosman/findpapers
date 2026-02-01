#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from arXiv.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://info.arxiv.org/help/api/user-manual.html
"""

import json
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
LIMIT = 50

# Query: [machine learning] OR [deep learning] AND [nlp OR natural language processing]
# Date range: 2020-2022

# arXiv API base URL
BASE_URL = "http://export.arxiv.org/api/query"

# arXiv uses field prefixes for search:
# - ti: title
# - abs: abstract
# - all: all fields
# Boolean operators: AND, OR, ANDNOT

# Build the query
# We want: (machine learning OR deep learning) AND (nlp OR natural language processing)
QUERY_TERMS = (
    "(all:machine AND all:learning) OR (all:deep AND all:learning) "
    "AND (all:nlp OR all:natural AND all:language AND all:processing)"
)

# Date filter using submittedDate
# Format: submittedDate:[YYYYMMDDTTTT TO YYYYMMDDTTTT]
# 2020-01-01 to 2022-12-31
DATE_FROM = "202001010000"
DATE_TO = "202212312359"
DATE_FILTER = f"submittedDate:[{DATE_FROM} TO {DATE_TO}]"

# Full query with date filter
FULL_QUERY = f"({QUERY_TERMS}) AND {DATE_FILTER}"


def collect_arxiv_sample() -> None:
    """Collect sample data from arXiv API."""
    print("=" * 60)
    print("arXiv API Sample Data Collector")
    print("=" * 60)

    params = {
        "search_query": FULL_QUERY,
        "start": 0,
        "max_results": LIMIT,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    # Build URL for logging
    encoded_params = urllib.parse.urlencode(params)
    full_url = f"{BASE_URL}?{encoded_params}"
    print(f"\nRequest URL:\n{full_url}\n")

    print(f"Fetching {LIMIT} papers from arXiv...")

    try:
        response = requests.get(BASE_URL, params=params, timeout=60)
        response.raise_for_status()

        # Save raw XML response
        xml_path = OUTPUT_DIR / "sample_response.xml"
        xml_path.write_text(response.text, encoding="utf-8")
        print(f"✓ Saved raw XML response to: {xml_path}")

        # Save metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "api_url": full_url,
            "query": FULL_QUERY,
            "date_range": {"from": "2020-01-01", "to": "2022-12-31"},
            "limit": LIMIT,
            "response_status": response.status_code,
            "response_size_bytes": len(response.content),
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"✓ Saved collection metadata to: {metadata_path}")

        # Count entries (simple count without parsing)
        entry_count = response.text.count("<entry>")
        print(f"\n✓ Found approximately {entry_count} entries in response")

        print("\n" + "=" * 60)
        print("Collection complete!")
        print("=" * 60)

    except requests.RequestException as e:
        print(f"✗ Error fetching data: {e}")
        raise


if __name__ == "__main__":
    collect_arxiv_sample()
