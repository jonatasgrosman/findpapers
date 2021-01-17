import os
import datetime
import logging
import requests
import copy
import re
from urllib.parse import urlparse
from lxml import html
from typing import Optional, List
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession
import findpapers.searchers.scopus_searcher as scopus_searcher
import findpapers.searchers.ieee_searcher as ieee_searcher
import findpapers.searchers.pubmed_searcher as pubmed_searcher
import findpapers.searchers.arxiv_searcher as arxiv_searcher
import findpapers.searchers.acm_searcher as acm_searcher
import findpapers.searchers.medrxiv_searcher as medrxiv_searcher
import findpapers.searchers.biorxiv_searcher as biorxiv_searcher
import findpapers.utils.common_util as common_util
import findpapers.utils.persistence_util as persistence_util
import findpapers.utils.publication_util as publication_util


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
    for paper in list(search.papers):

        i += 1
        logging.info(f'({i}/{total}) Enriching paper: {paper.title}')

        try:

            urls = set()
            if paper.doi is not None:
                urls.add(f'http://doi.org/{paper.doi}')
            else:
                urls = copy.copy(paper.urls)

            for url in urls:

                if 'pdf' in url: # trying to skip PDF links
                    continue

                paper_metadata = _get_paper_metadata_by_url(url)

                if paper_metadata is not None and 'citation_title' in paper_metadata:

                    # when some paper data is present on page's metadata, force to use it. In most of the cases this data is more relyable

                    paper_title = _force_single_metadata_value_by_key(paper_metadata, 'citation_title')
                    
                    if paper_title is None or len(paper_title.strip()) == 0:
                        continue

                    paper.title = paper_title

                    paper_doi = _force_single_metadata_value_by_key(paper_metadata, 'citation_doi')
                    if paper_doi is not None and len(paper_doi.strip()) > 0:
                        paper.doi = paper_doi

                    paper_abstract = _force_single_metadata_value_by_key(paper_metadata, 'citation_abstract')
                    if paper_abstract is not None and len(paper_abstract.strip()) > 0:
                        paper.abstract = paper_abstract
                    
                    paper_authors = paper_metadata.get('citation_author', None)
                    if paper_authors is not None and not isinstance(paper_authors, list): # there is only one author
                        paper_authors = [paper_authors]

                    if paper_authors is not None and len(paper_authors) > 0:
                        paper.authors = paper_authors

                    paper_keywords = _force_single_metadata_value_by_key(paper_metadata, 'citation_keywords')
                    if paper_keywords is None or len(paper_keywords.strip()) > 0:
                        paper_keywords = _force_single_metadata_value_by_key(paper_metadata, 'keywords')

                    if paper_keywords is not None and len(paper_keywords.strip()) > 0:
                        if ',' in paper_keywords:
                            paper_keywords = paper_keywords.split(',')
                        elif ';' in paper_keywords:
                            paper_keywords = paper_keywords.split(';')
                        paper_keywords = set([x.strip() for x in paper_keywords])

                    if paper_keywords is not None and len(paper_keywords) > 0:
                        paper.keywords = paper_keywords
                    
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

                    if publication_title is not None and len(publication_title) > 0 and publication_title.lower() not in ['biorxiv', 'medrxiv', 'arxiv']:
                    
                        publication_issn = _force_single_metadata_value_by_key(paper_metadata, 'citation_issn')
                        publication_isbn = _force_single_metadata_value_by_key(paper_metadata, 'citation_isbn')
                        publication_publisher = _force_single_metadata_value_by_key(paper_metadata, 'citation_publisher')

                        publication = Publication(publication_title, publication_isbn, publication_issn, publication_publisher, publication_category)
                        
                        if paper.publication is None:
                            paper.publication = publication
                        else:
                            paper.publication.enrich(publication)

                    paper_pdf_url = _force_single_metadata_value_by_key(paper_metadata, 'citation_pdf_url')
                    
                    if paper_pdf_url is not None: 
                        paper.add_url(paper_pdf_url)

        except Exception:  # pragma: no cover
            pass

    if scopus_api_token is not None:

        try:
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception:  # pragma: no cover
            logging.debug(
                'Error while fetching data from Scopus database', exc_info=True)


