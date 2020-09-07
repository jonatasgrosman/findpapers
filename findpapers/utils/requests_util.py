import os
import requests
from fake_useragent import UserAgent
import findpapers.utils.common_util as common_util


DEFAULT_USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/84.0.4147.135 Safari/537.36'


class DefaultSession(requests.Session, metaclass=common_util.ThreadSafeSingletonMetaclass):

    """
    Session class with singleton feature and custom headers config
    """

    def __init__(self, *args, **kwargs):

        super(DefaultSession, self).__init__()

        PROXY = os.getenv('FINDPAPERS_PROXY')

        if PROXY is not None:

            self.proxies = {
                'http': PROXY,
                'https': PROXY
            }

        self.headers.update({'User-Agent': str(UserAgent(fallback=DEFAULT_USER_AGENT).chrome)})

    def request(self, method, url, **kwargs):
        """
        This is just a common request, the only difference is that when proxies are provided
        and a response isn't ok, we'll try one more time without using the proxies
        """

        try:
            response = super().request(method, url, **kwargs)
        except Exception:
            response = requests.Response()
            response.status_code = 500

        if not response.ok and ('http' in self.proxies or 'https' in self.proxies):
            # if the response is not ok using proxies,
            # let's try one more time without using them
            kwargs['proxies'] = {
                'http': None,
                'https': None,
            }
            response = super().request(method, url, **kwargs)

        return response
