import requests
import datetime
import logging
import re
from lxml import html
from typing import Optional
import findpapers.utils.common_util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


DEFAULT_SESSION = DefaultSession()
DATABASE_LABEL = 'Scopus'
BASE_URL = 'https://api.elsevier.com'


def _get_query(search: Search) -> str:
    """
    Get the translated query from search instance to fetch data from Scopus database
    See https://dev.elsevier.com/tips/ScopusSearchTips.htm for query tips

    Parameters
    ----------
    search : Search
        A search instance

    Returns
    -------
    str
        The translated query
    """

    query = f'TITLE-ABS-KEY({search.query})'

    if search.since is not None:
        query += f' AND PUBYEAR > {search.since.year - 1}'
    if search.until is not None:
        query += f' AND PUBYEAR < {search.until.year + 1}'

    return query


def _get_publication_entry(publication_issn: str, api_token: str) -> dict:  # pragma: no cover
    """
    Get publication entry by publication ISSN

    Parameters
    ----------
    publication_issn : str
        A publication ISSN
    api_token : str
        A Scopus API token

    Returns
    -------
    dict (or None)
        publication entry in dict format, or None if the API doesn't return a valid entry
    """

    url = f'{BASE_URL}/content/serial/title/issn/{publication_issn}?apiKey={api_token}'
    headers = {'Accept': 'application/json'}
    response = util.try_success(lambda: DEFAULT_SESSION.get(
        url, headers=headers).json().get('serial-metadata-response', None), 2)

    if response is not None and 'entry' in response and len(response.get('entry')) > 0:
        return response.get('entry')[0]


