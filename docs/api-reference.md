# API Reference

This document describes all public classes, enums, functions, and exceptions exported by the `findpapers` package.

Only objects that are part of the public API are documented here. Internal connectors, parsers, validators, and other implementation details are omitted.

---

## Engine

The `Engine` class is the main entry point for all findpapers operations.

```python
from findpapers import Engine
```

### Constructor

```python
Engine(
    *,
    ieee_api_key: str | None = None,
    scopus_api_key: str | None = None,
    pubmed_api_key: str | None = None,
    openalex_api_key: str | None = None,
    email: str | None = None,
    semantic_scholar_api_key: str | None = None,
    wos_api_key: str | None = None,
    proxy: str | None = None,
    ssl_verify: bool = True,
)
```

| Parameter | Type | Description |
|---|---|---|
| `ieee_api_key` | `str \| None` | IEEE Xplore API key. Falls back to `FINDPAPERS_IEEE_API_TOKEN` env var. |
| `scopus_api_key` | `str \| None` | Elsevier Scopus API key. Falls back to `FINDPAPERS_SCOPUS_API_TOKEN` env var. |
| `pubmed_api_key` | `str \| None` | NCBI PubMed API key. Falls back to `FINDPAPERS_PUBMED_API_TOKEN` env var. |
| `openalex_api_key` | `str \| None` | OpenAlex API key. Falls back to `FINDPAPERS_OPENALEX_API_TOKEN` env var. |
| `email` | `str \| None` | Contact email for polite-pool access. Falls back to `FINDPAPERS_EMAIL` env var. |
| `semantic_scholar_api_key` | `str \| None` | Semantic Scholar API key. Falls back to `FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN` env var. |
| `wos_api_key` | `str \| None` | Clarivate Web of Science API key. Falls back to `FINDPAPERS_WOS_API_TOKEN` env var. |
| `proxy` | `str \| None` | Proxy URL for HTTP requests. Falls back to `FINDPAPERS_PROXY` env var. |
| `ssl_verify` | `bool` | Whether to verify SSL certificates. Defaults to `True`. Falls back to `FINDPAPERS_SSL_VERIFY` env var. |

### `search()`

Search for papers across multiple academic databases.

```python
engine.search(
    query: str,
    *,
    databases: list[str] | None = None,
    max_papers_per_database: int | None = None,
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    num_workers: int = 1,
    verbose: bool = False,
    show_progress: bool = True,
) -> SearchResult
```

| Parameter | Type | Description |
|---|---|---|
| `query` | `str` | Boolean query with optional field filters (e.g., `"ti[deep learning] AND abs[transformer]"`). See [Query Syntax](query-syntax.md). |
| `databases` | `list[str] \| None` | Database identifiers to query. `None` uses all available databases. Accepted values: `"arxiv"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"wos"`. |
| `max_papers_per_database` | `int \| None` | Maximum number of papers to retrieve per database. |
| `since` | `datetime.date \| None` | Only include papers published on or after this date. |
| `until` | `datetime.date \| None` | Only include papers published on or before this date. |
| `num_workers` | `int` | Number of parallel database workers. Defaults to `1`. |
| `verbose` | `bool` | Enable debug logging. Defaults to `False`. |
| `show_progress` | `bool` | Display progress bars. Defaults to `True`. |
| `enrichment_databases` | `list[str] \| None` | Databases for post-search enrichment. Defaults to `["crossref", "web_scraping"]`. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. Pass `[]` or `None` to disable enrichment. |

**Returns:** `SearchResult` with deduplicated papers.

**Raises:** `QueryValidationError` if the query string is invalid. `InvalidParameterError` for invalid parameter values (e.g. unknown database names, empty databases list).

### `download()`

Download PDFs for a list of papers.

```python
engine.download(
    papers: list[Paper],
    output_directory: str,
    *,
    num_workers: int = 1,
    timeout: float | None = 30.0,
    verbose: bool = False,
    show_progress: bool = True,
) -> dict[str, int | float]
```

