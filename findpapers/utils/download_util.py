import os
import re
import json
import requests
import logging
import datetime
import urllib.parse
from lxml import html
from fake_useragent import UserAgent
from typing import Optional
import findpapers.utils.common_util as util
from findpapers.models.search import Search


DEFAULT_SESSION = requests.Session()
DEFAULT_HEADERS = {'User-Agent': str(UserAgent().chrome)}


def _get_response(url, requests_session: requests.Session):

    response = util.try_success(
        lambda url=url: requests_session.get(url, allow_redirects=True, headers=DEFAULT_HEADERS), 2, 2)

    if (response is None or not response.ok) and requests_session != DEFAULT_SESSION: 
        # maybe the user provided session isn't working properly, so we'll try one more time with our default session
        response = util.try_success(
            lambda url=url: DEFAULT_SESSION.get(url, allow_redirects=True, headers=DEFAULT_HEADERS), 2, 2)
    
    return response


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
        requests_session = DEFAULT_SESSION

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    log_filepath = os.path.join(output_directory, 'download.log')
    with open(log_filepath, 'a' if os.path.exists(log_filepath) else 'w') as fp:
        now = datetime.datetime.now()
        fp.write(f"A new download process started at: {datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')} \n")

    for paper in search.papers:

        logging.info(f'Trying to get fulltext for: {paper.title}')

        downloaded = False
        output_filename = f'{paper.publication_date.year}-{paper.title}'
        output_filename = re.sub(
            r'[^\w\d-]', '_', output_filename)  # sanitize filename
        output_filename += '.pdf'
        output_filepath = os.path.join(output_directory, output_filename)

        if os.path.exists(output_filepath): # PDF already collected
            continue

        if not only_selected_papers or paper.selected:

            for url in paper.urls:  # we'll try to download the PDF file of the paper by its URLs
                try:
                    logging.info(f'Fetching data from: {url}')

                    response = _get_response(url, requests_session)

                    if response is None:
                        continue

                    if 'text/html' in response.headers.get('content-type').lower():

                        response_url = urllib.parse.urlsplit(response.url)
                        response_query_string = urllib.parse.parse_qs(urllib.parse.urlparse(response.url).query)
                        response_url_path = response_url.path
                        host_url = f'{response_url.scheme}://{response_url.hostname}'
                        pdf_url = None

                        if response_url_path.endswith('/'):
                            response_url_path = response_url_path[:-1]

                        if host_url == 'https://dl.acm.org':

                            doi = paper.doi
                            if doi is None and response_url_path.startswith('/doi/') and '/doi/pdf/' not in response_url_path:
                                doi = response_url_path[4:]
                            elif doi is None:
                                continue

                            pdf_url = f'https://dl.acm.org/doi/pdf/{doi}'

                        elif host_url == 'https://ieeexplore.ieee.org':

                            if response_url_path.startswith('/document/'):
                                document_id = response_url_path[10:]
                            elif response_query_string.get('arnumber', None) is not None:
                                document_id = response_query_string.get('arnumber')[0]
                            else:
                                continue

                            pdf_url = f'{host_url}/stampPDF/getPDF.jsp?tp=&arnumber={document_id}'

                        elif host_url == 'https://www.sciencedirect.com' or host_url == 'https://linkinghub.elsevier.com':
                            
                            paper_id = response_url_path.split('/')[-1]
                            pdf_url = f'https://www.sciencedirect.com/science/article/pii/{paper_id}/pdfft?isDTMRedir=true&download=true'

                        elif host_url == 'https://pubs.rsc.org':

                            pdf_url = response.url.replace('articlelanding', 'articlepdf')

                        elif host_url == 'https://www.tandfonline.com':

                            pdf_url = response.url.replace('full', 'pdf')
                        
                        elif host_url == 'https://pubs.acs.org' or host_url == 'https://journals.sagepub.com':

                            pdf_url = response.url.replace('doi', 'doi/pdf')
                        
                        if pdf_url is not None:

                            response = _get_response(pdf_url, requests_session)

                    if 'application/pdf' in response.headers.get('content-type').lower():
                        with open(output_filepath, 'wb') as fp:
                            fp.write(response.content)
                        downloaded = True
                        break

                except Exception as e:  # pragma: no cover
                    pass

        if downloaded:
            with open(log_filepath, 'a') as fp:
                fp.write(f'[DOWNLOADED] {paper.title}\n')
        else:
            with open(log_filepath, 'a') as fp:
                fp.write(f'[FAILED] {paper.title}\n')
                for url in paper.urls:
                    fp.write(f'{url}\n')
