# Snowball

The `engine.snowball()` method discovers related papers from a seed paper via breadth-first citation traversal. Starting from a single paper, it iteratively fetches its references (backward) and/or citing papers (forward) to map the citation network around it.

## Basic Usage

```python
import findpapers

engine = findpapers.Engine()

# Start from a paper found by DOI
seed = engine.get("10.1038/nature12373")

result = engine.snowball(seed, max_depth=1, direction="both")

print(f"{len(result.papers)} discovered papers (plus the seed in result.seed_paper)")
```

## Parameters

```python
result = engine.snowball(
    paper,                           # Paper - the seed paper
    max_depth=1,                    # int - maximum traversal depth
    direction="both",               # "both" | "backward" | "forward"
    max_papers_per_level=None,             # int | None - keep only top N papers per level in the result
    max_expansion_per_level=None,   # int | None - expand only top N papers per level to the next BFS round
    max_cited_by=100,               # int | None - max citing-paper DOIs to collect per paper
    databases=None,                 # list[str] | None - databases for BFS discovery
    enrichment_databases=None,      # list[str] | None - databases for post-BFS enrichment of non-seed papers
    since=None,                     # datetime.date | None - exclude papers before this date
    until=None,                     # datetime.date | None - exclude papers after this date
    num_workers=1,                  # int - number of parallel workers
    verbose=False,                  # bool - enable detailed logging
    show_progress=True,             # bool - show progress bars
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `paper` | `Paper` | *(required)* | The seed paper from which the snowball starts. Must have a DOI |
| `max_depth` | `int` | `1` | Maximum number of snowball iterations |
| `direction` | `"both" \| "backward" \| "forward"` | `"both"` | Direction of citation traversal |
| `max_papers_per_level` | `int \| None` | `None` | Keep only the N most-cited papers per level in the result. Papers outside the top N are excluded from the result but still drive the next level. The seed paper is never filtered. `None` keeps all papers |
| `max_expansion_per_level` | `int \| None` | `None` | Limit how many papers per level become seeds for the next BFS round. Only the top N most-cited papers from each level are expanded. Papers already in the result are unaffected. `None` expands all |
| `max_cited_by` | `int \| None` | `100` | Maximum number of citing-paper DOIs collected per paper in `paper.cited_by` during seed and frontier enrichment. OpenAlex is used first (results sorted by citation count so the most-impactful papers are kept when truncated); Semantic Scholar is the fallback. `None` means no limit: use with caution for forward/both directions as highly-cited papers may have thousands of citations. A warning is emitted when this value is `None` or greater than `100` |
| `databases` | `list[str] \| None` | direction-based | Databases used for BFS discovery. Only `"crossref"`, `"openalex"`, and `"semantic_scholar"` are accepted. Defaults to `["crossref"]` for `"backward"` direction, or all three for `"forward"`/`"both"`. Pass `None` for the same direction-based default. Raises an error if direction requires forward citation data but none of the selected databases support it |
| `enrichment_databases` | `list[str] \| None` | `["crossref", "web_scraping"]` | Databases used to enrich non-seed papers after all BFS levels complete. Databases already used during discovery are not applied again. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. `None` uses the default. Pass `[]` to disable enrichment entirely. |
| `since` | `datetime.date \| None` | `None` | Only include discovered papers published on or after this date. The seed paper is never filtered |
| `until` | `datetime.date \| None` | `None` | Only include discovered papers published on or before this date. The seed paper is never filtered |
| `num_workers` | `int` | `1` | Number of parallel workers used to fetch papers per level |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |
| `show_progress` | `bool` | `True` | Display tqdm progress bars while papers are being fetched |

## Return Value

Returns a `SnowballResult` object containing:

| Attribute | Type | Description |
|-----------|------|-------------|
| `papers` | `list[Paper]` | Discovered papers (seed excluded; the seed is in `seed_paper`) |
| `seed_paper` | `Paper` | The enriched seed paper (fetched during snowball; the original is used as a fallback) |
| `max_depth` | `int` | Maximum traversal depth used |
| `direction` | `str` | Direction used (`"both"`, `"backward"`, or `"forward"`) |
| `since` | `datetime.date \| None` | Lower-bound date filter applied |
| `until` | `datetime.date \| None` | Upper-bound date filter applied |
| `databases` | `list[str] \| None` | Databases used for paper lookups |
| `max_papers_per_level` | `int \| None` | Per-level result cap that was used |
| `max_expansion_per_level` | `int \| None` | Per-level frontier cap that was used |
| `processed_at` | `datetime.datetime` | UTC timestamp when the snowball was executed |
| `runtime_seconds` | `float \| None` | Wall-clock runtime in seconds |
| `enrichment_databases` | `list[str] \| None` | Enrichment databases that were used |
| `max_cited_by` | `int \| None` | `max_cited_by` limit that was applied |

Citation relationships are encoded directly on each `Paper` object:

- `paper.references`: DOIs of papers cited *by* this paper (backward links)
- `paper.cited_by`: DOIs of papers that *cite* this paper (forward links)

## Direction

The `direction` parameter controls which citation relationships are followed:

- **`"backward"`** - fetches references (papers cited *by* the seed). Answers: "What did this paper build on?"
- **`"forward"`** - fetches citing papers (papers that cite the seed). Answers: "What was built on top of this paper?"
- **`"both"`** - follows both directions. Gives the most complete picture of the citation neighbourhood.

```python
# Only find what the seed cites
result = engine.snowball(seed, direction="backward")

