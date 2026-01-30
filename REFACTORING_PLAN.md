# Refactoring Plan: OO API with `SearchRunner`

## Goal
Replace the current functional API with a fully object‑oriented, single‑run public API named `SearchRunner`. Keep the pipeline fixed but configurable via constructor parameters, store everything in memory, and export only when explicitly requested.

## Final API (Public)
`SearchRunner` is the new entry point:
- `__init__(..., enrich: bool = True, max_workers: int | None = None, timeout: float = 10.0)`
- `run(verbose: bool = False) -> None`
- `get_results() -> list[Paper]` (deep copy, preserves types)
- `get_metrics() -> dict[str, int | float]` (copy, numeric only)
- `to_json(path)`, `to_csv(path)`, `to_bibtex(path)`

Rules:
- **Multi‑run**: calling `run()` twice will clear previous results.
- **No exports before run**: export and getters raise a custom error if `run()` has not executed.
- `verbose=True` logs configuration and metrics.
- You can create a new folder structure under `findpapers/`, you don't need to keep the project structure like it is now.

## Pipeline (Fixed Order)
1. Fetch from databases (searchers)
2. Filter by publication types
3. Deduplicate + merge ("most complete")
4. Flag predatory publications
5. Enrich (optional; last step, controlled by `enrich` flag)

## Merge Rule (Most Complete)
- **Strings**: keep the longest string
- **Numbers**: keep the greatest number
- **Collections**: union
- **Nulls**: prefer non‑null

## Enrichment
- Enrichment runs **only if** `enrich=True` and is always the **last** stage.
- `max_workers=None` means **no parallelism**; values > 1 enable parallelism.
- `timeout` defaults to **10s** and is global.
- Failures keep partial results and log errors when `verbose=True`.

## Metrics & Logging
- Metrics are **numeric only** and include:
  - time per searcher
  - time per stage
  - counts before/after filters and dedupe
  - per‑searcher result counts
  - error counts
- `verbose=True` logs:
  - effective configuration
  - per‑searcher summary
  - per‑stage summary
  - final summary

## Export Formats
### JSON
- Separate sections:
  - `metadata`: query, databases, limits, enrich, timeout, timestamp (UTC ISO 8601), version, runtime_seconds
  - `papers`: list of papers
  - `metrics`: numeric metrics

### CSV
- columns with **priority order**:
  1. Paper fields
  2. Publication fields

### BibTeX
- Papers only (no metrics/header)

## Errors (Custom Exceptions)
- `SearchRunnerNotExecutedError`

## Package Version
- Prefer `importlib.metadata.version("findpapers")`
- Fallback to reading `pyproject.toml` if not installed

## Implementation Plan
1. **Public API**: Add `SearchRunner` in `findpapers/__init__.py`.
2. **Exceptions**: Add `findpapers/exceptions.py`.
3. **Engine + Pipeline**: Build internal `SearchEngine`pipeline with logging using the common logger.
4. **Searchers as Classes**: Convert each database searcher into a class implementing `SearcherBase` (ABC), with dependencies injected via `__init__`.
5. **Exports**: Update JSON/CSV/BibTeX export paths with the new schema.
6. **Docs**: Update README with a minimal `SearchRunner` usage example.
7. **Cleanup**: Remove the old functional API, obsolete tools/utils, samples, and tests; rewrite tests with mocks for all searchers.

## Staged Execution Checklist ✅

The following checklist breaks the refactoring into small, reviewable phases. Each item is self-contained: implement, add tests, and create a pull request. Mark items as done as you complete them to track progress. The old code was moved to `findpapers_old` and `tests_old` folders to keep it available for reference during the migration.

- [x] **Stage 0 — Preparation (quick wins)**
  - Scope: add `findpapers/exceptions.py`, a `SearcherBase` ABC skeleton, and a minimal `SearchRunner` placeholder that raises `SearchRunnerNotExecutedError` on getters/exports.
  - Tests: unit tests for exceptions and ABC presence; basic smoke test for `SearchRunner` construction.
  - Review checklist: new files follow project import style, no behavioral changes to existing code.
  - Comment: Stage 0 done — tests added in `tests/unit`; keep Stage 1 focused on `SearchRunner` run state/metrics only (no external calls yet).

- [x] **Stage 1 — Public API scaffold**
  - Scope: implement `SearchRunner.__init__` signature and `run(verbose=False)` that runs a trivial pipeline (no external calls) and records `run` state and basic metrics.
  - Tests: verify `run()` sets executed flag, `get_results()` and `get_metrics()` raise before `run()`, and work after `run()`.
  - Review checklist: API surface matches the plan; errors are raised when expected.
  - Comment: Basic metrics are numeric-only (`papers_count`, `runtime_seconds`); keep richer metrics for later stages.

