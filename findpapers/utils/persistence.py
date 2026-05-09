from __future__ import annotations

import contextlib
import csv
import datetime
import json
import re
from pathlib import Path
from typing import Any, TypeAlias

from findpapers.core.author import Author
from findpapers.core.citation_graph import CitationGraph
from findpapers.core.paper import Paper, PaperType
from findpapers.core.search_result import SearchResult
from findpapers.core.source import Source
from findpapers.exceptions import PersistenceError
from findpapers.utils.version import package_version

#: Union of all persistable types.
Persistable: TypeAlias = "SearchResult | CitationGraph | list[Paper]"


def _extract_papers(data: Persistable) -> list[Paper]:
    """Extract a flat list of papers from any persistable input.

    Parameters
    ----------
    data : SearchResult | CitationGraph | list[Paper]
        Source of papers.

    Returns
    -------
    list[Paper]
        Papers extracted from *data*.

    Raises
    ------
    PersistenceError
        If *data* is not a supported type.
    """
    if isinstance(data, list):
        return data
    if isinstance(data, SearchResult):
        return data.papers
    if isinstance(data, CitationGraph):
        return data.nodes
    raise PersistenceError(
        f"Expected SearchResult, CitationGraph, or list[Paper], got {type(data).__name__}"
    )


def _serialize_to_dict(data: Persistable) -> dict:
    """Serialize any persistable input to a dictionary.

    The output always contains a top-level ``"type"`` key so that
    :func:`load_from_json` can reconstruct the original object.

    Parameters
    ----------
    data : SearchResult | CitationGraph | list[Paper]
        Data to serialize.

    Returns
    -------
    dict
        JSON-ready dictionary.

    Raises
    ------
    PersistenceError
        If *data* is not a supported type.
    """
    if isinstance(data, SearchResult):
        payload = data.to_dict()
        payload["type"] = "search_result"
        return payload
    if isinstance(data, CitationGraph):
        payload = data.to_dict()
        payload["type"] = "citation_graph"
        return payload
    if isinstance(data, list):
        return {
            "type": "paper_list",
            "metadata": {
                "version": package_version(),
                "total_papers": len(data),
            },
            "papers": [p.to_dict() for p in data],
        }
    raise PersistenceError(
        f"Expected SearchResult, CitationGraph, or list[Paper], got {type(data).__name__}"
    )


def save_to_json(data: Persistable, path: str) -> None:
    """Write data to a JSON file.

    Accepts a :class:`~findpapers.core.search_result.SearchResult`,
    a :class:`~findpapers.core.citation_graph.CitationGraph`, or a
    plain ``list[Paper]``.

    Parameters
    ----------
    data : SearchResult | CitationGraph | list[Paper]
        Data to save.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    payload = _serialize_to_dict(data)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def save_to_bibtex(papers: list[Paper], path: str) -> None:
    """Write a list of papers to a BibTeX file.

    Parameters
    ----------
    papers : list[Paper]
        Papers to save.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    bibtex_output = "".join(paper_to_bibtex(paper) for paper in papers)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8") as handle:
        handle.write(bibtex_output)


def load_from_json(
    path: str,
) -> SearchResult | CitationGraph | list[Paper]:
    """Load data previously saved with :func:`save_to_json`.

    The ``"type"`` key in the JSON payload is used to reconstruct the
    correct Python object:

    * ``"search_result"`` → :class:`~findpapers.core.search_result.SearchResult`
    * ``"citation_graph"`` → :class:`~findpapers.core.citation_graph.CitationGraph`
    * ``"paper_list"`` → ``list[Paper]``

    Files saved **before** the ``"type"`` key was introduced are
    auto-detected as either a ``SearchResult`` (when the payload
    contains a ``"papers"`` key) or a ``CitationGraph`` (when it
    contains ``"nodes"`` and ``"edges"`` keys).

    Parameters
    ----------
    path : str
        Path to a JSON file created by :func:`save_to_json`.

    Returns
    -------
    SearchResult | CitationGraph | list[Paper]
        The reconstructed object.

    Raises
    ------
    PersistenceError
        If the file format cannot be identified.
    """
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    kind = payload.get("type")

    # Explicit type discriminator.
    if kind == "search_result":
        return SearchResult.from_dict(payload)
    if kind == "citation_graph":
        return CitationGraph.from_dict(payload)
    if kind == "paper_list":
        return [Paper.from_dict(p) for p in payload.get("papers", [])]

    # Legacy auto-detection (files saved before "type" was added).
    if "nodes" in payload and "edges" in payload:
        return CitationGraph.from_dict(payload)
    if "papers" in payload:
        return SearchResult.from_dict(payload)

    raise PersistenceError(
        "Unrecognised JSON format: expected a 'type' key or a recognisable "
        "SearchResult / CitationGraph structure."
    )


