import itertools
import json
import os
import util as Util

PAPERS_FILE_PATH = os.path.dirname(os.path.abspath(__file__)) + '/data/result.json'

with open(PAPERS_FILE_PATH, 'r') as fp:
    data = json.load(fp)

threshold = 0.2

print('processing data...')

values = list(itertools.combinations(data, 2))

for i, pair in enumerate(values):

    # print('{0}/{1}'.format(i, len(values)))

    paper_1 = pair[0]
    paper_2 = pair[1]

    title_1 = paper_1['paper']['title']
    max_distance = int(len(title_1) * threshold)
    if paper_1 != paper_2:
        title_2 = paper_2['paper']['title']

        title_distance = Util.levenshtein_distance(title_1, title_2)
        if title_distance <= max_distance:
            print('Possible duplication with edit distance of {0} and threshold of {1}'.format(title_distance, max_distance))
            print('{0} - {1} - {2}'.format(title_1, paper_1['paper']['date'], paper_1['paper']['first_author']))
            print('{0} - {1} - {2}'.format(title_2, paper_2['paper']['date'], paper_2['paper']['first_author']))
            print('\n')