#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from IEEE Xplore.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://developer.ieee.org/docs

IMPORTANT: This script requires an IEEE API key.
Set the IEEE_API_KEY environment variable or create a .env file in the project root.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent.parent
LIMIT = 50

# Try to load API key from environment or .env file
def load_api_key() -> str | None:
    """Load IEEE API key from environment or .env file."""
    # Try both variable names
    api_key = os.environ.get("FINDPAPERS_IEEE_API_TOKEN") or os.environ.get("IEEE_API_KEY")
    if api_key:
        return api_key

    # Try to load from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_IEEE_API_TOKEN=") or line.startswith("IEEE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


# IEEE Xplore API configuration
# Base URL: https://ieeexploreapi.ieee.org/api/v1/search/articles
# Parameters:
# - apikey: API key (required)
# - querytext: Boolean search query
# - start_year: Start year filter
# - end_year: End year filter
# - max_records: Maximum records to return (max 200)
# - start_record: Offset for pagination (1-based)
# - sort_field: Sort field (article_number, article_title, author, publication_title, publication_year)
# - sort_order: asc or desc

BASE_URL = "https://ieeexploreapi.ieee.org/api/v1/search/articles"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# IEEE uses standard Boolean operators in querytext
QUERY = '("machine learning" OR "deep learning") AND ("nlp" OR "natural language processing")'

# Date range: 2020-2022
START_YEAR = 2020
END_YEAR = 2022


def collect_ieee_sample() -> None:
    """Collect sample data from IEEE Xplore API."""
    print("=" * 60)
    print("IEEE Xplore API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        print("\n✗ ERROR: IEEE_API_KEY not found!")
        print("Please set the IEEE_API_KEY environment variable or add it to .env file")
        print("You can get an API key at: https://developer.ieee.org/")
        return

    params = {
        "apikey": api_key,
        "querytext": QUERY,
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "max_records": LIMIT,
        "start_record": 1,
        "sort_field": "publication_year",
        "sort_order": "desc",
    }

    # Build URL for logging (hide API key)
    params_display = {k: v if k != "apikey" else "***HIDDEN***" for k, v in params.items()}
    print(f"\nRequest URL: {BASE_URL}")
    print(f"Parameters: {json.dumps(params_display, indent=2)}\n")

    print(f"Fetching {LIMIT} papers from IEEE Xplore...")
    print(f"Query: {QUERY}")
    print(f"Date range: {START_YEAR} to {END_YEAR}")

    try:
        response = requests.get(BASE_URL, params=params, timeout=60)
        response.raise_for_status()

        data = response.json()

        # Save JSON response
        json_path = OUTPUT_DIR / "sample_response.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"✓ Saved JSON response to: {json_path}")

        # Save metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "api_url": BASE_URL,
            "query": QUERY,
            "date_range": {"from": START_YEAR, "to": END_YEAR},
            "limit": LIMIT,
            "response_status": response.status_code,
            "total_records": data.get("total_records", "N/A"),
            "articles_returned": len(data.get("articles", [])),
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"✓ Saved collection metadata to: {metadata_path}")

        total = data.get("total_records", "N/A")
        returned = len(data.get("articles", []))
        print(f"\n✓ Total matching records: {total}")
        print(f"✓ Articles returned: {returned}")

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
    collect_ieee_sample()