| Parameter | Type | Description |
|---|---|---|
| `papers` | `list[Paper]` | Papers to download. |
| `output_directory` | `str` | Directory where PDFs and logs will be saved. |
| `num_workers` | `int` | Number of parallel download workers. Defaults to `1`. |
| `timeout` | `float \| None` | HTTP timeout in seconds. Defaults to `30.0`. |
| `verbose` | `bool` | Enable debug logging. Defaults to `False`. |
| `show_progress` | `bool` | Display progress bar. Defaults to `True`. |

**Returns:** Metrics dictionary with keys: `total_papers`, `downloaded_papers`, `runtime_in_seconds`.

### `get()`

Fetch a single paper by its DOI or landing-page URL.

```python
engine.get(
    identifier: str,
    *,
    databases: list[str] | None = None,
    timeout: float | None = 10.0,
    verbose: bool = False,
) -> Paper | None
```

| Parameter | Type | Description |
|---|---|---|
| `identifier` | `str` | Bare DOI, DOI URL (`doi.org`/`dx.doi.org`), or paper landing-page URL. |
| `databases` | `list[str] \| None` | Sources to consult. `None` uses all available sources. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. |
| `timeout` | `float \| None` | HTTP timeout in seconds. Defaults to `10.0`. |
| `verbose` | `bool` | Enable debug logging. Defaults to `False`. |

**Routing:**
- All identifier types (bare DOI, `doi.org` URL, landing-page URL) are handled by `GetRunner`.
- Landing-page URLs run web scraping first (delegating to the matching database API when recognised), then enrich via DOI-based connectors if a DOI is found.
- Bare DOIs and `doi.org` URLs go directly to the multi-database DOI lookup pipeline.

**Returns:** `Paper`, or `None` if the paper cannot be found or the page yields no metadata.

**Raises:** `InvalidParameterError` if identifier is a bare DOI that is empty or blank after sanitization, or if `databases` is an empty list or contains an unrecognised value.

### `snowball()`

Build a snowball result via forward and/or backward citation traversal using a three-tier fetch strategy: fast BFS discovery with CrossRef, full enrichment of frontier papers with all API connectors, and a final HTML scraping pass on all surviving papers.

```python
engine.snowball(
    papers: list[Paper] | Paper,
    *,
    max_depth: int = 1,
    direction: Literal["both", "backward", "forward"] = "both",
    max_per_level: int | None = None,
    max_expansion_per_level: int | None = None,
    databases: list[str] | None = ["crossref"],
    enrichment_databases: list[str] | None = None,
    final_webscraping: bool = True,
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    num_workers: int = 1,
    verbose: bool = False,
    show_progress: bool = True,
) -> SnowballResult
```

| Parameter | Type | Description |
|---|---|---|
| `papers` | `list[Paper] \| Paper` | Seed paper(s) to start snowballing from. |
| `max_depth` | `int` | Maximum traversal depth. Defaults to `1`. |
| `direction` | `Literal["both", "backward", "forward"]` | Snowball direction. Defaults to `"both"`. |
| `max_per_level` | `int \| None` | Keep only the N most-cited papers per level in the result; papers outside the top N are excluded from the result but still drive the next BFS level. Seed papers are never filtered. Defaults to `None` (no limit). |
| `max_expansion_per_level` | `int \| None` | Limit how many papers per level become seeds for the next BFS round; only the top N most-cited papers are expanded. Papers already in the result are unaffected. Defaults to `None` (expand all). |
| `databases` | `list[str] \| None` | Databases used for fast BFS discovery of candidate papers. Defaults to `["crossref"]`. Pass `None` to use all available databases. Accepted values: `"arxiv"`, `"crossref"`, `"ieee"`, `"openalex"`, `"pubmed"`, `"scopus"`, `"semantic_scholar"`, `"web_scraping"`, `"wos"`. |
| `enrichment_databases` | `list[str] \| None` | Databases used when re-fetching seeds and frontier papers to populate `paper.references` and `paper.cited_by`. Defaults to all API connectors (web scraping excluded). `None` keeps the default. |
| `final_webscraping` | `bool` | When `True` (default), all papers that survive BFS filtering are re-enriched via HTML scraping at the end of the run to fill any remaining metadata gaps. Set to `False` to skip this pass. |
| `since` | `datetime.date \| None` | Only add discovered papers published on or after this date. Seed papers are never filtered. `None` disables the filter. |
| `until` | `datetime.date \| None` | Only add discovered papers published on or before this date. Seed papers are never filtered. `None` disables the filter. |
| `num_workers` | `int` | Number of parallel workers. Defaults to `1`. |
| `verbose` | `bool` | Enable debug logging. Defaults to `False`. |
| `show_progress` | `bool` | Display progress bars. Defaults to `True`. |

