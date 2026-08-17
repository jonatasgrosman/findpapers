#!/usr/bin/env python3
"""
Standalone script to collect sample API responses for the "similar papers"
(content-similarity) related endpoints.

Collects real responses from:
- Semantic Scholar: recommendations (from=all-cs)
- OpenAlex: related_works field + batch resolution of those IDs
- PubMed: esearch (DOI->PMID) + elink neighbor_score (related PMIDs)

This script does NOT use any findpapers code.
It collects raw API responses for testing purposes.

Usage:
    python tests/data/collect_similar_samples.py
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

# Seed papers used to collect "similar" samples, chosen for diversity of
# field (CS and biomedicine) to exercise both the OpenAlex/SS-only path and
# the PubMed-applicable path.
SAMPLE_DOIS = [
    {
        "doi": "10.1162/neco.1997.9.8.1735",
        "pmid": "9377276",
        "reason": "LSTM (Hochreiter & Schmidhuber, 1997): CS paper, also has recommendations",
    },
    {
        "doi": "10.1126/science.1225829",
        "pmid": "22745249",
        "reason": "CRISPR/Cas9 (Jinek et al., 2012): biomedical paper, PubMed-applicable",
    },
]

# Rate-limit delays (seconds)
SS_DELAY = 1.5  # Semantic Scholar public rate limit
OA_DELAY = 0.2  # OpenAlex polite pool
PM_DELAY = 0.4  # PubMed without API key (3 req/s)

# Semantic Scholar configuration
SS_RECOMMENDATIONS_URL = "https://api.semanticscholar.org/recommendations/v1/papers/forpaper"
SS_PAPER_FIELDS = "title,externalIds,abstract,authors,year,publicationDate,fieldsOfStudy"

# OpenAlex configuration
OA_BASE = "https://api.openalex.org/works"
OA_SELECT_FIELDS = (
    "id,doi,title,display_name,publication_date,authorships,"
    "abstract_inverted_index,cited_by_count,open_access,locations,"
    "primary_location,concepts,keywords,type,biblio,primary_topic"
)

# PubMed (NCBI E-utilities) configuration
PM_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PM_ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"

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
# Semantic Scholar collector
# ---------------------------------------------------------------------------


def collect_ss_recommendations(doi: str, headers: dict) -> dict:
    """Fetch recommendations (from=all-cs) for a DOI from Semantic Scholar.

    Note: `from=all-cs` is used deliberately here (not the API's default
    `from=recent`), see the plan notes: despite the name, it is the widest
    candidate pool (whole corpus, no date restriction), not a CS-only pool.
    """
    url = f"{SS_RECOMMENDATIONS_URL}/DOI:{doi}"
    params = {"from": "all-cs", "fields": SS_PAPER_FIELDS}
    print(f"  SS recommendations: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# OpenAlex collectors
# ---------------------------------------------------------------------------


def collect_oa_related_works(doi: str, headers: dict, api_key: str | None = None) -> dict:
    """Fetch id + related_works for a DOI."""
    url = f"{OA_BASE}/doi:{doi}"
    params = {"select": "id,related_works"}
    if api_key:
        params["api_key"] = api_key
    print(f"  OA related_works: {_sanitize_url(url)}")
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_oa_works_by_ids(
    openalex_ids: list[str], headers: dict, api_key: str | None = None
) -> dict:
    """Batch-fetch works by OpenAlex IDs (first 50)."""
    batch = openalex_ids[:50]
    id_filter = "|".join(batch)
    params = {
        "filter": f"openalex:{id_filter}",
        "per-page": 200,
        "select": OA_SELECT_FIELDS,
    }
    if api_key:
        params["api_key"] = api_key
    print(f"  OA batch works: {len(batch)} IDs")
    r = requests.get(OA_BASE, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# PubMed collectors
# ---------------------------------------------------------------------------


def collect_pm_esearch_doi(doi: str, headers: dict, api_key: str | None = None) -> dict:
    """Resolve a DOI to a PMID via esearch."""
    params = {"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json", "retmax": 1}
    if api_key:
        params["api_key"] = api_key
    print(f"  PM esearch (DOI->PMID): {doi}")
    r = requests.get(PM_ESEARCH_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def collect_pm_elink_neighbor_score(pmid: str, headers: dict, api_key: str | None = None) -> dict:
    """Fetch related-article scores for a PMID via elink neighbor_score.

    The `pubmed_pubmed` linkname (confirmed via live testing) is the one
    carrying the PMRA algorithm score, capped at 100 candidates by NCBI.
    """
    params = {
        "dbfrom": "pubmed",
        "db": "pubmed",
        "id": pmid,
        "cmd": "neighbor_score",
        "retmode": "json",
    }
    if api_key:
        params["api_key"] = api_key
    print(f"  PM elink neighbor_score: PMID {pmid}")
    r = requests.get(PM_ELINK_URL, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Collect all "similar papers" sample data."""
    print("=" * 60)
    print("Similar Papers API Sample Data Collector")
    print("=" * 60)

    ss_key = _load_env_key(["FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN", "SEMANTIC_SCHOLAR_API_KEY"])
    oa_key = _load_env_key(["FINDPAPERS_OPENALEX_API_TOKEN", "OPENALEX_API_KEY"])
    pm_key = _load_env_key(["FINDPAPERS_PUBMED_API_TOKEN", "PUBMED_API_KEY"])

    ss_headers = dict(HEADERS)
    if ss_key:
        ss_headers["x-api-key"] = ss_key
        print("[OK] Using Semantic Scholar API key")
    else:
        print("[WARN] No Semantic Scholar API key: using public rate limit")

    oa_headers = dict(HEADERS)
    if oa_key:
        print("[OK] Using OpenAlex API key")
    else:
        print("[WARN] No OpenAlex API key: using public rate limit")

    pm_headers = dict(HEADERS)
    if pm_key:
        print("[OK] Using PubMed API key")
    else:
        print("[WARN] No PubMed API key: using public rate limit (3 req/s)")

    for entry in SAMPLE_DOIS:
        doi = entry["doi"]
        print(f"\n--- DOI: {doi} ---")
        print(f"    ({entry['reason']})")

        result: dict = {"doi": doi}

        # --- Semantic Scholar ---
        print("\n  [Semantic Scholar]")
        try:
            result["ss_recommendations"] = collect_ss_recommendations(doi, ss_headers)
            time.sleep(SS_DELAY)
        except requests.RequestException as e:
            print(f"  [FAIL] Semantic Scholar error: {e}")

        # --- OpenAlex ---
        print("\n  [OpenAlex]")
        try:
            result["oa_related_works"] = collect_oa_related_works(doi, oa_headers, oa_key)
            time.sleep(OA_DELAY)

            related_ids = result["oa_related_works"].get("related_works", [])
            if related_ids:
                result["oa_works_by_ids"] = collect_oa_works_by_ids(related_ids, oa_headers, oa_key)
                time.sleep(OA_DELAY)
        except requests.RequestException as e:
            print(f"  [FAIL] OpenAlex error: {e}")

        # --- PubMed ---
        print("\n  [PubMed]")
        try:
            result["pm_esearch"] = collect_pm_esearch_doi(doi, pm_headers, pm_key)
            time.sleep(PM_DELAY)

            pmid_list = result["pm_esearch"].get("esearchresult", {}).get("idlist", [])
            pmid = pmid_list[0] if pmid_list else entry.get("pmid")
            if pmid:
                result["pm_elink_neighbor_score"] = collect_pm_elink_neighbor_score(
                    pmid, pm_headers, pm_key
                )
                time.sleep(PM_DELAY)
        except requests.RequestException as e:
            print(f"  [FAIL] PubMed error: {e}")

        # Write per-DOI file
        safe_doi = doi.replace("/", "_")
        outfile = DATA_DIR / "similar_samples" / f"{safe_doi}.json"
        outfile.parent.mkdir(parents=True, exist_ok=True)
        outfile.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n  [OK] Saved: {outfile.relative_to(DATA_DIR)}")

    # Write metadata
    metadata = {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "dois": [e["doi"] for e in SAMPLE_DOIS],
        "description": (
            "Real API responses for content-similarity ('similar papers') "
            "related endpoints (Semantic Scholar recommendations, OpenAlex "
            "related_works, PubMed elink neighbor_score). Used for unit "
            "testing the similar() connector methods."
        ),
        "endpoints": {
            "semantic_scholar": [
                "recommendations, from=all-cs "
                "(/recommendations/v1/papers/forpaper/DOI:{doi}?from=all-cs)",
            ],
            "openalex": [
                "related_works (/works/doi:{doi}?select=id,related_works)",
                "batch works (/works?filter=openalex:{ids})",
            ],
            "pubmed": [
                "esearch DOI->PMID (esearch.fcgi?term={doi}[doi])",
                "elink neighbor_score (elink.fcgi?cmd=neighbor_score)",
            ],
        },
    }
    meta_file = DATA_DIR / "similar_samples" / "collection_metadata.json"
    meta_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[OK] Metadata: {meta_file.relative_to(DATA_DIR)}")

    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)


if __name__ == "__main__":
    main()
