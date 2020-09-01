import inquirer
import re
from typing import Optional, List
from colorama import Fore, Back, Style, init
from findpapers.models.search import Search
from findpapers.models.paper import Paper
import findpapers.utils.common_util as util
from findpapers.utils.outputfile_util import save, load


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

    init(autoreset=True)  # colorama initializer

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
