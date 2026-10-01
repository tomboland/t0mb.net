#!/usr/bin/env python3
"""Explicit, optional metadata refresh; normal site builds never use the network."""
import argparse
import concurrent.futures
import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location('matcher', Path(__file__).with_name('match-tmdb.py'))
matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(matcher)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--token-file', type=Path, required=True)
    args = parser.parse_args()
    api = matcher.API(args.token_file.read_text().strip(), Path('/tmp/t0mb-tmdb-cache'))
    films = json.loads(Path('cinema/films.json').read_text())
    people = {p['id']: p for film in films for p in film['directors'] if isinstance(p['id'], int)}
    def fetch(person):
        credits = api.get(f"person/{person['id']}/movie_credits")
        movies = {r['id']: {'tmdb_id': r['id'], 'title': r['title'], 'year': r.get('release_date', '')[:4]} for r in credits['crew'] if r['job'] == 'Director'}
        return dict(person, filmography=sorted(movies.values(), key=lambda r: (r['year'], r['title'])))
    result = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for person in pool.map(fetch, people.values()):
            result.append(person)
            if len(result) % 50 == 0:
                print(f"Saved metadata for {len(result)}/{len(people)} directors", flush=True)
    path = Path('cinema/directors.json')
    path.parent.mkdir(exist_ok=True)
    # Preserve any manually maintained local director records.
    if path.exists():
        result += [p for p in json.loads(path.read_text()) if not isinstance(p['id'], int)]
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Fetched {len(result)} director filmographies')


if __name__ == '__main__':
    main()
