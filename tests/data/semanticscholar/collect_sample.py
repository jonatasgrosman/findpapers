#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from Semantic Scholar.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://api.semanticscholar.org/api-docs

Semantic Scholar API features:
- Paper search endpoint: /graph/v1/paper/search
- Boolean search support in bulk search (AND, OR, NOT, -, |, +)
- Date filtering with year or publicationDateOrYear parameters
- Pagination with offset/limit
- Fields parameter to select which data to return
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

# Semantic Scholar API configuration
# Base URL: https://api.semanticscholar.org/graph/v1/paper/search
# Parameters:
# - query: Plain-text search query
# - year: Year range (e.g., "2020-2022")
# - offset: Pagination offset
# - limit: Max results (max 100)
# - fields: Comma-separated list of fields to return

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
BULK_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# For relevance search, use plain text query
QUERY = "machine learning deep learning nlp natural language processing"

# For bulk search, boolean syntax is supported:
# + for AND, | for OR, - for negation
BULK_QUERY = '("machine learning" | "deep learning") "natural language processing"'

# Date range: 2020-2022
YEAR_RANGE = "2020-2022"

# Fields to retrieve
FIELDS = "paperId,corpusId,externalIds,url,title,abstract,venue,year,referenceCount,citationCount,isOpenAccess,openAccessPdf,fieldsOfStudy,s2FieldsOfStudy,publicationTypes,publicationDate,journal,authors"


def load_api_key() -> str | None:
    """Load Semantic Scholar API key from environment or .env file."""
    # Try both variable names
    api_key = os.environ.get("FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN") or os.environ.get(
        "SEMANTIC_SCHOLAR_API_KEY"
    )
    if api_key:
        return api_key

    # Try to load from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN=") or line.startswith(
                "SEMANTIC_SCHOLAR_API_KEY="
            ):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def collect_relevance_search(api_key: str | None) -> dict:
    """Collect sample using relevance search endpoint."""
    print("\n" + "-" * 40)
    print("Step 1: Relevance Search (/paper/search)")
    print("-" * 40)

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    params = {
        "query": QUERY,
        "year": YEAR_RANGE,
        "offset": 0,
        "limit": LIMIT,
        "fields": FIELDS,
    }

    print(f"Query: {QUERY}")
    print(f"Year: {YEAR_RANGE}")
    print(f"Limit: {LIMIT}")

    response = requests.get(BASE_URL, headers=headers, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    # Save response
    json_path = OUTPUT_DIR / "relevance_search_response.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"✓ Saved relevance search response to: {json_path}")

    total = data.get("total", "N/A")
    results = data.get("data", [])
    print(f"✓ Total results: {total}, returned: {len(results)}")

    return data


def collect_bulk_search(api_key: str | None) -> dict:
    """Collect sample using bulk search endpoint (supports boolean queries)."""
    print("\n" + "-" * 40)
    print("Step 2: Bulk Search (/paper/search/bulk)")
    print("-" * 40)

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    params = {
        "query": BULK_QUERY,
        "year": YEAR_RANGE,
        "fields": FIELDS,
    }

    print(f"Query: {BULK_QUERY}")
    print(f"Year: {YEAR_RANGE}")

    response = requests.get(BULK_SEARCH_URL, headers=headers, params=params, timeout=60)
    response.raise_for_status()

    data = response.json()

    # Limit results to LIMIT papers
    if "data" in data and len(data["data"]) > LIMIT:
        data["data"] = data["data"][:LIMIT]
        print(f"Limited results to {LIMIT} papers")

    # Save response
    json_path = OUTPUT_DIR / "bulk_search_response.json"
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"✓ Saved bulk search response to: {json_path}")

    total = data.get("total", "N/A")
    results = data.get("data", [])
    print(f"✓ Total results: {total}, returned: {len(results)}")

    return data


def collect_semanticscholar_sample() -> None:
    """Collect sample data from Semantic Scholar API."""
    print("=" * 60)
    print("Semantic Scholar API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()
    if api_key:
        print("✓ Using API key for authentication")
    else:
        print("⚠ No API key found - using anonymous access (lower rate limits)")

    try:
        # Collect from both endpoints
        relevance_data = collect_relevance_search(api_key)
        bulk_data = collect_bulk_search(api_key)

        # Save collection metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "relevance_search": {
                "api_url": BASE_URL,
                "query": QUERY,
                "year_range": YEAR_RANGE,
                "limit": LIMIT,
                "total_results": relevance_data.get("total", "N/A"),
                "results_returned": len(relevance_data.get("data", [])),
            },
            "bulk_search": {
                "api_url": BULK_SEARCH_URL,
                "query": BULK_QUERY,
                "year_range": YEAR_RANGE,
                "total_results": bulk_data.get("total", "N/A"),
                "results_returned": len(bulk_data.get("data", [])),
            },
            "api_key_used": api_key is not None,
            "fields_requested": FIELDS,
            "files_created": [
                "relevance_search_response.json",
                "bulk_search_response.json",
                "collection_metadata.json",
            ],
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"\n✓ Saved collection metadata to: {metadata_path}")

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
    collect_semanticscholar_sample()
