# API Sample Data Collectors

This directory contains standalone scripts to collect fresh API response samples from each database.
These samples are used for testing the searcher implementations.

## Directory Structure

```
tests/data/
├── collect_all_samples.py    # Master script to run all collectors
├── README.md                  # This file
├── arxiv/
│   ├── collect_sample.py     # arXiv API collector
│   ├── sample_response.xml   # Raw XML response (after running)
│   └── collection_metadata.json
├── biorxiv/
│   ├── collect_sample.py     # bioRxiv API collector
│   ├── sample_response.json  # Raw JSON response (after running)
│   └── collection_metadata.json
├── medrxiv/
│   ├── collect_sample.py     # medRxiv API collector
│   ├── sample_response.json  # Raw JSON response (after running)
│   └── collection_metadata.json
├── ieee/
│   ├── collect_sample.py     # IEEE Xplore API collector
│   ├── sample_response.json  # Raw JSON response (after running)
│   └── collection_metadata.json
├── pubmed/
│   ├── collect_sample.py     # PubMed API collector
│   ├── esearch_response.json # Search response with IDs
│   ├── efetch_response.xml   # Full article records
│   └── collection_metadata.json
├── scopus/
│   ├── collect_sample.py     # Scopus API collector
│   ├── sample_response.json  # Raw JSON response (after running)
│   └── collection_metadata.json
├── openalex/
│   ├── collect_sample.py     # OpenAlex API collector
│   ├── sample_response.json  # Raw JSON response (after running)
│   └── collection_metadata.json
└── semanticscholar/
    ├── collect_sample.py     # Semantic Scholar API collector
    ├── relevance_search_response.json  # Relevance search response
    ├── bulk_search_response.json       # Bulk search response
    └── collection_metadata.json
```

## Usage

### Run all collectors

```bash
python tests/data/collect_all_samples.py
```

### Run specific collectors

```bash
python tests/data/collect_all_samples.py arxiv pubmed
```

### Run individual collector

```bash
python tests/data/arxiv/collect_sample.py
```

## API Keys

Some APIs require authentication:

| Database         | API Key Required | Environment Variable                    |
|------------------|------------------|-----------------------------------------|
| arXiv            | No               | -                                       |
| bioRxiv          | No               | -                                       |
| medRxiv          | No               | -                                       |
| IEEE             | **Yes**          | `FINDPAPERS_IEEE_API_TOKEN`             |
| PubMed           | No*              | `FINDPAPERS_PUBMED_API_TOKEN`           |
| Scopus           | **Yes**          | `FINDPAPERS_SCOPUS_API_TOKEN`           |
| OpenAlex         | **Yes**          | `FINDPAPERS_OPENALEX_API_TOKEN`         |
| Semantic Scholar | No*              | `FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN` |

*PubMed and Semantic Scholar work without authentication but recommend using an API key for higher rate limits.

**Note**: As of February 2026, OpenAlex requires an API key (free tier: 100k credits/day).

### Setting up API keys

1. **IEEE Xplore**: Register at https://developer.ieee.org/
2. **Scopus/Elsevier**: Register at https://dev.elsevier.com/
3. **PubMed**: Register at https://www.ncbi.nlm.nih.gov/account/ (optional, 10 req/sec vs 3 req/sec)
4. **OpenAlex**: Request at https://docs.openalex.org/how-to-use-the-api/api-key (optional)
5. **Semantic Scholar**: Request at https://www.semanticscholar.org/product/api#api-key (optional)

Add keys to the `.env` file in the project root (see `.env.sample` for detailed instructions on how to obtain each key):

```
FINDPAPERS_IEEE_API_TOKEN=your_ieee_key_here
FINDPAPERS_SCOPUS_API_TOKEN=your_scopus_key_here
FINDPAPERS_PUBMED_API_TOKEN=your_pubmed_key_here
FINDPAPERS_OPENALEX_API_TOKEN=your_openalex_key_here
FINDPAPERS_SEMANTIC_SCHOLAR_API_TOKEN=your_semanticscholar_key_here
```

## Query Parameters

All collectors use the same search concepts and date range:

- **Search terms**: machine learning, deep learning, NLP, natural language processing
- **Date range**: 2020-01-01 to 2022-12-31
- **Limit**: 50 papers per database

> **Note**: Each API uses different query syntax. The collectors adapt the search terms
> to each API's specific format (Boolean operators, field specifiers, etc.).
>
> **bioRxiv/medRxiv**: These APIs don't support keyword search, so their collectors
> use web scraping on www.medrxiv.org/search to find DOIs, then fetch metadata via API.

## API Documentation

- **arXiv**: https://info.arxiv.org/help/api/user-manual.html
- **bioRxiv/medRxiv**: https://api.biorxiv.org/
- **IEEE Xplore**: https://developer.ieee.org/docs
- **PubMed**: https://www.ncbi.nlm.nih.gov/books/NBK25500/
- **Scopus**: https://dev.elsevier.com/documentation/ScopusSearchAPI.wadl
- **OpenAlex**: https://docs.openalex.org/
- **Semantic Scholar**: https://api.semanticscholar.org/api-docs

## Output Files

Each collector creates:

1. **sample_response.{xml,json}**: Raw API response
2. **collection_metadata.json**: Metadata about the collection including:
   - Collection timestamp
   - API URL used
   - Query parameters
   - Response status
   - Number of results

## Notes

- These scripts are standalone and don't use any findpapers code
- Responses are saved as-is for test fixtures
- Re-running will overwrite existing files
- Some APIs may have rate limits - wait between runs if needed
