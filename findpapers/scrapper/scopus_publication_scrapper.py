import util as Util
import requests
from fake_useragent import UserAgent

class ScopusPublicationScrapper():

    @staticmethod
    def run(api_key, issn, partial_result):

        url = 'https://api.elsevier.com/content/serial/title/issn/{0}?apiKey={1}'.format(issn, api_key)

        response = Util.try_n(lambda: requests.get(url, headers={'User-Agent': str(UserAgent().chrome), 'Accept': 'application/json'}).json()['serial-metadata-response'], 5)

        if response == None or 'entry' not in response or len(response['entry']) == 0:
            return partial_result    
            
        response = response['entry'][0]

        partial_result['publication']['publisher'] = Util.get_dict_value(response, 'dc:publisher')
        partial_result['publication']['scopus_values'] = {
            'coverage_start_year': Util.try_to_return_or_none(lambda: int(response['coverageStartYear'])),
            'coverage_end_year': Util.try_to_return_or_none(lambda: int(response['coverageEndYear'])),
        }

        partial_result['publication']['subject_areas'] = []
        for area in response['subject-area']:
            partial_result['publication']['subject_areas'].append(area['$'])

        partial_result['publication']['scopus_values']['snip'] = None
        if 'SNIPList' in response and len(response['SNIPList']['SNIP']) > 0:
            partial_result['publication']['scopus_values']['snip'] = Util.try_to_return_or_none(lambda: float(response['SNIPList']['SNIP'][0]['$']))

        partial_result['publication']['scopus_values']['sjr'] = None
        if 'SJRList' in response and len(response['SJRList']['SJR']) > 0:
            partial_result['publication']['scopus_values']['sjr'] = Util.try_to_return_or_none(lambda: float(response['SJRList']['SJR'][0]['$']))

        partial_result['publication']['scopus_values']['cite_score'] = Util.try_to_return_or_none(lambda: float(response['citeScoreYearInfoList']['citeScoreCurrentMetric']))

        return partial_result
