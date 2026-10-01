#!/usr/bin/env python3
"""One-time import. Refuses to overwrite the local source of truth."""
import argparse
import csv
import html
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile
from review_files import review_path


def slug(text):
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode().lower()
    return re.sub('[^a-z0-9]+', '-', text).strip('-')


def write_review(path, metadata, body):
    header = '\n'.join(f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in metadata.items())
    path.write_text('---\n' + header + '\n---\n\n' + body + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('export', type=Path)
    args = parser.parse_args()
    root = Path('cinema')
    if (root / 'films.json').exists() or (root / 'reviews').exists():
        raise SystemExit('Cinema content already exists; refusing to overwrite local edits.')
    root.mkdir(exist_ok=True)
    (root / 'reviews').mkdir()
    manifest = json.loads(Path('data/film-matching/confirmed.json').read_text())
    matches = {m['letterboxd_uri']: m for m in manifest['matches']}
    excluded = {m['letterboxd_uri'] for m in manifest['excluded']}
    def read(z, name):
        return list(csv.DictReader(io.StringIO(z.read(name + '.csv').decode('utf-8-sig'))))
    with zipfile.ZipFile(args.export) as z:
        watched, diary, reviews, ratings = [read(z, name) for name in ('watched', 'diary', 'reviews', 'ratings')]
    ratings = {r['Letterboxd URI']: r['Rating'] for r in ratings}
    films, by_title = [], {}
    used_slugs = set()
    short_uri = 'https://boxd.it/6pZO'
    for row in watched:
        uri = row['Letterboxd URI']
        if uri in excluded:
            continue
        match = matches.get(uri, {})
        film_id = 'lb-' + uri.rsplit('/', 1)[-1]
        route = slug(row['Name']) + '-' + row['Year']
        if route in used_slugs:
            route += '-' + film_id
        used_slugs.add(route)
        film = {'id': film_id, 'slug': route, 'title': row['Name'], 'year': row['Year'],
                'watched': True, 'letterboxd_url': uri, 'directors': match.get('directors', []),
                'rating': ratings.get(uri) or None}
        if match:
            film['tmdb'] = {'type': match['tmdb_type'], 'id': match['tmdb_id']}
            film['runtime'] = match.get('runtime')
            film['original_title'] = match.get('original_title')
        if uri == short_uri:
            film['rating'] = None
        films.append(film)
        key = (row['Name'], row['Year'])
        if key in by_title:
            raise ValueError(f'Ambiguous film: {key}')
        by_title[key] = film
    # Use the feature's verified director identity for its related short.
    feature = next(f for f in films if f.get('tmdb', {}).get('id') == 49010)
    next(f for f in films if f['letterboxd_url'] == short_uri)['directors'] = feature['directors']
    viewings = []
    for row in diary:
        film = by_title.get((row['Name'], row['Year']))
        if not film:
            continue
        viewings.append({'id': 'lb-' + row['Letterboxd URI'].rsplit('/', 1)[-1], 'film': film['id'],
                         'date': row['Watched Date'], 'rating': None if film['letterboxd_url'] == short_uri else row['Rating'] or None,
                         'rewatch': row['Rewatch'] == 'Yes', 'letterboxd_url': row['Letterboxd URI']})
    count = 0
    for row in reviews:
        film = by_title.get((row['Name'], row['Year']))
        if not film or film['letterboxd_url'] == short_uri:
            continue
        review_id = 'lb-' + row['Letterboxd URI'].rsplit('/', 1)[-1]
        meta = {'id': review_id, 'film': film['id'], 'title': row['Name'], 'date': row['Date'],
                'watched_date': row['Watched Date'] or None, 'rating': row['Rating'] or None,
                'letterboxd_url': row['Letterboxd URI'], 'draft': False}
        write_review(review_path(root / 'reviews', film['slug'], row['Date']), meta, html.escape(row['Review'].replace('\r\n', '\n'), quote=False))
        count += 1
    first = next(f for f in films if f.get('tmdb', {}).get('id') == 147)
    write_review(root / 'reviews' / 'the-400-blows-1959.md', {'id': 'the-400-blows-first-review', 'film': first['id'],
                 'title': 'The 400 Blows', 'date': '2026-10-01', 'draft': True, 'spoilers': False},
                 '<!-- Write your review here. Set the publication date and change draft to false when ready. -->')
    for name, value in [('films', films), ('viewings', viewings)]:
        (root / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(f'Imported {len(films)} films, {len(viewings)} viewings and {count} reviews; created one draft.')


if __name__ == '__main__':
    main()
