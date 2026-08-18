<p align="center">
  <img src="https://raw.githubusercontent.com/jonatasgrosman/findpapers/main/logo.png" alt="Findpapers Logo" width="400">
</p>

<p align="center">
  <a href="https://github.com/jonatasgrosman/findpapers/blob/master/LICENSE"><img src="https://img.shields.io/pypi/l/findpapers" alt="PyPI - License"></a>
  <a href="https://pypi.org/project/findpapers"><img src="https://img.shields.io/pypi/v/findpapers" alt="PyPI"></a>
</p>

> **WARNING:** A new release is currently being prepared. The `main` branch may change frequently until then. If something stops working, update the tool with `pip install --upgrade git+https://github.com/jonatasgrosman/findpapers.git` and check the latest version of the [documentation](https://github.com/jonatasgrosman/findpapers/tree/main/docs). If you find a bug, please [open an issue](https://github.com/jonatasgrosman/findpapers/issues).

Findpapers is a Python library that gives researchers unified access to **hundreds of millions of academic papers** from different databases - all through a single query. Instead of searching the databases one by one, each with its own interface and query language, Findpapers lets you write one boolean expression and run it everywhere at once, automatically merging and deduplicating the results. It also fetches additional metadata (abstracts, keywords, citations) during search and snowballing, and can download PDFs with automatic URL resolution for major publishers. Whether you're doing a literature review, building a citation graph, or just looking for related work, Findpapers makes it easy to find the papers you need - no matter where they're published.

Findpapers searches for papers through **arXiv**, **CrossRef**, **IEEE Xplore**, **OpenAlex**, **PubMed**, **Scopus**, **Semantic Scholar**, and **Web of Science** - together covering virtually every peer-reviewed paper, preprint, and conference proceeding published across all fields of science.

## Key Features

- **Massive coverage** - access hundreds of millions of papers across eight databases that together span every scientific discipline
- **Multi-database search** - query all databases in parallel with one boolean search expression without needing to learn each database's query syntax
- **Smart deduplication** - automatically merges duplicate papers found across different databases
- **Paper enrichment** - automatically fetch additional metadata (abstracts, keywords, citations) during search and snowball
- **PDF downloading** - download PDFs with automatic URL resolution for major publishers
- **Citation snowballing** - build citation graphs by traversing references and citations (forward and backward)
- **Content-similarity lookup** - find topically related papers around a single seed paper, complementing citation-based discovery
- **Flexible export** - save results as JSON, BibTeX, or CSV
- **Filter codes** - restrict search terms to specific fields (title, abstract, keywords, author, source, affiliation)
- **Parallel execution** - speed up searches and downloads using multiple worker threads

## Requirements

- Python 3.11+

## Installation

```bash
pip install git+https://github.com/jonatasgrosman/findpapers.git
```

## Quick Start

```python
import findpapers
import datetime

engine = findpapers.Engine()

# Search for papers across all databases
search_result = engine.search(
    "[machine learning] AND [healthcare]",
    since=datetime.date(2022, 1, 1),
)

# Download PDFs
engine.download(search_result.papers, "./pdfs")

# Look up a single paper by DOI or landing-page URL
paper = engine.get("10.1038/nature11804")

# Build a snowball result from a seed paper
snowball_result = engine.snowball(paper, max_depth=1, direction="forward")

# Find content-similar papers around a single seed paper
similar_result = engine.similar(paper)

# Save results
findpapers.save_to_json(search_result, "search_result.json")
findpapers.save_to_json(snowball_result, "snowball_result.json")
findpapers.save_to_json(similar_result, "similar_result.json")
findpapers.save_to_bibtex(result.papers, "references.bib")
```

## The Paper Object

Every paper retrieved by Findpapers (via `search()`, `get()`, or `snowball()`) is a `Paper` instance. Call `paper.to_dict()` to get a plain dictionary ready for JSON serialisation. Here is what a fully-populated paper looks like:

```json
{
  "title": "Attention Is All You Need",
  "abstract": "The dominant sequence transduction models are based on complex recurrent or convolutional neural networks that include an encoder and a decoder. The best performing models also connect the encoder and decoder through an attention mechanism. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms, dispensing with recurrence and convolutions entirely...",
  "authors": [
    {"name": "Vaswani, A.", "affiliation": "Google Brain"},
    {"name": "Shazeer, N.", "affiliation": "Google Brain"},
    {"name": "Parmar, N.", "affiliation": "Google Research"}
  ],
  "source": {
    "title": "31st Conference on Neural Information Processing Systems",
    "isbn": null,
    "issn": null,
    "publisher": "Curran Associates",
    "source_type": "conference"
  },
  "publication_date": "2017-12-06",
  "url": "https://arxiv.org/abs/1706.03762",
  "pdf_url": "https://arxiv.org/pdf/1706.03762",
  "doi": "10.48550/arXiv.1706.03762",
  "citations": 140000,
  "keywords": ["attention mechanism", "neural machine translation", "transformer"],
  "comments": null,
  "page_count": 15,
  "page_range": "5998-6008",
  "found_in": ["arxiv", "semantic_scholar"],
  "paper_type": "inproceedings",
  "fields_of_study": ["Computer Science"],
  "subjects": ["Computation and Language", "Machine Learning"],
  "language": "en",
  "is_open_access": true,
  "is_retracted": false,
  "funders": ["Google Brain"],
  "references": ["10.1162/neco.1997.9.8.1735", "10.3115/v1/d14-1179"],
  "cited_by": ["10.18653/v1/2020.acl-main.703", "10.48550/arXiv.1810.04805"]
}
```

See the [API Reference](https://github.com/jonatasgrosman/findpapers/blob/main/docs/api-reference.md) for the full list of fields and methods available on the `Paper` object and other classes.

## Supported Databases

The table below summarizes each supported database - for full details on authentication, rate limits, and per-database quirks, see the [Databases](https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md) documentation.

| Database | Size (papers) | API Key | Coverage |
|----------|------------|---------|----------|
| [arXiv](https://arxiv.org) | 3M+ [¹](https://arxiv.org/stats/monthly_submissions) | Not required | Open-access preprints in physics, math, CS, biology, economics, and more |
| [CrossRef](https://www.crossref.org) | 180M+ [²](https://www.crossref.org/about) | Not required | Authoritative DOI registry for scholarly works across all disciplines |
| [IEEE Xplore](https://ieeexplore.ieee.org) | 7M+ [³](https://innovate.ieee.org/about-the-ieee-xplore-digital-library) | Required | Journals, conferences, and standards in electrical engineering and CS |
| [OpenAlex](https://openalex.org) | 480M+ [⁴](https://openalex.org) | Optional | The largest open catalog of scholarly works across all disciplines |
| [PubMed](https://pubmed.ncbi.nlm.nih.gov) | 40M+ [⁵](https://pubmed.ncbi.nlm.nih.gov/about/) | Optional | Biomedical and life sciences literature (MEDLINE, PMC, and more) |
| [Scopus](https://www.scopus.com) | 100M+ [⁶](https://www.elsevier.com/products/scopus) | Required | Peer-reviewed literature in science, technology, medicine, social sciences, and humanities |
| [Semantic Scholar](https://www.semanticscholar.org) | 214M+ [⁷](https://www.semanticscholar.org/product/api) | Optional | AI-powered academic graph covering all fields of science |
| [Web of Science](https://www.webofscience.com) | 240M+ [⁸](https://clarivate.libguides.com/librarianresources/coverage) | Required | Multidisciplinary curated index of peer-reviewed literature with citation data |


> **Every API key from the databases listed above can be obtained at no cost** - just create an account on each provider's website. We strongly recommend getting all of them before using Findpapers, as they unlock additional databases (IEEE, Scopus, Web of Science) and dramatically improve rate limits and reliability on the others (OpenAlex, PubMed, Semantic Scholar). See [Databases](https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md) for more details on how to get these API keys, and [Configuration](https://github.com/jonatasgrosman/findpapers/blob/main/docs/configuration.md) for how to set them up.

## Documentation

| Document | Description |
|----------|-------------|
| [Databases](https://github.com/jonatasgrosman/findpapers/blob/main/docs/databases.md) | Supported databases, authentication, and per-database details |
| [Query Syntax](https://github.com/jonatasgrosman/findpapers/blob/main/docs/query-syntax.md) | How to write search queries, boolean operators, wildcards, and filter codes |
| [Configuration](https://github.com/jonatasgrosman/findpapers/blob/main/docs/configuration.md) | Environment variables, proxy, SSL, and API keys |
| [Search](https://github.com/jonatasgrosman/findpapers/blob/main/docs/search.md) | Multi-database search with boolean queries |
| [Download](https://github.com/jonatasgrosman/findpapers/blob/main/docs/download.md) | Download PDFs for papers |
| [Snowball](https://github.com/jonatasgrosman/findpapers/blob/main/docs/snowball.md) | Build citation graphs via forward and backward snowballing |
| [Similar](https://github.com/jonatasgrosman/findpapers/blob/main/docs/similar.md) | Find content-similar papers around a single seed paper |
| [Get](https://github.com/jonatasgrosman/findpapers/blob/main/docs/get.md) | Look up a single paper |
| [Save/Load](https://github.com/jonatasgrosman/findpapers/blob/main/docs/save-load.md) | JSON, BibTeX, and CSV persistence details |
| [API Reference](https://github.com/jonatasgrosman/findpapers/blob/main/docs/api-reference.md) | Public classes, functions, enums, and exceptions |

## Want to help?

See the [contribution guidelines](https://github.com/jonatasgrosman/findpapers/blob/main/CONTRIBUTING.md) if you'd like to contribute to the project.
Please follow our [Code of Conduct](https://github.com/jonatasgrosman/findpapers/blob/main/CODE_OF_CONDUCT.md). You don't need to know how to code to contribute, even improving documentation is a valuable contribution.

If this project has been useful for you, please share it with your friends and give us a star on GitHub to help others discover it. You can also [sponsor me](https://github.com/sponsors/jonatasgrosman) to support the development of Findpapers.

![Support the project by starring and sponsoring](https://raw.githubusercontent.com/jonatasgrosman/findpapers/main/support.gif)

## Citation

If you use Findpapers in your research, please cite it:

```bibtex
@misc{grosman2020findpapers,
  title={{Findpapers: A tool for helping researchers who are looking for related works}},
  author={Grosman, Jonatas},
  howpublished={\url{https://github.com/jonatasgrosman/findpapers}},
  year={2020}
}
```
