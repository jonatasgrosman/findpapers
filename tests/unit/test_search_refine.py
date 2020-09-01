import json
import tempfile
import findpapers
from findpapers.models.search import Search
from findpapers.models.paper import Paper


def _get_temp_search_result_path(search: Search, paper: Paper, force_unrefined=True):
    temp_filepath = tempfile.NamedTemporaryFile().name
    if force_unrefined:
        paper.selected = None
        paper.category = None
    search.add_paper(paper)
    findpapers.save(search, temp_filepath)
    return temp_filepath


def test_select_skip(monkeypatch, search: Search, paper: Paper):
    with monkeypatch.context() as context:
        context.setattr(
            findpapers.utils.refine_util, '_get_select_question_input', lambda: 'Skip')

        temp_filepath = _get_temp_search_result_path(search, paper)
        findpapers.refine(temp_filepath)
        loaded_search = findpapers.load(temp_filepath)

        for loaded_paper in loaded_search.papers:
            assert loaded_paper.selected == None


def test_select_no(monkeypatch, search: Search, paper: Paper):
    with monkeypatch.context() as context:
        context.setattr(findpapers.utils.refine_util, '_get_select_question_input', lambda: 'No')

        temp_filepath = _get_temp_search_result_path(search, paper)
        findpapers.refine(temp_filepath)
        loaded_search = findpapers.load(temp_filepath)

        for loaded_paper in loaded_search.papers:
            loaded_paper.selected = False


def test_select_leave(monkeypatch, search: Search, paper: Paper):
    with monkeypatch.context() as context:
        context.setattr(findpapers.utils.refine_util, '_get_select_question_input',
                        lambda: 'Other string')

        temp_filepath = _get_temp_search_result_path(search, paper)
        findpapers.refine(temp_filepath)
        loaded_search = findpapers.load(temp_filepath)

        for loaded_paper in loaded_search.papers:
            assert loaded_paper.selected == None


def test_select_yes_and_category(monkeypatch, search: Search, paper: Paper):
    with monkeypatch.context() as context:
        context.setattr(
            findpapers.utils.refine_util, '_get_select_question_input', lambda: 'Yes')
        context.setattr(
            findpapers.utils.refine_util, '_get_category_question_input', lambda x: x[0])

        temp_filepath = _get_temp_search_result_path(search, paper)
        categories = ['Category A']
        findpapers.refine(temp_filepath, categories=categories)
        loaded_search = findpapers.load(temp_filepath)

        for loaded_paper in loaded_search.papers:
            assert loaded_paper.selected == True
            assert loaded_paper.category == categories[0]


def test_already_defined_selected(monkeypatch, search: Search, paper: Paper):
    with monkeypatch.context() as context:
        context.setattr(
            findpapers.utils.refine_util, '_get_select_question_input', lambda: 'Yes')
        context.setattr(
            findpapers.utils.refine_util, '_get_category_question_input', lambda x: x[0])

        paper.selected = False
        paper.category = 'Other category'

        temp_filepath = _get_temp_search_result_path(search, paper, False)
        findpapers.refine(temp_filepath, categories=['Category A'])
        loaded_search = findpapers.load(temp_filepath)

        for loaded_paper in loaded_search.papers:
            assert loaded_paper.selected == False
            assert loaded_paper.category == 'Other category'