- [x] **Stage 2 — Searcher classes & wiring**
  - Scope: convert one searchers (e.g., `arxiv`) into class-based searchers implementing `SearcherBase`; add dependency injection into `SearchRunner` and measure per-searcher timing.
  - Tests: mock network calls, assert per-searcher metrics and counts present.
  - Review checklist: searchers are easily instantiated and replaceable; no duplicate global state.
  - Comment: `ArxivSearcher` is a placeholder returning an empty list; migrate real logic from `findpapers_old` in Stage 2.2/3.

  - [x] **Stage 2.2 — The other Searchers**
  - Scope: repeat Stage 2 for all remaining searchers in batches (e.g., 2–3 at a time) to keep PRs small.
  - Tests: same as Stage 2, but for each batch.
  - Review checklist: all searchers converted; no regressions in existing tests.
  - Comment: Placeholders added for all remaining searchers. `rxiv` is an internal base searcher (not user-selectable).

- [x] **Stage 3 — Fetch pipeline implementation**
  - Scope: implement the fetch stage to call all configured searchers, collect raw `Paper` objects`, and record per-searcher counts and error counts.
  - Tests: integration-like tests using mocks from `tests_old/mocks/*` to assert counts and error handling. If the mocks are outdated, create new ones asking for help.
  - Review checklist: timeouts and failures do not crash the run; partial results are kept.
  - Comment: Fetch stage now records `stage.fetch.runtime_seconds` and preserves partial results on failure.

- [x] **Stage 4 — Filtering & Deduplication**
  - Scope: implement publication-type filtering and the dedupe+merge stage following the "most complete" rules (strings longest, numbers greatest, collections union, prefer non-null).
  - Tests: unit tests covering merge rules and end-to-end example where duplicates are merged correctly.
  - Review checklist: metrics include counts before/after filter and dedupe.
  - Comment: Filtering uses `publication.category`; dedupe uses DOI/title/year keys and merges most complete values.

- [ ] **Stage 5 — Predatory flagging**
  - Scope: add a predatory-flagging stage that marks papers and increments metrics for flagged items.
  - Tests: unit tests for flagging logic and metrics increment.
  - Review checklist: flags are deterministic and documented.

- [ ] **Stage 6 — Enrichment (optional, parallelism, timeouts)**
  - Scope: implement enrichment as a final stage, honoring `enrich`, `max_workers`, and `timeout`. Implement graceful failures and logging when `verbose=True`.
  - Tests: test with a slow mock enrichment to assert `timeout` behavior and partial results on failure.
  - Review checklist: parallelism is optional, errors are recorded but do not fail the entire run.

- [ ] **Stage 7 — Exports (JSON / CSV / BibTeX)**
  - Scope: implement `to_json`, `to_csv`, and `to_bibtex` according to the spec (metadata, papers, metrics; column priorities; BibTeX-only papers).
  - Tests: serialization tests that validate JSON schema, CSV columns order, and BibTeX formatting.
  - Review checklist: exporting before `run()` raises `SearchRunnerNotExecutedError`.

- [ ] **Stage 8 — Metrics, logging & verbose output**
  - Scope: finalize numeric-only metrics, add runtime per stage, and implement `verbose=True` summaries and logger integration with the project logger.
  - Tests: assert metrics keys/types and that verbose run emits expected log messages (use caplog or similar).
  - Review checklist: metrics are stable, documented, and appear in JSON `metrics` section.

- [ ] **Stage 8.5 — Documentation hygiene (comments, docstrings, test naming)**
  - Scope: ensure public methods/classes have docstrings; add concise comments where non-obvious; align test filenames to behavior (not refactor stages).
  - Tests: rename tests as needed; ensure no duplicate stage-based filenames remain.
  - Review checklist: docstrings present for public APIs, tests are discoverable and descriptive.

- [ ] **Stage 9 — Tests, CI, and compatibility**
  - Scope: update and add unit and integration tests; ensure CI passes; add tests that mock all searchers and cover error/failure modes.
  - Tests: coverage targets for new code; migration tests ensuring old functional API usage still works (if keeping compatibility layer) or that deprecation is documented.
  - Review checklist: no regressions in existing test suite.

- [ ] **Stage 10 — Documentation and examples**
  - Scope: update `README.md` with minimal usage example, document configuration options and metrics schema, and add a short migration guide.
  - Tests: docs build or lint (if using docs tooling); example code in README validated by tests where possible.
  - Review checklist: examples are copy-paste runnable.

- [ ] **Stage 11 — Cleanup and removal of old API**
  - Scope: remove or mark deprecated the old functional API and obsolete utilities/samples/tests. Replace samples with new-use examples.
  - Tests: ensure removal does not break required exports; add deprecation notes if removal is staged.
  - Review checklist: changelog updated and PR describes migration.

- [ ] **Stage 12 — Release & post-release checks**
  - Scope: bump version, ensure `importlib.metadata.version("findpapers")` works or implement fallback to `pyproject.toml`, write release notes, and publish.
  - Tests: post-release smoke test on installed package and package metadata retrieval.
  - Review checklist: release notes reference breaking changes and migration steps.

---

Notes:
- Prefer multiple small PRs (one stage per PR) to keep reviews lean ✅
- Keep `verbose` and metrics-driven logging enabled during the migration to make behavior changes visible
- If a stage grows too large, split it into sub-stages (e.g., convert searchers in 2–3 batches)

---

This checklist is intentionally ordered to minimize risk and maximize reviewability. Adjust stage boundaries as you progress.