**Returns:** `SnowballResult` containing discovered papers (seeds in `seed_papers`, BFS-discovered papers in `papers`).

---

## Models

### Paper

Represents an academic paper.

```python
from findpapers import Paper
```

#### Constructor

```python
Paper(
    title: str,
    abstract: str,
    authors: list[Author],
    source: Source | None,
    publication_date: datetime.date | None,
    url: str | None = None,
    pdf_url: str | None = None,
    doi: str | None = None,
    citations: int | None = None,
    keywords: set[str] | None = None,
    comments: str | None = None,
    page_count: int | None = None,
    page_range: str | None = None,
    found_in: set[str] | None = None,
    paper_type: PaperType | None = None,
    fields_of_study: set[str] | None = None,
    subjects: set[str] | None = None,
    language: str | None = None,
    is_open_access: bool | None = None,
    is_retracted: bool | None = None,
    funders: set[str] | None = None,
    references: list[str] | None = None,
    cited_by: list[str] | None = None,
)
```

#### Attributes

| Attribute | Type | Description |
|---|---|---|
| `title` | `str` | Paper title. |
| `abstract` | `str` | Paper abstract. |
| `authors` | `list[Author]` | List of authors. |
| `source` | `Source \| None` | Publication venue (journal, conference, etc.). |
| `publication_date` | `datetime.date \| None` | Publication date. |
| `url` | `str \| None` | Landing page URL. |
| `pdf_url` | `str \| None` | Direct PDF URL. |
| `doi` | `str \| None` | Digital Object Identifier. |
| `citations` | `int \| None` | Citation count. |
| `keywords` | `set[str]` | Research keywords. |
| `comments` | `str \| None` | Additional comments. |
| `page_count` | `int \| None` | Total number of pages. |
| `page_range` | `str \| None` | Page range (e.g., `"223-230"`). |
| `found_in` | `set[str]` | Databases where this paper was found. Values are `Database` enum strings (e.g. `"arxiv"`, `"pubmed"`). Populated by `search()`, `get()`, and `snowball()`. |
| `paper_type` | `PaperType \| None` | BibTeX-aligned classification. |
| `fields_of_study` | `set[str]` | Broad knowledge areas. |
| `subjects` | `set[str]` | Disciplinary classifications. |
| `language` | `str \| None` | ISO 639-1 two-letter language code (e.g. `"en"`, `"pt"`). |
| `is_open_access` | `bool \| None` | `True` when the paper is freely available online, `False` when behind a paywall, `None` when unknown. |
| `is_retracted` | `bool \| None` | `True` when the paper was retracted, `False` when known not to be retracted, `None` when unknown. |
| `funders` | `set[str]` | Funding organisations. |
| `references` | `list[str]` | DOIs of papers cited by this paper (backward references). Populated during snowballing and enrichment. Empty list when unknown. |
| `cited_by` | `list[str]` | DOIs of papers that cite this paper (forward references). Populated during snowballing and `get()` lookups via OpenAlex and Semantic Scholar. Empty list when unknown. |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `add_database(database_name: str)` | `None` | Register a database where this paper was found. |
| `merge(paper: Paper)` | `None` | Merge another paper instance into this one, filling missing fields. |
| `to_dict()` | `dict[str, Any]` | Serialize to a dictionary (suitable for JSON). |
| `from_dict(paper_dict: dict)` | `Paper` | *Class method.* Create a `Paper` from a dictionary. |

