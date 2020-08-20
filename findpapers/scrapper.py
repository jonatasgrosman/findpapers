from searcher.scopus_searcher import ScopusScrapper
from searcher.acm_searcher import AcmScrapper
from searcher.arxiv_searcher import ArxivScrapper
import json
import datetime

class Scrapper():

    @staticmethod
    def run(config):

        print('running...')

        # API_KEY = config['DEFAULT']['SCOPUS_API_KEY']
        # SCOPUS_QUERY = config['DEFAULT']['SCOPUS_QUERY']
        # ACM_QUERY = config['DEFAULT']['ACM_QUERY']
        # ACM_AFTER_YEAR = config['DEFAULT']['ACM_AFTER_YEAR']
        # ARXIV_QUERY = config['DEFAULT']['ARXIV_QUERY']

        QUERY = config['DEFAULT']['QUERY']
        SCOPUS_API_KEY = config['DEFAULT']['SCOPUS_API_KEY']
        AREA = config['DEFAULT']['AREA']
        PUBLICATION_YEAR_LOWER_BOUND = config['DEFAULT']['PUBLICATION_YEAR_LOWER_BOUND']

        if len(PUBLICATION_YEAR_LOWER_BOUND) == 0:
            PUBLICATION_YEAR_LOWER_BOUND = None
        else:
            PUBLICATION_YEAR_LOWER_BOUND = int(PUBLICATION_YEAR_LOWER_BOUND)

        data_by_key = {}
        results = []
        duplicated_papers_count = 0

        scopus_data = []
        if len(SCOPUS_API_KEY) > 0:
            scopus_data = ScopusScrapper.run(SCOPUS_API_KEY, QUERY, PUBLICATION_YEAR_LOWER_BOUND, AREA)
            data_by_key, results, duplicated_papers_count = Scrapper.fill_data(scopus_data, 'Scopus', data_by_key, results, duplicated_papers_count)
        
        acm_data = AcmScrapper.run(QUERY, PUBLICATION_YEAR_LOWER_BOUND)
        data_by_key, results, duplicated_papers_count = Scrapper.fill_data(acm_data, 'ACM', data_by_key, results, duplicated_papers_count)

        arxiv_data = ArxivScrapper.run(QUERY, PUBLICATION_YEAR_LOWER_BOUND, AREA)
        data_by_key, results, duplicated_papers_count = Scrapper.fill_data(arxiv_data, 'arXiv', data_by_key, results, duplicated_papers_count)

        print('total of {0} papers collected from Scopus'.format(len(scopus_data)))
        print('total of {0} papers collected from ACM'.format(len(acm_data)))
        print('total of {0} papers collected from arXiv'.format(len(arxiv_data)))
        print('total of {0} papers collected after duplication removal'.format(len(results)))
        print('total of {0} duplicated papers collected'.format(duplicated_papers_count))

        result = {
            'query': QUERY,
            'fetched_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            'area': AREA,
            'publication_year_lower_bound': PUBLICATION_YEAR_LOWER_BOUND,
            'results': results,
        }

        with open('data/result.json', 'w') as fp:
           json.dump(result, fp, indent=2, sort_keys=True)

    @staticmethod
    def fill_data(data, database, data_by_key={}, result=[], duplicated_papers_count=0):

        for datum in data:
            paper_key = Scrapper.get_paper_key(datum['paper'])

            if paper_key in data_by_key:
                print('Duplicated paper found: {0}'.format(datum['paper']['title']))
                duplicated_papers_count += 1
                if database not in data_by_key[paper_key]['databases']:
                    data_by_key[paper_key]['databases'].append(database)
            else:
                data_by_key[paper_key] = datum
                datum['databases'] = [database]
                result.append(datum)

        return data_by_key, result, duplicated_papers_count

    @staticmethod
    def get_paper_key(paper):
        if paper.get('doi', None) != None:
            return paper['doi']
        else:
            return '{0}-{1}'.format(paper['title'].lower(), paper['date'].split('-')[0]) # title - year