def _get_publication(paper_entry: dict, api_token: str) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from scopus API
    api_token : str
        A Scopus API token

    Returns
    -------
    Publication
        A publication instance or None
    """

    # getting data

    publication_title = paper_entry.get('prism:publicationName', None)

    if publication_title is None or len(publication_title) == 0:
        return None

    publication_isbn = paper_entry.get('prism:isbn', None)
    publication_issn = paper_entry.get('prism:issn', None)
    publication_category = paper_entry.get('prism:aggregationType', None)

    if isinstance(publication_isbn, list):
        publication_isbn = publication_isbn[0].get('$')

    if isinstance(publication_issn, list):
        publication_issn = publication_issn[0].get('$')

    publication = Publication(publication_title, publication_isbn,
                              publication_issn, None, publication_category)

    return publication


def _get_paper_page(url: str) -> object:  # pragma: no cover
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


def _get_paper(paper_entry: dict, publication: Publication) -> Paper:
    """
    Using a paper entry provided, this method builds a paper instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from scopus API
    publication : Publication
        A publication instance that will be associated with the paper

    Returns
    -------
    Paper
        A paper instance or None
    """

    # getting data

    paper_title = paper_entry.get('dc:title', None)

    if paper_title is None or len(paper_title) == 0:
        return None

    paper_publication_date = paper_entry.get('prism:coverDate', None)
    paper_doi = paper_entry.get('prism:doi', None)
    paper_citations = paper_entry.get('citedby-count', None)
    paper_first_author = paper_entry.get('dc:creator', None)
    paper_abstract = None
    paper_authors = []
    paper_urls = set()
    paper_keywords = set()
    paper_pages = None
    paper_number_of_pages = None

    # post processing data

    if paper_first_author is not None:
        paper_authors.append(paper_first_author)

    if paper_publication_date is not None:
        date_split = paper_publication_date.split('-')
        paper_publication_date = datetime.date(
            int(date_split[0]), int(date_split[1]), int(date_split[2]))

    if paper_citations is not None:
        paper_citations = int(paper_citations)

    # enriching data

    paper_scopus_link = None
    for link in paper_entry.get('link', []):
        if link.get('@ref') == 'scopus':
            paper_scopus_link = link.get('@href')
            break

    if paper_scopus_link is not None:

        paper_urls.add(paper_scopus_link)

        try:

            paper_page = _get_paper_page(paper_scopus_link)

            paper_abstract = paper_page.xpath(
                '//section[@id="abstractSection"]//p//text()[normalize-space()]')
            if len(paper_abstract) > 0:
                paper_abstract = re.sub(
                    '\xa0', ' ', ''.join(paper_abstract)).strip()

            authors = paper_page.xpath(
                '//*[@id="authorlist"]/ul/li/span[@class="previewTxt"]')
            paper_authors = []
            for author in authors:
                paper_authors.append(author.text.strip())

            keywords = paper_page.xpath('//*[@id="authorKeywords"]/span')
            for keyword in keywords:
                paper_keywords.add(keyword.text.strip())

            try:
                paper_pages = paper_page.xpath(
                    '//span[@id="journalInfo"]')[0].text.split('Pages')[1].strip()
                if paper_pages.isdigit():  # pragma: no cover
                    paper_number_of_pages = 1
                else:
                    pages_split = paper_pages.split('-')
                    paper_number_of_pages = abs(
                        int(pages_split[0])-int(pages_split[1]))+1
            except Exception:  # pragma: no cover
                pass

        except Exception as e:
            logging.debug(e, exc_info=True)

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, paper_urls, paper_doi, paper_citations, paper_keywords,
                  None, paper_number_of_pages, paper_pages)

    return paper


def _get_search_results(search: Search, api_token: str, url: Optional[str] = None) -> dict:  # pragma: no cover
    """
    This method fetch papers from Scopus database using the provided search parameters

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from Scopus database,
    url : Optional[str]
        A predefined URL to be used for the search execution, 
        this is usually used for make the next recursive call on a result pagination
    """

    # is url is not None probably this is a recursive call to the next url of a pagination
    if url is None:
        query = _get_query(search)
        url = f'{BASE_URL}/content/search/scopus?&sort=citedby-count,relevancy,pubyear&apiKey={api_token}&query={query}'

    headers = {'Accept': 'application/json'}

    return util.try_success(lambda: DEFAULT_SESSION.get(url, headers=headers).json()['search-results'], 2)


def enrich_publication_data(search: Search, api_token: str):
    """
    This method fetch papers from Scopus database to enrich publication data

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from Scopus database,

    Raises
    ------
    AttributeError
        - The API token cannot be null
    """

    if api_token is None or len(api_token.strip()) == 0:
        raise AttributeError('The API token cannot be null')
    
    i = 0
    total = len(search.publication_by_key.items())
    for publication_key, publication in search.publication_by_key.items():
        
        i += 1
        logging.info(f'({i}/{total}) Enriching publication: {publication.title}')

        if publication.issn is not None:

            publication_entry = _get_publication_entry(
                publication.issn, api_token)

            if publication_entry is not None:

                publication_category = publication_entry.get(
                    'prism:aggregationType', None)
                if publication_category is not None and publication.category is None:
                    publication.category = publication_category

                publication_publisher = publication_entry.get(
                    'dc:publisher', None)

                if publication_publisher is not None:
                    publication.publisher = publication_publisher

                for subject_area in publication_entry.get('subject-area', []):
                    publication.subject_areas.add(subject_area.get('$'))

                publication_cite_score = util.try_success(lambda x=publication_entry: float(
                    x.get('citeScoreYearInfoList').get('citeScoreCurrentMetric')))

                if publication_cite_score is not None:
                    publication.cite_score = publication_cite_score

                if 'SJRList' in publication_entry and len(publication_entry.get('SJRList').get('SJR')) > 0:
                    publication_sjr = util.try_success(lambda x=publication_entry: float(
                        x.get('SJRList').get('SJR')[0].get('$')))

                if publication_sjr is not None:
                    publication.sjr = publication_sjr

                if 'SNIPList' in publication_entry and len(publication_entry.get('SNIPList').get('SNIP')) > 0:
                    publication_snip = util.try_success(lambda x=publication_entry: float(
                        x.get('SNIPList').get('SNIP')[0].get('$')))

                if publication_snip is not None:
                    publication.snip = publication_snip


def run(search: Search, api_token: str, url: Optional[str] = None, papers_count: Optional[int] = 0):
    """
    This method fetch papers from Scopus database using the provided search parameters
    After fetch the data from Scopus, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance
    api_token : str
        The API key used to fetch data from Scopus database,
    url : Optional[str]
        A predefined URL to be used for the search execution, 
        this is usually used for make the next recursive call on a result pagination
    papers_count : Optional[int]
        Papers count used on recursion calls

    Raises
    ------
    AttributeError
        - The API token cannot be null
    """

    if api_token is None or len(api_token.strip()) == 0:
        raise AttributeError('The API token cannot be null')

    search_results = _get_search_results(search, api_token, url)

    total_papers = int(search_results.get('opensearch:totalResults', 0))

    logging.info(f'{total_papers} papers to fetch')

    for paper_entry in search_results.get('entry', []):

        if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
            break

        papers_count += 1

        try:

            paper_title = paper_entry.get("dc:title")
            logging.info(f'({papers_count}/{total_papers}) Fetching Scopus paper: {paper_title}')

            publication = _get_publication(paper_entry, api_token)
            paper = _get_paper(paper_entry, publication)

            if paper is not None:
                paper.add_database(DATABASE_LABEL)
                search.add_paper(paper)

        except Exception as e:  # pragma: no cover
            logging.debug(e, exc_info=True)

    next_url = None
    for link in search_results['link']:
        if link['@ref'] == 'next':
            next_url = link['@href']
            break

    # If there is a next url, the API provided response was paginated and we need to process the next url
    # We'll make a recursive call for it
    if papers_count < total_papers and next_url is not None and not search.reached_its_limit(DATABASE_LABEL):
        run(search, api_token, next_url, papers_count)