Two papers are considered equal if they share the same DOI (case-insensitive) or, when DOI is absent, the same title.

---

### PaperType

Enum for BibTeX-aligned paper type classifications.

```python
from findpapers import PaperType
```

| Member | Value | Description |
|---|---|---|
| `ARTICLE` | `"article"` | Journal article. |
| `INPROCEEDINGS` | `"inproceedings"` | Conference paper. |
| `INBOOK` | `"inbook"` | Book chapter. |
| `INCOLLECTION` | `"incollection"` | Part of an edited book. |
| `BOOK` | `"book"` | Complete book. |
| `PHDTHESIS` | `"phdthesis"` | PhD thesis. |
| `MASTERSTHESIS` | `"mastersthesis"` | Master's thesis. |
| `TECHREPORT` | `"techreport"` | Technical report. |
| `UNPUBLISHED` | `"unpublished"` | Preprints and unpublished work. |
| `MISC` | `"misc"` | Miscellaneous. |

---

### Database

Enum of supported academic database identifiers. Values are the canonical string identifiers used in `Paper.found_in`, `SearchResult.databases`, and the `databases` parameter of `search()` and `get()`.

```python
from findpapers import Database
```

| Member | Value | Description |
|---|---|---|
| `ARXIV` | `"arxiv"` | arXiv preprint server. |
| `CROSSREF` | `"crossref"` | CrossRef DOI registration authority. |
| `IEEE` | `"ieee"` | IEEE Xplore digital library. |
| `OPENALEX` | `"openalex"` | OpenAlex open scholarly graph. |
| `PUBMED` | `"pubmed"` | PubMed biomedical literature database. |
| `SCOPUS` | `"scopus"` | Elsevier Scopus abstract and citation database. |
| `SEMANTIC_SCHOLAR` | `"semantic_scholar"` | Semantic Scholar AI-powered research database. |
| `WOS` | `"wos"` | Clarivate Web of Science citation index. |

`Database` is a `StrEnum`, so `Database.ARXIV == "arxiv"` is `True`. `"web_scraping"` is intentionally absent — web scraping is a retrieval mechanism, not a database, and is never stored in `Paper.databases`.

---

### Author

Represents a paper author.

```python
from findpapers import Author
```

#### Constructor

```python
Author(
    name: str,
    affiliation: str | None = None,
)
```

| Parameter | Type | Description |
|---|---|---|
| `name` | `str` | Author's full name (required, non-empty). |
| `affiliation` | `str \| None` | Institutional affiliation. |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `to_dict()` | `dict[str, Any]` | Serialize to dictionary with `"name"` and optional `"affiliation"`. |
| `from_dict(data: dict)` | `Author` | *Class method.* Create an `Author` from a dictionary. |

Two authors are considered equal if they share the same name (case-insensitive).

---

### Source

Represents a publication venue (journal, conference, book, or repository).

```python
from findpapers import Source
```

#### Constructor

```python
Source(
    title: str,
    isbn: str | None = None,
    issn: str | None = None,
    publisher: str | None = None,
    source_type: SourceType | None = None,
)
```

#### Attributes

| Attribute | Type | Description |
|---|---|---|
| `title` | `str` | Source title. |
| `isbn` | `str \| None` | ISBN number. |
| `issn` | `str \| None` | ISSN number. |
| `publisher` | `str \| None` | Publisher name. |
| `source_type` | `SourceType \| None` | Type classification. |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `merge(source: Source)` | `None` | Merge another source into this one, filling missing fields. |
| `to_dict()` | `dict[str, Any]` | Serialize to dictionary. |
| `from_dict(source_dict: dict)` | `Source` | *Class method.* Create a `Source` from a dictionary. |

