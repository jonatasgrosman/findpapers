# Get

The `engine.get()` method fetches a single paper by its **DOI** or **landing-page URL**. This is useful when you already have a specific identifier and want to retrieve metadata without running a full search.

## Basic Usage

```python
import findpapers

engine = findpapers.Engine()

# By bare DOI
paper = engine.get("10.1038/nature12373")

# By landing-page URL
paper = engine.get("https://arxiv.org/abs/1706.03762")

if paper:
    print(paper.title)
    print(paper.authors)
    print(paper.publication_date)
```

## Parameters

```python
paper = engine.get(
    identifier,                     # str - DOI, DOI URL, or landing-page URL
    databases=None,                 # list[str] | None - sources to use (default: all)
    timeout=10.0,                   # float | None - request timeout in seconds
    verbose=False,                  # bool - enable detailed logging
)
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `identifier` | `str` | *(required)* | DOI, DOI URL, or paper landing-page URL |
| `databases` | `list[str] \| None` | `None` | Sources to consult. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos".` Pass `None` to use all sources |
| `timeout` | `float \| None` | `10.0` | HTTP request timeout in seconds. `None` disables the timeout |
| `verbose` | `bool` | `False` | Enable detailed DEBUG-level log messages |

### The `databases` parameter

`get()` queries multiple sources and merges their results into a single paper.
The `databases` parameter controls which sources to include.  When `None`
(the default), all available sources are used.

```python
# CrossRef only — fast, authoritative structured metadata
paper = engine.get("10.1038/nature12373", databases=["crossref"])

# Web scraping + OpenAlex — scrape the landing page and enrich via OpenAlex
paper = engine.get("10.1038/nature12373", databases=["web_scraping", "crossref", "openalex"])

# Web scraping only — fetch from URL without any API-based enrichment
paper = engine.get("https://arxiv.org/abs/1706.03762", databases=["web_scraping"])
```

## Return Value

Returns a `Paper` object, or `None` when the paper cannot be found or the page yields no metadata.

When a DOI is resolved, `get()` also populates `paper.cited_by` with the DOIs of papers that cite this paper, using OpenAlex and Semantic Scholar. The `paper.cited_by` field will be an empty list when no citers are found or when the paper has no DOI.

## Exceptions

| Exception | When |
|-----------|------|
| `ValueError` | The identifier is a bare DOI that is empty or blank after stripping whitespace |
| `InvalidParameterError` | `databases` is an empty list or contains an unrecognised value |

## Accepted Identifier Formats

`get()` accepts three forms of identifier and routes each to the most appropriate backend:

### Bare DOI

Queries each configured database via their APIs and merges the results.

```python
paper = engine.get("10.1038/nature12373")
```

### DOI URL

The `doi.org` prefix is stripped automatically and the paper is resolved through the same multi-database path as a bare DOI.

```python
paper = engine.get("https://doi.org/10.1038/nature12373")
paper = engine.get("http://dx.doi.org/10.1038/nature12373")
```

### Landing-page URL

For URLs belonging to a supported database (arXiv, PubMed, IEEE Xplore, OpenAlex, Semantic Scholar), the paper is fetched directly via that database's API (no HTML scraping involved). For all other URLs the page is downloaded and metadata is extracted from HTML `<meta>` tags.

```python
# arXiv — fetched via arXiv API
paper = engine.get("https://arxiv.org/abs/1706.03762")

# PubMed — fetched via NCBI E-utilities
paper = engine.get("https://pubmed.ncbi.nlm.nih.gov/34265844/")

# IEEE Xplore — fetched via IEEE API (requires ieee_api_key)
paper = engine.get("https://ieeexplore.ieee.org/document/726791")

# OpenAlex — fetched via OpenAlex API
paper = engine.get("https://openalex.org/W2626778328")

# Semantic Scholar — fetched via S2 API
paper = engine.get("https://www.semanticscholar.org/paper/204e3073870fae3d05bcbc2f6a8e263d9b72e776")

# Any other publisher page — HTML scraping fallback
paper = engine.get("https://www.nature.com/articles/s41586-021-03819-2")
```

## Using as a Snowball Seed

A common use case is to fetch a paper and then use it as a seed for citation snowballing:

```python
import findpapers

engine = findpapers.Engine()

# Fetch the seed paper — works with DOI or URL
seed = engine.get("10.1038/nature12373")

if seed:
    graph = engine.snowball(seed, max_depth=1, direction="both")
    print(f"{len(graph.nodes)} papers in the citation network")

    findpapers.save_to_json(graph, "citation_graph.json")
```

## Fetching Multiple Papers

To look up multiple identifiers (mix of DOIs and URLs), call `get()` in a loop:

```python
identifiers = [
    "10.1038/nature12373",
    "https://arxiv.org/abs/1706.03762",
    "https://pubmed.ncbi.nlm.nih.gov/34265844/",
]

papers = []
for identifier in identifiers:
    paper = engine.get(identifier)
    if paper:
        papers.append(paper)

print(f"Fetched {len(papers)} of {len(identifiers)} papers")
```