# Characters that must be escaped inside BibTeX field values.
# Order matters: backslash must be escaped first to avoid double-escaping.
_BIBTEX_ESCAPE_MAP: list[tuple[str, str]] = [
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
]


def _normalize_whitespace(text: str) -> str:
    """Collapse newlines and surrounding whitespace into single spaces.

    Prevents literal line breaks from appearing inside BibTeX field values
    and CSV cells, which can confuse external parsers.

    Parameters
    ----------
    text : str
        Raw text that may contain newlines.

    Returns
    -------
    str
        Text with newlines collapsed into single spaces.
    """
    # Replace each run of whitespace that contains at least one newline
    # with a single space, preserving intentional spaces within lines.
    return re.sub(r"\s*\n\s*", " ", text).strip()


def _escape_bibtex(text: str) -> str:
    r"""Escape LaTeX special characters in a BibTeX field value.

    Replaces characters that would otherwise break BibTeX/LaTeX parsing
    with their LaTeX-safe equivalents.

    Parameters
    ----------
    text : str
        Raw text to escape.

    Returns
    -------
    str
        LaTeX-safe text suitable for inclusion in a BibTeX field.
    """
    text = _normalize_whitespace(text)
    for char, replacement in _BIBTEX_ESCAPE_MAP:
        text = text.replace(char, replacement)
    return text


def paper_to_bibtex(paper: Paper) -> str:
    """Convert a paper into a BibTeX entry.

    The BibTeX entry type is taken directly from ``paper.paper_type``
    (whose values are already BibTeX-aligned).  When ``paper_type`` is
    ``None``, the entry falls back to ``@misc``.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    str
        BibTeX entry.
    """
    default_tab = " " * 4
    source = paper.source
    # paper_type values are already BibTeX entry types; fall back to @misc.
    citation_type = f"@{paper.paper_type.value}" if paper.paper_type is not None else "@misc"
    citation_key = citation_key_for(paper)
    lines = [f"{citation_type}{{{citation_key},"]
    lines.append(f"{default_tab}title = {{{_escape_bibtex(paper.title)}}},")

    if paper.authors:
        authors = " and ".join(author.name for author in paper.authors)
        lines.append(f"{default_tab}author = {{{_escape_bibtex(authors)}}},")

    how_published = bibtex_how_published(paper)
    if how_published:
        lines.append(f"{default_tab}howpublished = {{{how_published}}},")

    lines.extend(_bibtex_venue_lines(paper, source, default_tab))

    if paper.doi is not None:
        lines.append(f"{default_tab}doi = {{{paper.doi}}},")

    if source is not None and source.publisher is not None:
        lines.append(f"{default_tab}publisher = {{{_escape_bibtex(source.publisher)}}},")

    if paper.publication_date is not None:
        lines.append(f"{default_tab}year = {{{paper.publication_date.year}}},")

    if paper.page_range is not None:
        lines.append(f"{default_tab}pages = {{{paper.page_range}}},")

    if paper.abstract:
        lines.append(f"{default_tab}abstract = {{{_escape_bibtex(paper.abstract)}}},")

    if paper.keywords:
        kw_str = ", ".join(sorted(paper.keywords))
        lines.append(f"{default_tab}keywords = {{{_escape_bibtex(kw_str)}}},")

    if paper.url is not None:
        lines.append(f"{default_tab}url = {{{paper.url}}},")

    # BibTeX @unpublished requires a note field (contains URL, date, and comments).
    if paper.paper_type == PaperType.UNPUBLISHED:
        note = bibtex_note(paper)
        if note:
            lines.append(f"{default_tab}note = {{{_escape_bibtex(note)}}},")

    entry = "\n".join(lines)
    entry = entry.rstrip(",") + "\n" if entry.endswith(",") else entry
    return f"{entry}\n}}\n\n"


