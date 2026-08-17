# Databases

One of the biggest advantages of Findpapers is that it connects you to **hundreds of millions of academic papers** from eight major databases through a single query. Instead of visiting each portal separately and learning its query syntax, you write one search expression and Findpapers handles the rest - translating your query, running parallel searches, and merging all results with automatic deduplication.

Findpapers searches for papers through **arXiv**, **CrossRef**, **IEEE Xplore**, **OpenAlex**, **PubMed**, **Scopus**, **Semantic Scholar**, and **Web of Science** - together covering virtually every peer-reviewed paper, preprint, and conference proceeding published across all fields of science.

## Overview

The table below shows a quick databases comparison.

| Database | Size (papers) | API Key | Search | Snowball | Similar | Rate Limit |
|----------|------------|---------|--------|-------------|---------|------------|
| arXiv | 3M+ [¹](https://arxiv.org/stats/monthly_submissions) | Not required | Yes | No | No | ~3 s between requests |
| CrossRef | 180M+ [²](https://www.crossref.org/about) | Not required | No | Backward only | No | ~10 req/s |
| IEEE Xplore | 7M+ [³](https://innovate.ieee.org/about-the-ieee-xplore-digital-library) | Required | Yes | No | No | ~200 req/day |
| OpenAlex | 480M+ [⁴](https://openalex.org) | Optional | Yes | Yes (both) | Yes | ~10 req/s with email |
| PubMed | 40M+ [⁵](https://pubmed.ncbi.nlm.nih.gov/about/) | Optional | Yes | No | Yes (biomedical only) | 3 req/s (10 with key) |
| Scopus | 100M+ [⁶](https://www.elsevier.com/products/scopus) | Required | Yes | No | No | 20k req/week |
| Semantic Scholar | 214M+ [⁷](https://www.semanticscholar.org/product/api) | Optional | Yes | Yes (both) | Yes | ~1 req/s with key |
| Web of Science | 240M+ [⁸](https://clarivate.com/webofsciencegroup/solutions/web-of-science/) | Required | Yes | No | No | 1 req/s (Free Trial) / 5 req/s (Institutional) |

> **Every API key from the databases listed above can be obtained at no cost** - just create an account on each provider's website. We strongly recommend getting all of them before using Findpapers, as they unlock additional databases (IEEE, Scopus, Web of Science) and dramatically improve rate limits and reliability on the others (OpenAlex, PubMed, Semantic Scholar). See the **Supported Databases** section for more details on how to get these API keys, and [Configuration](https://github.com/jonatasgrosman/findpapers/blob/main/docs/configuration.md) for how to set them up.

> `Engine.similar()` only queries `semantic_scholar` and `pubmed` by default. OpenAlex supports it too, but its `related_works` signal proved noisier in testing, so it is opt-in only (`databases=["semantic_scholar", "pubmed", "openalex"]`). See [docs/similar.md](similar.md) for details.

---

## Selecting Databases to Search

By default, `Engine.search()` queries all databases. To restrict to specific databases:

```python
result = engine.search(
    "[machine learning]",
    databases=["arxiv", "openalex", "semantic_scholar"],
)
```

Valid database identifiers: `arxiv`, `ieee`, `openalex`, `pubmed`, `scopus`, `semantic_scholar`, `wos`.

## Rate Limiting

Findpapers automatically respects each database's rate limits. When a rate limit is hit, it waits for the required cooldown period before retrying. Responses with status codes 429 (Too Many Requests) and 5xx are retried with exponential backoff.

## Supported Databases

### arXiv

- **URL:** https://arxiv.org
- **API:** Atom Feed API
- **Authentication:** Not required
- **Estimated papers:** 3 million+ ([source](https://arxiv.org/stats/monthly_submissions))
- **Coverage:** Preprints in physics, mathematics, computer science, quantitative biology, quantitative finance, statistics, electrical engineering, systems science, and economics

arXiv is one of the most important open-access repositories in science. Founded in 1991, it hosts preprints - papers that have not yet undergone formal peer review - making it the fastest way to access cutting-edge research. It is especially dominant in physics, mathematics, and computer science, where sharing preprints on arXiv before journal publication is standard practice. Because papers appear here weeks or months before they are published in journals, arXiv is essential for researchers who need to stay ahead of the latest developments.

> **Note:** arXiv's API enforces a minimum interval of 3 seconds between requests. No API key is available - this limit applies to all users equally.

#### Features

- Full boolean query support
- Supports `*` and `?` wildcards (not in first character position)
- Extracts title, abstract, authors (with affiliations), publication date, DOI, landing-page URL, PDF URL, source, paper type, fields of study, subjects (from arXiv category taxonomy), and comments
- All papers are marked as open access

#### Limitations

- No citation count, keywords, language, retraction status, funder, or page range data
- **Not usable for snowballing**: the arXiv API does not expose citation or reference data
- **Stemming:** arXiv uses Lucene-based stemming, so `ti[transformer]` also matches "transformers" and "transforming". Keep this in mind when looking for exact terms
- **Hyphens:** Hyphens are treated as spaces (`ti[self-attention]` is equivalent to `ti[self attention]`). Findpapers normalizes hyphens automatically
- **Filter support:** `ti[]`, `abs[]`, `au[]`, and `tiabs[]` are supported; `key[]`, `src[]`, and `aff[]` are not

---

### CrossRef

- **URL:** https://www.crossref.org
- **API:** CrossRef REST API
- **Authentication:** Not required
- **Estimated DOIs:** 180 million+ ([source](https://www.crossref.org/about))
- **Coverage:** Metadata for scholarly works with DOIs across all disciplines

CrossRef is a nonprofit organization that serves as the official DOI (Digital Object Identifier) registration agency for scholarly content. It provides authoritative, structured metadata for millions of DOIs, including publisher information, reference lists, licensing data, and funding details. While Findpapers does not use CrossRef as a search database, it plays a critical role behind the scenes: it enriches papers found in other databases with additional metadata (abstracts, keywords, citation counts) and enables backward snowballing by following the reference lists attached to each DOI.

> **Note:** No API key is needed. Providing your email enables the CrossRef "polite pool", which offers faster and more reliable responses (~50 requests/s instead of ~10 requests/s for anonymous users).

#### Features

- Extracts title, abstract, authors (with affiliations), DOI, landing-page URL, PDF URL, citation count, keywords (from CrossRef subject field), source (with ISSN, ISBN, publisher), and page range
- **Backward snowballing only:** follows the reference list of a paper (papers it cites) by resolving each cited DOI

#### Limitations

- Not available as a search database. Used only for DOI lookups, enrichment, and backward snowballing
- No paper type, language, open access status, retraction status, or funder data
- Forward snowballing (cited-by) is not supported by the CrossRef API
- Reference lists may be incomplete: only references that carry a DOI can be followed

---

### IEEE Xplore

- **URL:** https://ieeexplore.ieee.org
- **API:** IEEE Xplore API v1
- **Authentication:** API key **required** - free, just register
- **Estimated papers:** 7 million+ ([source](https://innovate.ieee.org/about-the-ieee-xplore-digital-library))
- **Coverage:** Journals, conferences, standards, books, and early access articles in electrical engineering, computer science, and related fields

IEEE Xplore is the digital library of the Institute of Electrical and Electronics Engineers (IEEE), one of the world's largest technical professional organizations. It is the primary source for peer-reviewed content in electrical engineering, computer science, telecommunications, and related disciplines. Its collection includes top-tier conference proceedings (such as CVPR, ICCV, and INFOCOM), highly cited journals (like IEEE Transactions), and technical standards that define industry practices. If your research touches hardware, networking, signal processing, robotics, or AI, IEEE Xplore is likely indispensable.

> **Note:** Register at the [IEEE Developer Portal](https://developer.ieee.org/) to obtain a free API key. No payment or subscription is required. The API is limited to approximately 200 calls per day.

#### Features

- Extracts title, abstract, authors (with per-author affiliations), DOI, landing-page URL, PDF URL, keywords (author-provided terms and MeSH terms), subjects (INSPEC/IEEE controlled vocabulary), citation count, source, paper type, page range, and open access status
- Supports boolean queries with `*` wildcard
- Citation counts are available and will be populated on resulting papers

#### Limitations

- **Not usable for snowballing**: the IEEE API does not expose citation or reference lists
- No language, retraction status, or funder data
- Publication date has year-level granularity only
- Only `*` wildcard supported (not `?`); requires at least 3 characters before the `*`
- **Title-only filter disabled:** The `ti[]` filter is disabled for IEEE because the API's `"Article Title"` field silently returns zero results in `querytext` mode (used for boolean expressions).

---

### OpenAlex

- **URL:** https://openalex.org
- **API:** OpenAlex REST API
- **Authentication:** Optional but **highly recommended** - free, just register
- **Estimated papers:** 480 million+ ([source](https://openalex.org/about))
- **Coverage:** Over 480 million scholarly works across all disciplines

OpenAlex is the largest fully open index of scholarly works in the world. It was built as the open-source successor to Microsoft Academic Graph and is maintained by the nonprofit OurResearch. OpenAlex indexes papers, authors, institutions, and concepts across every academic discipline - from engineering and medicine to social sciences and humanities. Because it is completely open (no paywall, no subscription), it is an ideal backbone for large-scale bibliometric analysis and systematic reviews. It also provides rich citation links, making it one of the best sources for forward and backward snowballing in Findpapers.

> **Note:** Without an API key, OpenAlex allows only ~10 requests per day ($0.01 budget), which is too low for practical use. A free API key raises this to ~10,000 requests per day - no payment needed, just a free account. We strongly recommend obtaining one at [openalex.org/settings/api](https://openalex.org/settings/api).

#### Features

- Extracts title, abstract, authors (with institutional affiliations), publication date, DOI, landing-page URL, PDF URL, citation count, keywords, source, paper type, page range, language (ISO 639-1 code), open access status, retraction status, funders, fields of study, and subjects
- **Citation-capable:** supports both forward snowballing (papers that cite a seed) and backward snowballing (references cited by a seed)
- Best source selection (prefers journals/conferences over repositories)

#### Limitations

- **Wildcards are not supported**: queries using `*` or `?` will raise an error
- `key[]` (keywords) and `src[]` (source) filter codes are not supported
- Abstract reconstruction from inverted index may occasionally differ from the original

---

### PubMed

- **URL:** https://pubmed.ncbi.nlm.nih.gov
- **API:** NCBI E-utilities (esearch + efetch)
- **Authentication:** Optional - free, just register
- **Estimated papers:** 40 million+ ([source](https://pubmed.ncbi.nlm.nih.gov/about/))
- **Coverage:** Biomedical and life sciences literature

PubMed is the world's most important database for biomedical and life sciences research. Maintained by the U.S. National Library of Medicine (NLM) at the National Institutes of Health (NIH), it indexes content from MEDLINE, PubMed Central (PMC), and other life sciences journals. What sets PubMed apart is its use of MeSH (Medical Subject Headings) - a curated, hierarchical vocabulary that human indexers assign to each article, enabling highly precise topical searches that keyword-based systems cannot match. If your research involves medicine, biology, pharmacology, public health, or any health-related field, PubMed is almost certainly your primary database.

> **Note:** Register at the [NCBI website](https://www.ncbi.nlm.nih.gov/account/) and generate an API key from your account settings. It's completely free. Without a key, PubMed allows 3 requests per second; with a key, this increases to 10 requests per second.

#### Features

- Extracts title, abstract, authors (with affiliations), publication date, DOI, URL (PMID-based landing page), keywords (MeSH headings and author keywords), subjects (major MeSH topic headings), page range, source (journal with ISSN), paper type, language (ISO 639-1 code), retraction status, and funders
- Supports `*` wildcard

#### Limitations

- **Not usable for snowballing**: PubMed does not expose citation or reference data through its API
- No PDF URL, citation count, open access status, or fields of study data
- Source type is always `JOURNAL`: conference papers and other types cannot be distinguished
- Only `*` wildcard supported (not `?`); requires at least 4 characters before the `*`
- **Author name format:** PubMed indexes authors as "LastName Initials" (e.g., `Doudna JA`). When using the `au` filter, provide the name in this format for reliable results: `au[Doudna JA]`. Full first names (e.g., `au[Jennifer Doudna]`) may return no results
- **Phrase length limit:** PubMed's phrase index only supports exact-match phrases up to approximately 3 words. Queries like `ti[deep learning]` (2 words) work, but `ti[deep learning for image recognition]` (5 words) returns zero results. Keep `ti[]`, `abs[]`, and `tiabs[]` terms short (1-3 words) for best results. To search for longer concepts, combine shorter phrases with AND: `ti[deep learning] AND ti[image recognition]`

---

### Scopus

- **URL:** https://www.scopus.com
- **API:** Elsevier Scopus Search API
- **Authentication:** API key **required** - free, just register
- **Estimated papers:** 100 million+ ([source](https://www.elsevier.com/products/scopus))
- **Coverage:** Over 100 million records across science, technology, medicine, social sciences, and arts & humanities

Scopus is Elsevier's flagship abstract and citation database, and one of the two largest curated indexes of peer-reviewed literature in the world (alongside Web of Science). It covers over 27,000 journals, 130,000 books, and 13 million conference papers across virtually every scientific discipline. Scopus is the go-to database for many universities and funding agencies when performing bibliometric analysis, rankings, and research evaluation (e.g., h-index calculations). Its broad, multidisciplinary coverage makes it especially valuable for systematic reviews that need to span multiple fields.

> **Note:** Register at the [Elsevier Developer Portal](https://dev.elsevier.com/) and create an API key - it's free. Scopus has a rate limit of 20,000 requests per week, which should be sufficient for most users.

#### Features

- Extracts title, publication date, DOI, URL, citation count, source (with ISSN, eISSN, ISBN, publisher), paper type, page range, and open access status
- Supports boolean queries with `*` and `?` wildcards (requires at least 3 characters before the wildcard)
- Citation counts are available and will be populated on resulting papers

#### Limitations

- **Not usable for snowballing**: the Scopus Search API does not expose reference or citing-paper lists
- Only the first author is returned per result (full author lists require a separate API call not performed by Findpapers)
- No abstract, keywords, PDF URL, language, subjects, fields of study, retraction status, or funder data; enrichment is strongly recommended to fill in missing metadata
- No URL-based paper lookup: only search and DOI lookup are supported
- Date filtering has year-level granularity only

---

### Semantic Scholar

- **URL:** https://www.semanticscholar.org
- **API:** Semantic Scholar Academic Graph API (bulk search + paper details)
- **Authentication:** Optional but **highly recommended** - free, just register
- **Estimated papers:** 214 million+ ([source](https://www.semanticscholar.org/product/api))
- **Coverage:** Over 214 million papers across all fields, powered by AI-based metadata extraction

Semantic Scholar is a free, AI-powered academic search engine developed by the Allen Institute for AI (AI2). Unlike traditional databases that rely on publisher-submitted metadata, Semantic Scholar uses machine learning models to automatically extract titles, authors, abstracts, citations, and topics from the full text of papers. This allows it to index a vast number of sources, including papers from smaller publishers and open-access repositories that other databases may miss. It is particularly strong in computer science and biomedical research, and its citation graph - with both forward and backward links - makes it one of the best sources for snowballing.

> **Note:** Without an API key, Semantic Scholar’s rate limit of 1,000 requests/second is shared among all unauthenticated users, which can lead to throttling during peak times. With a free API key you get a dedicated rate limit, making searches much more reliable. No payment needed - request one at [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api). With an API key, rate limit is 1 request/second (introductory tier).

#### Features

- Extracts title, abstract, authors (with affiliations, resolved in a batch request after search), publication date, DOI, landing-page URL, PDF URL, citation count, source (journal or venue), paper type, page range, open access status, fields of study, and subjects
- **Citation-capable:** supports both forward snowballing (papers that cite a seed) and backward snowballing (references cited by a seed)

#### Limitations

- No keywords, language, retraction status, or funder data
- When exact publication date is unavailable, falls back to year only (January 1)
- Only `tiabs[]` (title + abstract) filter is supported: `ti[]`, `abs[]`, `au[]`, `aff[]`, `src[]`, and `key[]` are all silently resolved to title + abstract
- `?` wildcard not supported; `*` is allowed

---

### Web of Science

- **URL:** https://www.webofscience.com
- **API:** Clarivate Web of Science Starter API v1
- **Authentication:** API key **required** - free, just register
- **Estimated papers:** 240 million+ ([source](https://clarivate.libguides.com/librarianresources/coverage))
- **Coverage:** Multidisciplinary index of peer-reviewed literature across all scientific disciplines, with authoritative citation data

Web of Science is one of the two largest curated indexes of peer-reviewed literature in the world (alongside Scopus). Maintained by Clarivate, it has been indexing scientific literature since 1900 and is considered the gold standard for citation-based research evaluation. It is especially valued by research institutions and funding agencies for its high curation standards and its citation data (including the Journal Impact Factor). Its multidisciplinary coverage spans the sciences, social sciences, arts, and humanities.

> **Note:** Register at the [Clarivate Developer Portal](https://developer.clarivate.com/apis/wos-starter) to obtain a free API key. Free Trial keys are limited to 50 requests per day and do not return citation counts. Institutional members have access to higher quotas (5,000+ req/day) and citation data. Use your institutional email when registering to ensure you get the correct plan.

#### Features

- Extracts title, authors, publication date, DOI, landing-page URL, keywords (author-provided), citation count (institutional plans only), source (with ISSN, eISSN, ISBN), paper type, and page range
- Supports boolean queries with `*` and `?` wildcards (requires at least 3 characters before `*`)
- Supports DOI lookup and Web of Science URL lookup

#### Limitations

- **Abstracts are not returned** by the Starter API: the `abstract` field will remain empty unless filled by enrichment (e.g. CrossRef)
- **Citation counts require an institutional-plan key**: free trial keys always receive no citation data
- **Not usable for snowballing**: the Starter API does not expose reference or citing-paper lists
- No author affiliations, language, open access status, retraction status, funder, or PDF URL data
- Only `ti[]`, `au[]`, `src[]`, `aff[]`, and `tiabskey[]` filters are supported. The `abs[]`, `key[]`, and `tiabs[]` filters are **not available** in the WoS Starter API (there is no abstract-only or keyword-only field tag)
