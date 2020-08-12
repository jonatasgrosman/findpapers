import json
from colorama import Fore, Back, Style, init
import numpy as np
import inquirer
import os
import configparser
import itertools
import util as Util
import re

config = configparser.ConfigParser()
config.read('config.ini')

FILTER_CATEGORIES = config['DEFAULT']['FILTER_CATEGORIES'].split(',')
FILTER_HIGHLIGHT_ABSTRACT_TERMS = config['DEFAULT']['FILTER_HIGHLIGHT_ABSTRACT_TERMS'].split(',')

PUBLICATION_YEAR_LOWER_BOUND = config['DEFAULT']['PUBLICATION_YEAR_LOWER_BOUND']
if len(PUBLICATION_YEAR_LOWER_BOUND) > 0:
    PUBLICATION_YEAR_LOWER_BOUND = int(PUBLICATION_YEAR_LOWER_BOUND)
else:
    PUBLICATION_YEAR_LOWER_BOUND = None

init(autoreset=True)

PAPERS_FILE_PATH = os.path.dirname(os.path.abspath(__file__)) + '/data/result.json'

# Fore: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET.
# Back: BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, RESET.
# Style: DIM, NORMAL, BRIGHT, RESET_ALL

def save_data(data):

    with open(PAPERS_FILE_PATH, 'w') as fp:
        json.dump(data, fp, indent=2, sort_keys=True)


def get_numeric_value_with_color_by_scale(value, scale):

    if value == None:
        return value
    elif value <= scale['low_upper_bound']:
        return Fore.RED + Style.BRIGHT + str(value) + Fore.RESET + Style.RESET_ALL
    elif value >= scale['high_lower_bound']:
        return Fore.GREEN + Style.BRIGHT + str(value) + Fore.RESET + Style.RESET_ALL
    else:
        return Fore.YELLOW + Style.BRIGHT + str(value) + Fore.RESET + Style.RESET_ALL


def get_score_scale(data):

    already_processed_publication = {}
    cite_score_values = []
    snip_values = []
    sjr_values = []
    prominence_percentiles = []
    citations_by_year = {}

    for paper in data:

        if paper['paper'].get('citations', None) == None:
            continue

        year = paper['paper']['date'].split('-')[0]
        if year not in citations_by_year:
            citations_by_year[year] = []
        
        if paper['paper']['citations'] != None:
            citations_by_year[year].append(paper['paper']['citations'])

        if paper['publication']['name'] in already_processed_publication:
            continue

        if 'scopus_values' in paper['paper']:

            if 'prominence_percentile' in paper['paper']['scopus_values'] and paper['paper']['scopus_values']['prominence_percentile'] != None:
                prominence_percentiles.append(paper['paper']['scopus_values']['prominence_percentile'])


        if 'scopus_values' in paper['publication']:

            if 'cite_score' in paper['publication']['scopus_values'] and paper['publication']['scopus_values']['cite_score'] != None:
                cite_score_values.append(paper['publication']['scopus_values']['cite_score'])
            if 'snip' in paper['publication']['scopus_values'] and paper['publication']['scopus_values']['snip'] != None:
                snip_values.append(paper['publication']['scopus_values']['snip'])
            if 'cite_score' in paper['publication']['scopus_values'] and paper['publication']['scopus_values']['sjr'] != None:
                sjr_values.append(paper['publication']['scopus_values']['sjr'])

        already_processed_publication[paper['publication']['name']] = True

    score_scale = {
        'cite_score': {'low_upper_bound': np.percentile(cite_score_values, 25), 'high_lower_bound': np.percentile(cite_score_values, 75)},
        'snip': {'low_upper_bound': np.percentile(snip_values, 25), 'high_lower_bound': np.percentile(snip_values, 75)},
        'sjr': {'low_upper_bound': np.percentile(sjr_values, 25), 'high_lower_bound': np.percentile(sjr_values, 75)},
        'prominence_percentile': {'low_upper_bound': np.percentile(prominence_percentiles, 25), 'high_lower_bound': np.percentile(prominence_percentiles, 75)},
        'citations_by_year': {}
    }

    for year, values in citations_by_year.items():
        score_scale['citations_by_year'][year] = {
            'low_upper_bound': np.percentile(values, 25), 'high_lower_bound': np.percentile(values, 75)
        }

    return score_scale


def get_default_key_value_print(key, value):

    return Fore.BLUE + Style.BRIGHT + key + ': ' + Fore.RESET + Style.NORMAL + (value if value != None else '')


def show_paper_header(paper):

    print(Fore.GREEN + Style.BRIGHT + paper['paper']['title'])
    print(Fore.GREEN + ', '.join(paper['paper']['authors']))
    print(Fore.GREEN + paper['paper']['date'])
    if paper['filter']['category'] != None:
        print(Fore.GREEN + 'CATEGORY: ' + paper['filter']['category'])

    print('\n')


def print_key_value_by_function(key, func):

    value = Util.try_to_return_or_none(func, False)
    if value != None and len(value) > 0:
        print(get_default_key_value_print(key, value))


def get_abstract():

    abstract = paper['paper']['abstract']

    for term in FILTER_HIGHLIGHT_ABSTRACT_TERMS:
        abstract = re.sub(r'({0}+)'.format(term), Fore.GREEN + Style.BRIGHT + r'\1' + Fore.RESET + Style.NORMAL, abstract, flags=re.IGNORECASE)

    return abstract


