import inquirer
import re
import os
from typing import Optional, List
from colorama import Fore, Back, Style, init
from findpapers.models.search import Search
from findpapers.models.paper import Paper
import findpapers.utils.common_util as common_util
import findpapers.utils.persistence_util as persistence_util


def _print_paper_details(paper: Paper, show_abstract: bool, highlights: List[str]):  # pragma: no cover
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

    print(f'{Fore.GREEN}{Style.BRIGHT}Title:{Style.NORMAL} {paper.title}')
    print(f'{Fore.GREEN}{Style.BRIGHT}Authors:{Style.NORMAL} {" | ".join(paper.authors)}')
    print(f'{Fore.GREEN}{Style.BRIGHT}Publication date:{Style.NORMAL} {paper.publication_date.strftime("%Y-%m-%d")}')

    print('\n')

    if show_abstract:
        abstract = paper.abstract
        for term in highlights:
            abstract = re.sub(r'({0}+)'.format(term), Fore.YELLOW + Style.BRIGHT +
                              r'\1' + Fore.RESET + Style.NORMAL, abstract, flags=re.IGNORECASE)
        print(abstract)

        print('\n')

    if len(paper.keywords) > 0:
        print(f'{Style.BRIGHT}Papar keywords:{Style.NORMAL} {", ".join(paper.keywords)}')
    if paper.comments is not None:
        print(f'{Style.BRIGHT}Paper comments:{Style.NORMAL} {paper.comments}')
    if paper.citations is not None:
        print(f'{Style.BRIGHT}Paper citations:{Style.NORMAL} {paper.citations}')
    if paper.doi is not None:
        print(f'{Style.BRIGHT}Paper DOI:{Style.NORMAL} {paper.doi}')
    if paper.databases is not None:
        print(f'{Style.BRIGHT}Paper found in:{Style.NORMAL} {", ".join(paper.databases)}')

    if paper.publication is not None:
        print(f'{Style.BRIGHT}Publication name:{Style.NORMAL} {paper.publication.title}')
        if paper.publication.category is not None:
            print(f'{Style.BRIGHT}Publication category:{Style.NORMAL} {paper.publication.category}')
        if len(paper.publication.subject_areas) > 0:
            print(f'{Style.BRIGHT}Publication areas:{Style.NORMAL} {", ".join(paper.publication.subject_areas)}')
        if paper.publication.isbn is not None:
            print(f'{Style.BRIGHT}Publication ISBN:{Style.NORMAL} {paper.publication.isbn}')
        if paper.publication.issn is not None:
            print(f'{Style.BRIGHT}Publication ISSN:{Style.NORMAL} {paper.publication.issn}')
        if paper.publication.publisher is not None:
            print(f'{Style.BRIGHT}Publication publisher:{Style.NORMAL} {paper.publication.publisher}')
        if paper.publication.cite_score is not None:
            print(f'{Style.BRIGHT}Publication cite score:{Style.NORMAL} {paper.publication.cite_score}')
        if paper.publication.sjr is not None:
            print(f'{Style.BRIGHT}Publication SJR:{Style.NORMAL} {paper.publication.sjr}')
        if paper.publication.snip is not None:
            print(f'{Style.BRIGHT}Publication SNIP:{Style.NORMAL} {paper.publication.snip}')

    print('\n')

    if paper.selected is not None:

        print(f'{Fore.BLUE}{Style.BRIGHT}Selected: {Style.NORMAL}{"Yes" if paper.selected else "No"}')
        
        if paper.categories is not None and len(paper.categories.items()) > 0:
            categories_string = ' | '.join([f'{k}: {", ".join(v)}' for k, v in paper.categories.items() if len(v) > 0])
            print(f'{Fore.BLUE}{Style.BRIGHT}Categories: {Style.NORMAL}{categories_string}')

        print('\n')


