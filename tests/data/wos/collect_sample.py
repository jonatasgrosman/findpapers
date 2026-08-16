#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from Web of Science (WoS) Starter API.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://developer.clarivate.com/apis/wos-starter

IMPORTANT: This script requires a Clarivate API key with access to the WoS Starter API.
Set the FINDPAPERS_WOS_API_TOKEN environment variable or create a .env file in the
project root with:
    FINDPAPERS_WOS_API_TOKEN=your_api_key_here

Free trial keys (50 req/day) can be obtained at:
    https://developer.clarivate.com/apis/wos-starter
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


def load_api_key() -> str | None:
    """Load WoS API key from environment or .env file.

    Returns
    -------
    str | None
        The API key string, or ``None`` when not found.
    """
    api_key = os.environ.get("FINDPAPERS_WOS_API_TOKEN")
    if api_key:
        return api_key

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_WOS_API_TOKEN="):
                value = line.split("=", 1)[1]
                # Strip inline comments (e.g. "key123 # comment")
                value = value.split("#")[0].strip().strip('"').strip("'")
                if value:
                    return value

    return None


# WoS Starter API configuration
# Base URL: https://api.clarivate.com/apis/wos-starter/v1/documents
# Headers:
#   X-ApiKey: <api_key>
# Parameters:
#   q:        WoS advanced query string using supported field tags
#   db:       Database (default: WOS = Web of Science Core Collection)
#   limit:    Number of results per page (1-50, default 10)
#   page:     Page number (default 1)
#   sortField: Sort order (e.g. PY+D = publication year descending)
#   publishTimeSpan: Date range filter (YYYY-MM-DD+YYYY-MM-DD)
#
# Supported field tags for searching:
#   TI - Title
#   AU - Author
#   SO - Source title
#   OG - Organization
#   TS - Topic (title + abstract + author keywords + Keywords Plus)
#   DO - DOI
#   PY - Year Published

BASE_URL = "https://api.clarivate.com/apis/wos-starter/v1/documents"

# Query: (machine learning OR deep learning) AND (natural language processing OR NLP)
# WoS uses TS= for topic search (title+abstract+author keywords+Keywords Plus)
QUERY = 'TS=("machine learning" OR "deep learning") AND TS=("natural language processing" OR "NLP")'

# Date range: 2020-2022
DATE_FROM = "2020-01-01"
DATE_TO = "2022-12-31"


def collect_wos_sample() -> None:
    """Collect sample data from WoS Starter API."""
    print("=" * 60)
    print("Web of Science Starter API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()
    if not api_key:
        print("\n[FAIL] ERROR: FINDPAPERS_WOS_API_TOKEN not found!")
        print(
            "Please set the FINDPAPERS_WOS_API_TOKEN environment variable "
            "or add it to the .env file in the project root."
        )
        print("Obtain a free trial key at: https://developer.clarivate.com/apis/wos-starter")
        return

    headers = {
        "X-ApiKey": api_key,
        "Accept": "application/json",
    }

    params = {
        "q": QUERY,
        "db": "WOS",
        "limit": LIMIT,
        "page": 1,
        "sortField": "PY+D",
        "publishTimeSpan": f"{DATE_FROM}+{DATE_TO}",
    }

    # Build display params (hide API key)
    print(f"\nRequest URL: {BASE_URL}")
    print(f"Parameters: {json.dumps(params, indent=2)}\n")

    print(f"Fetching up to {LIMIT} papers from Web of Science...")
    print(f"Query: {QUERY}")
    print(f"Date range: {DATE_FROM} to {DATE_TO}")

    try:
        response = requests.get(BASE_URL, headers=headers, params=params, timeout=60)
        response.raise_for_status()

        data = response.json()

        # Save JSON response
        json_path = OUTPUT_DIR / "sample_response.json"
        json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[OK] Saved JSON response to: {json_path}")

        # Save metadata
        metadata_obj = data.get("metadata") or {}
        hits = data.get("hits") or []
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "api_url": BASE_URL,
            "query": QUERY,
            "date_range": {"from": DATE_FROM, "to": DATE_TO},
            "limit": LIMIT,
            "response_status": response.status_code,
            "total_records": metadata_obj.get("total", "N/A"),
            "records_returned": len(hits),
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"[OK] Saved collection metadata to: {metadata_path}")

        total = metadata_obj.get("total", "N/A")
        returned = len(hits)
        print(f"\n[OK] Total matching records: {total}")
        print(f"[OK] Records returned: {returned}")

        if returned > 0:
            first = hits[0]
            print(f"\nFirst result title: {first.get('title', 'N/A')}")
            print(f"First result UID:   {first.get('uid', 'N/A')}")

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
    collect_wos_sample()
