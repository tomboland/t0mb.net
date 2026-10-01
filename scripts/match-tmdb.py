#!/usr/bin/env python3
"""Match watched.csv to TMDB, caching API evidence and retaining uncertain candidates.

Usage: python3 scripts/match-tmdb.py EXPORT.zip --token-file /private/token
Credentials are sent only to TMDB in the Authorization header, never saved in output.
"""
import argparse
import concurrent.futures
import csv
import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile


def normalized(title):
    return re.sub(r"[^\w]", "", unicodedata.normalize("NFKD", title).casefold())


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


def compact(movie):
    return {k: movie.get(k) for k in ('id', 'title', 'original_title', 'release_date')}


def match_film(film, known, api):
    uri, title, year = film['Letterboxd URI'], film['Name'], film['Year']
    base = {'letterboxd_uri': uri, 'title': title, 'year': year}
    media_type = known.get(uri, {}).get('tmdb_type', 'movie')
    if uri in known:
        append = 'credits' if media_type == 'movie' else 'aggregate_credits,external_ids'
        try:
            selected = api.get(media_type + '/' + str(known[uri]['tmdb_id']), append_to_response=append)
        except RuntimeError as error:
            if 'HTTP 404 ' not in str(error):
                raise
            return dict(base, status='tmdb_unavailable', historical_tmdb_type=media_type,
                        historical_tmdb_id=known[uri]['tmdb_id'], source_url=known[uri]['source_url'],
                        note='Letterboxd links to this TMDB ID, but the TMDB API returns 404. Keep the local entry; do not substitute a different film.')
        method = known[uri].get('status', 'letterboxd_link_api_checked')
        source = known[uri]['source_url']
    else:
        results = api.search(title, year)
        exact = [r for r in results if r.get('release_date', '')[:4] == year and normalized(title) in {normalized(r['title']), normalized(r['original_title'])}]
        if len(exact) != 1:
            if not exact:
                results = api.search(title)
            return dict(base, status='needs_review', candidates=[compact(r) for r in results])
        selected = api.get('movie/' + str(exact[0]['id']), append_to_response='credits')
        method = 'unique_exact_title_year'
        source = 'https://api.themoviedb.org/3/search/movie?' + urllib.parse.urlencode({'query': title, 'primary_release_year': year})
    if media_type == 'movie':
        directors = [{'id': p['id'], 'name': p['name']} for p in selected['credits']['crew'] if p['job'] == 'Director']
    else:
        directors = [{'id': p['id'], 'name': p['name']} for p in selected['aggregate_credits']['crew'] if any(j['job'] == 'Director' for j in p['jobs'])]
    return dict(base, tmdb_type=media_type, tmdb_id=selected['id'], status=method, source_url=source,
                checked_on=str(datetime.date.today()), tmdb_title=selected.get('title', selected.get('name')),
                original_title=selected.get('original_title', selected.get('original_name')), release_date=selected.get('release_date', selected.get('first_air_date')),
                directors=directors, imdb_id=selected.get('imdb_id', selected.get('external_ids', {}).get('imdb_id')), runtime=selected.get('runtime'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--cache', type=Path, default=Path('/tmp/t0mb-tmdb-cache'))
    parser.add_argument('--output', type=Path, default=Path('data/film-matching/tmdb-results.json'))
    args = parser.parse_args()
    manifest = json.loads(Path('data/film-matching/confirmed.json').read_text())
    excluded = {r['letterboxd_uri'] for r in manifest.get('excluded', [])}
    known = {r['letterboxd_uri']: r for r in manifest['matches']}
    resolutions = Path('data/film-matching/resolved-links.json')
    if resolutions.exists():
        known.update({r['letterboxd_uri']: r for r in json.loads(resolutions.read_text())})
    with zipfile.ZipFile(args.export) as archive:
        films = list(csv.DictReader(io.StringIO(archive.read('watched.csv').decode('utf-8-sig'))))
    films = [r for r in films if r['Letterboxd URI'] not in excluded]
    api = API(args.token_file.read_text().strip(), args.cache)
    # Fail fast on authentication/network errors before launching the full batch.
    api.get('movie/147', append_to_response='credits')
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(match_film, film, known, api): film for film in films}
        for future in concurrent.futures.as_completed(futures):
            film = futures[future]
            try:
                results.append(future.result())
            except Exception as error:
                results.append({'letterboxd_uri': film['Letterboxd URI'], 'title': film['Name'], 'year': film['Year'], 'status': 'error', 'error': str(error)})
            if len(results) % 50 == 0:
                print(f'Processed {len(results)}/{len(films)}', flush=True)
    results.sort(key=lambda r: (r['title'].casefold(), r['year']))
    args.output.write_text(json.dumps({'excluded': manifest.get('excluded', []), 'results': results}, ensure_ascii=False, indent=2) + '\n')
    from collections import Counter
    print(json.dumps(dict(Counter(r['status'] for r in results)), indent=2))


if __name__ == '__main__':
    main()
