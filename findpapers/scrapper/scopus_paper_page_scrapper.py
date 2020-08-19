import util as Util
import re
import requests
from fake_useragent import UserAgent
from lxml import html
import json

class ScopusPaperPageScrapper():

    @staticmethod
    def run(url, partial_result):

        response = Util.try_n(lambda: requests.get(url, headers={'User-Agent': str(UserAgent().chrome)}), 5)
        page = html.fromstring(response.content.decode('UTF-8'))

        try:
            partial_result['paper']['abstract'] = None
            result = page.xpath('//section[@id="abstractSection"]//p//text()[normalize-space()]')
            result = re.sub('\xa0', ' ', ''.join(result)).strip()
            partial_result['paper']['abstract'] = result
        except Exception as e:
            print(e)

        try:
            partial_result['paper']['authors'] = None
            result = page.xpath('//*[@id="authorlist"]/ul/li/span[@class="previewTxt"]')

            authors = []
            for author in result:
                authors.append(author.text)

            partial_result['paper']['authors'] = authors
        except Exception as e:
            print(e)
        
        try:
            partial_result['paper']['keywords'] = None
            result = page.xpath('//*[@id="authorKeywords"]/span')

            keywords = []
            for keyword in result:
                keywords.append(keyword.text)

            partial_result['paper']['keywords'] = keywords
        except Exception as e:
            print(e)
        
        try:
            partial_result['paper']['scopus_values'] = {
                'topics': [],
                'prominence_percentile': None
            }
            result = page.xpath('//*[@class="sciTopicsVal displayNone"]')
            value = json.loads(result[0].text)

            partial_result['paper']['scopus_values']['topics'] = value['topic']['name'].split('; ')
            partial_result['paper']['scopus_values']['prominence_percentile'] = value['topic']['prominencePercentile']

        except Exception as e:
            print(e)

        return partial_result
