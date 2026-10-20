"""Shared TMDB client for everyday catalogue and artwork commands."""
import re
import unicodedata
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

class API:
    def __init__(self, token, cache):
        self.token = token
        self.cache = cache
        cache.mkdir(parents=True, exist_ok=True)

    def get(self, path, **params):
        url = 'https://api.themoviedb.org/3/' + path + '?' + urllib.parse.urlencode(params)
        target = self.cache / (hashlib.sha256(url.encode()).hexdigest() + '.json')
        if target.exists():
            return json.loads(target.read_text())
        for attempt in range(4):
            try:
                request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'})
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.load(response)
                target.write_text(json.dumps(data, ensure_ascii=False))
                return data
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise RuntimeError(f'TMDB HTTP {error.code} for {path}') from None
                time.sleep(min(30, max(1, int(error.headers.get('Retry-After', 2 ** attempt)))))
            except urllib.error.URLError:
                if attempt == 3:
                    raise RuntimeError(f'TMDB network failure for {path}') from None
                time.sleep(2 ** attempt)

    def search(self, title, year=None):
        params = {'query': title, 'include_adult': 'true', 'language': 'en-US'}
        if year:
            params['primary_release_year'] = year
        result = self.get('search/movie', **params)
        rows = result['results']
        for page in range(2, min(result['total_pages'], 500) + 1):
            rows += self.get('search/movie', page=page, **params)['results']
        return rows



def normalized(title):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKD", title).casefold())
