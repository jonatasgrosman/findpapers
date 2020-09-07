import requests
import datetime
import logging
import re
import math
import xmltodict
from lxml import html
from typing import Optional
import findpapers.utils.common_util as util
from findpapers.models.search import Search
from findpapers.models.paper import Paper
from findpapers.models.publication import Publication
from findpapers.utils.requests_util import DefaultSession


DEFAULT_SESSION = DefaultSession()
DATABASE_LABEL = 'arXiv'
BASE_URL = 'http://export.arxiv.org'
MAX_ENTRIES_PER_PAGE = 200
SUBJECT_AREA_BY_KEY = {
    'astro-ph': 'Astrophysics',
    'astro-ph.CO': 'Cosmology and Nongalactic Astrophysics',
    'astro-ph.EP': 'Earth and Planetary Astrophysics',
    'astro-ph.GA': 'Astrophysics of Galaxies',
    'astro-ph.HE': 'High Energy Astrophysical Phenomena',
    'astro-ph.IM': 'Instrumentation and Methods for Astrophysics',
    'astro-ph.SR': 'Solar and Stellar Astrophysics',
    'cond-mat.dis-nn': 'Disordered Systems and Neural Networks',
    'cond-mat.mes-hall': 'Mesoscale and Nanoscale Physics',
    'cond-mat.mtrl-sci': 'Materials Science',
    'cond-mat.other': 'Other Condensed Matter',
    'cond-mat.quant-gas': 'Quantum Gases',
    'cond-mat.soft': 'Soft Condensed Matter',
    'cond-mat.stat-mech': 'Statistical Mechanics',
    'cond-mat.str-el': 'Strongly Correlated Electrons',
    'cond-mat.supr-con': 'Superconductivity',
    'cs.AI': 'Artificial Intelligence',
    'cs.AR': 'Hardware Architecture',
    'cs.CC': 'Computational Complexity',
    'cs.CE': 'Computational Engineering, Finance, and Science',
    'cs.CG': 'Computational Geometry',
    'cs.CL': 'Computation and Language',
    'cs.CR': 'Cryptography and Security',
    'cs.CV': 'Computer Vision and Pattern Recognition',
    'cs.CY': 'Computers and Society',
    'cs.DB': 'Databases',
    'cs.DC': 'Distributed, Parallel, and Cluster Computing',
    'cs.DL': 'Digital Libraries',
    'cs.DM': 'Discrete Mathematics',
    'cs.DS': 'Data Structures and Algorithms',
    'cs.ET': 'Emerging Technologies',
    'cs.FL': 'Formal Languages and Automata Theory',
    'cs.GL': 'General Literature',
    'cs.GR': 'Graphics',
    'cs.GT': 'Computer Science and Game Theory',
    'cs.HC': 'Human-Computer Interaction',
    'cs.IR': 'Information Retrieval',
    'cs.IT': 'Information Theory',
    'cs.LG': 'Learning',
    'cs.LO': 'Logic in Computer Science',
    'cs.MA': 'Multiagent Systems',
    'cs.MM': 'Multimedia',
    'cs.MS': 'Mathematical Software',
    'cs.NA': 'Numerical Analysis',
    'cs.NE': 'Neural and Evolutionary Computing',
    'cs.NI': 'Networking and Internet Architecture',
    'cs.OH': 'Other Computer Science',
    'cs.OS': 'Operating Systems',
    'cs.PF': 'Performance',
    'cs.PL': 'Programming Languages',
    'cs.RO': 'Robotics',
    'cs.SC': 'Symbolic Computation',
    'cs.SD': 'Sound',
    'cs.SE': 'Software Engineering',
    'cs.SI': 'Social and Information Networks',
    'cs.SY': 'Systems and Control',
    'econ.EM': 'Econometrics',
    'eess.AS': 'Audio and Speech Processing',
    'eess.IV': 'Image and Video Processing',
    'eess.SP': 'Signal Processing',
    'gr-qc': 'General Relativity and Quantum Cosmology',
    'hep-ex': 'High Energy Physics - Experiment',
    'hep-lat': 'High Energy Physics - Lattice',
    'hep-ph': 'High Energy Physics - Phenomenology',
    'hep-th': 'High Energy Physics - Theory',
    'math.AC': 'Commutative Algebra',
    'math.AG': 'Algebraic Geometry',
    'math.AP': 'Analysis of PDEs',
    'math.AT': 'Algebraic Topology',
    'math.CA': 'Classical Analysis and ODEs',
    'math.CO': 'Combinatorics',
    'math.CT': 'Category Theory',
    'math.CV': 'Complex Variables',
    'math.DG': 'Differential Geometry',
    'math.DS': 'Dynamical Systems',
    'math.FA': 'Functional Analysis',
    'math.GM': 'General Mathematics',
    'math.GN': 'General Topology',
    'math.GR': 'Group Theory',
    'math.GT': 'Geometric Topology',
    'math.HO': 'History and Overview',
    'math.IT': 'Information Theory',
    'math.KT': 'K-Theory and Homology',
    'math.LO': 'Logic',
    'math.MG': 'Metric Geometry',
    'math.MP': 'Mathematical Physics',
    'math.NA': 'Numerical Analysis',
    'math.NT': 'Number Theory',
    'math.OA': 'Operator Algebras',
    'math.OC': 'Optimization and Control',
    'math.PR': 'Probability',
    'math.QA': 'Quantum Algebra',
    'math.RA': 'Rings and Algebras',
    'math.RT': 'Representation Theory',
    'math.SG': 'Symplectic Geometry',
    'math.SP': 'Spectral Theory',
    'math.ST': 'Statistics Theory',
    'math-ph': 'Mathematical Physics',
    'nlin.AO': 'Adaptation and Self-Organizing Systems',
    'nlin.CD': 'Chaotic Dynamics',
    'nlin.CG': 'Cellular Automata and Lattice Gases',
    'nlin.PS': 'Pattern Formation and Solitons',
    'nlin.SI': 'Exactly Solvable and Integrable Systems',
    'nucl-ex': 'Nuclear Experiment',
    'nucl-th': 'Nuclear Theory',
    'physics.acc-ph': 'Accelerator Physics',
    'physics.ao-ph': 'Atmospheric and Oceanic Physics',
    'physics.app-ph': 'Applied Physics',
    'physics.atm-clus': 'Atomic and Molecular Clusters',
    'physics.atom-ph': 'Atomic Physics',
    'physics.bio-ph': 'Biological Physics',
    'physics.chem-ph': 'Chemical Physics',
    'physics.class-ph': 'Classical Physics',
    'physics.comp-ph': 'Computational Physics',
    'physics.data-an': 'Data Analysis, Statistics and Probability',
    'physics.ed-ph': 'Physics Education',
    'physics.flu-dyn': 'Fluid Dynamics',
    'physics.gen-ph': 'General Physics',
    'physics.geo-ph': 'Geophysics',
    'physics.hist-ph': 'History and Philosophy of Physics',
    'physics.ins-det': 'Instrumentation and Detectors',
    'physics.med-ph': 'Medical Physics',
    'physics.optics': 'Optics',
    'physics.plasm-ph': 'Plasma Physics',
    'physics.pop-ph': 'Popular Physics',
    'physics.soc-ph': 'Physics and Society',
    'physics.space-ph': 'Space Physics',
    'q-bio.BM': 'Biomolecules',
    'q-bio.CB': 'Cell Behavior',
    'q-bio.GN': 'Genomics',
    'q-bio.MN': 'Molecular Networks',
    'q-bio.NC': 'Neurons and Cognition',
    'q-bio.OT': 'Other Quantitative Biology',
    'q-bio.PE': 'Populations and Evolution',
    'q-bio.QM': 'Quantitative Methods',
    'q-bio.SC': 'Subcellular Processes',
    'q-bio.TO': 'Tissues and Organs',
    'q-fin.CP': 'Computational Finance',
    'q-fin.EC': 'Economics',
    'q-fin.GN': 'General Finance',
    'q-fin.MF': 'Mathematical Finance',
    'q-fin.PM': 'Portfolio Management',
    'q-fin.PR': 'Pricing of Securities',
    'q-fin.RM': 'Risk Management',
    'q-fin.ST': 'Statistical Finance',
    'q-fin.TR': 'Trading and Market Microstructure',
    'quant-ph': 'Quantum Physics',
    'stat.AP': 'Applications',
    'stat.CO': 'Computation',
    'stat.ME': 'Methodology',
    'stat.ML': 'Machine Learning',
    'stat.OT': 'Other Statistics',
    'stat.TH': 'Statistics Theory'
}


