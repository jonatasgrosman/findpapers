# Save/Load

Findpapers supports three persistence formats: **JSON**, **BibTeX**, and **CSV**. All persistence functions are available as top-level functions in the `findpapers` package.

## JSON

JSON is the recommended format for preserving all metadata. It supports saving and reloading `SearchResult`, `CitationGraph`, and plain `list[Paper]` objects.

### Save

```python
import findpapers

# Save a SearchResult (includes query, dates, database info, and all papers)
findpapers.save_to_json(result, "search_result.json")

# Save a CitationGraph (includes seed papers, edges, and all discovered papers)
findpapers.save_to_json(graph, "citation_graph.json")

# Save a plain list of papers
findpapers.save_to_json(papers, "papers.json")
```

### Load

```python
# Automatically detects the type and returns the correct object
data = findpapers.load_from_json("search_result.json")
# Returns SearchResult, CitationGraph, or list[Paper] depending on file contents
```

### Format Details

The JSON file includes a `"type"` discriminator field:

- `"search_result"` - contains query metadata and a list of papers
- `"citation_graph"` - contains seed papers, edges, depth, direction, and all papers
- `"paper_list"` - contains a plain list of papers

Each paper is serialized with all its attributes, including nested `Author` and `Source` objects. The format is stable and can be used for long-term storage and exchange.

---

## BibTeX

BibTeX save generates standard `.bib` files compatible with LaTeX.

### Save

```python
findpapers.save_to_bibtex(papers, "references.bib")
```

### Load

```python
papers = findpapers.load_from_bibtex("references.bib")
```

### Format Details

- Each paper becomes a BibTeX entry with a type matching its `PaperType` (`@article`, `@inproceedings`, `@book`, etc.). Papers without a type default to `@misc`.
- **Citation keys** are auto-generated from the first author's name, the publication year, and the first word of the title (e.g., `smith2023attention`).
- LaTeX special characters (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`) are escaped automatically.
- Fields included: `title`, `author`, `abstract`, `year`, `doi`, `url`, `keywords`, `journal` (for `@article`), `booktitle` (for `@inproceedings`/`@incollection`), `institution` (for `@techreport`/`@phdthesis`/`@mastersthesis`), `publisher`, `pages`, `howpublished` (for `@misc`/`@unpublished` with a URL), `note` (for `@unpublished`).

### Limitations

- Some metadata is lost during BibTeX save (e.g., `citation count`, `references`, `found_in`, `pdf_url`, `fields_of_study`, `subjects`, `language`, `is_open_access`, `is_retracted`, `funders`). Use JSON for lossless round-trips.

---

## CSV

CSV save creates spreadsheet-compatible files with one paper per row.

### Save

```python
findpapers.save_to_csv(papers, "papers.csv")
```

### Load

```python
papers = findpapers.load_from_csv("papers.csv")
```

### Columns

| Column | Description |
|--------|-------------|
| `title` | Paper title |
| `authors` | Authors, separated by `"; "` |
| `abstract` | Paper abstract |
| `publication_date` | Publication date (ISO format) |
| `doi` | Digital Object Identifier |
| `url` | Paper URL |
| `pdf_url` | Direct PDF URL |
| `source` | Publication source title |
| `publisher` | Publisher name |
| `citations` | Citation count |
| `keywords` | Keywords, separated by `"; "` |
| `paper_type` | BibTeX publication type |
| `page_range` | Page range |
| `found_in` | Database names, separated by `"; "` |
| `fields_of_study` | Fields of study, separated by `"; "` |
| `subjects` | Subjects, separated by `"; "` |
| `language` | ISO 639-1 two-letter language code (e.g. `"en"`) |
| `is_open_access` | `"true"`, `"false"`, or empty when unknown |
| `is_retracted` | `"true"`, `"false"`, or empty when unknown |
| `funders` | Funding organisations, separated by `"; "` |
| `comments` | Free-text comments |

### Format Details

- Multi-valued fields (authors, keywords, found_in, fields_of_study, subjects, funders) are joined with `"; "` as separator
- CSV formula injection is prevented by prefixing cells starting with `=`, `+`, `-`, or `@` with a single quote (`'`)
- The single-quote prefix is automatically removed when importing

### Limitations

- Nested objects like `Source` are flattened (only `source` title and `publisher` are saved)
- Author affiliations are not included in CSV save
- Use JSON for lossless round-trips

---

## Format Comparison

| Feature | JSON | BibTeX | CSV |
|---------|------|--------|-----|
| Lossless round-trip | ✅ | ❌ | ❌ |
| Supports SearchResult | ✅ | ❌ | ❌ |
| Supports CitationGraph | ✅ | ❌ | ❌ |
| LaTeX-compatible | ❌ | ✅ | ❌ |
| Spreadsheet-compatible | ❌ | ❌ | ✅ |
| Author affiliations | ✅ | ❌ | ❌ |
| Citation count | ✅ | ❌ | ✅ |
| Database provenance | ✅ | ❌ | ✅ |
| Fields of study | ✅ | ❌ | ✅ |
