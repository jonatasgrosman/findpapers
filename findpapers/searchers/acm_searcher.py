import logging
import math
import requests
import datetime
from urllib.parse import urlencode
from typing import Optional
from lxml import html
import findpapers.utils.query_util as query_util
import findpapers.utils.common_util as common_util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


DATABASE_LABEL = "ACM"
"""ACM searcher removed.

The ACM searcher was deprecated and removed because it depended on HTML scraping
instead of a stable API. It is no longer part of the available searchers.
"""

raise ImportError("ACM searcher removed: use API-based searchers instead.")
'''
    if paper_number_of_pages is not None:
        paper_number_of_pages = int(paper_number_of_pages)

    if paper_doi is None:
        paper_doi = paper_metadata.get("DOI")

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, {paper_url}, paper_doi,
                  paper_citations, paper_keywords, None, paper_number_of_pages, paper_pages)

    return paper


def run(search: Search):
    """
    This method fetch papers from ACM database using the provided search parameters
    After fetch the data from ACM, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    """

    papers_count = 0
    result = _get_result(search)

    try:
        total_papers = int(result.xpath(
            "//*[@class=\"hitsLength\"]")[0].text.strip().replace(",", ""))
    except Exception:  # pragma: no cover
        total_papers = 0

    logging.info(f"ACM: {total_papers} papers to fetch")

    page_index = 0
    while(papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL)):

        papers_urls = [BASE_URL+x.attrib["href"]
                       for x in result.xpath("//*[@class=\"issue-item__title\"]//a")]

        if len(papers_urls) == 0:
            break

        for paper_url in papers_urls:

            if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
                break

            try:
                papers_count += 1

                paper_page = _get_paper_page(paper_url)

                paper_title = paper_page.xpath("//*[@class=\"citation__title\"]")[0].text

                logging.info(f"({papers_count}/{total_papers}) Fetching ACM paper: {paper_title}")
                
                paper_doi = None
                if "/abs/" in paper_url:
                    paper_doi = paper_url.split("/abs/")[1]
                elif "/book/" in paper_url:
                    paper_doi = paper_url.split("/book/")[1]
                else:
                    paper_doi = paper_url.split("/doi/")[1]

                paper = _get_paper(paper_page, paper_doi, paper_url)

                if paper is None:
                    continue
                
                paper.add_database(DATABASE_LABEL)

                search.add_paper(paper)

            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)

        if papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL):
            page_index += 1
            result = _get_result(search, page_index)
'''
