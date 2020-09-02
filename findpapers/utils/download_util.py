import os
import re
import json
import requests
import logging
import urllib.parse
from lxml import html
from typing import Optional
import findpapers.utils.common_util as util
from findpapers.models.search import Search


def download(search: Search, output_directory: str, only_selected_papers: Optional[bool] = True,
             requests_session: Optional[requests.Session] = None):
    """
    Method used to save a search result in a JSON representation

    Parameters
    ----------
    search : Search
        A Search instance
    filepath : str
        A valid file path used to save the search results
    """

    if requests_session is None:
        requests_session = requests.Session()

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    for paper in search.papers:

        logging.info(f'Trying to get fulltext for {paper.title}')

        downloaded = False
        output_filename = f'{paper.publication_date.year}-{paper.title}'
        output_filename = re.sub(
            r'[^\w\d-]', '_', output_filename)  # sanitize filename
        output_filename += '.pdf'

        output_filepath = os.path.join(output_directory, output_filename)

        if not only_selected_papers or paper.selected:

            urls = paper.urls
            if paper.doi is not None:  # adding some possible valid URLs based on the paper's DOI
                urls.add(f'https://doi.org/{paper.doi}')
                urls.add(f'https://dl.acm.org/doi/pdf/{paper.doi}')

            for url in urls:  # we'll try to download the PDF file of the paper by its URLs
                try:
                    logging.info(f'Trying to get paper fulltext from: {url}')
                    response = util.try_success(
                        lambda url=url: requests_session.get(url, allow_redirects=True), 3, 2)

                    if response is None:
                        continue
                    
                    if 'text/html' in response.headers.get('content-type').lower():
                        
                        response_url_split = urllib.parse.urlsplit(response.url)
                        host_url = f'{response_url_split.scheme}://{response_url_split.hostname}'
                        pdf_url = None

                        if host_url.startswith('https://ieeexplore.ieee.org'):
                            #IEEE
                            #PAGE https://ieeexplore.ieee.org/document/9076358
                            #PDF https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber=9076358
                            document_id = response_url_split.path.replace('document','').replace('/','')
                            pdf_url = f'{host_url}/stamp/stamp.jsp?tp=&arnumber={document_id}'

                            #TODO: this URL only returns a page with the PDF embedded on an iframe, we need to get the real PDF url, 

                        # some pages has "citation_pdf_url" META on the HTML header that points to the fulltext PDF

                        page = html.fromstring(response.content.decode('UTF-8'))

                        citation_pdf_url_meta = page.xpath('//meta[contains(@name, "citation_pdf_url")]')

                        if pdf_url is not None:
                            response = util.try_success(lambda pdf_url=pdf_url: requests_session.get(pdf_url, allow_redirects=True), 3, 2)

                    if 'application/pdf' in response.headers.get('content-type').lower():
                        open(output_filepath, 'wb').write(response.content)
                        downloaded = True
                        break

                except Exception as e:  # pragma: no cover
                    pass

        if downloaded:
            pass
        else:
            pass
