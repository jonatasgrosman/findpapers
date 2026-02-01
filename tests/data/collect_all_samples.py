#!/usr/bin/env python3
"""
Master script to run all API sample collectors.

This script runs all database-specific collector scripts to gather
fresh API response samples for testing purposes.

Usage:
    python tests/data/collect_all_samples.py [database...]

Examples:
    python tests/data/collect_all_samples.py          # Run all collectors
    python tests/data/collect_all_samples.py arxiv    # Run only arXiv
    python tests/data/collect_all_samples.py ieee scopus  # Run IEEE and Scopus only

Notes:
- IEEE and Scopus require API keys in .env file or environment variables
- bioRxiv and medRxiv don't support keyword search (only date filtering)
- arXiv and PubMed are fully open APIs
"""

import subprocess
import sys
from pathlib import Path

# Available collectors
COLLECTORS = {
    "arxiv": "arxiv/collect_sample.py",
    "biorxiv": "biorxiv/collect_sample.py",
    "medrxiv": "medrxiv/collect_sample.py",
    "ieee": "ieee/collect_sample.py",
    "pubmed": "pubmed/collect_sample.py",
    "scopus": "scopus/collect_sample.py",
    "openalex": "openalex/collect_sample.py",
    "semanticscholar": "semanticscholar/collect_sample.py",
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
        print(f"\n✗ {name} collector failed with exit code {e.returncode}")
        return False
    except FileNotFoundError:
        print(f"\n✗ {name} collector script not found: {script_path}")
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
            print(f"\n✗ Unknown database(s): {', '.join(invalid)}")
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

    # Summary
    print("\n" + "=" * 70)
    print("  Summary")
    print("=" * 70)

    success_count = 0
    for name, success in results.items():
        status = "✓ SUCCESS" if success else "✗ FAILED"
        print(f"  {name:12} {status}")
        if success:
            success_count += 1

    print(f"\nTotal: {success_count}/{len(results)} collectors succeeded")

    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
