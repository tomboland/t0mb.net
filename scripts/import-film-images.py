#!/usr/bin/env python3
"""Explicit TMDB artwork import; builds and visitors never contact TMDB."""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time
import tempfile
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('matcher', Path(__file__).with_name('match-tmdb.py'))
matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matcher)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file', type=Path, help='Needed for metadata not already cached')
    p.add_argument('--cache', type=Path, default=Path('/tmp/t0mb-tmdb-cache'))
    p.add_argument('--film', help='Import only this film slug or local ID')
    args = p.parse_args()
    api = matcher.API(args.token_file.read_text().strip() if args.token_file else '', args.cache)
    films = json.loads((ROOT / 'cinema/films.json').read_text())
    target = ROOT / 'cinema/artwork.json'
    artwork = json.loads(target.read_text()) if target.exists() else {}
    output = ROOT / 'images/films/tmdb'
    output.mkdir(parents=True, exist_ok=True)

    def download(path, size):
        if not re.fullmatch(r'/[A-Za-z0-9._-]+\.(jpg|png)', path):
            raise ValueError('Unexpected TMDB image path')
        url = 'https://image.tmdb.org/t/p/' + size + path
        filename = size + '-' + hashlib.sha256(url.encode()).hexdigest()[:20] + Path(path).suffix
        dest = output / filename
        if not dest.exists():
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(url, timeout=40) as response:
                        data = response.read()
                    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n')):
                        raise ValueError('Response was not a JPEG or PNG')
                    with tempfile.NamedTemporaryFile(dir=output, suffix='.tmp', delete=False) as handle:
                        handle.write(data)
                        temp = Path(handle.name)
                    temp.chmod(0o644)
                    temp.replace(dest)
                    break
                except (urllib.error.URLError, TimeoutError):
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
        return '/images/films/tmdb/' + filename

    def fetch(film):
        t = film.get('tmdb')
        if not t:
            return film['id'], {}
        # Reuse the same cached detail request as the original catalogue import.
        details = api.get(t['type'] + '/' + str(t['id']), append_to_response='credits' if t['type'] == 'movie' else 'aggregate_credits,external_ids')
        record = {'tmdb': t}
        if details.get('poster_path'):
            record['poster'] = {'path': download(details['poster_path'], 'w500'),
                                'thumbnail': download(details['poster_path'], 'w185'),
                                'alt': 'Poster for ' + film['title'], 'source_path': details['poster_path']}
        if details.get('backdrop_path'):
            record['backdrop'] = {'path': download(details['backdrop_path'], 'w780'),
                                  'alt': 'Backdrop for ' + film['title'], 'source_path': details['backdrop_path']}
        return film['id'], record

    selected = [f for f in films if not args.film or args.film in (f['id'], f['slug'])]
    if not selected:
        p.error('Film not found')
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(fetch, f): f for f in selected}
        for n, future in enumerate(concurrent.futures.as_completed(futures), 1):
            try:
                key, record = future.result()
                artwork[key] = record
            except Exception as error:
                failures.append(futures[future]['slug'])
                print(f'Failed: {failures[-1]}: {type(error).__name__}', flush=True)
            if n % 50 == 0:
                print(f'Processed {n}/{len(selected)} films', flush=True)
    target.write_text(json.dumps(artwork, ensure_ascii=False, indent=2, sort_keys=True) + '\n')
    print(f'Saved artwork metadata; {len(failures)} failures. Existing image overrides were untouched.')
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
