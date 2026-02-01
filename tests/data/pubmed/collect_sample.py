#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from PubMed.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

API Documentation: https://www.ncbi.nlm.nih.gov/books/NBK25500/

PubMed uses E-utilities:
1. esearch.fcgi - Search and get list of IDs
2. efetch.fcgi - Fetch full records by IDs

API Key: Optional but recommended for higher rate limits (10 req/sec vs 3 req/sec)
"""

import json
import os
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

# Configuration
OUTPUT_DIR = Path(__file__).parent
PROJECT_ROOT = OUTPUT_DIR.parent.parent.parent
LIMIT = 50

# PubMed E-utilities base URLs
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# PubMed uses [field] syntax for field-specific searches
# [tiab] = title/abstract, [pdat] = publication date
QUERY = '(("machine learning"[tiab] OR "deep learning"[tiab]) AND ("nlp"[tiab] OR "natural language processing"[tiab]))'

# Date range: 2020-2022
# PubMed uses mindate and maxdate parameters with format YYYY/MM/DD
DATE_FROM = "2020/01/01"
DATE_TO = "2022/12/31"


def load_api_key() -> str | None:
    """Load PubMed API key from environment or .env file."""
    api_key = os.environ.get("FINDPAPERS_PUBMED_API_TOKEN") or os.environ.get("PUBMED_API_KEY")
    if api_key:
        return api_key

    # Try to load from .env file
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("FINDPAPERS_PUBMED_API_TOKEN=") or line.startswith("PUBMED_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def collect_pubmed_sample() -> None:
    """Collect sample data from PubMed API."""
    print("=" * 60)
    print("PubMed API Sample Data Collector")
    print("=" * 60)

    api_key = load_api_key()
    if api_key:
        print("✓ Using API key for higher rate limits (10 req/sec)")
    else:
        print("⚠ No API key found - using anonymous access (3 req/sec)")

    # Step 1: Search for article IDs using esearch
    search_params = {
        "db": "pubmed",
        "term": QUERY,
        "retmax": LIMIT,
        "retmode": "json",
        "mindate": DATE_FROM,
        "maxdate": DATE_TO,
        "datetype": "pdat",  # Publication date
        "sort": "pub_date",  # Sort by publication date
    }

    # Add API key if available
    if api_key:
        search_params["api_key"] = api_key

    encoded_params = urllib.parse.urlencode(search_params)
    search_url = f"{ESEARCH_URL}?{encoded_params}"
    print(f"\nStep 1: Search for article IDs")
    print(f"Query: {QUERY}")
    print(f"Date range: {DATE_FROM} to {DATE_TO}")

    try:
        # Search for IDs
        print(f"\nFetching article IDs from PubMed...")
        search_response = requests.get(ESEARCH_URL, params=search_params, timeout=60)
        search_response.raise_for_status()

        search_data = search_response.json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        total_count = search_data.get("esearchresult", {}).get("count", "0")

        print(f"✓ Found {total_count} total matches, retrieved {len(id_list)} IDs")

        # Save search response
        search_json_path = OUTPUT_DIR / "esearch_response.json"
        search_json_path.write_text(json.dumps(search_data, indent=2), encoding="utf-8")
        print(f"✓ Saved esearch response to: {search_json_path}")

        if not id_list:
            print("No articles found matching the query")
            return

        # Step 2: Fetch full article details using efetch
        print(f"\nStep 2: Fetch full article details for {len(id_list)} articles...")

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "rettype": "xml",
            "retmode": "xml",
        }

        # Add API key if available
        if api_key:
            fetch_params["api_key"] = api_key

        fetch_response = requests.get(EFETCH_URL, params=fetch_params, timeout=60)
        fetch_response.raise_for_status()

        # Save raw XML response
        xml_path = OUTPUT_DIR / "efetch_response.xml"
        xml_path.write_text(fetch_response.text, encoding="utf-8")
        print(f"✓ Saved efetch XML response to: {xml_path}")

        # Count articles in response
        try:
            root = ET.fromstring(fetch_response.text)
            article_count = len(root.findall(".//PubmedArticle"))
            print(f"✓ Retrieved {article_count} full article records")
        except ET.ParseError:
            article_count = "parse error"
            print("Warning: Could not parse XML to count articles")

        # Save metadata
        metadata = {
            "collected_at": datetime.now().isoformat(),
            "esearch_url": search_url,
            "efetch_url": EFETCH_URL,
            "query": QUERY,
            "date_range": {"from": DATE_FROM, "to": DATE_TO},
            "limit": LIMIT,
            "total_matches": total_count,
            "ids_retrieved": len(id_list),
            "articles_fetched": article_count,
            "search_response_status": search_response.status_code,
            "fetch_response_status": fetch_response.status_code,
            "api_key_used": api_key is not None,
        }
        metadata_path = OUTPUT_DIR / "collection_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"✓ Saved collection metadata to: {metadata_path}")

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
    collect_pubmed_sample()
