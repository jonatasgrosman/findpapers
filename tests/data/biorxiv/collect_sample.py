#!/usr/bin/env python3
"""
Standalone script to collect sample API responses from bioRxiv.

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

bioRxiv search works in 2 steps:
1. Web scraping on www.medrxiv.org/search to find DOIs matching query
2. API call to api.biorxiv.org/details to get full metadata for each DOI

References:
- Search tips: https://www.medrxiv.org/content/search-tips
- API: https://api.biorxiv.org/
"""

import json
import re
from datetime import datetime
from pathlib import Path

import requests
from lxml import html

# Configuration
OUTPUT_DIR = Path(__file__).parent
LIMIT = 50
DATABASE = "biorxiv"

# URLs
BASE_URL = "https://www.medrxiv.org"
API_BASE_URL = "https://api.biorxiv.org"

# Query: (machine learning OR deep learning) AND (nlp OR natural language processing)
# bioRxiv search uses abstract_title field with match-any or match-all flags
# We'll use multiple search URLs for OR groups between parentheses

# Date range: 2020-2022
DATE_FROM = "2020-01-01"
DATE_TO = "2022-12-31"

# Simplified query terms - bioRxiv doesn't support complex boolean well
# We'll search for: "machine learning" OR "deep learning" (in title/abstract)
SEARCH_TERMS = [
    "machine+learning+natural+language+processing",
    "deep+learning+natural+language+processing",
    "machine+learning+nlp",
    "deep+learning+nlp",
]


def build_search_url(terms: str, page: int = 0) -> str:
    """Build a bioRxiv search URL."""
    # URL pattern from old searcher
    # abstract_title:{query} abstract_title_flags:match-all jcode:biorxiv limit_from:YYYY-MM-DD limit_to:YYYY-MM-DD
    date_param = f"limit_from%3A{DATE_FROM}%20limit_to%3A{DATE_TO}"
    url_suffix = f"jcode%3A{DATABASE}%20{date_param}%20numresults%3A75%20sort%3Apublication-date%20direction%3Adescending%20format_result%3Acondensed"

    # Encode terms for URL
    encoded_terms = terms.replace("+", "%252B").replace(" ", "%2B")

    url = f"{BASE_URL}/search/abstract_title%3A{encoded_terms}%20abstract_title_flags%3Amatch-all%20{url_suffix}"

    if page > 0:
        url += f"?page={page}"

    return url


def scrape_search_results(url: str) -> dict:
    """Scrape search results page and extract DOIs and pagination info."""
    print(f"  Fetching: {url[:100]}...")

    response = requests.get(url, timeout=60)
    response.raise_for_status()

    page = html.fromstring(response.content)

    # Extract total papers count
    title_elements = page.xpath('//*[@id="page-title"]/text()')
    total_papers = 0
    if title_elements:
        title_text = title_elements[0].strip()
        if "no results" not in title_text.lower():
            match = re.search(r"([\d,]+)", title_text)
            if match:
                total_papers = int(match.group(1).replace(",", ""))

    # Extract DOIs
    dois = []
    if total_papers > 0:
        doi_elements = page.xpath(
            '//*[@class="highwire-cite-metadata-doi highwire-cite-metadata"]/text()'
        )
        dois = [x.strip().replace("https://doi.org/", "") for x in doi_elements]

    # Check for next page
    next_page_url = None
    next_elements = page.xpath('//*[@class="link-icon link-icon-after"]')
    if next_elements:
        next_page_url = BASE_URL + next_elements[0].attrib.get("href", "")

    return {
        "url": url,
        "total_papers": total_papers,
        "dois": dois,
        "next_page_url": next_page_url,
        "raw_html": response.text,
    }


def get_paper_metadata(doi: str) -> dict | None:
    """Get paper metadata from API given a DOI."""
    url = f"{API_BASE_URL}/details/{DATABASE}/{doi}"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get("collection") and len(data["collection"]) > 0:
            return {
                "doi": doi,
                "api_url": url,
                "metadata": data["collection"][0],
                "raw_response": data,
            }
    except requests.RequestException as e:
        print(f"    Warning: Failed to fetch metadata for {doi}: {e}")

    return None