Two sources are considered equal if they share the same title (case-insensitive).

---

### SourceType

Enum for publication source classifications.

```python
from findpapers import SourceType
```

| Member | Value | Description |
|---|---|---|
| `JOURNAL` | `"journal"` | Peer-reviewed periodicals. |
| `CONFERENCE` | `"conference"` | Conferences and workshops. |
| `BOOK` | `"book"` | Books and monographs. |
| `REPOSITORY` | `"repository"` | Preprint servers. |
| `OTHER` | `"other"` | Other sources. |

---

### SearchResult

Container for search configuration and results.

```python
from findpapers import SearchResult
```

#### Constructor

```python
SearchResult(
    query: str,
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    max_papers_per_database: int | None = None,
    processed_at: datetime.datetime | None = None,
    databases: list[str] | None = None,
    papers: list[Paper] | None = None,
    runtime_seconds: float | None = None,
    runtime_seconds_per_database: dict[str, float] | None = None,
    failed_databases: list[str] | None = None,
)
```

#### Attributes

| Attribute | Type | Description |
|---|---|---|
| `query` | `str` | The search query string. |
| `since` | `datetime.date \| None` | Lower bound date filter. |
| `until` | `datetime.date \| None` | Upper bound date filter. |
| `max_papers_per_database` | `int \| None` | Per-database paper limit. |
| `processed_at` | `datetime.datetime` | Timestamp when the search was executed. |
| `databases` | `list[str] \| None` | Database identifiers that were queried. |
| `papers` | `list[Paper]` | List of retrieved papers. |
| `runtime_seconds` | `float \| None` | Total execution time in seconds. |
| `runtime_seconds_per_database` | `dict[str, float]` | Execution time per database. |
| `failed_databases` | `list[str]` | Databases that failed during search. |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `add_paper(paper: Paper)` | `None` | Add a paper to the results. |
| `remove_paper(paper: Paper)` | `None` | Remove a paper from the results. |
| `to_dict()` | `dict[str, Any]` | Serialize to dictionary (includes metadata and all papers). |
| `from_dict(data: dict)` | `SearchResult` | *Class method.* Create a `SearchResult` from a dictionary. |

---

### SnowballResult

Container for snowball traversal configuration and results.

```python
from findpapers import SnowballResult
```

#### Constructor

```python
SnowballResult(
    seed_papers: list[Paper],
    max_depth: int,
    direction: Literal["both", "backward", "forward"],
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    databases: list[str] | None = None,
    max_per_level: int | None = None,
    max_expansion_per_level: int | None = None,
    papers: list[Paper] | None = None,
    processed_at: datetime.datetime | None = None,
    runtime_seconds: float | None = None,
    skipped_seeds_without_doi: int = 0,
)
```

#### Attributes

| Attribute | Type | Description |
|---|---|---|
| `seed_papers` | `list[Paper]` | Enriched seed papers (fetched during snowball; originals used as fallback when lookup fails). |
| `papers` | `list[Paper]` | Papers *discovered* during BFS traversal (seeds excluded). |
| `max_depth` | `int` | Maximum traversal depth used. |
| `direction` | `str` | Direction used (`"both"`, `"backward"`, or `"forward"`). |
| `since` | `datetime.date \| None` | Lower-bound date filter applied. |
| `until` | `datetime.date \| None` | Upper-bound date filter applied. |
| `databases` | `list[str] \| None` | Databases used for paper lookups. |
| `max_per_level` | `int \| None` | Per-level result cap that was used (`None` = no limit). |
| `max_expansion_per_level` | `int \| None` | Per-level frontier cap that was used (`None` = expand all). |
| `processed_at` | `datetime.datetime` | UTC timestamp when the snowball was executed. |
| `runtime_seconds` | `float \| None` | Wall-clock runtime in seconds. |
| `skipped_seeds_without_doi` | `int` | Number of seed papers skipped because they had no DOI. |

