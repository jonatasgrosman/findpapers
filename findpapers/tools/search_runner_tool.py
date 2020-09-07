import os
import datetime
import logging
import requests
import copy
from lxml import html
from typing import Optional
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
import findpapers.searchers.scopus_searcher as scopus_searcher
import findpapers.searchers.ieee_searcher as ieee_searcher
import findpapers.searchers.pubmed_searcher as pubmed_searcher
import findpapers.searchers.arxiv_searcher as arxiv_searcher
import findpapers.searchers.acm_searcher as acm_searcher
import findpapers.utils.common_util as common_util
import findpapers.utils.persistence_util as persistence_util


def _get_paper_metadata_by_url(url: str):
    """
    Private method that returns the paper metadata for a given URL, based on the HTML meta tags

    Parameters
    ----------
    url : str
        A paper URL

    Returns
    -------
    dict
        A paper metadata dict (or None if the paper metadata cannot be found)
    """

    response = common_util.try_success(
        lambda url=url: requests.get(url, allow_redirects=True), 2, 2)

    if response is not None and 'text/html' in response.headers.get('content-type').lower():

        page = html.fromstring(response.content)
        meta_list = page.xpath('//meta')

        paper_metadata = {}

        for meta in meta_list:
            meta_name = meta.attrib.get('name')
            meta_content = meta.attrib.get('content')
            if meta_name is not None and meta_content is not None:

                if meta_name in paper_metadata:
                    if not isinstance(paper_metadata.get(meta_name), list):
                        paper_metadata[meta_name] = [paper_metadata.get(meta_name)]
                    paper_metadata.get(meta_name).append(meta_content)
                else:
                    paper_metadata[meta_name] = meta_content

        return paper_metadata


def _force_single_metadata_value_by_key(metadata_entry: dict, metadata_key: str):
    """
    Sometimes a paper page has some erroneous metadata value duplication, 
    this private method is used to workaround this problem

    Parameters
    ----------
    metadata_entry : dict
        A metadata entry
    metadata_key : str
        A metadata key

    Returns
    -------
    object
        A single value
    """

    return metadata_entry.get(metadata_key, None) if not isinstance(metadata_entry.get(metadata_key, None), list) else metadata_entry.get(metadata_key)[0]



def _enrich(search: Search, scopus_api_token: Optional[str] = None):
    """
    Private method that enriches the search results based on paper metadata

    Parameters
    ----------
    search : Search
        A search instance
    scopus_api_token : Optional[str], optional
        A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it, by default None
    """

    i = 0
    total = len(search.papers)
    for paper in copy.copy(search.papers):

        i += 1
        logging.info(f'({i}/{total}) Enriching paper: {paper.title}')

        urls = set()
        if paper.doi is not None:
            urls.add(f'http://doi.org/{paper.doi}')
        else:
            urls = copy.copy(paper.urls)

        for url in urls:

            if paper.title is not None and paper.abstract is not None and paper.publication is not None \
                and len(paper.authors) > 0 and len(paper.keywords) > 0 and paper.publication.issn is not None \
                and paper.publication.category is not None:
                # skipping enrichment if the main values are already filled
                break

            if 'pdf' in url: # trying to skip PDF links
                continue

            paper_metadata = _get_paper_metadata_by_url(url)

            if paper_metadata is not None and 'citation_title' in paper_metadata:

                paper_title = _force_single_metadata_value_by_key(paper_metadata, 'citation_title')

                if paper_title is None or len(paper_title) == 0:
                    continue

                paper_doi = _force_single_metadata_value_by_key(paper_metadata, 'citation_doi')
                paper_abstract = _force_single_metadata_value_by_key(paper_metadata, 'citation_abstract')
                
                paper_authors = paper_metadata.get('citation_author', None)
                if paper_authors is not None and not isinstance(paper_authors, list): # there is only one author
                    paper_authors = [paper_authors]

                paper_keywords = _force_single_metadata_value_by_key(paper_metadata, 'keywords')
                if paper_keywords is not None:
                    paper_keywords = set(paper_keywords.split(','))
                
                publication = None
                publication_title = None
                publication_category = None
                if 'citation_journal_title' in paper_metadata:
                    publication_title = _force_single_metadata_value_by_key(paper_metadata, 'citation_journal_title')
                    publication_category = 'Journal'
                elif 'citation_conference_title' in paper_metadata:
                    publication_title = _force_single_metadata_value_by_key(paper_metadata, 'citation_conference_title')
                    publication_category = 'Conference Proceedings'
                elif 'citation_book_title' in paper_metadata:
                    publication_title = _force_single_metadata_value_by_key(paper_metadata, 'citation_book_title')
                    publication_category = 'Book'

                if publication_title is not None and len(publication_title) > 0:
                
                    publication_issn = _force_single_metadata_value_by_key(paper_metadata, 'citation_issn')
                    publication_isbn = _force_single_metadata_value_by_key(paper_metadata, 'citation_isbn')
                    publication_publisher = _force_single_metadata_value_by_key(paper_metadata, 'citation_publisher')

                    publication = Publication(publication_title, publication_isbn, publication_issn, publication_publisher, publication_category)
                    
                new_paper = Paper(paper_title, paper_abstract, paper_authors, publication, None, set(), paper_doi, keywords=paper_keywords)
                paper.enrich(new_paper)
                
                paper_pdf_url = _force_single_metadata_value_by_key(paper_metadata, 'citation_pdf_url')
                if paper_pdf_url is not None: 
                    paper.add_url(paper_pdf_url)

    if scopus_api_token is not None:

        try:
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception:  # pragma: no cover
            logging.debug(
                'Error while fetching data from Scopus database', exc_info=True)


