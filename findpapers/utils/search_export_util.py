from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

from findpapers.models.paper import Paper

if TYPE_CHECKING:
    from findpapers.models.search import Search


def export_search_to_json(search: Search, path: str) -> None:
    """Write search results to a JSON file.

    Parameters
    ----------
    search : Search
        Search instance with results and metadata.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    payload = search.to_dict()
    with Path(path).open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def export_search_to_csv(search: Search, path: str) -> None:
    """Write search results to a CSV file using the standard column order.

    Parameters
    ----------
    search : Search
        Search instance with papers to export.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    columns = csv_columns()
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for paper in search.papers:
            writer.writerow(paper_to_csv_row(paper))


def export_search_to_bibtex(search: Search, path: str) -> None:
    """Write search results to a BibTeX file.

    Parameters
    ----------
    search : Search
        Search instance with papers to export.
    path : str
        Output file path.

    Returns
    -------
    None
    """
    bibtex_output = "".join(paper_to_bibtex(paper) for paper in search.papers)
    with Path(path).open("w", encoding="utf-8") as handle:
        handle.write(bibtex_output)


def csv_columns() -> list[str]:
    """Return the CSV column order.

    Returns
    -------
    list[str]
        Column names ordered by priority.
    """
    paper_fields = [
        "title",
        "abstract",
        "authors",
        "publication_date",
        "urls",
        "doi",
        "citations",
        "keywords",
        "comments",
        "number_of_pages",
        "pages",
        "databases",
    ]
    publication_fields = [
        "publication_title",
        "publication_isbn",
        "publication_issn",
        "publication_publisher",
        "publication_category",
        "publication_cite_score",
        "publication_sjr",
        "publication_snip",
        "publication_subject_areas",
        "publication_is_potentially_predatory",
    ]
    return paper_fields + publication_fields


def paper_to_csv_row(paper: Paper) -> dict[str, object]:
    """Convert a paper into a CSV row mapping.

    Parameters
    ----------
    paper : Paper
        Paper instance.

    Returns
    -------
    dict[str, object]
        CSV row mapping.
    """
    publication = paper.publication
    row: dict[str, object] = {
        "title": paper.title,
        "abstract": paper.abstract,
        "authors": "; ".join(paper.authors),
        "publication_date": paper.publication_date.isoformat() if paper.publication_date else None,
        "urls": "; ".join(sorted(paper.urls)),
        "doi": paper.doi,
        "citations": paper.citations,
        "keywords": "; ".join(sorted(paper.keywords)),
        "comments": paper.comments,
        "number_of_pages": paper.number_of_pages,
        "pages": paper.pages,
        "databases": "; ".join(sorted(paper.databases)),
        "publication_title": publication.title if publication else None,
        "publication_isbn": publication.isbn if publication else None,
        "publication_issn": publication.issn if publication else None,
        "publication_publisher": publication.publisher if publication else None,
        "publication_category": publication.category if publication else None,
        "publication_cite_score": publication.cite_score if publication else None,
        "publication_sjr": publication.sjr if publication else None,
        "publication_snip": publication.snip if publication else None,
        "publication_subject_areas": (
            "; ".join(sorted(publication.subject_areas)) if publication else None
        ),
        "publication_is_potentially_predatory": (
            publication.is_potentially_predatory if publication else None
        ),
    }
    return row


def paper_to_bibtex(paper: Paper) -> str:
    """Convert a paper into a BibTeX entry.

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
    citation_type = "@unpublished"
    publication = paper.publication
    if publication is not None and publication.category is not None:
        if publication.category == "Journal":
            citation_type = "@article"
        elif publication.category == "Conference Proceedings":
            citation_type = "@inproceedings"
        elif publication.category == "Book":
            citation_type = "@book"
        else:
            citation_type = "@misc"
    citation_key = citation_key_for(paper)
    lines = [f"{citation_type}{{{citation_key},"]
    lines.append(f"{default_tab}title = {{{paper.title}}},")

    if paper.authors:
        authors = " and ".join(paper.authors)
        lines.append(f"{default_tab}author = {{{authors}}},")

    if citation_type == "@unpublished":
        note = bibtex_note(paper)
        if note:
            lines.append(f"{default_tab}note = {{{note}}},")
    elif citation_type == "@article" and publication is not None:
        lines.append(f"{default_tab}journal = {{{publication.title}}},")
    elif citation_type == "@inproceedings" and publication is not None:
        lines.append(f"{default_tab}booktitle = {{{publication.title}}},")
    elif citation_type == "@misc":
        how_published = bibtex_how_published(paper)
        if how_published:
            lines.append(f"{default_tab}howpublished = {{{how_published}}},")

    if publication is not None and publication.publisher is not None:
        lines.append(f"{default_tab}publisher = {{{publication.publisher}}},")

    if paper.publication_date is not None:
        lines.append(f"{default_tab}year = {{{paper.publication_date.year}}},")

    if paper.pages is not None:
        lines.append(f"{default_tab}pages = {{{paper.pages}}},")

    entry = "\n".join(lines)
    entry = entry.rstrip(",") + "\n" if entry.endswith(",") else entry
    return f"{entry}\n}}\n\n"


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
        author_key = paper.authors[0].lower().replace(" ", "").replace(",", "")
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
    urls = sorted(paper.urls)
    if urls:
        parts.append(f"Available at {urls[0]}")
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
    urls = sorted(paper.urls)
    if not urls or paper.publication_date is None:
        return ""
    date = paper.publication_date.strftime("%Y/%m/%d")
    return f"Available at {urls[0]} ({date})"
