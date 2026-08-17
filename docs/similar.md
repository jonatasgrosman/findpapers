# Similar

The `engine.similar()` method finds papers that are **content-similar** to a single seed paper: topically or semantically related work, as opposed to papers connected by citation links.

## Basic Usage

```python
import findpapers

engine = findpapers.Engine()

seed = engine.get("10.1038/nature12373")

result = engine.similar(seed)

print(f"{len(result.papers)} related papers found")
for paper in result.papers[:5]:
    print(f"- {paper.title} (found in: {sorted(paper.found_in)})")
```

## Parameters

```python
result = engine.similar(
    paper,                           # Paper - the seed paper
    databases=None,                  # list[str] | None - sources to use (default: semantic_scholar + pubmed)
    max_papers_per_database=None,    # int | None - cap on related papers kept per source
    since=None,                      # datetime.date | None - exclude related papers before this date
    until=None,                      # datetime.date | None - exclude related papers after this date
    enrichment_databases=["crossref", "web_scraping"],  # list[str] | None - post-fetch enrichment
    max_cited_by=100,                # int | None - max citing-paper DOIs collected during enrichment
    num_workers=1,                   # int - parallel workers for the enrichment pass
    timeout=10.0,                    # float | None - request timeout in seconds
    verbose=False,                   # bool - enable detailed logging
    show_progress=True,              # bool - show a progress bar across sources
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `paper` | `Paper` | *(required)* | Seed paper to find related papers for. Must have a DOI: papers without one yield an empty result, since all three sources are DOI-anchored |
| `databases` | `list[str] \| None` | `None` | Sources to consult, in priority order. Accepted values: `"semantic_scholar"`, `"pubmed"`, `"openalex"`. `None` uses `["semantic_scholar", "pubmed"]`: `"openalex"` is supported but excluded from the default because its signal is noisier (see [Data Sources](#data-sources)); pass it explicitly to include it |
| `max_papers_per_database` | `int \| None` | `None` | Cap on the number of related papers requested/kept from each source before merging. `None` lets each source's own natural default apply (see [Data Sources](#data-sources)) |
| `since` | `datetime.date \| None` | `None` | Only keep related papers published on or after this date. Applied as a post-fetch filter, since none of the three sources supports native date filtering. The seed paper is never filtered (it is never part of `result.papers` anyway) |
| `until` | `datetime.date \| None` | `None` | Only keep related papers published on or before this date. Applied as a post-fetch filter |
| `enrichment_databases` | `list[str] \| None` | `["crossref", "web_scraping"]` | Databases used to enrich the merged, filtered related papers via per-paper `get()`-style lookups, same mechanism as `search()`/`snowball()`. Fills metadata gaps that a single similarity source's own parser may have missed. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. Pass `[]` to disable enrichment entirely. `None` uses the default |
| `max_cited_by` | `int \| None` | `100` | Maximum number of citing-paper DOIs collected per paper during enrichment, when `"openalex"` or `"semantic_scholar"` are in `enrichment_databases`. `None` means no limit: use with caution. A warning is emitted when this value is `None` or greater than `100` |
| `num_workers` | `int` | `1` | Number of parallel workers used for the enrichment pass |
| `timeout` | `float \| None` | `10.0` | HTTP request timeout in seconds |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |
| `show_progress` | `bool` | `True` | Display a tqdm progress bar while sources are queried |

## Return Value

Returns a `SimilarResult` object containing:

| Attribute | Type | Description |
|-----------|------|-------------|
| `papers` | `list[Paper]` | Related papers, deduplicated, merged, filtered, and enriched (the seed paper itself is excluded) |
| `seed_paper` | `Paper` | The paper the lookup was performed around |
| `databases` | `list[str] \| None` | Sources that were requested |
| `max_papers_per_database` | `int \| None` | Cap that was applied per source |
| `since` | `datetime.date \| None` | Lower-bound date filter applied |
| `until` | `datetime.date \| None` | Upper-bound date filter applied |
| `enrichment_databases` | `list[str] \| None` | Enrichment databases that were used |
| `max_cited_by` | `int \| None` | `max_cited_by` limit that was applied during enrichment |
| `processed_at` | `datetime.datetime` | UTC timestamp when the lookup was executed |
| `runtime_seconds` | `float \| None` | Wall-clock runtime in seconds |
| `failed_databases` | `list[str]` | Sources that were queried but raised an error |
| `skipped_databases` | `list[str]` | Sources not applicable to this seed paper (e.g. PubMed with no resolvable PMID, or every source when the seed has no DOI) |

`failed_databases` and `skipped_databases` are intentionally distinct: a skip is an expected outcome ("this source does not apply here"), while a failure means the source was queried but errored.

Each paper in `result.papers` records which source(s) found it via `paper.found_in`, so you can judge confidence: a paper found by more than one source is generally a stronger match than one found by a single, noisier source.

## Data Sources

`similar()` queries up to three sources, each with a different relatedness signal:

### Semantic Scholar (highest priority)

Uses the Semantic Scholar **Recommendations API**, which is built on SPECTER embeddings: a language model trained specifically to represent scientific papers, so recommendations reflect learned semantic similarity rather than keyword overlap.

This call always requests the `all-cs` candidate pool explicitly. Despite the name, `all-cs` is **not** restricted to Computer Science: live testing (including against a pure biology paper) confirmed it is the widest pool the API offers, covering every field with no date restriction. The alternative pool, `recent` (the API's own default when the parameter is omitted), only covers papers published in the last 60 days, which silently returns nothing for anything older. This is not user-configurable.

Without an explicit cap, the API returns 100 results by default (accepts higher values via `max_papers_per_database`, up to roughly 500).

### PubMed

Uses NCBI's **ELink `neighbor_score`** command, which implements the PMRA (PubMed Related Articles) algorithm: a probabilistic model over article terms, weighted heavily by curated MeSH vocabulary. Only applicable to papers indexed in PubMed (biomedical/life sciences literature); for any other paper, `similar()` silently resolves no PMID and lists `"pubmed"` under `result.skipped_databases` rather than treating it as an error.

NCBI hard-caps this endpoint at 100 candidates regardless of any parameter; `max_papers_per_database` can only truncate further, not request more.

### OpenAlex (lowest priority)

Uses the `related_works` field already embedded in the OpenAlex `Work` record for the seed paper, so no dedicated "recommendation" request is needed beyond the initial lookup. This reflects shared topic/concept tags rather than a learned semantic signal, so it is the coarsest of the three: expect it to mix genuinely related papers with broadly-related-but-not-quite ones.

`related_works` is already a short, fixed list (typically 10-20 entries) with no pagination: there is nothing to request more of. Because it reflects topic-tag overlap rather than a learned semantic signal, its quality varies more than the other two sources: for some seed papers every entry is genuinely related, for others the list can include entries with no discernible connection to the seed at all. Live testing turned up recurring examples of unrelated entries across unrelated seed papers, so **OpenAlex is excluded from the default `databases`** and must be requested explicitly (see [Restricting Sources](#restricting-sources)).

## Merge Strategy: Union, Not Ranked Score

`similar()` queries every configured source and merges the results into a single deduplicated list (matched by DOI, falling back to normalised title). It does **not** compute or expose a combined similarity score: Semantic Scholar and OpenAlex do not return a numeric score at all (only an ordered list), and PubMed's score is a source-specific probabilistic model output, not comparable across sources. Mixing them into one fake unified ranking would misrepresent the data.

Instead, results are returned in **source-priority order**: all papers found by Semantic Scholar first, then papers found only by PubMed, then papers found only by OpenAlex. A paper found by multiple sources keeps the position of its highest-priority source, with provenance from every source it was found in recorded in `paper.found_in`.

## Date Filtering

Use `since` and `until` to narrow which related papers are kept. None of the three sources supports native date filtering, so this always runs as a post-fetch pass over the merged result, the same way `search()` enforces exact date boundaries after fetching.

```python
import datetime