def _get_search_url(search: Search, start_record: Optional[int] = 0) -> str:
    """
    This method return the URL to be used to retrieve data from arXiv database
    See https://arxiv.org/help/api/user-manual for query tips

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str
        Sequence number of first record to fetch, by default 0

    Returns
    -------
    str
        a URL to be used to retrieve data from arXiv database
    """

    transformed_query = search.query.replace(' AND NOT ', ' ANDNOT ')
    if transformed_query[0] == '"':
        transformed_query = ' ' + transformed_query
    transformed_query = transformed_query.replace(' "', ' all:"')
    transformed_query = transformed_query.replace('("', '(all:"')
    transformed_query = transformed_query.replace('"', '')
    transformed_query = transformed_query.strip()

    url = f'{BASE_URL}/api/query?search_query={transformed_query}&start={start_record}&sortBy=submittedDate&sortOrder=descending&max_results={MAX_ENTRIES_PER_PAGE}'

    return url


def _get_api_result(search: Search, start_record: Optional[int] = 0) -> dict: # pragma: no cover
    """
    This method return results from arXiv database using the provided search parameters

    Parameters
    ----------
    search : Search
        A search instance
    start_record : str
        Sequence number of first record to fetch, by default 1

    Returns
    -------
    dict
        a result from arXiv database
    """

    url = _get_search_url(search, start_record)

    return util.try_success(lambda: xmltodict.parse(DEFAULT_SESSION.get(url).content), 2, pre_delay=1)