def _bibtex_venue_lines(paper: Paper, source: Source | None, default_tab: str) -> list[str]:
    """Build venue-specific BibTeX lines (journal / booktitle / institution).

    Parameters
    ----------
    paper : Paper
        Paper instance.
    source : Source | None
        Paper source (may be ``None``).
    default_tab : str
        Indentation string.

    Returns
    -------
    list[str]
        Zero or more BibTeX field lines.
    """
    lines: list[str] = []
    if paper.paper_type == PaperType.ARTICLE and source is not None:
        lines.append(f"{default_tab}journal = {{{_escape_bibtex(source.title)}}},")
    if paper.paper_type in {PaperType.INPROCEEDINGS, PaperType.INCOLLECTION} and source is not None:
        lines.append(f"{default_tab}booktitle = {{{_escape_bibtex(source.title)}}},")
    if (
        paper.paper_type in {PaperType.TECHREPORT, PaperType.PHDTHESIS, PaperType.MASTERSTHESIS}
        and source is not None
        and source.publisher is not None
    ):
        lines.append(f"{default_tab}institution = {{{_escape_bibtex(source.publisher)}}},")
    return lines


def citation_key_for(paper: Paper) -> str:
    """Generate a BibTeX citation key for a paper.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    str
        Citation key string.
    """
    author_key = "unknown"
    if paper.authors:
        author_key = paper.authors[0].name.lower().replace(" ", "").replace(",", "")
    year_key = "XXXX"
    if paper.publication_date is not None:
        year_key = str(paper.publication_date.year)
    title_key = paper.title.split(" ")[0].lower() if paper.title else "paper"
    return re.sub(r"[^\w\d]", "", f"{author_key}{year_key}{title_key}")


def bibtex_note(paper: Paper) -> str:
    """Build a BibTeX note field for unpublished entries.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    str
        Note field content.
    """
    parts: list[str] = []
    if paper.url:
        parts.append(f"Available at {paper.url}")
    if paper.publication_date is not None:
        parts.append(f"({paper.publication_date.strftime('%Y/%m/%d')})")
    if paper.comments:
        parts.append(paper.comments)
    return " ".join(parts).strip()


def bibtex_how_published(paper: Paper) -> str:
    """Build a BibTeX howpublished field for misc entries.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    str
        howpublished content.
    """
    if not paper.url or paper.publication_date is None:
        return ""
    date = paper.publication_date.strftime("%Y/%m/%d")
    return f"Available at {paper.url} ({date})"


# ---------------------------------------------------------------------------
# BibTeX import
# ---------------------------------------------------------------------------

# Reverse of _BIBTEX_ESCAPE_MAP for unescaping BibTeX field values.
# Order matters: LaTeX commands must be replaced before the backslash char
# so that intermediate results are not mangled.
_BIBTEX_UNESCAPE_MAP: list[tuple[str, str]] = [
    (r"\textasciicircum{}", "^"),
    (r"\textasciitilde{}", "~"),
    (r"\textbackslash{}", "\\"),
    (r"\&", "&"),
    (r"\%", "%"),
    (r"\$", "$"),
    (r"\#", "#"),
    (r"\_", "_"),
]


def _unescape_bibtex(text: str) -> str:
    r"""Reverse LaTeX escapes produced by :func:`_escape_bibtex`.

    Parameters
    ----------
    text : str
        Escaped BibTeX field value.

    Returns
    -------
    str
        Plain-text value.
    """
    for escaped, raw in _BIBTEX_UNESCAPE_MAP:
        text = text.replace(escaped, raw)
    return text


def _parse_bibtex_entries(raw: str) -> list[dict[str, str]]:
    """Parse raw BibTeX text into a list of field dictionaries.

    Each returned dictionary contains the lowercased field names as keys
    and the brace-delimited values (with outer braces stripped). A special
    ``"_entry_type"`` key holds the entry type (e.g. ``"article"``).

    Parameters
    ----------
    raw : str
        Full contents of a BibTeX file.

    Returns
    -------
    list[dict[str, str]]
        One dict per entry found.
    """
    entries: list[dict[str, str]] = []
    # Match entries like @article{key, ... }
    entry_pattern = re.compile(r"@(\w+)\s*\{([^,]*),", re.IGNORECASE)

    pos = 0
    while pos < len(raw):
        match = entry_pattern.search(raw, pos)
        if match is None:
            break

        entry_type = match.group(1).lower()
        # Find the balanced closing brace for this entry
        body_start = match.end()
        depth = 1
        i = body_start
        while i < len(raw) and depth > 0:
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
            i += 1
        body = raw[body_start : i - 1] if depth == 0 else raw[body_start:]

        fields: dict[str, str] = {"_entry_type": entry_type}
        # Parse individual fields: name = {value} or name = "value"
        field_pattern = re.compile(
            r"(\w+)\s*=\s*(?:\{([^}]*(?:\{[^}]*\}[^}]*)*)\}|\"([^\"]*)\")",
            re.DOTALL,
        )
        for field_match in field_pattern.finditer(body):
            name = field_match.group(1).lower()
            value = (
                field_match.group(2) if field_match.group(2) is not None else field_match.group(3)
            )
            fields[name] = value.strip()
        entries.append(fields)
        pos = i

    return entries


