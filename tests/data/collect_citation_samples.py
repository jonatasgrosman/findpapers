#!/usr/bin/env python3
"""
Standalone script to collect sample API responses for citation-related endpoints.

Collects real responses from:
- Semantic Scholar: references, citations, paper counts
- OpenAlex: DOI->ID resolution, referenced_works, cited-by, batch works

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

Usage:
    python tests/data/collect_citation_samples.py
"""

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent
PROJECT_ROOT = DATA_DIR.parent.parent

# DOIs to collect citation data for.  These are chosen for moderate counts
# (all data fits in a single API page) and represent different publishers.
SAMPLE_DOIS = [
    {
        "doi": "10.3758/s13428-022-02028-7",
        "reason": "Springer: moderate refs (40) and low citations (3)",
    },
    {
        "doi": "10.1016/j.apenergy.2023.121323",
        "reason": "Elsevier: moderate refs (47) and citations (20)",
    },
]

# Rate-limit delays (seconds)
SS_DELAY = 1.2  # Semantic Scholar public rate limit
OA_DELAY = 0.2  # OpenAlex polite pool

# Semantic Scholar configuration
SS_BASE = "https://api.semanticscholar.org/graph/v1/paper"
SS_PAPER_FIELDS = (
    "paperId,externalIds,title,abstract,authors,year,publicationDate,"
    "journal,venue,citationCount,openAccessPdf,url,fieldsOfStudy,"
    "s2FieldsOfStudy,publicationTypes,publicationVenue"
)

# OpenAlex configuration
OA_BASE = "https://api.openalex.org/works"
OA_SELECT_FIELDS = (
    "id,doi,title,display_name,publication_date,authorships,"
    "abstract_inverted_index,cited_by_count,open_access,locations,"
    "primary_location,concepts,keywords,type,biblio,primary_topic"
)

HEADERS = {
    "User-Agent": (
        "findpapers-test-collector/1.0 "
        "(https://github.com/jonatasgrosman/findpapers; "
        "mailto:findpapers@users.noreply.github.com)"
    ),
}


def _sanitize_url(url: str) -> str:
    """Remove api_key parameters from URLs."""
    return re.sub(r"([?&])api_key=[^&]*", r"\1api_key=***REDACTED***", url)


def _load_env_key(names: list[str]) -> str | None:
    """Load API key from environment or .env file."""
    for name in names:
        val = os.environ.get(name)
        if val:
            return val

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            for name in names:
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


# ---------------------------------------------------------------------------
# Semantic Scholar collectors
# ---------------------------------------------------------------------------