def _get_wanna_re_refine_papers_input():  # pragma: no cover
    """
    Private method that prompts a question about the paper selection

    Returns
    -------
    str
        User provided input
    """
    REFINE_TEXT = 'Show me the not yet refined papers'
    REREFINE_TEXT = 'Show me the already refined papers'
    questions = [
        inquirer.List('answer',
                      message='What would you like to do now?',
                      choices=[REFINE_TEXT, REREFINE_TEXT])
    ]
    return inquirer.prompt(questions).get('answer') == REREFINE_TEXT


def _get_select_question_input():  # pragma: no cover
    """
    Private method that prompts a question about the paper selection

    Returns
    -------
    str
        User provided input
    """
    questions = [
        inquirer.List('answer',
                      message='Do you wanna select this paper?',
                      choices=[
                          'Skip', 
                          'No', 
                          'Yes', 
                          'Save what I\'ve done so far and leave'],
                      ),
    ]
    return inquirer.prompt(questions).get('answer')


def _get_category_question_input(categories: dict):  # pragma: no cover
    """
    Private method that prompts a question about the paper category
    
    Parameters
    ----------
    categories : dict
        A dict with lists of categories by their facets, used to assign to papers

    Returns
    -------
    dict
        A dict with lists of selected categories by their facets
    """

    selections = {}

    for facet, facet_categories in categories.items():

        questions = [
            inquirer.Checkbox('answer',
                        message=f'With respect to "{facet}"", which categories does the document belong to?',
                        choices=facet_categories,
                        ),
        ]

        answers = inquirer.prompt(questions)

        selections[facet] = answers.get('answer')
        
    return selections


def refine(search_path: str, show_abstract: Optional[bool] = False, categories: Optional[dict] = None,
           highlights: Optional[list] = None):
    """
    When you have a search result and wanna refine it, this is the method that you'll need to call.
    This method will iterate through all the papers showing their collected data, 
    then asking if you wanna select a particular paper or not, and assign a category if a list of categories is provided.
    And to help you on the refinement, this method can also highlight some terms on the paper's abstract by a provided list of them 

    Parameters
    ----------
    search_path : str
        valid file path containing a JSON representation of the search results
    show_abstract : bool, optional
        A flag to indicate if the abstract should be shown or not, by default False
    categories : dict, optional
        A dict with lists of categories by their facets, used to assign to selected papers, by default None
        E.g.:
            {
                'Research Type': [
                    'Validation Research', 'Evaluation Research', 'Solution Proposal', 'Philosophical', 'Opinion', 'Experience'
                ],
                'Contribution': [
                    'Metric', 'Tool', 'Model', 'Method'
                ]
            }
    highlights : list, optional
        A list of terms to highlight on the paper's abstract', by default None
    """

    common_util.check_write_access(search_path)

    init(autoreset=True)  # colorama initializer

    if categories is None:
        categories = {}
    if highlights is None:
        highlights = []

    search = persistence_util.load(search_path)

    wanna_re_refine_papers = _get_wanna_re_refine_papers_input()

    todo_papers = []
    done_papers = []
    for paper in search.papers:
        if wanna_re_refine_papers:
            if paper.selected is not None:
                todo_papers.append(paper)
        else:
            if paper.selected is None:
                todo_papers.append(paper)
            else:
                done_papers.append(paper)

    for paper in todo_papers:

        print(f'\n{Fore.CYAN}{len(done_papers)}/{len(todo_papers)} of the papers already done!\n')

        print(f'\n{"." * os.get_terminal_size()[0]}\n\n')

        _print_paper_details(paper, show_abstract, highlights)

        answer = _get_select_question_input()

        if answer == 'Skip':
            continue
        elif answer == 'No':
            paper.selected = False
        elif answer == 'Yes':
            paper.selected = True
        else:
            break

        if paper.selected:
            paper.categories = _get_category_question_input(categories)

        done_papers.append(paper)

    print(f'\n{Fore.CYAN}{len(done_papers)}/{len(todo_papers)} of the papers already done!\n')

    persistence_util.save(search, search_path)
