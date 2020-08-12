import util as Util
import requests
from fake_useragent import UserAgent
from lxml import html

class AcmPaperPageScrapper():

    @staticmethod
    def run(url, partial_result):

        headers = {'User-Agent': str(UserAgent().chrome)}
        response = Util.try_n(lambda: requests.get(url, headers=headers), 5)
        page = html.fromstring(response.content.decode('UTF-8'))

        abstract = page.xpath('//*[contains(@class, "abstractSection")]/p')[0].text
        citation_elements = page.xpath('//*[contains(@class, "article-metric citation")]//span')
        citations = None
        if len(citation_elements) == 1:
            citations = int(citation_elements[0].text)

        PAPER_METADATA_BASE_URL = 'https://dl.acm.org/action/exportCiteProcCitation'

        url_split = None
        if '/abs/' in url:
            url_split = url.split('/abs/')
        elif '/book/' in url:
            url_split = url.split('/book/')
        else:
            url_split = url.split('/doi/')

        doi = url_split[1]
        
        form = {
            'dois': doi,
            'targetFile': 'custom-bibtex',
            'format': 'bibTex'
        }

        paper_metadata = requests.post(PAPER_METADATA_BASE_URL, headers=headers, data=form).json()['items'][0][doi]
        
        authors = paper_metadata.get('author', [])
        authors = ['{0}, {1}'.format(x['family'], x['given']) for x in authors]

        date = None
        if paper_metadata.get('issued', None) != None:
            date_parts = paper_metadata['issued']['date-parts'][0]
            if len(date_parts) == 1: #only year
                date = str(date_parts[0])
            else:
                date = '{0}-{1}-{2}'.format(date_parts[0], str(date_parts[1]).zfill(2), str(date_parts[2]).zfill(2))

        keywords = None
        if paper_metadata.get('keyword', None) != None:
            keywords = [x.strip() for x in paper_metadata['keyword'].split(',')]
            

        paper = {
            'abstract': abstract,
            'authors': authors,
            'citations': citations,
            'date': date,
            'doi': doi,
            'first_author': None if len(authors) == 0 else authors[0],
            'keywords': keywords,
            'subtype': paper_metadata.get('type', None),
            'title': paper_metadata.get('title', None)
        }

        publication = {
            'isbn': paper_metadata.get('ISBN', None),
            'issn': paper_metadata.get('ISSN', None),
            'name': paper_metadata.get('container-title', None),
            'publisher': paper_metadata.get('publisher', None)
        }

        partial_result['paper'] = paper
        partial_result['publication'] = publication

        print(paper['title'])
        print(paper['date'])

        return partial_result
