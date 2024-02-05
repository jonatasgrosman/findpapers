#pip install matplotlib matplotlib_venn

import os
import json
import random
import datetime
import numpy as np
from matplotlib import pyplot as plt
from matplotlib_venn import venn2, venn2_circles
from matplotlib_venn import venn3, venn3_circles
import matplotlib.cm as cmap

BASEDIR = os.path.dirname(os.path.abspath(__file__))


def autolabel(rects, ax):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()
        width = rect.get_width()
        x = rect.get_x()
        y = rect.get_y()
        if height > 0:
            ax.annotate("{}".format(height),
                        xy=(x + width/2, y + height/2),
                        xytext=(0, -5),  # 5 points vertical offset
                        textcoords="offset points",
                        ha="center", va="bottom")


def databases_venn_chart(papers):

    #(Abc, aBc, ABc, abC, AbC, aBC, ABC)
    all_papers_count = {"Scopus": 0, "ACM": 0, "Scopus-ACM": 0, "IEEE": 0, "Scopus-IEEE": 0, "ACM-IEEE": 0, "all": 0}
    selected_papers_count = {"Scopus": 0, "ACM": 0, "Scopus-ACM": 0, "IEEE": 0, "Scopus-IEEE": 0, "ACM-IEEE": 0, "all": 0}

    def fill_papers_count(key):
        all_papers_count[key] += 1
        if paper.get("selected"):
            selected_papers_count[key] += 1


    def plot_papers_count(values, plot_title, filename):

        f = plt.figure(figsize=(4,4))

        #(Abc, aBc, ABc, abC, AbC, aBC, ABC)
        Abc = values["Scopus"]
        aBc = values["ACM"]
        Abc = values["Scopus"]
        ABc = values["Scopus-ACM"]
        abC = values["IEEE"]
        AbC = values["Scopus-IEEE"]
        aBC = values["ACM-IEEE"]
        ABC = values["all"]
        
        venn3(subsets = (Abc, aBc, ABc, abC, AbC, aBC, ABC), set_labels = ("Scopus", "ACM", "IEEE"))
        
        # circles = venn3_circles(subsets = (Abc, aBc, ABc, abC, AbC, aBC, ABC))
        # for circle in circles:
        #     circle.set_lw(1.0)

        #plt.title(plot_title)

        plt.show()
        f.savefig(os.path.join(BASEDIR, filename), bbox_inches="tight")


    for paper in papers:

        is_in_scopus = "Scopus" in paper["databases"]
        is_in_acm = "ACM" in paper["databases"]
        is_in_IEEE = "IEEE" in paper["databases"]

        if is_in_scopus and not is_in_acm and not is_in_IEEE:
            fill_papers_count("Scopus")
        elif is_in_acm and not is_in_scopus and not is_in_IEEE:
            fill_papers_count("ACM")
        elif is_in_IEEE and not is_in_scopus and not is_in_acm:
            fill_papers_count("IEEE")
        elif is_in_scopus and is_in_acm and not is_in_IEEE:
            fill_papers_count("Scopus-ACM")
        elif is_in_scopus and is_in_IEEE and not is_in_acm:
            fill_papers_count("Scopus-IEEE")
        elif is_in_acm and is_in_IEEE and not is_in_scopus:
            fill_papers_count("ACM-IEEE")
        elif is_in_scopus and is_in_acm and is_in_IEEE:
            fill_papers_count("all")
        else:
            print(paper)

    plot_papers_count(all_papers_count, "Collected papers count", "databases_venn.pdf")
    plot_papers_count(selected_papers_count, "Selected papers count", "databases_venn_selected.pdf")