def collect_ss_paper_counts(doi: str, headers: dict) -> dict:
    """Fetch paper counts from Semantic Scholar."""
    url = f"{SS_BASE}/DOI:{doi}"
    params = {"fields": "citationCount,referenceCount"}
    print(f"  SS paper counts: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_ss_references(doi: str, headers: dict) -> dict:
    """Fetch first page of references from Semantic Scholar."""
    url = f"{SS_BASE}/DOI:{doi}/references"
    params = {"fields": SS_PAPER_FIELDS, "limit": 1000, "offset": 0}
    print(f"  SS references: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_ss_citations(doi: str, headers: dict) -> dict:
    """Fetch first page of citations from Semantic Scholar."""
    url = f"{SS_BASE}/DOI:{doi}/citations"
    params = {"fields": SS_PAPER_FIELDS, "limit": 1000, "offset": 0}
    print(f"  SS citations: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# OpenAlex collectors
# ---------------------------------------------------------------------------


def collect_oa_doi_resolution(doi: str, headers: dict) -> dict:
    """Resolve DOI to OpenAlex ID."""
    url = f"{OA_BASE}/doi:{doi}"
    params = {"select": "id"}
    print(f"  OA DOI->ID: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_oa_referenced_works(doi: str, headers: dict) -> dict:
    """Fetch referenced_works list for a DOI."""
    url = f"{OA_BASE}/doi:{doi}"
    params = {"select": "id,referenced_works"}
    print(f"  OA referenced_works: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_oa_works_by_ids(openalex_ids: list[str], headers: dict) -> dict:
    """Batch-fetch works by OpenAlex IDs (first 50)."""
    batch = openalex_ids[:50]
    id_filter = "|".join(batch)
    params = {
        "filter": f"openalex:{id_filter}",
        "per-page": 200,
        "select": OA_SELECT_FIELDS,
    }
    print(f"  OA batch works: {len(batch)} IDs")
    r = requests.get(OA_BASE, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_oa_cited_by(openalex_id: str, headers: dict) -> dict:
    """Fetch first page of cited-by for an OpenAlex ID."""
    params = {
        "filter": f"cites:{openalex_id}",
        "per-page": 200,
        "cursor": "*",
        "select": OA_SELECT_FIELDS,
    }
    print(f"  OA cited-by: {openalex_id}")
    r = requests.get(OA_BASE, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Collect all citation sample data."""
    print("=" * 60)
    print("Citation API Sample Data Collector")
    print("=" * 60)

    ss_key = _load_env_key(
        [
            "FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN",
            "SEMANTIC_SCHOLAR_API_KEY",
        ]
    )
    oa_key = _load_env_key(
        [
            "FINDPAPERS_OPENALEX_API_TOKEN",
            "OPENALEX_API_KEY",
        ]
    )

    ss_headers = dict(HEADERS)
    if ss_key:
        ss_headers["x-api-key"] = ss_key
        print("[OK] Using Semantic Scholar API key")
    else:
        print("[WARN] No Semantic Scholar API key: using public rate limit")

    oa_headers = dict(HEADERS)
    oa_params_extra: dict[str, str] = {}
    if oa_key:
        oa_params_extra["api_key"] = oa_key
        print("[OK] Using OpenAlex API key")
    else:
        print("[WARN] No OpenAlex API key: using public rate limit")

    # Collect per-DOI data
    for entry in SAMPLE_DOIS:
        doi = entry["doi"]
        print(f"\n--- DOI: {doi} ---")
        print(f"    ({entry['reason']})")

        result: dict = {"doi": doi}

        # --- Semantic Scholar ---
        print("\n  [Semantic Scholar]")
        try:
            result["ss_paper_counts"] = collect_ss_paper_counts(doi, ss_headers)
            time.sleep(SS_DELAY)
            result["ss_references"] = collect_ss_references(doi, ss_headers)
            time.sleep(SS_DELAY)
            result["ss_citations"] = collect_ss_citations(doi, ss_headers)
            time.sleep(SS_DELAY)
        except requests.RequestException as e:
            print(f"  [FAIL] Semantic Scholar error: {e}")

        # --- OpenAlex ---
        print("\n  [OpenAlex]")
        try:
            result["oa_doi_resolution"] = collect_oa_doi_resolution(doi, oa_headers)
            time.sleep(OA_DELAY)
            result["oa_referenced_works"] = collect_oa_referenced_works(doi, oa_headers)
            time.sleep(OA_DELAY)

            # Batch-fetch referenced works
            ref_ids = result["oa_referenced_works"].get("referenced_works", [])
            if ref_ids:
                result["oa_works_by_ids"] = collect_oa_works_by_ids(ref_ids, oa_headers)
                time.sleep(OA_DELAY)

            # Cited-by
            oa_id = result["oa_doi_resolution"].get("id")
            if oa_id:
                result["oa_cited_by"] = collect_oa_cited_by(oa_id, oa_headers)
                time.sleep(OA_DELAY)
        except requests.RequestException as e:
            print(f"  [FAIL] OpenAlex error: {e}")

        # Write per-DOI file
        safe_doi = doi.replace("/", "_")
        outfile = DATA_DIR / "citation_samples" / f"{safe_doi}.json"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  [OK] Saved: {outfile.relative_to(DATA_DIR)}")

    # Write metadata
    metadata = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "dois": [e["doi"] for e in SAMPLE_DOIS],
        "description": (
            "Real API responses for citation-related endpoints "
            "(Semantic Scholar + OpenAlex). Used for unit testing "
            "citation connector methods."
        ),
        "endpoints": {
            "semantic_scholar": [
                "paper counts (citationCount, referenceCount)",
                "references (/paper/DOI:{doi}/references)",
                "citations (/paper/DOI:{doi}/citations)",
            ],
            "openalex": [
                "DOI->ID resolution (/works/doi:{doi}?select=id)",
                "referenced_works (/works/doi:{doi}?select=id,referenced_works)",
                "batch works (/works?filter=openalex:{ids})",
                "cited-by (/works?filter=cites:{id})",
            ],
        },
    }
    meta_file = DATA_DIR / "citation_samples" / "collection_metadata.json"
    meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Metadata: {meta_file.relative_to(DATA_DIR)}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
