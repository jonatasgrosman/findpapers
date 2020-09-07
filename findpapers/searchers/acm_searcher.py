import logging
import math
import requests
import datetime
from urllib.parse import urlencode
from typing import Optional
from lxml import html
import findpapers.utils.common_util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


DEFAULT_SESSION = DefaultSession()
DATABASE_LABEL = 'ACM'
BASE_URL = 'https://dl.acm.org'
MAX_ENTRIES_PER_PAGE = 100


def _get_search_url(search: Search, start_record: Optional[int] = 0) -> str:
    """
    This method return the URL to be used to retrieve data from ACM database
    See https://dl.acm.org/search/advanced for query tips

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str
        Sequence number of first record to fetch, by default 0

    Returns
    -------
    str
        a URL to be used to retrieve data from ACM database
    """

    query = search.query.replace(' AND NOT ', ' NOT ')

    url_parameters = {
        'fillQuickSearch': 'false',
        'expand': 'all',
        'AllField': query,
        'pageSize': MAX_ENTRIES_PER_PAGE,
        'startPage': start_record
    }

    if search.since is not None:
        url_parameters['AfterMonth'] = search.since.month
        url_parameters['AfterYear'] = search.since.year

    if search.until is not None:
        url_parameters['BeforeMonth'] = search.since.month
        url_parameters['BeforeYear'] = search.since.year

    url = f'{BASE_URL}/action/doSearch?{urlencode(url_parameters)}'

    return url


def _get_result(search: Search, start_record: Optional[int] = 0) -> dict:  # pragma: no cover
    """
    This method return results from ACM database using the provided search parameters

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str
        Sequence number of first record to fetch, by default 0

    Returns
    -------
    dict
        a result from ACM database
    """

    url = _get_search_url(search, start_record)

    response = util.try_success(lambda: DEFAULT_SESSION.get(url), 2)
    return html.fromstring(response.content)


def _get_paper_page(url: str) -> html.HtmlElement:  # pragma: no cover
    """
    Get a paper page element from a provided URL

    Parameters
    ----------
    url : str
        The paper URL

    Returns
    -------
    Object
        A HTML element representing the paper given by the provided URL
    """

    response = util.try_success(lambda: DEFAULT_SESSION.get(url), 2)
    return html.fromstring(response.content)


def _get_paper_metadata(doi: str) -> dict:  # pragma: no cover
    """
    Get a paper metadata from a provided DOI

    Parameters
    ----------
    doi : str
        The paper DOI

    Returns
    -------
    dict
        The ACM paper metadata, or None if there's no metadata available
    """

    form = {
        'dois': doi,
        'targetFile': 'custom-bibtex',
        'format': 'bibTex'
    }

    response = util.try_success(lambda: DEFAULT_SESSION.post(
        f'{BASE_URL}/action/exportCiteProcCitation', data=form).json(), 2)

    if response is not None and response.get('items', None) is not None and len(response.get('items')) > 0:
        return response['items'][0][doi]


def _get_paper(paper_page: html.HtmlElement, paper_doi: str, paper_url: str) -> Paper:
    """
    Using a paper entry provided, this method builds a paper instance

    Parameters
    ----------
    paper_page : html.HtmlElement
        A paper page retrived from ACM
    paper_doi : str
        The paper DOI
    paper_url : str
        The ACM paper URL

    Returns
    -------
    Paper
        A paper instance
    """

    paper_abstract = paper_page.xpath(
        '//*[contains(@class, "abstractSection")]/p')[0].text

    citation_elements = paper_page.xpath(
        '//*[contains(@class, "article-metric citation")]//span')
    paper_citations = None
    if len(citation_elements) == 1:
        paper_citations = int(citation_elements[0].text)

    paper_metadata = _get_paper_metadata(paper_doi)

    if paper_metadata is None:
        return None

    publication = None
    publication_title = paper_metadata.get('container-title', None)

    if publication_title is not None and len(publication_title) > 0:

        publication_isbn = paper_metadata.get('ISBN', None)
        publication_issn = paper_metadata.get('ISSN', None)
        publication_publisher = paper_metadata.get('publisher', None)
        publication_category = paper_metadata.get('type', None)

        publication = Publication(publication_title, publication_isbn,
                                publication_issn, publication_publisher, publication_category)

    paper_title = paper_metadata.get('title', None)

    if paper_title is None or len(paper_title) == 0:
        return None

    paper_authors = paper_metadata.get('author', [])
    paper_authors = ['{} {}'.format(
        x.get('given'), x.get('family')) for x in paper_authors]

    paper_publication_date = None
    if paper_metadata.get('issued', None) != None:
        date_parts = paper_metadata['issued']['date-parts'][0]
        if len(date_parts) == 1:  # only year
            paper_publication_date = datetime.date(date_parts[0], 1, 1)
        else:
            paper_publication_date = datetime.date(
                date_parts[0], date_parts[1], date_parts[2])

    paper_keywords = set()
    if paper_metadata.get('keyword', None) is not None:
        paper_keywords = set([x.strip()
                              for x in paper_metadata['keyword'].split(',')])

    paper_pages = paper_metadata.get('page', None)
    if paper_pages is not None:
        paper_pages = paper_pages.replace('\u2013', '-')

    paper_number_of_pages = paper_metadata.get('number-of-pages', None)
    if paper_number_of_pages is not None:
        paper_number_of_pages = int(paper_number_of_pages)

    if paper_doi is None:
        paper_doi = paper_metadata.get('DOI')

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
            '//*[@class="hitsLength"]')[0].text.strip())
    except Exception:  # pragma: no cover
        total_papers = 0

    logging.info(f'{total_papers} papers to fetch')

    page_index = 0
    while(papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL)):

        papers_urls = [BASE_URL+x.attrib['href']
                       for x in result.xpath('//*[@class="hlFld-Title"]/a')]

        for paper_url in papers_urls:

            if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
                break

            try:
                papers_count += 1

                paper_page = _get_paper_page(paper_url)

                paper_title = paper_page.xpath('//*[@class="citation__title"]')[0].text

                logging.info(f'({papers_count}/{total_papers}) Fetching ACM paper: {paper_title}')
                
                paper_doi = None
                if '/abs/' in paper_url:
                    paper_doi = paper_url.split('/abs/')[1]
                elif '/book/' in paper_url:
                    paper_doi = paper_url.split('/book/')[1]
                else:
                    paper_doi = paper_url.split('/doi/')[1]

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