def _database_safe_run(function: callable, search: Search, database_label: str):
    """
    Private method that calls a provided function catching all exceptions without rasing them, only logging a ERROR message

    Parameters
    ----------
    function : callable
        A function that will be call for database fetching
    search : Search
        A search instance
    database_label : str
        A database label
    """
    if not search.reached_its_limit(database_label):
        logging.info(f'Fetching papers from {database_label} database...')
        try:
            function()
        except Exception:  # pragma: no cover
            logging.debug(
                f'Error while fetching papers from {database_label} database', exc_info=True)


def search(outputpath: str, query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, limit_per_database: Optional[int] = None,
        scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None):
    """
    When you have a query and needs to get papers using it, this is the method that you'll need to call.
    This method will find papers from some databases based on the provided query.

    Parameters
    ----------
    outputpath : str
        A valid file path where the search result file will be placed

    query : str
        A query string that will be used to perform the papers search.

        All the query terms need to be enclosed in quotes and can be associated using boolean operators,
        and grouped using parentheses. 
        E.g.: "term A" AND ("term B" OR "term C") AND NOT "term D"

        You can use some wildcards in the query too. Use ? to replace a single character or * to replace any number of characters. 
        E.g.: "son?" -> will match song, sons, ...
        E.g.: "son*" -> will match song, sons, sonar, songwriting, ...

        Note: All boolean operators needs to be uppercased. The boolean operator "NOT" must be preceded by an "AND" operator.

    since : Optional[datetime.date], optional
        A lower bound (inclusive) date that will be used to filter the search results, by default None

    until : Optional[datetime.date], optional
        A upper bound (inclusive) date that will be used to filter the search results, by default None

    limit : Optional[int], optional
        The max number of papers to collect, by default None

    limit_per_database : Optional[int], optional
        The max number of papers to collect per each database, by default None

    scopus_api_token : Optional[str], optional
        A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it, by default None

    ieee_api_token : Optional[str], optional
        A API token used to fetch data from IEEE database. If you don't have one go to https://developer.ieee.org and get it, by default None

    """
    
    logging.info('Let\'s find some papers, this process may take a while...')

    common_util.check_write_access(outputpath)

    if ieee_api_token is None:
        ieee_api_token = os.getenv('FINDPAPERS_IEEE_API_TOKEN')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('FINDPAPERS_SCOPUS_API_TOKEN')

    search = Search(query, since, until, limit, limit_per_database)

    _database_safe_run(lambda: arxiv_searcher.run(search),
                       search, arxiv_searcher.DATABASE_LABEL)
    _database_safe_run(lambda: pubmed_searcher.run(search),
                       search, pubmed_searcher.DATABASE_LABEL)
    _database_safe_run(lambda: acm_searcher.run(search),
                       search, acm_searcher.DATABASE_LABEL)

    if ieee_api_token is not None:
        _database_safe_run(lambda: ieee_searcher.run(
            search, ieee_api_token), search, ieee_searcher.DATABASE_LABEL)

    if scopus_api_token is not None:
        _database_safe_run(lambda: scopus_searcher.run(
            search, scopus_api_token), search, scopus_searcher.DATABASE_LABEL)

    logging.info('Enriching data...')

    _enrich(search, scopus_api_token)

    logging.info('Finding and merging duplications...')

    search.merge_duplications()

    logging.info(f'It\'s finally over! Good luck with your research :)')

    persistence_util.save(search, outputpath)