def load_from_bibtex(path: str) -> list[Paper]:
    """Load papers from a BibTeX file.

    Parses the BibTeX entries and reconstructs
    :class:`~findpapers.core.paper.Paper` instances.  Fields that cannot
    be represented (e.g. custom BibTeX fields) are silently ignored.

    Parameters
    ----------
    path : str
        Path to a ``.bib`` file.

    Returns
    -------
    list[Paper]
        Papers reconstructed from BibTeX entries.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    content = Path(path).read_text(encoding="utf-8")
    entries = _parse_bibtex_entries(content)

    papers: list[Paper] = []
    for fields in entries:
        title = _unescape_bibtex(fields.get("title", "")).strip()
        if not title:
            continue

        # Authors: BibTeX uses " and " as separator
        raw_authors = fields.get("author", "")
        authors = [
            Author(name=_unescape_bibtex(a.strip()))
            for a in raw_authors.split(" and ")
            if a.strip()
        ]

        abstract = _unescape_bibtex(fields.get("abstract", ""))

        # Publication date from year field
        publication_date: datetime.date | None = None
        year_str = fields.get("year", "").strip()
        if year_str.isdigit():
            publication_date = datetime.date(int(year_str), 1, 1)

        doi = fields.get("doi")
        url = fields.get("url")
        page_range = fields.get("pages")
        keywords_raw = fields.get("keywords", "")
        keywords = {
            _unescape_bibtex(k.strip()) for k in keywords_raw.split(",") if k.strip()
        } or None

        # Source from journal, booktitle, or institution
        source_title = fields.get("journal") or fields.get("booktitle") or fields.get("institution")
        publisher = fields.get("publisher")
        source: Source | None = None
        if source_title:
            source = Source(
                title=_unescape_bibtex(source_title),
                publisher=_unescape_bibtex(publisher) if publisher else None,
            )

        # PaperType from entry type
        entry_type = fields.get("_entry_type", "misc")
        paper_type: PaperType | None = None
        with contextlib.suppress(ValueError):
            paper_type = PaperType(entry_type)

        papers.append(
            Paper(
                title=title,
                abstract=abstract,
                authors=authors,
                source=source,
                publication_date=publication_date,
                url=url,
                doi=doi,
                page_range=page_range,
                keywords=keywords,
                paper_type=paper_type,
            )
        )

    return papers


# ---------------------------------------------------------------------------
# CSV save / import
# ---------------------------------------------------------------------------

# Characters that trigger formula interpretation in spreadsheet applications
# (Excel, LibreOffice Calc, Google Sheets).  Values starting with any of
# these are prefixed with a single quote on save and stripped on import
# so that round-trips are transparent while preventing formula injection.
# The single quote is the OWASP-recommended prefix (CWE-1236) and is
# natively recognised by Excel as a text-indicator — it hides the quote
# from the displayed cell value.
_CSV_FORMULA_CHARS = frozenset("=+-@")


def _sanitize_csv_value(value: str) -> str:
    """Prevent CSV formula injection in spreadsheet applications.

    If *value* starts with a character that spreadsheet programs interpret
    as a formula (``=``, ``+``, ``-``, ``@``), a leading single quote is
    prepended.  Excel natively recognises ``'`` as a text-indicator and
    hides it from the displayed cell value.  The prefix is transparently
    stripped by :func:`_unsanitize_csv_value` on import.

    Parameters
    ----------
    value : str
        Raw cell value.

    Returns
    -------
    str
        Sanitized value safe for CSV save.
    """
    value = _normalize_whitespace(value)
    if value and value[0] in _CSV_FORMULA_CHARS:
        return "'" + value
    return value


def _unsanitize_csv_value(value: str) -> str:
    """Reverse the sanitization applied by :func:`_sanitize_csv_value`.

    Strips the leading single quote that was prepended to prevent formula
    injection, restoring the original value.

    Parameters
    ----------
    value : str
        Sanitized cell value read from a CSV file.

    Returns
    -------
    str
        Original value with the protective quote prefix removed.
    """
    if value and value[0] == "'" and len(value) > 1 and value[1] in _CSV_FORMULA_CHARS:
        return value[1:]
    return value


#: Columns written by :func:`save_to_csv`.
_CSV_COLUMNS: list[str] = [
    "title",
    "authors",
    "abstract",
    "publication_date",
    "doi",
    "url",
    "pdf_url",
    "source",
    "publisher",
    "citations",
    "keywords",
    "paper_type",
    "page_range",
    "databases",
    "fields_of_study",
    "subjects",
    "language",
    "is_open_access",
    "is_retracted",
    "funders",
    "comments",
]


def save_to_csv(papers: list[Paper], path: str) -> None:
    """Write a list of papers to a CSV file.

    Each row represents one paper.  Multi-valued fields (authors,
    keywords, databases, etc.) are joined with ``"; "``.

    Parameters
    ----------
    papers : list[Paper]
        Papers to save.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for paper in papers:
            writer.writerow(_paper_to_csv_row(paper))