def show_paper_details(paper, score_scale, show_abstract=True):

    show_paper_header(paper)

    if show_abstract:
        print_key_value_by_function('Abstract', get_abstract)
        print('\n')

    print_key_value_by_function('Keywords', lambda: ', '.join(paper['paper']['keywords']))
    print_key_value_by_function('Comments', lambda: paper['paper']['comments'])

    print_key_value_by_function('Paper type', lambda: paper['paper']['type'])
    print_key_value_by_function('Paper subtype', lambda: paper['paper']['type'])
    print_key_value_by_function('Paper topics', lambda: ', '.join(paper['paper']['scopus_values']['topics']))

    try:
        year = paper['paper']['date'].split('-')[0]
        citations = get_numeric_value_with_color_by_scale(paper['paper']['citations'], score_scale['citations_by_year'][year])

        prominence_percentile = paper['paper']['scopus_values']['prominence_percentile'] if 'prominence_percentile' in paper['paper']['scopus_values'] else None
        prominence_percentile = get_numeric_value_with_color_by_scale(prominence_percentile, score_scale['prominence_percentile'])

        paper_metrics = 'Citations = {0}, Topics prominence = {1}'.format(citations, prominence_percentile)
        print(get_default_key_value_print('Paper metrics', paper_metrics))
    except Exception:
        pass
    
    print('\n')

    if paper.get('publication', None) != None: 

        print_key_value_by_function('Publication name', lambda: paper['publication']['name'])
        print_key_value_by_function('Publication areas', lambda: ', '.join(paper['publication']['subject_areas']))
        print_key_value_by_function('Publication publisher', lambda: paper['publication']['publisher'])

        if paper['publication'].get('scopus_values', None) != None:

            try:
                cite_score = paper['publication']['scopus_values']['cite_score'] if 'cite_score' in paper['publication']['scopus_values'] else None
                cite_score = get_numeric_value_with_color_by_scale(cite_score, score_scale['cite_score'])
                
                snip = paper['publication']['scopus_values']['snip'] if 'snip' in paper['publication']['scopus_values'] else None
                snip = get_numeric_value_with_color_by_scale(snip, score_scale['snip'])

                sjr = paper['publication']['scopus_values']['sjr'] if 'sjr' in paper['publication']['scopus_values'] else None
                sjr = get_numeric_value_with_color_by_scale(sjr, score_scale['sjr'])

                publication_metrics = 'Cite score = {0}, SNIP = {1}, SJR = {2}'.format(cite_score, snip, sjr)
                print(get_default_key_value_print('Publication metrics', publication_metrics))
            except Exception:
                pass
    
    print('\n')
    print_key_value_by_function('Databases', lambda: ', '.join(paper['databases']))


# loading data

with open(PAPERS_FILE_PATH, 'r') as fp:
    data = json.load(fp)

# initial config

questions = [
    inquirer.List('show_abstract',
        message='Do you wanna see the paper abstract while filtering?',
        choices=['Yes', 'No'],
    ),
]
answers = inquirer.prompt(questions)
show_abstract = answers['show_abstract'] == 'Yes'

questions = [
  inquirer.List('filter_mode',
        message='What kind of papers do you wanna filter?',
        choices=['Unfiltered papers', 'Selected papers', 'Unselected papers'],
    ),
]
answers = inquirer.prompt(questions)

# papers selection

already_filtered_papers = []
papers_to_filter = []

for paper in data:

    paper_year = int(paper['paper']['date'].split('-')[0])

    if PUBLICATION_YEAR_LOWER_BOUND != None and paper_year < PUBLICATION_YEAR_LOWER_BOUND:
        continue

    score_scale = get_score_scale(data)

    if 'filter' not in paper:
        paper['filter'] = {
            'selected': None,
            'category': None
        }

    if answers['filter_mode'] == 'Unfiltered papers':

        if paper['filter']['selected'] == None:
            papers_to_filter.append(paper)
        else:
            already_filtered_papers.append(paper)

    elif answers['filter_mode'] == 'Selected papers':

        if paper['filter']['selected'] == True:
            papers_to_filter.append(paper)
        else:
            already_filtered_papers.append(paper)

    elif answers['filter_mode'] == 'Unselected papers':

        if paper['filter']['selected'] == False:
            papers_to_filter.append(paper)
        else:
            already_filtered_papers.append(paper)

print(Fore.MAGENTA + Style.BRIGHT + 'You\'ve already filtered {0} papers!\n'.format(len(already_filtered_papers)))

# filtering process

for i, paper in enumerate(papers_to_filter):

    print('{0}/{1} papers filtered in this section\n\n'.format(i, len(papers_to_filter)))

    show_paper_details(paper, score_scale, show_abstract)

    questions = [
        inquirer.List('select',
            message='Do you wanna select this paper?',
            choices=['Skip', 'No', 'Yes'],
        ),
    ]

    print('\n')
    answers = inquirer.prompt(questions)

    if answers['select'] == 'Skip':
        continue

    paper['filter']['selected'] = answers['select'] == 'Yes'

    if paper['filter']['selected'] and len(FILTER_CATEGORIES) > 0:

        questions = [
            inquirer.List('category',
                message='Which category does this work belong to?',
                choices=FILTER_CATEGORIES,
            ),
        ]

        print('\n')
        answers = inquirer.prompt(questions)
        paper['filter']['category'] = answers['category']

    already_filtered_papers.append(paper)
    save_data(data)

    print('\n\n')

# showing selected papers

print(Fore.BLUE + Style.BRIGHT + 'Selected papers:\n')

selected_papers_count = 0
for paper in already_filtered_papers:
    if paper['filter']['selected']:
        selected_papers_count += 1
        show_paper_header(paper)

print(Fore.BLUE + Style.BRIGHT + '{0} papers were selected!\n'.format(selected_papers_count))