def _get_publication(paper_entry: dict) -> Publication:
    """
    Using a paper entry provided, this method builds a publication instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from arXiv API

    Returns
    -------
    Publication, or None
        A publication instance
    """

    if 'arxiv:journal_ref' in paper_entry:

        publication_title = paper_entry.get('arxiv:journal_ref').get('#text')

        if publication_title is None or len(publication_title) == 0:
            return None

        subject_areas = set()

        if 'category' in paper_entry:
            if isinstance(paper_entry.get('category'), list):
                for category in paper_entry.get('category'):
                    subject_areas.add(
                        SUBJECT_AREA_BY_KEY.get(category.get('@term')))
            else:
                subject_areas.add(SUBJECT_AREA_BY_KEY.get(
                    paper_entry.get('category').get('@term')))

        publication = Publication(
            publication_title, subject_areas=subject_areas)

        return publication


def _get_paper(paper_entry: dict, paper_publication_date: datetime.date, publication: Publication) -> Paper:
    """
    Using a paper entry provided, this method builds a paper instance

    Parameters
    ----------
    paper_entry : dict
        A paper entry retrived from arXiv API
    paper_publication_date : datetime.date
        The paper publication date
    publication : Publication
        A publication instance that will be associated with the paper

    Returns
    -------
    Paper
        A paper instance
    """

    paper_title = paper_entry.get('title', None)

    if paper_title is None or len(paper_title) == 0:
        return None

    paper_title = paper_title.replace('\n','') 
    paper_title = re.sub(' +', ' ', paper_title)

    paper_doi = paper_entry.get('arxiv:doi').get(
        '#text') if 'arxiv:doi' in paper_entry else None
    paper_abstract = paper_entry.get('summary', None)
    paper_urls = set()
    paper_authors = []

    if 'link' in paper_entry:
        if isinstance(paper_entry.get('link'), list):
            for link in paper_entry.get('link'):
                paper_urls.add(link.get('@href'))
        else:
            paper_urls.add(paper_entry.get('link').get('@href'))

    if 'author' in paper_entry:
        if isinstance(paper_entry.get('author'), list):
            for author in paper_entry.get('author'):
                paper_authors.append(author.get('name'))
        else:
            paper_authors.append(paper_entry.get('author').get('name'))

    paper_comments = paper_entry.get('arxiv:comment', {}).get('#text', None)

    paper = Paper(paper_title, paper_abstract, paper_authors, publication,
                  paper_publication_date, paper_urls, paper_doi, comments=paper_comments)

    return paper


def run(search: Search):
    """
    This method fetch papers from arXiv database using the provided search parameters
    After fetch the data from arXiv, the collected papers are added to the provided search instance

    Parameters
    ----------
    search : Search
        A search instance

    """

    papers_count = 0
    result = _get_api_result(search)

    total_papers = int(result.get('feed').get(
        'opensearch:totalResults').get('#text'))

    logging.info(f'{total_papers} papers to fetch')

    while(papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL)):

        for paper_entry in result.get('feed').get('entry'):

            if papers_count >= total_papers or search.reached_its_limit(DATABASE_LABEL):
                break

            papers_count += 1

            try:

                paper_title = paper_entry.get("title")
                logging.info(f'({papers_count}/{total_papers}) Fetching arXiv paper: {paper_title}')

                published_date = datetime.datetime.strptime(
                    paper_entry.get('published')[:10], '%Y-%m-%d').date()

                # nowadays we don't have a date filter on arXiv API, so we need to do it by ourselves'
                if search.since is not None and published_date < search.since:
                    logging.info(
                        'Skipping paper due to "since" date constraint')
                    continue
                elif search.until is not None and published_date > search.until:
                    logging.info(
                        'Skipping paper due to "until" date constraint')
                    continue

                publication = _get_publication(paper_entry)
                paper = _get_paper(paper_entry, published_date, publication)

                if paper is not None:
                    paper.add_database(DATABASE_LABEL)
                    search.add_paper(paper)

            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)

        if papers_count < total_papers and not search.reached_its_limit(DATABASE_LABEL):
            result=_get_api_result(search, papers_count)