def _bool_to_csv(value: bool | None) -> str:
    """Convert a nullable boolean to a CSV cell string.

    Parameters
    ----------
    value : bool | None
        Boolean value to convert.

    Returns
    -------
    str
        ``"true"``, ``"false"``, or ``""`` for ``None``.
    """
    if value is None:
        return ""
    return "true" if value else "false"


def _csv_parse_bool(raw: str) -> bool | None:
    """Parse a CSV boolean cell back to ``bool | None``.

    Parameters
    ----------
    raw : str
        Cell value (case-insensitive ``"true"``/``"false"`` or ``""``).

    Returns
    -------
    bool | None
        Parsed boolean or ``None`` for empty/unknown strings.
    """
    lower = raw.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    return None


def _paper_to_csv_row(paper: Paper) -> dict[str, str]:
    """Convert a paper to a flat CSV row dictionary.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    dict[str, str]
        Column name → string value mapping.
    """
    row = _paper_to_csv_core_fields(paper)
    row.update(_paper_to_csv_meta_fields(paper))
    return row


def _paper_to_csv_core_fields(paper: Paper) -> dict[str, str]:
    """Build core identity CSV fields for a paper.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    dict[str, str]
        Core field subset: title, authors, abstract, dates, DOI/URL fields and source.
    """
    s = _sanitize_csv_value
    return {
        "title": s(paper.title or ""),
        "authors": s("; ".join(a.name for a in paper.authors)),
        "abstract": s(paper.abstract or ""),
        "publication_date": (paper.publication_date.isoformat() if paper.publication_date else ""),
        "doi": s(paper.doi or ""),
        "url": s(paper.url or ""),
        "pdf_url": s(paper.pdf_url or ""),
        "source": s(paper.source.title if paper.source else ""),
        "publisher": s(paper.source.publisher if paper.source and paper.source.publisher else ""),
        "citations": str(paper.citations) if paper.citations is not None else "",
    }


def _paper_to_csv_meta_fields(paper: Paper) -> dict[str, str]:
    """Build classification and metadata CSV fields for a paper.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    dict[str, str]
        Meta field subset: keywords, paper_type, databases, subjects, etc.
    """
    s = _sanitize_csv_value
    return {
        "keywords": s("; ".join(sorted(paper.keywords)) if paper.keywords else ""),
        "paper_type": paper.paper_type.value if paper.paper_type else "",
        "page_range": paper.page_range or "",
        "databases": "; ".join(sorted(paper.databases)) if paper.databases else "",
        "fields_of_study": (
            s("; ".join(sorted(paper.fields_of_study))) if paper.fields_of_study else ""
        ),
        "subjects": s("; ".join(sorted(paper.subjects)) if paper.subjects else ""),
        "language": paper.language or "",
        "is_open_access": _bool_to_csv(paper.is_open_access),
        "is_retracted": _bool_to_csv(paper.is_retracted),
        "funders": s("; ".join(sorted(paper.funders)) if paper.funders else ""),
        "comments": s(paper.comments or ""),
    }


def load_from_csv(path: str) -> list[Paper]:
    """Load papers from a CSV file.

    Expects a header row with column names matching those produced by
    :func:`save_to_csv`.  Unknown columns are silently ignored.

    Parameters
    ----------
    path : str
        Path to a ``.csv`` file.

    Returns
    -------
    list[Paper]
        Papers reconstructed from CSV rows.

    Raises
    ------
    FileNotFoundError
        If *path* does not exist.
    """
    with Path(path).open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [paper for row in reader if (paper := _csv_row_to_paper(row)) is not None]


