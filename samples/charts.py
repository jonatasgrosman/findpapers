# pip install matplotlib matplotlib_venn

import datetime
import json
import os

from matplotlib import pyplot as plt
from matplotlib_venn import venn3

BASEDIR = os.path.dirname(os.path.abspath(__file__))


def autolabel(rects, ax):
    """Attach a text label above each bar in *rects*, displaying its height."""
    for rect in rects:
        height = rect.get_height()
        width = rect.get_width()
        x = rect.get_x()
        y = rect.get_y()
        if height > 0:
            ax.annotate(
                "{}".format(height),
                xy=(x + width / 2, y + height / 2),
                xytext=(0, -5),  # 5 points vertical offset
                textcoords="offset points",
                ha="center",
                va="bottom",
            )


def databases_venn_chart(papers):

    # (Abc, aBc, ABc, abC, AbC, aBC, ABC)
    all_papers_count = {
        "Scopus": 0,
        "arXiv": 0,
        "Scopus-arXiv": 0,
        "IEEE": 0,
        "Scopus-IEEE": 0,
        "arXiv-IEEE": 0,
        "all": 0,
    }

    def fill_papers_count(key):
        all_papers_count[key] += 1

    def plot_papers_count(values, plot_title, filename):

        f = plt.figure(figsize=(4, 4))

        # (Abc, aBc, ABc, abC, AbC, aBC, ABC)
        Abc = values["Scopus"]
        aBc = values["arXiv"]
        Abc = values["Scopus"]
        ABc = values["Scopus-arXiv"]
        abC = values["IEEE"]
        AbC = values["Scopus-IEEE"]
        aBC = values["arXiv-IEEE"]
        ABC = values["all"]

        venn3(
            subsets=(Abc, aBc, ABc, abC, AbC, aBC, ABC),
            set_labels=("Scopus", "arXiv", "IEEE"),
        )

        # circles = venn3_circles(subsets = (Abc, aBc, ABc, abC, AbC, aBC, ABC))
        # for circle in circles:
        #     circle.set_lw(1.0)

        # plt.title(plot_title)

        plt.show()
        f.savefig(os.path.join(BASEDIR, filename), bbox_inches="tight")

    for paper in papers:

        is_in_scopus = "Scopus" in paper["databases"]
        is_in_arxiv = "arXiv" in paper["databases"]
        is_in_IEEE = "IEEE" in paper["databases"]

        if is_in_scopus and not is_in_arxiv and not is_in_IEEE:
            fill_papers_count("Scopus")
        elif is_in_arxiv and not is_in_scopus and not is_in_IEEE:
            fill_papers_count("arXiv")
        elif is_in_IEEE and not is_in_scopus and not is_in_arxiv:
            fill_papers_count("IEEE")
        elif is_in_scopus and is_in_arxiv and not is_in_IEEE:
            fill_papers_count("Scopus-arXiv")
        elif is_in_scopus and is_in_IEEE and not is_in_arxiv:
            fill_papers_count("Scopus-IEEE")
        elif is_in_arxiv and is_in_IEEE and not is_in_scopus:
            fill_papers_count("arXiv-IEEE")
        elif is_in_scopus and is_in_arxiv and is_in_IEEE:
            fill_papers_count("all")
        else:
            print(paper)

    plot_papers_count(all_papers_count, "Collected papers count", "databases_venn.pdf")


def papers_citations_chart(papers):

    papers_citations = [
        x["citations"] for x in papers if x.get("citations") is not None
    ]
    papers_publication_date = [
        datetime.datetime.strptime(x["publication_date"], "%Y-%m-%d").date()
        for x in papers
        if x.get("citations") is not None
    ]

    fig, ax = plt.subplots()
    ax.scatter(papers_publication_date, papers_citations, color="blue", s=50, alpha=0.4)

    # Add some text for labels, title and custom x-axis tick labels, etc.
    ax.set_ylabel("Papers citations")
    ax.set_xlabel("Publication date")
    # ax.set_title("Papers citations", pad=20)

    fig.tight_layout()

    plt.show()
    fig.savefig(os.path.join(BASEDIR, "papers_citations.pdf"), bbox_inches="tight")


# loadging data
with open(os.path.join(BASEDIR, "search_paul.json"), "r") as jsonfile:
    SEARCH_RESULTS = json.load(jsonfile)

databases_venn_chart(SEARCH_RESULTS["papers"])
papers_citations_chart(SEARCH_RESULTS["papers"])