def _filter(search: Search):
    """
    Private method that filter the search results

    Parameters
    ----------
    search : Search
        A search instance
    """

    if search.publication_types is not None:
        for paper in list(search.papers):
            try:
                if (paper.publication is not None and paper.publication.category.lower() not in search.publication_types) or \
                    (paper.publication is None and 'other' not in search.publication_types):
                    search.remove_paper(paper)
            except Exception:
                pass


def _flag_potentially_predatory_publications(search: Search):
    """
    Flag all the potentially predatory publications

    Parameters
    ----------
    search : Search
        A search instance
    """

    for paper in list(search.papers):
        try:

            if paper.publication is not None:
                publication_name = paper.publication.title.lower()
                publication_host = None
            
                if paper.doi is not None:
                    url = f'http://doi.org/{paper.doi}'
                    response = common_util.try_success(lambda url=url: DefaultSession().get(url), 2)

                    if response is not None:
                        publication_host = urlparse(response.url).netloc.replace("www.", "")

                if publication_name in publication_util.POTENTIAL_PREDATORY_JOURNALS_NAMES \
                    or publication_host in publication_util.POTENTIAL_PREDATORY_JOURNALS_HOSTS:

                    paper.publication.is_potentially_predatory = True

        except Exception:
            pass


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


def _sanitize_query(query: str) -> str:
    """
    Remove some invalid characters from the query

    Parameters
    ----------
    query : str
        A search query to be sanitized

    Returns
    -------
    str
        A sanitized query
    """

    query = re.sub(r'\s+', ' ', query)

    return query


def _is_query_ok(query: str) -> bool:
    """
    Checking a search query, it will return True if it's valid or False otherwise.

    Examples
    VALID = ([term a] OR [term b])
    INVALID = ([term a] OR [term b]
    VALID = [term a] OR [term b]
    INVALID = term a OR [term b]
    INVALID = term a [term b]
    INVALID = [] AND [term b]
    VALID = [term a]
    INVALID = []
    INVALID = [

    Parameters
    ----------
    query : str
        A search query to be validated

    Returns
    -------
    bool
        A boolean value indicating whether the query is valid or not
    """

    if len(query) == 0 or len(query) < 3 or query[0] not in ['(', '['] or query[-1] not in [')', ']']:
        return False
    
    # checking groups
    group_characters = []
    for character in query:
        if character in ['(', ')']:
            if len(group_characters) == 0:
                group_characters.append(character)
            else:
                last_group_character = group_characters[-1]

                if last_group_character == character:
                    group_characters.append(character)
                else:
                    group_characters.pop()

    if len(group_characters) > 0: 
        # after the processing above, the list needs to be empty
        return False
    
    # checking keywords and operators
    #TODO: improve this query validation, 'cause this approach ignore the parenthesis
    # and still can return True for invalid queries like [term a] O(R) [term b]

    query_ok = True
    inside_keyword = False
    current_operator = None
    current_keyword = None
    valid_operators = [' AND ', ' OR ', ' AND NOT ']
    transformed_query = query.replace('(','').replace(')','')
    
    for character in transformed_query:

        if inside_keyword:
            if character == ']': # closing a search term
                if current_keyword is None or len(current_keyword.strip()) == 0:
                    query_ok = False
                    break
                current_keyword = None
                inside_keyword = False
            else:
                if current_keyword is None:
                    current_keyword = character
                else:
                    current_keyword += character
        else:
            if character == '[': # opening a search term
                if current_operator is not None and current_operator not in valid_operators:
                    query_ok = False
                    break
                current_operator = None
                inside_keyword = True
            else:
                if current_operator is None:
                    current_operator = character
                else:
                    current_operator += character

    # after the processing above, query_ok needs to be True, 
    # and current_keyword and current_operator need to be null
    return query_ok and current_keyword is None and current_operator is None


