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
import findpapers.utils.common_util as common_util
import findpapers.utils.persistence_util as persistence_util
from findpapers.models.search import Search
from findpapers.utils.requests_util import DefaultSession


DEFAULT_SESSION = DefaultSession()


def download(search_path: str, output_directory: str, only_selected_papers: Optional[bool] = False):
    """
    If you've done your search, (probably made the search refinement too) and wanna download the papers, 
    this is the method that you need to call. This method will try to download the PDF version of the papers to
    the output directory path.

    We use some heuristics to do our job, but sometime they won't work properly, and we cannot be able
    to download the papers, but we logging the downloads or failures in a file download.log
    placed on the output directory, you can check out the log to find what papers cannot be downloaded
    and try to get them manually later. 

    Note: Some papers are behind a paywall and won't be able to be downloaded by this method. 
    However, if you have a proxy provided for the institution where you study or work that permit you 
    to "break" this paywall. You can use this proxy configuration here
    by setting the environment variables FINDPAPERS_HTTP_PROXY and FINDPAPERS_HTTPS_PROXY.

    Parameters
    ----------
    search_path : str
        A valid file path containing a JSON representation of the search results
    output_directory : str
        A valid file path of the directory where the downloaded papers will be placed
    only_selected_papers : bool, False by default
        If only the selected papers will be downloaded
    """

    search = persistence_util.load(search_path)

    if not os.path.exists(output_directory):
        os.makedirs(output_directory)

    log_filepath = os.path.join(output_directory, 'download.log')

    common_util.check_write_access(log_filepath)

    with open(log_filepath, 'a' if os.path.exists(log_filepath) else 'w') as fp:
        now = datetime.datetime.now()
        fp.write(
            f"------- A new download process started at: {datetime.datetime.strftime(now, '%Y-%m-%d %H:%M:%S')} \n")

    for i, paper in enumerate(search.papers):

        logging.info(f'({i+1}/{len(search.papers)}) {paper.title}')

        downloaded = False
        output_filename = f'{paper.publication_date.year}-{paper.title}'
        output_filename = re.sub(
            r'[^\w\d-]', '_', output_filename)  # sanitize filename
        output_filename += '.pdf'
        output_filepath = os.path.join(output_directory, output_filename)

        if os.path.exists(output_filepath):  # PDF already collected
            logging.info(f'Paper\'s PDF file has already been collected')
            continue
        
        if only_selected_papers and not paper.selected:
            with open(log_filepath, 'a') as fp:
                fp.write(f'[SKIPED] {paper.title}\n')
            continue

        if paper.doi is not None:
            paper.urls.add(f'http://doi.org/{paper.doi}')

        for url in paper.urls:  # we'll try to download the PDF file of the paper by its URLs
            try:
                logging.info(f'Fetching data from: {url}')

                response = common_util.try_success(
                    lambda url=url: DEFAULT_SESSION.get(url), 2)

                if response is None:
                    continue

                if 'text/html' in response.headers.get('content-type').lower():

                    response_url = urllib.parse.urlsplit(response.url)
                    response_query_string = urllib.parse.parse_qs(
                        urllib.parse.urlparse(response.url).query)
                    response_url_path = response_url.path
                    host_url = f'{response_url.scheme}://{response_url.hostname}'
                    pdf_url = None

                    if response_url_path.endswith('/'):
                        response_url_path = response_url_path[:-1]

                    response_url_path = response_url_path.split('?')[0]

                    if host_url in ['https://dl.acm.org']:

                        doi = paper.doi
                        if doi is None and response_url_path.startswith('/doi/') and '/doi/pdf/' not in response_url_path:
                            doi = response_url_path[4:]
                        elif doi is None:
                            continue

                        pdf_url = f'https://dl.acm.org/doi/pdf/{doi}'

                    elif host_url in ['https://ieeexplore.ieee.org']:

                        if response_url_path.startswith('/document/'):
                            document_id = response_url_path[10:]
                        elif response_query_string.get('arnumber', None) is not None:
                            document_id = response_query_string.get('arnumber')[
                                0]
                        else:
                            continue

                        pdf_url = f'{host_url}/stampPDF/getPDF.jsp?tp=&arnumber={document_id}'

                    elif host_url in ['https://www.sciencedirect.com', 'https://linkinghub.elsevier.com']:

                        paper_id = response_url_path.split('/')[-1]
                        pdf_url = f'https://www.sciencedirect.com/science/article/pii/{paper_id}/pdfft?isDTMRedir=true&download=true'

                    elif host_url in ['https://pubs.rsc.org']:

                        pdf_url = response.url.replace(
                            '/articlelanding/', '/articlepdf/')

                    elif host_url in ['https://www.tandfonline.com', 'https://www.frontiersin.org']:

                        pdf_url = response.url.replace('/full', '/pdf')

                    elif host_url in ['https://pubs.acs.org', 'https://journals.sagepub.com', 'https://royalsocietypublishing.org']:

                        pdf_url = response.url.replace('/doi', '/doi/pdf')

                    elif host_url in ['https://link.springer.com']:

                        pdf_url = response.url.replace(
                            '/article/', '/content/pdf/').replace('%2F', '/') + '.pdf'

                    elif host_url in ['https://www.isca-speech.org']:

                        pdf_url = response.url.replace(
                            '/abstracts/', '/pdfs/').replace('.html', '.pdf')

                    elif host_url in ['https://onlinelibrary.wiley.com']:

                        pdf_url = response.url.replace(
                            '/full/', '/pdfdirect/').replace('/abs/', '/pdfdirect/')

                    elif host_url in ['https://www.jmir.org', 'https://www.mdpi.com']:

                        pdf_url = response.url + '/pdf'

                    elif host_url in ['https://www.pnas.org']:

                        pdf_url = response.url.replace(
                            '/content/', '/content/pnas/') + '.full.pdf'

                    elif host_url in ['https://www.jneurosci.org']:

                        pdf_url = response.url.replace(
                            '/content/', '/content/jneuro/') + '.full.pdf'

                    elif host_url in ['https://www.ijcai.org']:

                        paper_id = response.url.split('/')[-1].zfill(4)
                        pdf_url = '/'.join(response.url.split('/')
                                            [:-1]) + '/' + paper_id + '.pdf'

                    elif host_url in ['https://asmp-eurasipjournals.springeropen.com']:

                        pdf_url = response.url.replace(
                            '/articles/', '/track/pdf/')

                    if pdf_url is not None:

                        response = common_util.try_success(
                            lambda url=pdf_url: DEFAULT_SESSION.get(url), 2)

                if 'application/pdf' in response.headers.get('content-type').lower():
                    with open(output_filepath, 'wb') as fp:
                        fp.write(response.content)
                    downloaded = True
                    break

            except Exception as e:  # pragma: no cover
                logging.debug(e, exc_info=True)

        if downloaded:
            with open(log_filepath, 'a') as fp:
                fp.write(f'[DOWNLOADED] {paper.title}\n')
        else:
            with open(log_filepath, 'a') as fp:
                fp.write(f'[FAILED] {paper.title}\n')
                if len(paper.urls) == 0:
                    fp.write(f'Empty URL list\n')
                else:
                    for url in paper.urls:
                        fp.write(f'{url}\n')