#### Methods

| Method | Returns | Description |
|---|---|---|
| `add_paper(paper: Paper)` | `None` | Add a discovered paper to the results. |
| `remove_paper(paper: Paper)` | `None` | Remove a paper from the results. |
| `to_dict()` | `dict[str, Any]` | Serialize to a dictionary (suitable for JSON). |
| `from_dict(data: dict)` | `SnowballResult` | *Class method.* Create a `SnowballResult` from a dictionary. |

---

## Query Enums

### FilterCode

Field filter codes used in search queries.

```python
from findpapers import FilterCode
```

| Member | Value | Description |
|---|---|---|
| `TITLE` | `"ti"` | Title field. |
| `ABSTRACT` | `"abs"` | Abstract field. |
| `KEYWORDS` | `"key"` | Keywords/subject field. |
| `AUTHOR` | `"au"` | Author name field. |
| `SOURCE` | `"src"` | Source/venue field. |
| `AFFILIATION` | `"aff"` | Affiliation field. |
| `TITLE_ABSTRACT` | `"tiabs"` | Title + abstract. |
| `TITLE_ABSTRACT_KEYWORDS` | `"tiabskey"` | Title + abstract + keywords. |

### ConnectorType

Boolean connector operators used in search queries.

```python
from findpapers import ConnectorType
```

| Member | Value | Description |
|---|---|---|
| `AND` | `"and"` | Intersection of result sets. |
| `OR` | `"or"` | Union of result sets. |
| `AND_NOT` | `"and not"` | Difference (left set minus right set). |

---

## Runners

Runners provide lower-level access to individual operations. They are useful when you need finer control than the `Engine` facade offers.

### SearchRunner

```python
from findpapers import SearchRunner
```

```python
SearchRunner(
    query: str,
    databases: list[str] | None = None,
    max_papers_per_database: int | None = None,
    ieee_api_key: str | None = None,
    scopus_api_key: str | None = None,
    pubmed_api_key: str | None = None,
    openalex_api_key: str | None = None,
    email: str | None = None,
    semantic_scholar_api_key: str | None = None,
    wos_api_key: str | None = None,
    num_workers: int = 1,
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    enrichment_databases: list[str] | None = ["crossref", "web_scraping"],
)
```

| Method | Returns | Description |
|---|---|---|
| `run(verbose=False, show_progress=True)` | `SearchResult` | Execute the search and return results. |

### DownloadRunner

```python
from findpapers import DownloadRunner
```

```python
DownloadRunner(
    papers: list[Paper],
    output_directory: str,
    num_workers: int = 1,
    timeout: float | None = 30.0,
    proxy: str | None = None,
    ssl_verify: bool = True,
)
```

| Method | Returns | Description |
|---|---|---|
| `run(verbose=False, show_progress=True)` | `dict[str, int \| float]` | Execute downloads and return metrics. |

### GetRunner

```python
from findpapers import GetRunner
```

```python
GetRunner(
    identifier: str,
    email: str | None = None,
    databases: list[str] | None = None,
    ieee_api_key: str | None = None,
    scopus_api_key: str | None = None,
    pubmed_api_key: str | None = None,
    openalex_api_key: str | None = None,
    semantic_scholar_api_key: str | None = None,
    wos_api_key: str | None = None,
    timeout: float | None = 10.0,
    proxy: str | None = None,
    ssl_verify: bool = True,
)
```

| Method | Returns | Description |
|---|---|---|
| `run(verbose=False)` | `Paper \| None` | Fetch the paper by identifier (DOI or URL), or return `None` if not found. |

**Raises:** `InvalidParameterError` if the identifier is a bare DOI that is empty or blank.

### SnowballRunner