def search(outputpath: str, query: Optional[str] = None, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, limit_per_database: Optional[int] = None, databases: Optional[List[str]] = None,
        publication_types: Optional[List[str]] = None, scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None,
        proxy: Optional[str] = None):
    """
    When you have a query and needs to get papers using it, this is the method that you'll need to call.
    This method will find papers from some databases based on the provided query.

    Parameters
    ----------
    outputpath : str
        A valid file path where the search result file will be placed

    query : str, optional

        A query string that will be used to perform the papers search.
        
        If not provided, the query will be loaded from the environment variable FINDPAPERS_QUERY

        All the query terms need to be enclosed in quotes and can be associated using boolean operators,
        and grouped using parentheses. 
        E.g.: [term A] AND ([term B] OR [term C]) AND NOT [term D]

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

    databases : List[str], optional
        List of databases where the search should be performed, if not specified all databases will be used, by default None

    publication_types : List[str], optional
        List of publication list of publication types to filter when searching, if not specified all the publication types 
        will be collected (this parameter is case insensitive). The available publication types are: journal, conference proceedings, book, other, by default None

    scopus_api_token : Optional[str], optional
        A API token used to fetch data from Scopus database. If you don't have one go to https://dev.elsevier.com and get it, by default None

    ieee_api_token : Optional[str], optional
        A API token used to fetch data from IEEE database. If you don't have one go to https://developer.ieee.org and get it, by default None
    
    proxy : Optional[str], optional
        proxy URL that can be used during requests. This can be also defined by an environment variable FINDPAPERS_PROXY. By default None

    """

    if proxy is not None:
        os.environ['FINDPAPERS_PROXY'] = proxy
    
    logging.info('Let\'s find some papers, this process may take a while...')

    if databases is not None:
        databases = [x.lower() for x in databases]
    
    if publication_types is not None:
        publication_types = [x.lower().strip() for x in publication_types]
        for publication_type in publication_types:
            if publication_type not in ['journal', 'conference proceedings', 'book', 'other']:
                raise ValueError(f'Invalid publication type: {publication_type}')

    if query is None:
        query = os.getenv('FINDPAPERS_QUERY')

    if query is not None:
        query = _sanitize_query(query)

    if query is None or not _is_query_ok(query):
        raise ValueError('Invalid query format')

    common_util.check_write_access(outputpath)

    if ieee_api_token is None:
        ieee_api_token = os.getenv('FINDPAPERS_IEEE_API_TOKEN')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('FINDPAPERS_SCOPUS_API_TOKEN')

    search = Search(query, since, until, limit, limit_per_database, databases=databases, publication_types=publication_types)

    if databases is None or arxiv_searcher.DATABASE_LABEL.lower() in databases:
        _database_safe_run(lambda: arxiv_searcher.run(search),
                        search, arxiv_searcher.DATABASE_LABEL)
    
    if databases is None or pubmed_searcher.DATABASE_LABEL.lower() in databases:
        _database_safe_run(lambda: pubmed_searcher.run(search),
                        search, pubmed_searcher.DATABASE_LABEL)

    if databases is None or acm_searcher.DATABASE_LABEL.lower() in databases:
        _database_safe_run(lambda: acm_searcher.run(search),
                        search, acm_searcher.DATABASE_LABEL)

    if ieee_api_token is not None:
        if databases is None or ieee_searcher.DATABASE_LABEL.lower() in databases:
            _database_safe_run(lambda: ieee_searcher.run(
                search, ieee_api_token), search, ieee_searcher.DATABASE_LABEL)
    else:
        logging.info('IEEE API token not found, skipping search on this database')

    if scopus_api_token is not None:
        if databases is None or scopus_searcher.DATABASE_LABEL.lower() in databases:
            _database_safe_run(lambda: scopus_searcher.run(
                search, scopus_api_token), search, scopus_searcher.DATABASE_LABEL)
    else:
        logging.info('Scopus API token not found, skipping search on this database')

    if databases is None or medrxiv_searcher.DATABASE_LABEL.lower() in databases:
        _database_safe_run(lambda: medrxiv_searcher.run(search),
                        search, medrxiv_searcher.DATABASE_LABEL)

    if databases is None or biorxiv_searcher.DATABASE_LABEL.lower() in databases:
        _database_safe_run(lambda: biorxiv_searcher.run(search),
                        search, biorxiv_searcher.DATABASE_LABEL)

    logging.info('Enriching results...')

    _enrich(search, scopus_api_token)

    logging.info('Filtering results...')

    _filter(search)

    logging.info('Finding and merging duplications...')

    search.merge_duplications()

    logging.info('Flagging potentially predatory publications...')

    _flag_potentially_predatory_publications(search)

    logging.info(f'It\'s finally over! {len(search.papers)} papers retrieved. Good luck with your research :)')

    persistence_util.save(search, outputpath)
