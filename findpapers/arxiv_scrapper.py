import util as Util
import requests
from typing import Optional
from fake_useragent import UserAgent
from lxml import html
#from scrapper.acm_paper_page_scrapper import AcmPaperPageScrapper

# switch to API... has support for parentheses :)
# https://arxiv.org/help/api/user-manual

class ArxivScrapper():

    @staticmethod
    def _get_converted_query(query: str, year_lower_bound: Optional[int], area_keys=Optional[str]):

        # arXiv QUERY TIPS: https://arxiv.org/search/advanced

        is_in_parentheses = False
        current_substring = ''
        current_term_index = 0
        current_connector = 'AND'
        converted_query = ''

        def get_query_string(term, index, connector):
            return '&terms-{0}-term={1}&terms-{0}-field=all&terms-{0}-operator={2}'.format(index, term, connector)
            
        for c in query:
            if c == '(':
                if is_in_parentheses:
                    raise Exception('we only support one level parentheses queries')
                is_in_parentheses = True
            elif c == ')':
                converted_query += get_query_string(current_substring, current_term_index, current_connector)
                current_substring = ''
                current_term_index += 1
                is_in_parentheses = False
            else:
                current_substring += c
                if is_in_parentheses and ' AND ' in current_substring:
                    raise Exception('we only support OR statements inside parentheses')
                elif not is_in_parentheses:
                    if ' AND ' in current_substring:
                        converted_query += get_query_string(current_substring.replace(' AND ', ''), current_term_index, current_connector)
                        current_term_index += 1
                        current_substring = ''
                        current_connector = 'AND'
                    elif ' OR ' in current_substring:
                        converted_query += get_query_string(current_substring.replace(' OR ', ''), current_term_index, current_connector)
                        current_term_index += 1
                        current_substring = ''
                        current_connector = 'OR'

        if len(current_substring) > 0:
            current_substring = current_substring.replace(' OR ', '').replace(' AND ', '')
            converted_query += get_query_string(current_substring, current_term_index, current_connector)

        # "human" AND "bias" AND ("annotation" OR "labeling" OR "labelling" OR "tagging")

        # Query: order: -announced_date_first; size: 200; include_cross_list: True; terms: AND title="chatbot" OR "conversational interface"; AND title="deep learning" OR "machine learning"

        #   terms-0-operator=AND&terms-0-term=%22chatbot%22+OR+%22conversational+interface%22&terms-0-field=title&terms-1-operator=AND&terms-1-term=%22deep+learning%22+OR+%22machine+learning%22&terms-1-field=title&classification-computer_science=y&classification-economics=y&classification-eess=y&classification-mathematics=y&classification-physics=y&classification-physics_archives=all&classification-q_biology=y&classification-q_finance=y&classification-statistics=y&classification-include_cross_list=include&date-filter_by=all_dates&date-year=&date-from_date=&date-to_date=&date-date_type=submitted_date&abstracts=show&size=200&order=-announced_date_first

        # terms-0-operator=AND&terms-0-term=%22annotation%22+OR+%22labeling%22+OR+%22labelling%22+OR+%22tagging%22&terms-0-field=all&terms-1-operator=AND&terms-1-term=%22human%22&terms-1-field=all&terms-2-operator=AND&terms-2-term=%22bias%22&terms-2-field=all&classification-computer_science=y&classification-economics=y&classification-eess=y&classification-mathematics=y&classification-physics=y&classification-physics_archives=all&classification-q_biology=y&classification-q_finance=y&classification-statistics=y&classification-include_cross_list=include&date-filter_by=all_dates&date-year=&date-from_date=&date-to_date=&date-date_type=submitted_date&abstracts=show&size=200&order=-announced_date_first


        areas_by_key = {
            'computer_science': ['computer_science'],
            'economics': ['economics', 'q_finance'],
            'engineering': ['eess'],
            'mathematics': ['mathematics', 'statistics'],
            'physics': ['physics'],
            'biology': ['q_biology']
        }

        # date-filter_by=date_range&date-from_date=2017&classification-computer_science=y

        if year_lower_bound != None:
            converted_query += '&date-filter_by=date_range&date-from_date={}'.format(year_lower_bound)
        
        if area_keys != None:
            for area_key in area_keys.split(','):
                areas = areas_by_key.get(area_key.strip(), [])
                for area in areas:
                    converted_query += '&classification-{}=y'.format(area)

        return converted_query

    @staticmethod
    def run(query: str, year_lower_bound: Optional[int], area_keys=Optional[str],only_papers_with_comments=Optional[bool]):

        print('initializing arXiv scrapper')

        BASE_URL = 'https://arxiv.org/search/advanced?advanced=&date-to_date=&date-date_type=submitted_date&abstracts=show&size=200&order=-announced_date_first&classification-include_cross_list=include&'
        
        papers = []
        
        queries = query.split(',')

        for q in queries:

            q = ArxivScrapper._get_converted_query(q, year_lower_bound, area_keys)

            next_page_url = BASE_URL + q
            current_papers = []

            while(True):

                retrieved_papers, next_page_url = ArxivScrapper._get_papers_and_next_page_url(next_page_url, len(current_papers), only_papers_with_comments)

                current_papers += retrieved_papers

                if next_page_url == None:
                    break

            papers += current_papers

        return papers


    @staticmethod
    def _get_papers_and_next_page_url(url, start_count, only_papers_with_comments):

        headers = {'User-Agent': str(UserAgent().chrome)}
        response = Util.try_n(lambda: requests.get(url, headers=headers), 5)

        page = html.fromstring(response.content.decode('UTF-8'))

        if 'no results' in page.xpath('//h1[contains(@class, "title")]')[0].text:
            return [], None
        
        total_of_papers = int(page.xpath('//h1[contains(@class, "title")]')[0].text.strip().split('of')[1].strip().split(' ')[0].replace(',',''))

        next_url = None
        if len(page.xpath('//*[contains(@class, "pagination-next")]')) > 0:
            pagination_url = page.xpath('//*[contains(@class, "pagination-next")]')[0].attrib['href']
            if len(pagination_url) > 0:
                next_url = 'https://arxiv.org' + page.xpath('//*[contains(@class, "pagination-next")]')[0].attrib['href']
        
        article_elements = page.xpath('//*[contains(@class, "arxiv-result")]')
        papers = []

        for i, article_element in enumerate(article_elements):

            try:

                comments = None
                if len(article_element.xpath('.//*[contains(@class, "comments")]//span')) > 0:
                    if 'comments' in article_element.xpath('.//*[contains(@class, "comments")]//span')[0].text.lower():
                        comments = ''.join(article_element.xpath('.//*[contains(@class, "comments")]//span')[1].itertext())

                if only_papers_with_comments and comments == None:
                    continue

                title_element = article_element.xpath('*[contains(@class, "title")]')[0]
                title = ''.join(title_element.itertext()).strip()
                abstract = ''.join(article_element.xpath('.//*[contains(@class, "abstract-full")]')[0].itertext()).strip().split('\n')[0]

                authors_element = article_element.xpath('.//*[contains(@class, "authors")]//a')
                authors = []

                for author_element in authors_element:
                    authors.append(author_element.text)

                dates_string_split = ''.join(article_element.xpath('.//p')[4].itertext()).split(';')

                date = None
                for dates_string in dates_string_split:
                    if 'Submitted' in dates_string:
                        submittion = dates_string.split(' ')
                        day = submittion[1]
                        month = Util.get_month_number_by_string(submittion[2].replace(',', ''))
                        year = submittion[3]
                        date = '{0}-{1}-{2}'.format(year, month, day)
                        break
                
                paper = {
                    'abstract': abstract,
                    'title': title,
                    'authors': authors,
                    'date': date,
                    'first_author': None if len(authors) == 0 else authors[0],
                }
                if comments != None and len(comments) > 0:
                    paper['comments'] = comments

                papers.append({
                    'paper': paper
                })

                print(paper['title'])
                print(paper['date'])

            except Exception as e:
                Util.print_exception(e)

            print('{0}/{1} documents processed'.format(i+1+start_count, total_of_papers))

        return papers, next_url
