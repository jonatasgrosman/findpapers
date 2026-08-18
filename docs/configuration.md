# Configuration

Findpapers is configured through the `Engine` constructor. All settings - API keys, proxy, SSL - are passed once when creating the engine and shared across all operations.

## API Keys

Some databases require API keys, while others work without them but benefit from having one. Pass them directly to the `Engine` constructor:

```python
import findpapers

engine = findpapers.Engine(
    ieee_api_key="your-ieee-key",           # Required for IEEE searches
    scopus_api_key="your-scopus-key",       # Required for Scopus searches
    pubmed_api_key="your-pubmed-key",       # Optional (improves rate limit)
    openalex_api_key="your-openalex-key",   # Optional (improves quota)
    semantic_scholar_api_key="your-s2-key", # Optional (improves rate limit)
    wos_api_key="your-wos-key",             # Required for Web of Science searches
    email="researcher@university.edu",      # Optional (enables polite pool for OpenAlex and CrossRef)
)
```

Without any keys, Findpapers can query arXiv, OpenAlex, PubMed, and Semantic Scholar. To unlock IEEE, Scopus, and Web of Science, provide their respective API keys. See [Databases](https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md) for details on how to get each key.

> **Tip:** All API keys from the supported databases can be obtained at no cost. We strongly recommend getting all of them for better rate limits and broader coverage.

## Proxy Configuration

To route all HTTP requests through a proxy:

```python
engine = findpapers.Engine(proxy="http://proxy.example.com:8080")
```

The proxy URL is applied to both HTTP and HTTPS requests.

## SSL Verification

SSL certificate verification is enabled by default. To disable it (e.g., behind a corporate proxy with a custom CA):

```python
engine = findpapers.Engine(ssl_verify=False)
```

> **Warning:** Disabling SSL verification makes requests vulnerable to man-in-the-middle attacks. Only use this in trusted network environments.

## Full Constructor Reference

```python
engine = findpapers.Engine(
    ieee_api_key=None,              # str | None - IEEE Xplore API key
    scopus_api_key=None,            # str | None - Elsevier Scopus API key
    pubmed_api_key=None,            # str | None - NCBI PubMed API key
    openalex_api_key=None,          # str | None - OpenAlex API key
    email=None,                     # str | None - contact email for polite pool access
    semantic_scholar_api_key=None,  # str | None - Semantic Scholar API key
    wos_api_key=None,               # str | None - Clarivate Web of Science API key
    proxy=None,                     # str | None - HTTP/HTTPS proxy URL
    ssl_verify=True,                # bool - verify SSL certificates
)
```

### Environment Variables as Fallback

Every constructor parameter falls back to an environment variable when not provided explicitly. This is useful for keeping credentials out of source code:

```bash
export FINDPAPERS_IEEE_API_TOKEN="your-ieee-key"
export FINDPAPERS_SCOPUS_API_TOKEN="your-scopus-key"
export FINDPAPERS_PUBMED_API_TOKEN="your-pubmed-key"
export FINDPAPERS_OPENALEX_API_TOKEN="your-openalex-key"
export FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN="your-s2-key"
export FINDPAPERS_WOS_API_TOKEN="your-wos-key"
export FINDPAPERS_EMAIL="researcher@university.edu"
export FINDPAPERS_PROXY="http://proxy.example.com:8080"
export FINDPAPERS_SSL_VERIFY="true"
```

Constructor parameters always take precedence over environment variables.

## Parallel Execution

Several methods support parallel execution via the `num_workers` parameter:

```python
# Search databases in parallel
result = engine.search("[machine learning]", num_workers=4)

# Download PDFs in parallel
engine.download(result.papers, "./pdfs", num_workers=8)

# Snowball in parallel
graph = engine.snowball(result.papers[0], num_workers=4)
```

When `num_workers=1` (default), operations run sequentially. When greater than 1, a thread pool is used. The optimal number depends on your network and the API rate limits.

## Verbose Logging

Enable detailed logging for debugging:

```python
result = engine.search("[machine learning]", verbose=True)
```

When `verbose=True`, Findpapers logs HTTP requests, responses, rate limiting events, and processing details to the console.

## Progress Bars

Progress bars are shown by default using [tqdm](https://tqdm.github.io/). Disable them with:

```python
result = engine.search("[machine learning]", show_progress=False)
```

## Timeouts

Download, enrichment, and paper-lookup operations accept a `timeout` parameter (in seconds) for individual HTTP requests:

```python
engine.download(result.papers, "./pdfs", timeout=30.0)
paper = engine.get("10.1038/nature12373", timeout=15.0)
paper = engine.get("https://arxiv.org/abs/1706.03762", timeout=15.0)
```

Set to `None` to disable timeouts (not recommended).
