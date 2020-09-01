import os
import datetime
import logging
import json
import inquirer
import re
from typing import Optional, List
from colorama import Fore, Back, Style, init
from findpapers.models.search import Search
from findpapers.models.paper import Paper
import findpapers.util as util
import findpapers.searcher.scopus_searcher as scopus_searcher
import findpapers.searcher.ieee_searcher as ieee_searcher
import findpapers.searcher.pubmed_searcher as pubmed_searcher
import findpapers.searcher.arxiv_searcher as arxiv_searcher
import findpapers.searcher.acm_searcher as acm_searcher

init(autoreset=True)  # colorama initializer

logging_level = os.getenv('LOGGING_LEVEL')
if logging_level is None:  # pragma: no cover
    logging_level = 'INFO'

logging.basicConfig(level=getattr(logging, logging_level),
                    format='%(asctime)s %(levelname)s: %(message)s')


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
            logging.error(
                f'Error while fetching papers from {database_label} database', exc_info=True)


def run(query: str, since: Optional[datetime.date] = None, until: Optional[datetime.date] = None,
        limit: Optional[int] = None, limit_per_database: Optional[int] = None,
        scopus_api_token: Optional[str] = None, ieee_api_token: Optional[str] = None) -> Search:
    """
    When you have a query and needs to get papers using it, this is the method that you'll need to call.
    This method will find papers from some databases based on the provided query, returning a Search instance when the search completes.

    Parameters
    ----------
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

    Returns
    -------
    Search
        A Search instance containing the search results
    """

    if ieee_api_token is None:
        ieee_api_token = os.getenv('IEEE_API_TOKEN')

    if scopus_api_token is None:
        scopus_api_token = os.getenv('SCOPUS_API_TOKEN')

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

        logging.info('Enriching publication data using Scopus database...')
        try:
            scopus_searcher.enrich_publication_data(search, scopus_api_token)
        except Exception:  # pragma: no cover
            logging.error(
                'Error while fetching data from Scopus database', exc_info=True)

    return search


def save(search: Search, filepath: str):
    """
    Method used to save a search result in a JSON representation

    Parameters
    ----------
    search : Search
        A Search instance
    filepath : str
        A valid file path used to save the search results
    """

    with open(filepath, 'w') as jsonfile:
        json.dump(Search.to_dict(search), jsonfile, indent=2, sort_keys=True)


def load(filepath: str):
    """
    Method used to load a search result using a JSON representation

    Parameters
    ----------
    filepath : str
        A valid file path containing a JSON representation of the search results
    """

    with open(filepath, 'r') as jsonfile:
        return Search.from_dict(json.load(jsonfile))


def _print_paper_details(paper: Paper, show_abstract: bool, highlights: List[str]): # pragma: no cover
    """
    Private method used to print on console the paper details

    Parameters
    ----------
    paper : Paper
        A paper instance
    show_abstract : bool
        A flag to indicate if the abstract should be shown or not
    highlights : List[str]
        A list of terms to highlight on the paper's abstract'
    """

    print(f'{Fore.GREEN}{Style.BRIGHT}{paper.title}')
    print(f'{Fore.GREEN}{" | ".join(paper.authors)}')
    print(f'{Fore.GREEN}{paper.publication_date.strftime("%Y-%m-%d")}')

    print('\n')

    if show_abstract:
        abstract = paper.abstract
        for term in highlights:
            abstract = re.sub(r'({0}+)'.format(term), Fore.YELLOW + Style.BRIGHT +
                              r'\1' + Fore.RESET + Style.NORMAL, abstract, flags=re.IGNORECASE)
        print(abstract)

        print('\n')

    if len(paper.keywords) > 0:
        print(f'{Style.BRIGHT}Keywords:{Style.NORMAL} {", ".join(paper.keywords)}')
    if paper.comments is not None:
        print(f'{Style.BRIGHT}Comments:{Style.NORMAL} {paper.comments}')
    if paper.citations is not None:
        print(f'{Style.BRIGHT}Citations:{Style.NORMAL} {paper.citations}')
    if paper.comments is not None:
        print(f'{Style.BRIGHT}Databases:{Style.NORMAL} {", ".join(paper.databases)}')

    print('\n')

    if paper.publication is not None:
        print(
            f'{Style.BRIGHT}Publication name:{Style.NORMAL} {paper.publication.title}')
        print(
            f'{Style.BRIGHT}Publication category:{Style.NORMAL} {paper.publication.category}')

        if paper.publication.isbn is not None:
            print(f'{Style.BRIGHT}ISBN:{Style.NORMAL} {paper.publication.isbn}')
        if paper.publication.issn is not None:
            print(f'{Style.BRIGHT}ISSN:{Style.NORMAL} {paper.publication.issn}')
        if paper.publication.publisher is not None:
            print(
                f'{Style.BRIGHT}Publisher:{Style.NORMAL} {paper.publication.publisher}')
        if paper.publication.cite_score is not None:
            print(
                f'{Style.BRIGHT}Cite score:{Style.NORMAL} {paper.publication.cite_score}')
        if paper.publication.sjr is not None:
            print(f'{Style.BRIGHT}SJR:{Style.NORMAL} {paper.publication.sjr}')
        if paper.publication.snip is not None:
            print(f'{Style.BRIGHT}SNIP:{Style.NORMAL} {paper.publication.snip}')
        if len(paper.publication.subject_areas) > 0:
            print(
                f'{Style.BRIGHT}Subject Areas:{Style.NORMAL} {", ".join(paper.publication.subject_areas)}')

        print('\n')


