# Similar

The `engine.similar()` method finds papers that are **content-similar** to a single seed paper: topically or semantically related work, as opposed to papers connected by citation links.

## Similar vs. Snowball

Both methods discover related papers around a seed, but by very different mechanisms:

| | `similar()` | `snowball()` |
|---|---|---|
| Relatedness signal | Content/topic similarity (embeddings, related-articles algorithms, topic-tag overlap) | Citation graph (references and citing papers) |
| Traversal | Single-hop only | Multi-level BFS (`max_depth`) |
| Seeds | One `Paper` per call | One or more `Paper` objects |
| Typical use | "Find latent related work a citation search would miss" | "Map the citation network around a paper" |

Use `similar()` to complement a literature review with topically related papers that neither direct citation nor keyword search would surface. Use `snowball()` to trace the citation lineage of a paper.

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
    databases=None,                  # list[str] | None - sources to use (default: all three)
    max_papers_per_database=None,    # int | None - cap on related papers kept per source
    timeout=10.0,                    # float | None - request timeout in seconds
    verbose=False,                   # bool - enable detailed logging
    show_progress=True,              # bool - show a progress bar across sources
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `paper` | `Paper` | *(required)* | Seed paper to find related papers for. Must have a DOI: papers without one yield an empty result, since all three sources are DOI-anchored |
| `databases` | `list[str] \| None` | `None` | Sources to consult, in priority order. Accepted values: `"semantic_scholar"`, `"pubmed"`, `"openalex"`. `None` uses all three |
| `max_papers_per_database` | `int \| None` | `None` | Cap on the number of related papers requested/kept from each source before merging. `None` lets each source's own natural default apply (see [Data Sources](#data-sources)) |
| `timeout` | `float \| None` | `10.0` | HTTP request timeout in seconds |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |
| `show_progress` | `bool` | `True` | Display a tqdm progress bar while sources are queried |

## Return Value

Returns a `SimilarResult` object containing:

| Attribute | Type | Description |
|-----------|------|-------------|
| `papers` | `list[Paper]` | Related papers, deduplicated and merged across sources (the seed paper itself is excluded) |
| `seed_paper` | `Paper` | The paper the lookup was performed around |
| `databases` | `list[str] \| None` | Sources that were requested |
| `max_papers_per_database` | `int \| None` | Cap that was applied per source |
| `processed_at` | `datetime.datetime` | UTC timestamp when the lookup was executed |
| `runtime_seconds` | `float \| None` | Wall-clock runtime in seconds |
| `failed_databases` | `list[str]` | Sources that were queried but raised an error |
| `skipped_databases` | `list[str]` | Sources not applicable to this seed paper (e.g. PubMed with no resolvable PMID, or every source when the seed has no DOI) |

`failed_databases` and `skipped_databases` are intentionally distinct: a skip is an expected outcome ("this source does not apply here"), while a failure means the source was queried but errored.

Each paper in `result.papers` records which source(s) found it via `paper.found_in`, so you can judge confidence: a paper found by more than one source is generally a stronger match than one found by a single, noisier source.

## Merge Strategy: Union, Not Ranked Score

`similar()` queries every configured source and merges the results into a single deduplicated list (matched by DOI, falling back to normalised title). It does **not** compute or expose a combined similarity score: Semantic Scholar and OpenAlex do not return a numeric score at all (only an ordered list), and PubMed's score is a source-specific probabilistic model output, not comparable across sources. Mixing them into one fake unified ranking would misrepresent the data.

Instead, results are returned in **source-priority order**: all papers found by Semantic Scholar first, then papers found only by PubMed, then papers found only by OpenAlex. A paper found by multiple sources keeps the position of its highest-priority source, with provenance from every source it was found in recorded in `paper.found_in`.

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

`related_works` is already a short, fixed list (typically 10-20 entries) with no pagination: there is nothing to request more of.

## Restricting Sources

Use `databases` to limit which sources are queried, for example to exclude OpenAlex's noisier signal and keep only the higher-precision sources:

```python
result = engine.similar(seed, databases=["semantic_scholar", "pubmed"])
```

Or to query a single source directly:

```python
result = engine.similar(seed, databases=["semantic_scholar"])
```

## Papers Without a DOI

All three sources are DOI-anchored, so a seed paper with no DOI yields an empty result without any HTTP calls, and every source is listed under `result.skipped_databases`. There is currently no supported way to find similar papers from just a title/abstract for an unpublished paper: no reliable public API accepts arbitrary text and returns similarity-ranked results against the full academic corpus.

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
assert result.skipped_databases == ["semantic_scholar", "pubmed", "openalex"]
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
