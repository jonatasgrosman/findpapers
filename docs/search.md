# Search

The `engine.search()` method queries multiple academic databases with a single boolean query, automatically deduplicating and merging results. It is the primary entry point for discovering papers.

## Basic Usage

```python
import findpapers
import datetime

engine = findpapers.Engine()

result = engine.search(
    "[deep learning] AND [medical imaging]",
    since=datetime.date(2023, 1, 1),
    until=datetime.date(2024, 12, 31),
)

print(f"Found {len(result.papers)} papers")
for paper in result.papers[:5]:
    print(paper)
```

## Parameters

```python
result = engine.search(
    query,                          # str - boolean query string
    databases=None,                 # list[str] | None - restrict to specific databases
    max_papers_per_database=None,   # int | None - limit results per database
    since=None,                     # datetime.date | None - start date filter
    until=None,                     # datetime.date | None - end date filter
    num_workers=1,                  # int - number of parallel workers
    verbose=False,                  # bool - enable detailed logging
    show_progress=True,             # bool - show progress bars
    enrichment_databases=None,      # list[str] | None - databases for post-search enrichment
    max_cited_by=100,               # int | None - max citing-paper DOIs to collect per paper
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `str` | *(required)* | Boolean query string following the [Query Syntax](https://github.com/jonatasgrosman/findpapers/blob/main/docs/query-syntax.md) |
| `databases` | `list[str] \| None` | `None` | Database identifiers to query. Accepted values: `"arxiv"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"wos"`. Pass `None` to select all databases |
| `max_papers_per_database` | `int \| None` | `None` | Cap on the number of papers retrieved from each database. `None` means no limit |
| `since` | `datetime.date \| None` | `None` | Only return papers published on or after this date |
| `until` | `datetime.date \| None` | `None` | Only return papers published on or before this date |
| `num_workers` | `int` | `1` | Number of parallel workers used to query databases concurrently |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |
| `show_progress` | `bool` | `True` | Display tqdm progress bars while papers are being fetched |
| `enrichment_databases` | `list[str] \| None` | `["crossref", "web_scraping"]` | Databases used to enrich papers after search and filtering. Defaults to `"crossref"` and `"web_scraping"`. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. Pass `[]` to disable enrichment. `None` uses the default. |
| `max_cited_by` | `int \| None` | `100` | Maximum number of citing-paper DOIs collected per paper in `paper.cited_by` when `"openalex"` or `"semantic_scholar"` are in `enrichment_databases`. OpenAlex is used first (results sorted by citation count so the most-impactful papers are kept when truncated); Semantic Scholar is the fallback. `None` means no limit. A warning is emitted when this value is `None` or greater than `100` |

## Return Value

Returns a `SearchResult` object containing:

| Attribute | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The search query used |
| `papers` | `list[Paper]` | Deduplicated results |
| `databases` | `list[str] \| None` | Databases that were queried |
| `failed_databases` | `list[str] \| None` | Databases that failed during search |
| `since` | `datetime.date \| None` | Start date filter applied |
| `until` | `datetime.date \| None` | End date filter applied |
| `max_papers_per_database` | `int \| None` | Per-database paper limit applied |
| `runtime_seconds` | `float \| None` | Total runtime |
| `runtime_seconds_per_database` | `dict[str, float] \| None` | Per-database runtime |
| `enrichment_databases` | `list[str] \| None` | Enrichment databases that were used |
| `max_cited_by` | `int \| None` | `max_cited_by` limit that was applied |

## Exceptions

| Exception | When |
|-----------|------|
| `QueryValidationError` | The query has syntax errors (unbalanced brackets, invalid filter codes, etc.) |
| `InvalidParameterError` | An unknown database name is passed in `databases`, or `databases` is an empty list |

## Selecting Databases

When `databases=None` (default), Findpapers queries every database that does not require a missing API key. You can restrict to specific databases:

```python
# Only search arXiv and OpenAlex
result = engine.search("[transformers]", databases=["arxiv", "openalex"])

# Search all databases (requires IEEE and Scopus API keys)
engine = findpapers.Engine(
    ieee_api_key="your-key",
    scopus_api_key="your-key",
)
result = engine.search("[transformers]")
```

Available database identifiers: `"arxiv"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"wos"`. See [Databases](https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md) for details on each.

## Limiting Results

Use `max_papers_per_database` to cap the number of papers retrieved from each database. This is useful for exploratory searches or when you want a manageable set:

```python
# Get at most 50 papers from each database
result = engine.search("[machine learning]", max_papers_per_database=50)
```

## Date Filtering

Restrict results to a publication date range with `since` and `until`:

```python
import datetime

result = engine.search(
    "[covid-19] AND [vaccine]",
    since=datetime.date(2020, 1, 1),
    until=datetime.date(2023, 12, 31),
)
```

Both parameters are optional - you can use either one alone or combine them.

## Deduplication

Findpapers automatically deduplicates papers found across multiple databases. Two papers are considered the same when they share:

- The same DOI (case-insensitive), or
- The same normalized title

When duplicates are found, their metadata is merged - keeping the richest information from each source.

## Enrichment

After collecting and deduplicating papers, `search()` can automatically enrich them with additional metadata (abstracts, keywords, citation counts, PDF URLs) from multiple databases. Use the `enrichment_databases` parameter to control this:

```python
# Enrich with crossref and web_scraping (default) — covers most metadata gaps
# without consuming quota from rate-limited databases
result = engine.search("[transformers]")

# Enrich with a broader set of sources
result = engine.search("[transformers]", enrichment_databases=["crossref", "web_scraping", "openalex", "semantic_scholar"])

# Enrich only via CrossRef and Semantic Scholar
result = engine.search("[transformers]", enrichment_databases=["crossref", "semantic_scholar"])

# Skip enrichment entirely
result = engine.search("[transformers]", enrichment_databases=[])
```

Databases that already returned a given paper during the search phase are always excluded from its enrichment to avoid redundant requests.

Available identifiers for `enrichment_databases`: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`.

## Working with Results

```python
import findpapers
from findpapers.core.paper import PaperType

result = engine.search("[machine learning] AND [healthcare]")

# Iterate over papers
for paper in result.papers:
    print(f"{paper.title} ({paper.publication_date})")
    print(f"  DOI: {paper.doi}")
    print(f"  Databases: {paper.databases}")

# Filter by paper type (only journals and conference papers)
articles = [p for p in result.papers if p.paper_type in (PaperType.ARTICLE, PaperType.INPROCEEDINGS)]

# Save results for later
findpapers.save_to_json(result, "results.json")
findpapers.save_to_bibtex(result.papers, "references.bib")

# Reload a previous search
result = findpapers.load_from_json("results.json")
```