```python
from findpapers import SnowballRunner
```

```python
SnowballRunner(
    seed_papers: list[Paper] | Paper,
    *,
    max_depth: int = 1,
    direction: Literal["both", "backward", "forward"] = "both",
    max_per_level: int | None = None,
    max_expansion_per_level: int | None = None,
    databases: list[str] | None = ["crossref"],
    enrichment_databases: list[str] | None = None,
    final_webscraping: bool = True,
    openalex_api_key: str | None = None,
    email: str | None = None,
    semantic_scholar_api_key: str | None = None,
    num_workers: int = 1,
    since: datetime.date | None = None,
    until: datetime.date | None = None,
    ieee_api_key: str | None = None,
    scopus_api_key: str | None = None,
    pubmed_api_key: str | None = None,
    wos_api_key: str | None = None,
    proxy: str | None = None,
    ssl_verify: bool = True,
)
```

| Method | Returns | Description |
|---|---|---|
| `run(verbose=False, show_progress=True)` | `SnowballResult` | Execute snowballing and return the result. |

---

## Persistence Functions

Functions for saving and loading papers, search results, and snowball results.

```python
from findpapers import save_to_json, load_from_json
from findpapers import save_to_bibtex, load_from_bibtex
from findpapers import save_to_csv, load_from_csv
```

### `save_to_json()`

```python
save_to_json(data: SearchResult | SnowballResult | list[Paper], path: str) -> None
```

Write data to a JSON file. Accepts a `SearchResult`, `SnowballResult`, or a plain `list[Paper]`.

### `load_from_json()`

```python
load_from_json(path: str) -> SearchResult | SnowballResult | list[Paper]
```

Load data from a JSON file created by `save_to_json()`. The type is auto-detected from the file contents.

### `save_to_bibtex()`

```python
save_to_bibtex(papers: list[Paper], path: str) -> None
```

Write papers to a BibTeX `.bib` file.

### `load_from_bibtex()`

```python
load_from_bibtex(path: str) -> list[Paper]
```

Load papers from a BibTeX `.bib` file.

### `save_to_csv()`

```python
save_to_csv(papers: list[Paper], path: str) -> None
```

Write papers to a CSV file. Multi-valued fields are joined with `"; "`.

### `load_from_csv()`

```python
load_from_csv(path: str) -> list[Paper]
```

Load papers from a CSV file. Expects the header row format produced by `save_to_csv()`.

---

## Exceptions

All exceptions inherit from `FindpapersError`. They also inherit from the corresponding built-in type (`ValueError`) so that existing `except ValueError` handlers continue to work.

```python
from findpapers import (
    FindpapersError,
    QueryValidationError,
    UnsupportedQueryError,
    ModelValidationError,
    InvalidParameterError,
    MissingApiKeyError,
    ConnectorError,
    PersistenceError,
)
```

| Exception | Inherits From | Description |
|---|---|---|
| `FindpapersError` | `Exception` | Base exception for all findpapers errors. |
| `QueryValidationError` | `FindpapersError`, `ValueError` | Raised when a query string is syntactically or semantically invalid. |
| `UnsupportedQueryError` | `FindpapersError`, `ValueError` | Raised when a query uses features not supported by a specific database. |
| `ModelValidationError` | `FindpapersError`, `ValueError` | Raised when a model object (Paper, Author, Source) has invalid data (e.g. missing title). |
| `InvalidParameterError` | `FindpapersError`, `ValueError` | Raised when a function or runner receives an invalid argument (e.g. empty DOI, unknown database). |
| `MissingApiKeyError` | `InvalidParameterError`, `ValueError` | Raised when a connector that requires an API key is used without one (e.g. IEEE, Scopus, WoS). |
| `ConnectorError` | `FindpapersError` | Raised when an external database API encounters an unrecoverable error. |
| `PersistenceError` | `FindpapersError` | Raised when save/load encounters an unsupported data type or format. |
