#pip install matplotlib matplotlib_venn

import os
import json
import random
import numpy as np
from matplotlib import pyplot as plt
from matplotlib_venn import venn2, venn2_circles
from matplotlib_venn import venn3, venn3_circles
import matplotlib.cm as cmap

BASEDIR = os.path.dirname(os.path.abspath(__file__))

def show_db_venn(papers):

    #(Abc, aBc, ABc, abC, AbC, aBC, ABC)
    all_papers_count = {'Scopus': 0, 'ACM': 0, 'Scopus-ACM': 0, 'IEEE': 0, 'Scopus-IEEE': 0, 'ACM-IEEE': 0, 'all': 0}
    selected_papers_count = {'Scopus': 0, 'ACM': 0, 'Scopus-ACM': 0, 'IEEE': 0, 'Scopus-IEEE': 0, 'ACM-IEEE': 0, 'all': 0}

    def fill_papers_count(key):
        all_papers_count[key] += 1
        if paper.get('selected'):
            selected_papers_count[key] += 1


    def plot_papers_count(values, plot_title, filename):

        f = plt.figure(figsize=(4,4))

        #(Abc, aBc, ABc, abC, AbC, aBC, ABC)
        Abc = values['Scopus']
        aBc = values['ACM']
        Abc = values['Scopus']
        ABc = values['Scopus-ACM']
        abC = values['IEEE']
        AbC = values['Scopus-IEEE']
        aBC = values['ACM-IEEE']
        ABC = values['all']
        
        venn3(subsets = (Abc, aBc, ABc, abC, AbC, aBC, ABC), set_labels = ('Scopus', 'ACM', 'IEEE'))
        
        # circles = venn3_circles(subsets = (Abc, aBc, ABc, abC, AbC, aBC, ABC))
        # for circle in circles:
        #     circle.set_lw(1.0)

        plt.title(plot_title)

        plt.show()
        f.savefig(os.path.join(BASEDIR, filename), bbox_inches='tight')


    for paper in papers:

        is_in_scopus = 'Scopus' in paper['databases']
        is_in_acm = 'ACM' in paper['databases']
        is_in_IEEE = 'IEEE' in paper['databases']

        if is_in_scopus and not is_in_acm and not is_in_IEEE:
            fill_papers_count('Scopus')
        elif is_in_acm and not is_in_scopus and not is_in_IEEE:
            fill_papers_count('ACM')
        elif is_in_IEEE and not is_in_scopus and not is_in_acm:
            fill_papers_count('IEEE')
        elif is_in_scopus and is_in_acm and not is_in_IEEE:
            fill_papers_count('Scopus-ACM')
        elif is_in_scopus and is_in_IEEE and not is_in_acm:
            fill_papers_count('Scopus-IEEE')
        elif is_in_acm and is_in_IEEE and not is_in_scopus:
            fill_papers_count('ACM-IEEE')
        elif is_in_scopus and is_in_acm and is_in_IEEE:
            fill_papers_count('all')
        else:
            print(paper)

    plot_papers_count(all_papers_count, 'Collected papers count', 'db_venn.pdf')
    plot_papers_count(selected_papers_count, 'Selected papers count', 'db_venn_selected.pdf')


def show_categories_headmap(papers, category_facet):

    papers_count_by_year_and_category = {}
    years = set()
    categories = set()

    for paper in papers:
        
        if not paper['selected']:
            continue

        year = paper['publication_date'].split('-')[0]

        for category in paper['categories'][category_facet]:

            if year not in papers_count_by_year_and_category:
                papers_count_by_year_and_category[year] = {}
                years.add(year)
            
            if category not in papers_count_by_year_and_category[year]:
                papers_count_by_year_and_category[year][category] = 0
                categories.add(category)

            papers_count_by_year_and_category[year][category] += 1

    years = list(years)
    years.sort()
    categories = list(categories)
    categories.sort()

    value_matrix = []

    for i, category in enumerate(categories):
        values = []
        for j, year in enumerate(years):
            values.append(papers_count_by_year_and_category.get(year, {}).get(category, 0))

        value_matrix.append(values)

    value_matrix = np.array(value_matrix)

    fig, ax = plt.subplots()
    im = ax.imshow(value_matrix, cmap="PuBu")

    # We want to show all ticks...
    ax.set_xticks(np.arange(len(years)))
    ax.set_yticks(np.arange(len(categories)))
    # ... and label them with the respective list entries
    ax.set_xticklabels(years)
    ax.set_yticklabels(categories)

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=90, ha="right", rotation_mode="anchor")

    # Loop over data dimensions and create text annotations.
    textcolors = ["k", "w"]
    threshold = int(value_matrix.max()/2)
    for i in range(len(categories)):
        for j in range(len(years)):
            text = ax.text(j, i, value_matrix[i, j],
                        ha="center", va="center", color=textcolors[int(value_matrix[i, j] > threshold)])

    ax.set_title("Selected papers count (category/year)", pad=20)
    fig.tight_layout()

    plt.show()
    fig.savefig(os.path.join(BASEDIR, 'categories.pdf'), bbox_inches='tight')


# loadging data
with open(os.path.join(BASEDIR, 'search_paul.json'), 'r') as jsonfile:
    SEARCH_RESULTS = json.load(jsonfile)

# generate fake selection/classification
for paper in SEARCH_RESULTS['papers']:

    paper['selected'] = random.choice([True, False])
    if paper['selected']:
        paper['categories'] = {
            'Contribution': random.sample(['Metric','Tool','Model','Method'], 2)
        }


show_db_venn(SEARCH_RESULTS['papers'])
show_categories_headmap(SEARCH_RESULTS['papers'], 'Contribution')