result = engine.similar(
    seed,
    since=datetime.date(2018, 1, 1),
    until=datetime.date(2023, 12, 31),
)
```

Related papers with an unknown publication date are excluded whenever `since` or `until` is set.

## Enrichment

Like `search()` and `snowball()`, the merged (and filtered) related papers are enriched via per-paper lookups against `enrichment_databases` (default `["crossref", "web_scraping"]`), filling in metadata gaps that a single similarity source's own parser may have missed. Databases that already returned a given paper are skipped for that paper to avoid redundant requests.

```python
# Also pull in OpenAlex-based enrichment (adds paper.cited_by via max_cited_by)
result = engine.similar(seed, enrichment_databases=["crossref", "web_scraping", "openalex"])

# Disable enrichment entirely: keep each paper exactly as its similarity source returned it
result = engine.similar(seed, enrichment_databases=[])
```

## Restricting Sources

`databases=None` (the default) already uses only the two higher-precision sources, `["semantic_scholar", "pubmed"]`. Use `databases` to narrow further, for example to query a single source directly:

```python
result = engine.similar(seed, databases=["semantic_scholar"])
```

Or to opt into OpenAlex as well, trading some precision for extra recall:

```python
result = engine.similar(seed, databases=["semantic_scholar", "pubmed", "openalex"])
```

## Papers Without a DOI

All three sources are DOI-anchored, so a seed paper with no DOI yields an empty result without any HTTP calls, and every *active* source (the default two, or all three if `openalex` was requested explicitly) is listed under `result.skipped_databases`. There is currently no supported way to find similar papers from just a title/abstract for an unpublished paper: no reliable public API accepts arbitrary text and returns similarity-ranked results against the full academic corpus.

```python
from findpapers.core.paper import Paper

unpublished = Paper(
    title="My unpublished draft",
    abstract="...",
    authors=[],
    source=None,
    publication_date=None,
)
result = engine.similar(unpublished)
assert result.papers == []
assert result.skipped_databases == ["semantic_scholar", "pubmed"]
```

As an approximation, you can fall back to `engine.search()` with keywords drawn from the title/abstract; this is ordinary text-relevance search, not the content-similarity mechanisms above, but the results can still be useful for casting a wider net.

## Using with Search or Snowball Results

A common workflow is to search or snowball first, then find similar papers around one specific result:

```python
import findpapers

engine = findpapers.Engine()

result = engine.search("[attention mechanism] AND [transformer]")

# Find papers similar to the top result
similar_result = engine.similar(result.papers[0])

print(f"{len(similar_result.papers)} related papers found")
```

## Saving the Result

```python
import findpapers

# Save as JSON
findpapers.save_to_json(result, "similar_result.json")

# Reload later
result = findpapers.load_from_json("similar_result.json")
```
