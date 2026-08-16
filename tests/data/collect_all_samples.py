#!/usr/bin/env python3
"""
Master script to run all API sample collectors and the page collector.

This script runs all database-specific collector scripts to gather
fresh API response samples for testing purposes, then collects the
landing pages for the DOIs found in those samples.

Usage:
    python tests/data/collect_all_samples.py [database...]

Examples:
    python tests/data/collect_all_samples.py          # Run all collectors
    python tests/data/collect_all_samples.py arxiv    # Run only arXiv
    python tests/data/collect_all_samples.py ieee scopus  # Run IEEE and Scopus only

Notes:
- IEEE and Scopus require API keys in .env file or environment variables
- arXiv and PubMed are fully open APIs
- After collecting API samples, pages/collect_pages.py is also run to fetch
  landing-page HTML for the collected DOIs
"""

import subprocess
import sys
from pathlib import Path

# Available collectors
COLLECTORS = {
    "arxiv": "arxiv/collect_sample.py",
    "crossref": "crossref/collect_sample.py",
    "ieee": "ieee/collect_sample.py",
    "pubmed": "pubmed/collect_sample.py",
    "scopus": "scopus/collect_sample.py",
    "openalex": "openalex/collect_sample.py",
    "semanticscholar": "semanticscholar/collect_sample.py",
    "wos": "wos/collect_sample.py",
    "citations": "collect_citation_samples.py",
}

DATA_DIR = Path(__file__).parent


def run_collector(name: str, script_path: Path) -> bool:
    """Run a single collector script."""
    print("\n" + "=" * 70)
    print(f"  Running {name.upper()} collector")
    print("=" * 70 + "\n")

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=script_path.parent,
            check=True,
            capture_output=False,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] {name} collector failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n[FAIL] {name} collector script not found: {script_path}")
        return False


def run_page_collector(selected_dbs: list[str]) -> bool:
    """Run the landing-page collector for the given databases.

    Databases that the page collector does not support (e.g. crossref, whose
    sample data uses a non-standard structure) are silently skipped.
    """
    # Only forward databases that the page collector actually supports.
    _PAGES_SUPPORTED = {"arxiv", "ieee", "pubmed", "scopus", "openalex", "semanticscholar", "wos"}
    page_dbs = [db for db in selected_dbs if db in _PAGES_SUPPORTED]

    if not page_dbs:
        print("\n[WARN] No databases eligible for page collection: skipping")
        return True

    print("\n" + "=" * 70)
    print("  Running PAGES collector")
    print("=" * 70 + "\n")

    pages_script = DATA_DIR / "pages" / "collect_pages.py"
    if not pages_script.exists():
        print(f"[FAIL] Pages collector not found: {pages_script}")
        return False

    try:
        result = subprocess.run(
            [sys.executable, str(pages_script), *page_dbs],
            cwd=pages_script.parent,
            check=True,
            capture_output=False,
        )
        return result.returncode == 0
    except subprocess.CalledProcessError as e:
        print(f"\n[FAIL] Pages collector failed with exit code {e.returncode}")
        return False


def main() -> int:
    """Main entry point."""
    print("=" * 70)
    print("  API Sample Data Collector - Master Script")
    print("=" * 70)

    # Determine which collectors to run
    if len(sys.argv) > 1:
        selected = sys.argv[1:]
        # Validate selection
        invalid = [s for s in selected if s not in COLLECTORS]
        if invalid:
            print(f"\n[FAIL] Unknown database(s): {', '.join(invalid)}")
            print(f"Available: {', '.join(COLLECTORS.keys())}")
            return 1
    else:
        selected = list(COLLECTORS.keys())

    print(f"\nWill run collectors for: {', '.join(selected)}")
    print(f"Data directory: {DATA_DIR}")

    # Run selected collectors
    results: dict[str, bool] = {}
    for name in selected:
        script_path = DATA_DIR / COLLECTORS[name]
        results[name] = run_collector(name, script_path)

    # Run page collector for successfully collected databases
    successful_dbs = [name for name, ok in results.items() if ok]
    pages_ok = False
    if successful_dbs:
        pages_ok = run_page_collector(successful_dbs)
        results["pages"] = pages_ok
    else:
        print("\n[WARN] Skipping page collector: no databases collected successfully")

    # Summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)

    success_count = 0
    for name, success in results.items():
        status = "[OK] SUCCESS" if success else "[FAIL] FAILED"
        print(f"  {name:12} {status}")
        if success:
            success_count += 1

    print(f"\nTotal: {success_count}/{len(results)} collectors succeeded")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
