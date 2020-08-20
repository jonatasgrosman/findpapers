import util as Util
import requests
import traceback
from typing import Optional
from fake_useragent import UserAgent
from lxml import html
from searcher.acm_paper_page_searcher import AcmPaperPageScrapper

class AcmScrapper():

    @staticmethod
    def _get_converted_query(query: str):

        # ACM QUERY TIPS: https://dl.acm.org/search/advanced

        #ACM_QUERY = Title:(("conversational interface" OR "conversational agent" OR "chatbot" OR "dialogue" OR "question answering") AND ("ontology" OR "domain knowledge")) OR Abstract:(("conversational interface" OR "chatbot" OR "dialogue" OR "question answering") AND ("ontology" OR "domain knowledge")) OR Keyword:(("conversational interface" OR "conversational agent" OR "chatbot" OR "dialogue" OR "question answering") AND ("ontology" OR "domain knowledge"))

        #"human" AND "bias" AND ("annotation" OR "labeling" OR "labelling" OR "tagging")

        converted_query = 'Title:({})'.format(query)
        converted_query += ' OR Keyword:({})'.format(query)
        converted_query += ' OR Abstract:({})'.format(query)

        return converted_query

    @staticmethod
    def run(query: str, year_lower_bound: Optional[int]):

        print('initializing ACM searcher')

        BASE_URL = 'https://dl.acm.org'
        SEARCH_BASE_URL = BASE_URL + '/action/doSearch'

        papers = []
        queries = query.split(',')

        for q in queries:

            q = AcmScrapper._get_converted_query(q)

            params = {
                'fillQuickSearch': 'false',
                'expand': 'all',
                'AllField': q,
                'AfterYear': year_lower_bound,
                'pageSize': 100
            }

            headers = {'User-Agent': str(UserAgent().chrome)}

            response = Util.try_n(lambda: requests.get(SEARCH_BASE_URL, headers=headers, params=params), 5)
            page = html.fromstring(response.content.decode('UTF-8'))

            papers_urls = []
            next_page_url = None

            while(True):

                if next_page_url == None: # first round
                    response = Util.try_n(lambda: requests.get(SEARCH_BASE_URL, headers=headers, params=params), 5)
                else:
                    response = Util.try_n(lambda: requests.get(next_page_url), 5)

                page = html.fromstring(response.content.decode('UTF-8'))

                next_page_url = AcmScrapper._fill_papers_urls_and_get_next_page_url(page, papers_urls)
                
                if next_page_url == None:
                    break
            
            for i, paper_url in enumerate(papers_urls):
                try:
                    paper = {}
                    AcmPaperPageScrapper.run(BASE_URL + paper_url, paper)

                    papers.append(paper)
                except Exception as e:
                    Util.print_exception(e)

                print('{0}/{1} documents processed'.format(i+1, len(papers_urls)))

        return papers
    

    @staticmethod
    def _fill_papers_urls_and_get_next_page_url(page, papers_urls=[]):

        paper_elements = page.xpath('//*[@class="hlFld-Title"]/a')

        for paper_element in paper_elements:
            papers_urls.append(paper_element.attrib['href'])
        
        next_page_elements = page.xpath('//*[@class="pagination__btn--next"]')
        next_page_url = None
        if len(next_page_elements) == 1:
            next_page_url = next_page_elements[0].attrib['href']
    
        return next_page_url