def _csv_row_to_paper(row: dict[str, str]) -> Paper | None:
    """Convert a CSV row dictionary back into a Paper.

    Parameters
    ----------
    row : dict[str, str]
        Column name → string value mapping.

    Returns
    -------
    Paper | None
        A :class:`Paper` instance, or ``None`` if the row has no title.
    """
    u = _unsanitize_csv_value

    title = u(row.get("title", "")).strip()
    if not title:
        return None

    raw_authors = u(row.get("authors", ""))
    authors = [Author(name=a.strip()) for a in raw_authors.split(";") if a.strip()]
    abstract = u(row.get("abstract", ""))
    publication_date = _csv_parse_date(row.get("publication_date", ""))
    doi = u(row.get("doi", "")).strip() or None
    url = u(row.get("url", "")).strip() or None
    pdf_url = u(row.get("pdf_url", "")).strip() or None
    source = _csv_parse_source(row, u)
    citations = _csv_parse_int(row.get("citations", ""))
    keywords = _csv_str_set(u(row.get("keywords", "")))
    paper_type = _csv_parse_paper_type(row.get("paper_type", ""))
    page_range = row.get("page_range", "").strip() or None
    databases = _csv_str_set(row.get("databases", ""))
    fields_of_study = _csv_str_set(u(row.get("fields_of_study", "")))
    subjects = _csv_str_set(u(row.get("subjects", "")))
    funders = _csv_str_set(u(row.get("funders", "")))
    language = row.get("language", "").strip() or None
    is_open_access = _csv_parse_bool(row.get("is_open_access", ""))
    is_retracted = _csv_parse_bool(row.get("is_retracted", ""))
    comments = u(row.get("comments", "")).strip() or None

    return Paper(
        title=title,
        abstract=abstract,
        authors=authors,
        source=source,
        publication_date=publication_date,
        url=url,
        pdf_url=pdf_url,
        doi=doi,
        citations=citations,
        keywords=keywords,
        comments=comments,
        page_range=page_range,
        databases=databases,
        paper_type=paper_type,
        fields_of_study=fields_of_study,
        subjects=subjects,
        language=language,
        is_open_access=is_open_access,
        is_retracted=is_retracted,
        funders=funders,
    )


def _csv_str_set(raw: str) -> set[str] | None:
    """Parse a semicolon-separated string into a set.

    Parameters
    ----------
    raw : str
        Semicolon-separated cell value (already unsanitized when applicable).

    Returns
    -------
    set[str] | None
        Non-empty set of stripped tokens, or ``None`` when the input is blank.
    """
    result = {token.strip() for token in raw.split(";") if token.strip()}
    return result or None


def _csv_parse_date(raw: str) -> datetime.date | None:
    """Parse an ISO-format date string from a CSV cell.

    Parameters
    ----------
    raw : str
        Raw cell value.

    Returns
    -------
    datetime.date | None
        Parsed date or ``None`` for empty/invalid strings.
    """
    raw = raw.strip()
    if not raw:
        return None
    with contextlib.suppress(ValueError):
        return datetime.date.fromisoformat(raw)
    return None


def _csv_parse_int(raw: str) -> int | None:
    """Parse an integer from a CSV cell.

    Parameters
    ----------
    raw : str
        Raw cell value.

    Returns
    -------
    int | None
        Parsed integer or ``None`` for empty/invalid strings.
    """
    raw = raw.strip()
    if not raw:
        return None
    with contextlib.suppress(ValueError):
        return int(raw)
    return None


def _csv_parse_source(
    row: dict[str, str],
    unsanitize: Any,
) -> Source | None:
    """Parse a Source from CSV row fields.

    Parameters
    ----------
    row : dict[str, str]
        CSV row dict.
    unsanitize : callable
        Unsanitize function to apply to cell values.

    Returns
    -------
    Source | None
        Parsed source or ``None`` when no title is present.
    """
    source_title = unsanitize(row.get("source", "")).strip()
    if not source_title:
        return None
    publisher = unsanitize(row.get("publisher", "")).strip() or None
    return Source(title=source_title, publisher=publisher)


def _csv_parse_paper_type(raw: str) -> PaperType | None:
    """Parse a PaperType from a CSV cell value.

    Parameters
    ----------
    raw : str
        Raw cell value.

    Returns
    -------
    PaperType | None
        Parsed paper type or ``None`` for unknown/empty strings.
    """
    raw = raw.strip()
    if not raw:
        return None
    with contextlib.suppress(ValueError):
        return PaperType(raw)
    return None