def categories_headmap_chart(papers, category_facet):

    papers_count_by_year_and_category = {}
    categories = set()

    for paper in papers:
        
        if not paper["selected"]:
            continue

        year = paper["publication_date"].split("-")[0]

        for category in paper["categories"][category_facet]:

            if year not in papers_count_by_year_and_category:
                papers_count_by_year_and_category[year] = {}
            
            if category not in papers_count_by_year_and_category[year]:
                papers_count_by_year_and_category[year][category] = 0
                categories.add(category)

            papers_count_by_year_and_category[year][category] += 1

    years = list(papers_count_by_year_and_category.keys())
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
    ax.set_ylabel(category_facet)
    ax.set_xlabel("Year")

    # Rotate the tick labels and set their alignment.
    plt.setp(ax.get_xticklabels(), rotation=90, ha="right", rotation_mode="anchor")

    # Loop over data dimensions and create text annotations.
    textcolors = ["k", "w"]
    threshold = int(value_matrix.max()/2)
    for i in range(len(categories)):
        for j in range(len(years)):
            text = ax.text(j, i, value_matrix[i, j],
                        ha="center", va="center", color=textcolors[int(value_matrix[i, j] > threshold)])

    #ax.set_title(f"Selected papers count ({category_facet}/year)", pad=20)
    fig.tight_layout()

    plt.show()
    fig.savefig(os.path.join(BASEDIR, "categories_headmap.pdf"), bbox_inches="tight")


def papers_selection_chart(papers, stacked=False):

    selected_paper_by_year = {}
    removed_paper_by_year = {}

    for paper in papers:
        year = paper["publication_date"].split("-")[0]

        if year not in selected_paper_by_year:
            selected_paper_by_year[year] = 0
            removed_paper_by_year[year] = 0

        if paper["selected"]:
            selected_paper_by_year[year] += 1
        else:
            removed_paper_by_year[year] += 1

    years = list(selected_paper_by_year.keys())
    years.sort()
    selected_papers = []
    removed_papers = []
    for year in years:
        selected_papers.append(selected_paper_by_year[year])
        removed_papers.append(removed_paper_by_year[year])

    x = np.arange(len(years))  # the label locations
    fig, ax = plt.subplots()

    if stacked:
        width = 0.8
        rects1 = ax.bar(x, selected_papers, width, label="Selected", color="green", alpha=0.4)
        rects2 = ax.bar(x, removed_papers, width, label="Removed", color="red", alpha=0.4, bottom=selected_papers)
    else:
        width = 0.4
        rects1 = ax.bar(x - width, selected_papers, width, label="Selected", color="green", alpha=0.4)
        rects2 = ax.bar(x, removed_papers, width, label="Removed", color="red", alpha=0.4)

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_ylabel("Papers count")
    ax.set_xlabel("Year")
    #ax.set_title("Papers count", pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(years)
    ax.legend()

    autolabel(rects1, ax)
    autolabel(rects2, ax)

    fig.tight_layout()

    plt.show()
    fig.savefig(os.path.join(BASEDIR, "papers_selection.pdf"), bbox_inches="tight")


def papers_citations_chart(papers):

    selected_papers = [x for x in papers if x["selected"]]
    selected_papers_citations = [x["citations"] for x in selected_papers]
    selected_papers_publication_date = [datetime.datetime.strptime(x["publication_date"], "%Y-%m-%d").date() for x in selected_papers]

    removed_papers = [x for x in papers if not x["selected"]]
    removed_papers_citations = [x["citations"] for x in removed_papers]
    removed_papers_publication_date = [datetime.datetime.strptime(x["publication_date"], "%Y-%m-%d").date() for x in removed_papers]

    fig, ax = plt.subplots()
    ax.scatter(selected_papers_publication_date, selected_papers_citations, color="green", label="Selected", s=50, alpha=0.4)
    ax.scatter(removed_papers_publication_date, removed_papers_citations, color="red", label="Removed", s=50, alpha=0.4)

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_ylabel("Papers citations")
    ax.set_xlabel("Publication date")
    #ax.set_title("Papers citations", pad=20)
    ax.legend()

    fig.tight_layout()

    plt.show()
    fig.savefig(os.path.join(BASEDIR, "papers_citations.pdf"), bbox_inches="tight")


# loadging data
with open(os.path.join(BASEDIR, "search_paul.json"), "r") as jsonfile:
    SEARCH_RESULTS = json.load(jsonfile)

# generate fake selection/classification
for paper in SEARCH_RESULTS["papers"]:

    paper["selected"] = random.choice([True, False])
    if paper["selected"]:
        paper["categories"] = {
            "Contribution": random.sample(["Metric","Tool","Model","Method"], 1)
        }


databases_venn_chart(SEARCH_RESULTS["papers"])
categories_headmap_chart(SEARCH_RESULTS["papers"], "Contribution")
papers_selection_chart(SEARCH_RESULTS["papers"], stacked=True)
papers_citations_chart(SEARCH_RESULTS["papers"])