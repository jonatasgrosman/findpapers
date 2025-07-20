import inquirer
import re
import os
from typing import Optional, List
from termcolor import colored
from findpapers.models.paper import Paper
import findpapers.utils.common_util as common_util
import findpapers.utils.persistence_util as persistence_util


def _print_paper_details(
    paper: Paper, highlights: List[str], show_abstract: bool, show_extra_info: bool
):  # pragma: no cover
    """
    Private method used to print on console the paper details

    Parameters
    ----------
    paper : Paper
        A paper instance
    highlights : List[str]
        A list of terms to highlight on the paper's abstract
    show_abstract : bool
        A flag to indicate if the abstract should be shown or not
    show_extra_info : bool, optional
        A flag to indicate if the paper's extra info should be shown or not, by default False
    """

    print(f"{colored('Title:', 'green', attrs=['bold'])} {paper.title}")
    print(f"{colored('Authors:', 'green', attrs=['bold'])} {' | '.join(paper.authors)}")
    if len(paper.keywords) > 0:
        print(
            f"{colored('Keywords:', 'green', attrs=['bold'])} {', '.join(paper.keywords)}"
        )
    print(
        f"{colored('Publication date:', 'green', attrs=['bold'])} {paper.publication_date.strftime('%Y-%m-%d')}"
    )

    print("\n")

    if show_abstract:
        abstract = paper.abstract
        for term in highlights:
            abstract = re.sub(
                r"({})".format(
                    re.escape(term)
                ),  # Use re.escape(term) for safety with special regex characters
                colored(r"\1", "yellow", attrs=["bold"]),
                abstract,
                flags=re.IGNORECASE,
            )
        print(abstract)

        print("\n")

        if show_extra_info:
            if paper.comments is not None:
                print(f"{colored('Paper comments:', attrs=['bold'])} {paper.comments}")
            if paper.citations is not None:
                print(
                    f"{colored('Paper citations:', attrs=['bold'])} {paper.citations}"
                )
            if paper.number_of_pages is not None:
                print(
                    f"{colored('Paper number of pages:', attrs=['bold'])} {paper.number_of_pages}"
                )
            if paper.doi is not None:
                print(f"{colored('Paper DOI:', attrs=['bold'])} {paper.doi}")
            if paper.databases is not None:
                print(
                    f"{colored('Paper found in:', attrs=['bold'])} {', '.join(paper.databases)}"
                )
            if len(paper.urls) > 0:
                print(f"{colored('Paper URL:', attrs=['bold'])} {list(paper.urls)[0]}")

            if paper.publication is not None:
                print(
                    f"{colored('Publication name:', attrs=['bold'])} {paper.publication.title}"
                )
                print(
                    f"{colored('Publication is potentially predatory:', attrs=['bold'])} {paper.publication.is_potentially_predatory}"
                )
                if paper.publication.category is not None:
                    print(
                        f"{colored('Publication category:', attrs=['bold'])} {paper.publication.category}"
                    )
                if len(paper.publication.subject_areas) > 0:
                    print(
                        f"{colored('Publication areas:', attrs=['bold'])} {', '.join(paper.publication.subject_areas)}"
                    )
                if paper.publication.isbn is not None:
                    print(
                        f"{colored('Publication ISBN:', attrs=['bold'])} {paper.publication.isbn}"
                    )
                if paper.publication.issn is not None:
                    print(
                        f"{colored('Publication ISSN:', attrs=['bold'])} {paper.publication.issn}"
                    )
                if paper.publication.publisher is not None:
                    print(
                        f"{colored('Publication publisher:', attrs=['bold'])} {paper.publication.publisher}"
                    )
                if paper.publication.cite_score is not None:
                    print(
                        f"{colored('Publication Cite Score:', attrs=['bold'])} {paper.publication.cite_score}"
                    )
                if paper.publication.sjr is not None:
                    print(
                        f"{colored('Publication SJR:', attrs=['bold'])} {paper.publication.sjr}"
                    )
                if paper.publication.snip is not None:
                    print(
                        f"{colored('Publication SNIP:', attrs=['bold'])} {paper.publication.snip}"
                    )

        print("\n")

        if paper.selected is not None:
            selected_text = "Yes" if paper.selected else "No"
            print(f"{colored('Selected:', 'blue', attrs=['bold'])} {selected_text}")

            if paper.categories is not None and len(paper.categories.items()) > 0:
                categories_string = " | ".join(
                    [
                        f"{k}: {', '.join(v)}"
                        for k, v in paper.categories.items()
                        if len(v) > 0
                    ]
                )
                print(
                    f"{colored('Categories:', 'blue', attrs=['bold'])} {categories_string}"
                )

        print("\n")