def _get_select_question_input():  # pragma: no cover
    """
    Private method that prompts a question about the paper selection

    Returns
    -------
    str
        User provided input
    """
    questions = [
        inquirer.List('select',
                      message='Do you wanna select this paper?',
                      choices=[
                          'Skip', 'No', 'Yes', 'Oh Gosh it never ends! I\'m tired! Save what I\'ve done so far and leave'],
                      ),
    ]
    return inquirer.prompt(questions).get('select')


def _get_category_question_input(categories):  # pragma: no cover
    """
    Private method that prompts a question about the paper category

    Returns
    -------
    str
        User provided input
    """

    questions = [
        inquirer.List('category',
                      message='Which category does this work belong to?',
                      choices=categories,
                      ),
    ]
    answers = inquirer.prompt(questions)
    return answers.get('category')


def refine(filepath: str, show_abstract: Optional[bool] = True, categories: Optional[list] = None,
           highlights: Optional[list] = None):
    """
    When you have a search result and wanna refine it, this is the method that you'll need to call.
    This method will iterate through all the papers showing their information, 
    then asking if you wanna select a particular paper or not, and assign a category if a list of categories is provided.
    This method can also highlights some terms on the paper's abstract by a provided list of terms 

    Parameters
    ----------
    filepath : str
        valid file path containing a JSON representation of the search results
    show_abstract : Optional[bool], optional
        A flag to indicate if the abstract should be shown or not, by default True
    categories : Optional[list], optional
        A list of categories to assign to the papers by the user, by default None
    highlights : Optional[list], optional
        A list of terms to highlight on the paper's abstract', by default None
    """

    if categories is None:
        categories = []
    if highlights is None:
        highlights = []

    search = load(filepath)

    papers_to_refine = []
    refined_papers = []
    for paper in search.papers:
        if paper.selected is None:
            papers_to_refine.append(paper)
        else:
            refined_papers.append(paper)

    for paper in papers_to_refine:

        util.clear()

        _print_paper_details(paper, show_abstract, highlights)

        print(
            f'{Fore.CYAN}You\'ve already refined {len(refined_papers)}/{len(search.papers)} papers!\n')

        print('\n')

        answer = _get_select_question_input()

        if answer == 'Skip':
            continue
        elif answer == 'No':
            paper.selected = False
        elif answer == 'Yes':
            paper.selected = True
        else:
            break

        print('\n')

        if len(categories) > 0:
            paper.category = _get_category_question_input(categories)

        refined_papers.append(paper)

    print(
        f'{Fore.CYAN}You\'ve already refined {len(refined_papers)}/{len(search.papers)} papers!\n')

    save(search, filepath)
