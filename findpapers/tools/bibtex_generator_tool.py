import logging
from typing import Optional
import findpapers.utils.persistence_util as persistence_util
import findpapers.utils.common_util as common_util


def generate_bibtex(search_path: str, outputpath: str, only_selected_papers: Optional[bool] = False):
    """
    Method used to generate a BibTeX file from a search result

    Parameters
    ----------
    search_path : str
        A valid file path containing a JSON representation of the search results
    outputpath : str
        A valid file path for the BibTeX output file
    only_selected_papers : bool, optional
        If you only want to generate a BibTeX file for selected papers, by default False
    verbose : bool, optional
        If the logging needs to be verbose, by default False
    """

    search = persistence_util.load(search_path)
    common_util.check_write_access(outputpath)

    default_tab = ' ' * 4
    bibtex_output = ''

    total = len(search.papers)
    for paper in search.papers:

        if only_selected_papers and not paper.selected:
            continue

        logging.info(f'Exporting bibtex for: {paper.title}')

        try:

            citation_type = '@unpublished'
            if paper.publication is not None:
                if paper.publication.category == 'Journal':
                    citation_type = '@article'
                elif paper.publication.category == 'Conference Proceedings':
                    citation_type = '@inproceedings'
                elif paper.publication.category == 'Book':
                    citation_type = '@book'
                else:
                    citation_type = '@misc'

            bibtex_output += f'{citation_type}{"{"}{paper.get_citation_key()},\n'

            bibtex_output += f'{default_tab}title = {{{paper.title}}},\n'

            if len(paper.authors) > 0:
                authors = ' and '.join(paper.authors)
                bibtex_output += f'{default_tab}author = {{{authors}}},\n'

            if citation_type == '@unpublished':
                note = ''
                if len(paper.urls) > 0:
                    note += f'Available at {list(paper.urls)[0]}'
                if paper.publication_date is not None:
                    note += f' ({paper.publication_date.strftime("%Y/%m/%d")})'
                if paper.comments is not None:
                    note += paper.comments if len(
                        note) == 0 else f' | {paper.comments}'
                bibtex_output += f'{default_tab}note = {{{note}}},\n'
            elif citation_type == '@article':
                bibtex_output += f'{default_tab}journal = {{{paper.publication.title}}},\n'
            elif citation_type == '@inproceedings':
                bibtex_output += f'{default_tab}booktitle = {{{paper.publication.title}}},\n'
            elif citation_type == '@misc' and len(paper.urls) > 0 and paper.publication_date is not None:
                date = paper.publication_date.strftime('%Y/%m/%d')
                url = list(paper.urls)[0]
                bibtex_output += f'{default_tab}howpublished = {{Available at {url} ({date})}},\n'

            if paper.publication is not None and paper.publication.publisher is not None:
                bibtex_output += f'{default_tab}publisher = {{{paper.publication.publisher}}},\n'

            if paper.publication_date is not None:
                bibtex_output += f'{default_tab}year = {{{paper.publication_date.year}}},\n'

            if paper.pages is not None:
                bibtex_output += f'{default_tab}pages = {{{paper.pages}}},\n'

            bibtex_output = bibtex_output.rstrip(
                ',\n') + '\n'  # removing last comma

            bibtex_output += '}\n\n'

        except Exception as e:
            logging.debug(e, exc_info=True)

    with open(outputpath, 'w') as fp:
        fp.write(bibtex_output)