def _get_select_question_input():  # pragma: no cover
    """
    Private method that prompts a question about the paper selection

    Returns
    -------
    str
        User provided input
    """
    questions = [
        inquirer.List(
            "answer",
            message="Do you wanna select this paper?",
            choices=["Skip", "No", "Yes", "Save what I've done so far and leave"],
        ),
    ]
    return inquirer.prompt(questions).get("answer")


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
            inquirer.Checkbox(
                "answer",
                message=f'With respect to "{facet}", which categories does the document belong to?',
                choices=facet_categories,
            ),
        ]

        answers = inquirer.prompt(questions)

        selections[facet] = answers.get("answer")

    return selections


def refine(
    search_path: str,
    categories: Optional[dict] = None,
    highlights: Optional[list] = None,
    show_abstract: Optional[bool] = False,
    show_extra_info: Optional[bool] = False,
    only_selected_papers: Optional[bool] = False,
    only_removed_papers: Optional[bool] = False,
    read_only: Optional[bool] = False,
    verbose: Optional[bool] = False,
):
    """
    When you have a search result and wanna refine it, this is the method that you'll need to call.
    This method will iterate through all the papers showing their collected data,
    then asking if you wanna select a particular paper or not, and assign a category if a list of categories is provided.
    And to help you on the refinement, this method can also highlight some terms on the paper's abstract by a provided list of them

    Parameters
    ----------
    search_path : str
        valid file path containing a JSON representation of the search results
    categories : dict, optional
        A dict with lists of categories by their facets, used to assign to selected papers, by default None
        E.g.:
            {
                "Research Type": [
                    "Validation Research", "Evaluation Research", "Solution Proposal", "Philosophical", "Opinion", "Experience"
                ],
                "Contribution": [
                    "Metric", "Tool", "Model", "Method"
                ]
            }
    highlights : list, optional
        A list of terms to highlight on the paper's abstract, by default None
    show_abstract : bool, optional
        A flag to indicate if the abstract should be shown or not, by default False
    show_extra_info : bool, optional
        A flag to indicate if the paper's extra info should be shown or not, by default False
    only_selected_papers : bool, False by default
        If only the selected papers will be refined, by default False
    only_removed_papers : bool, False by default
        If only the removed papers will be refined, by default False
    read_only : bool, optional
        If true, this method will only list the papers, by default False
    verbose : Optional[bool], optional
        If you wanna a verbose logging
    """

    common_util.logging_initialize(verbose)
    common_util.check_write_access(search_path)

    if categories is None:
        categories = {}
    if highlights is None:
        highlights = []

    search = persistence_util.load(search_path)

    has_already_refined_papers = False
    for paper in search.papers:
        if paper.selected is not None:
            has_already_refined_papers = True
            break

    todo_papers = []
    done_papers = []

    for paper in search.papers:
        # if wanna_re_refine_papers:
        if only_selected_papers or only_removed_papers:
            if paper.selected is not None and (
                (only_selected_papers and paper.selected)
                or (only_removed_papers and not paper.selected)
            ):
                todo_papers.append(paper)
        else:
            if paper.selected is None or read_only:
                todo_papers.append(paper)
            else:
                done_papers.append(paper)

    todo_papers = sorted(todo_papers, key=lambda x: x.publication_date, reverse=True)

    for i, paper in enumerate(todo_papers):
        print(f"\n{'.' * os.get_terminal_size()[0]}\n")

        if not read_only:
            print(f"\n{colored(f'{i + 1}/{len(todo_papers)} papers', 'cyan')}\n")

        _print_paper_details(paper, highlights, show_abstract, show_extra_info)

        if not read_only:
            answer = _get_select_question_input()

            if answer == "Skip":
                continue
            elif answer == "No":
                paper.selected = False
            elif answer == "Yes":
                paper.selected = True
            else:
                break

            if paper.selected:
                paper.categories = _get_category_question_input(categories)

            done_papers.append(paper)

    if read_only:
        print(f"\n{colored(f'{len(todo_papers)} papers', 'cyan')}\n")
    else:
        persistence_util.save(search, search_path)