def collect_biorxiv_sample() -> None:
    """Collect sample data from bioRxiv using web scraping and API."""
    print("=" * 60)
    print("bioRxiv Sample Data Collector (Web Scraping + API)")
    print("=" * 60)

    print(f"\nDatabase: {DATABASE}")
    print(f"Date range: {DATE_FROM} to {DATE_TO}")
    print(f"Target: {LIMIT} papers")

    # Step 1: Web scraping to find DOIs
    print("\n" + "-" * 40)
    print("Step 1: Web scraping search results")
    print("-" * 40)

    all_search_results = []
    all_dois = set()

    for terms in SEARCH_TERMS:
        if len(all_dois) >= LIMIT:
            break

        url = build_search_url(terms)
        result = scrape_search_results(url)
        all_search_results.append(result)

        new_dois = [d for d in result["dois"] if d not in all_dois]
        all_dois.update(new_dois)
        print(
            f"  Found {len(result['dois'])} DOIs ({len(new_dois)} new), total unique: {len(all_dois)}"
        )

    # Save first search HTML as sample
    if all_search_results:
        html_path = OUTPUT_DIR / "search_page_sample.html"
        html_path.write_text(all_search_results[0]["raw_html"], encoding="utf-8")
        print(f"\n✓ Saved sample search HTML to: {html_path}")

    # Save search results summary
    search_summary = {
        "collected_at": datetime.now().isoformat(),
        "database": DATABASE,
        "date_range": {"from": DATE_FROM, "to": DATE_TO},
        "search_terms": SEARCH_TERMS,
        "results": [
            {
                "url": r["url"],
                "total_papers": r["total_papers"],
                "dois_found": len(r["dois"]),
                "dois": r["dois"],
            }
            for r in all_search_results
        ],
        "unique_dois_total": len(all_dois),
    }
    search_path = OUTPUT_DIR / "search_results.json"
    search_path.write_text(json.dumps(search_summary, indent=2), encoding="utf-8")
    print(f"✓ Saved search results to: {search_path}")

    # Step 2: API calls to get metadata
    print("\n" + "-" * 40)
    print("Step 2: Fetching metadata via API")
    print("-" * 40)

    dois_to_fetch = list(all_dois)[:LIMIT]
    print(f"Fetching metadata for {len(dois_to_fetch)} papers...")

    api_responses = []
    for i, doi in enumerate(dois_to_fetch):
        print(f"  [{i+1}/{len(dois_to_fetch)}] {doi}")
        metadata = get_paper_metadata(doi)
        if metadata:
            api_responses.append(metadata)

    # Save API responses
    api_path = OUTPUT_DIR / "api_responses.json"
    api_path.write_text(json.dumps(api_responses, indent=2), encoding="utf-8")
    print(f"\n✓ Saved {len(api_responses)} API responses to: {api_path}")

    # Save collection metadata
    metadata = {
        "collected_at": datetime.now().isoformat(),
        "database": DATABASE,
        "date_range": {"from": DATE_FROM, "to": DATE_TO},
        "search_terms": SEARCH_TERMS,
        "limit": LIMIT,
        "search_urls_used": len(all_search_results),
        "unique_dois_found": len(all_dois),
        "papers_with_metadata": len(api_responses),
        "files_created": [
            "search_page_sample.html",
            "search_results.json",
            "api_responses.json",
            "collection_metadata.json",
        ],
    }
    metadata_path = OUTPUT_DIR / "collection_metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"✓ Saved collection metadata to: {metadata_path}")

    print("\n" + "=" * 60)
    print("Collection complete!")
    print(f"  - DOIs found: {len(all_dois)}")
    print(f"  - Papers with metadata: {len(api_responses)}")
    print("=" * 60)


if __name__ == "__main__":
    collect_biorxiv_sample()
