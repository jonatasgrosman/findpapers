import util as Util
import requests
import traceback
from typing import Optional
from fake_useragent import UserAgent
from scrapper.scopus_paper_page_scrapper import ScopusPaperPageScrapper
from scrapper.scopus_publication_scrapper import ScopusPublicationScrapper

class ScopusScrapper():

    @staticmethod
    def _get_converted_query(query: str, year_lower_bound: Optional[int], area_keys=Optional[list]):

        # SCOPUS QUERY TIPS: https://dev.elsevier.com/tips/ScopusSearchTips.htm

        # "human" AND "bias" AND ("annotation" OR "labeling" OR "labelling" OR "tagging")

        #SCOPUS_QUERY = PUBYEAR > 2016 AND LANGUAGE(english) AND SUBJAREA(COMP) AND TITLE-ABS-KEY(("conversational interface" OR "conversational agent" OR "chatbot" OR "dialogue" OR "question answering") AND ("ontology" OR "domain knowledge"))

        areas_by_key = {
            'computer_science': ['COMP', 'MULT'],
            'economics': ['ECON', 'BUSI', 'MULT'],
            'engineering': ['AGRI', 'CENG', 'ENER', 'ENGI', 'ENVI', 'MATE', 'MULT'],
            'mathematics': ['MATH', 'MULT'],
            'physics': ['EART', 'PHYS', 'MULT'],
            'biology': ['AGRI', 'BIOC', 'DENT', 'ENVI', 'HEAL', 'IMMU', 'MEDI', 'NEUR', "NURS", 'PHAR', 'VETE', 'MULT'],
            'chemistry': ['CENG', 'CHEM', 'PHAR', 'MULT'],
            'humanities': ['ARTS', 'DECI', 'ENVI', 'PSYC', 'SOCI', 'MULT']
        }

        converted_query = 'TITLE-ABS-KEY({})'.format(query)

        if year_lower_bound != None:
            converted_query += ' AND PUBYEAR > {}'.format(year_lower_bound + 1)

        if area_keys != None:
            selected_areas = []
            for area_key in area_keys.split(','):
                areas = areas_by_key.get(area_key.strip(), [])
                for area in areas:
                    selected_areas.append(area)
            if len(selected_areas) > 0:
                converted_query += ' AND SUBJAREA({})'.format(' OR '.join(selected_areas))

        return converted_query


    @staticmethod
    def run(api_key: str, query: str, year_lower_bound: Optional[int], area_key=Optional[str]):

        print('initializing Scopus scrapper')

        BASE_URL = 'https://api.elsevier.com/content/search/scopus?&sort=citedby-count,relevancy,pubyear&apiKey={0}'.format(api_key)
        
        papers = []
        queries = query.split(',')

        for q in queries:

            q = ScopusScrapper._get_converted_query(q, year_lower_bound, area_key)

            url = '{}&query={}'.format(BASE_URL, q)

            while(True):
                papers, url = ScopusScrapper._get_data_from_url(url, api_key, papers)

                if url == None:
                    break

        return papers
    

    @staticmethod
    def _get_data_from_url(url, api_key, papers=[]):

        response = Util.try_n(lambda: requests.get(url, headers={'User-Agent': str(UserAgent().chrome), 'Accept': 'application/json'}).json()['search-results'], 5)
        
        total_results = int(Util.get_dict_value(response, 'opensearch:totalResults'))

        if total_results == 0:
            return papers, None

        start_index = int(Util.get_dict_value(response, 'opensearch:startIndex'))
        item_per_page = int(Util.get_dict_value(response, 'opensearch:itemsPerPage'))

        for i, entry in enumerate(response['entry']):

            try:

                paper = {
                    'title': Util.get_dict_value(entry, 'dc:title'),
                    'first_author': Util.get_dict_value(entry, 'dc:creator'),
                    'date': Util.get_dict_value(entry, 'prism:coverDate'),
                    'doi': Util.get_dict_value(entry, 'prism:doi'),
                    'citations': Util.get_dict_value(entry, 'citedby-count'),
                    'type': Util.get_dict_value(entry, 'prism:aggregationType'),
                    'subtype': Util.get_dict_value(entry, 'subtypeDescription'),
                }

                print(paper['title'])
                print(paper['date'])

                if paper['citations'] != None:
                    paper['citations'] = int(paper['citations'])

                publication = {
                    'name': Util.get_dict_value(entry, 'prism:publicationName'),
                    'isbn': Util.try_to_return_or_none(lambda: Util.get_dict_value(entry, 'prism:isbn')),
                    'issn': Util.try_to_return_or_none(lambda: Util.get_dict_value(entry, 'prism:issn')),
                }

                if isinstance(publication['isbn'], list):
                    publication['isbn'] = publication['isbn'][0]['$']

                if isinstance(publication['issn'], list):
                    publication['issn'] = publication['issn'][0]['$']

                result = {
                    'paper': paper,
                    'publication': publication,
                }

                for link in entry['link']:
                    if link['@ref'] == 'scopus':
                        paper_scopus_link = link['@href']
                        break

                result = ScopusPaperPageScrapper.run(paper_scopus_link, result)

                if result['publication']['issn'] != None:
                    result = ScopusPublicationScrapper.run(api_key, result['publication']['issn'], result)
                
                papers.append(result)

            except Exception as e:
                Util.print_exception(e)

            print('{0}/{1} documents processed'.format(start_index+i+1, total_results))

        next_url = None
        for link in response['link']:
            if link['@ref'] == 'next':
                next_url = link['@href']
                break

        return papers, next_url

        