# Only find papers that cite the seed
result = engine.snowball(seed, direction="forward")

# Both directions (default)
result = engine.snowball(seed, direction="both")
```

## Depth

The `max_depth` parameter controls how many iterations the snowball runs:

- **`max_depth=1`** (default) - retrieves only the immediate neighbours of the seed paper
- **`max_depth=2`** - also expands papers found at level 1
- Higher values expand further, but the number of papers grows rapidly

```python
# Immediate neighbours only
result = engine.snowball(seed, max_depth=1)

# Two levels deep
result = engine.snowball(seed, max_depth=2)
```

> **Note:** Higher depths can result in very large result sets. Start with `max_depth=1` and increase gradually.

## Controlling the Result Size with `max_papers_per_level`

At each snowball level the number of discovered papers can grow quickly. The `max_papers_per_level` parameter limits how many papers from each level are kept in the final result: only the **N most-cited** papers per level are added. Papers that do not make the cut are excluded from the result but **still drive the next BFS level**: their references and citing papers are still fetched.

The seed paper is never filtered regardless of this limit.

```python
# Keep only the 10 most-cited papers per level in the result
result = engine.snowball(
    seed,
    max_depth=2,
    direction="backward",
    max_papers_per_level=10,
)
```

> **Tip:** Papers with an unknown citation count (`citations=None`) are ranked below papers with a known count, so well-indexed papers are always preferred.

## Controlling Expansion Cost with `max_expansion_per_level`

The `max_expansion_per_level` parameter limits how many papers from each level become seeds for the next BFS round: only the **N most-cited** papers per level are expanded. All papers already added to the result remain there.

Use this to cap API call costs on deep snowballs without discarding papers from the result.

```python
# Deep snowball but limit expansion to the 10 most-cited papers at each level
result = engine.snowball(
    seed,
    max_depth=3,
    direction="forward",
    max_expansion_per_level=10,
)
```

Both parameters can be combined:

```python
# Keep only top-5 in result AND only expand top-20 per level
result = engine.snowball(
    seed,
    max_depth=2,
    max_papers_per_level=5,
    max_expansion_per_level=20,
)
```

## Date Filtering

Use `since` and `until` to narrow which *discovered* papers are included. The seed paper is **never** filtered.

```python
import datetime

# Only papers published between 2018 and 2023
result = engine.snowball(
    seed,
    max_depth=2,
    since=datetime.date(2018, 1, 1),
    until=datetime.date(2023, 12, 31),
)
```

Papers with an unknown publication date are excluded when either `since` or `until` is active.

## Fetch Strategy

Snowballing uses a two-step strategy:

### Step 1: Seed enrichment

The seed paper is fetched using the **union** of `databases` and `enrichment_databases`, ensuring it has full metadata (including `references` and `cited_by`) before the first BFS round. Only `"crossref"`, `"openalex"`, and `"semantic_scholar"` populate citation link fields.

### Step 2: BFS discovery

For each BFS level, every candidate DOI found in frontier `references`/`cited_by` lists is fetched with the configured `databases`. After all levels complete and filters are applied, surviving non-seed papers are re-enriched with the `enrichment_databases` that were **not** already used during discovery, avoiding redundant API calls while still filling metadata gaps (abstracts, PDFs, keywords, etc.). The seed paper is excluded from this final pass since it was already fully enriched at the start.

```python
# Use all three snowball databases for discovery
result = engine.snowball(seed, databases=["crossref", "openalex", "semantic_scholar"])

# Use backward-only with crossref (the default for direction='backward')
result = engine.snowball(seed, direction="backward")
```

## Data Sources

Snowballing uses `GetRunner` for each discovered DOI, pulling metadata and citation lists from multiple databases:

- **OpenAlex**: large open catalog with both references and forward citation data
- **Semantic Scholar**: AI-powered academic graph with references and forward citation data
- **CrossRef**: metadata and backward references via DOI lookup (default discovery source)
- Other configured databases (IEEE, Scopus, PubMed, arXiv, WoS) contribute paper metadata

Papers without a DOI are silently skipped since they cannot be resolved by the upstream APIs, but the seed itself **must** have a DOI: `engine.snowball()` raises `InvalidParameterError` if it does not.

## Snowballing from a Search Result

A common workflow is to search for papers and then snowball from the most relevant one:

```python
import findpapers

engine = findpapers.Engine()

# Search for key papers
result = engine.search("[attention mechanism] AND [transformer]")

# Snowball from the top result
snowball_result = engine.snowball(result.papers[0], max_depth=1, direction="both")

print(f"Found {len(snowball_result.papers)} discovered papers (plus the seed in snowball_result.seed_paper)")

# Save the result
findpapers.save_to_json(snowball_result, "snowball_result.json")
```

`engine.snowball()` accepts a single `Paper` per call. To snowball from several starting points, call it once per seed and merge the results yourself.

## Saving the Result

```python
import findpapers

# Save as JSON
findpapers.save_to_json(result, "snowball_result.json")

# Reload later
result = findpapers.load_from_json("snowball_result.json")
```
