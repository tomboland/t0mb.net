#!/usr/bin/env python3
"""Add local films, diary entries and review drafts without editing generated files."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import uuid
from review_files import review_path


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


builder = module('builder', 'build-films.py')
ROOT = builder.ROOT / 'cinema'


def save(name, value):
    (ROOT / (name + '.json')).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('film', help='Add a film manually or using a TMDB movie ID')
    add.add_argument('--title')
    add.add_argument('--year')
    add.add_argument('--director', action='append', default=[])
    add.add_argument('--tmdb-id', type=int)
    add.add_argument('--token-file', type=Path)
    watch = commands.add_parser('watch', help='Log a dated viewing; rating is optional')
    watch.add_argument('film', help='Local film ID or slug')
    watch.add_argument('--date', required=True)
    watch.add_argument('--rating')
    watch.add_argument('--rewatch', action='store_true')
    review = commands.add_parser('review', help='Create an unpublished Markdown review')
    review.add_argument('film', help='Local film ID or slug')
    review.add_argument('--title')
    review.add_argument('--date', default=str(datetime.date.today()))
    review.add_argument('--viewing', help='Optional local viewing ID')
    tag = commands.add_parser('tag', help='Add or remove film tags')
    tag.add_argument('film', help='Local film ID or slug')
    tag.add_argument('tags', nargs='+', help='Quote tags containing spaces')
    tag.add_argument('--remove', action='store_true', help='Remove these tags')
    args = parser.parse_args()
    films = json.loads((ROOT / 'films.json').read_text())
    viewings = json.loads((ROOT / 'viewings.json').read_text())
    if args.command == 'film':
        film = {'id': 'local-' + uuid.uuid4().hex[:12], 'title': args.title, 'year': args.year,
                'watched': True, 'rating': None, 'directors': []}
        if args.tmdb_id:
            if not args.token_file:
                parser.error('--tmdb-id requires --token-file')
            if any(f.get('tmdb', {}).get('id') == args.tmdb_id and f['tmdb']['type'] == 'movie' for f in films):
                parser.error('That TMDB movie is already in the catalogue')
            matcher = module('matcher', 'match-tmdb.py')
            api = matcher.API(args.token_file.read_text().strip(), Path('/tmp/t0mb-tmdb-cache'))
            data = api.get(f'movie/{args.tmdb_id}', append_to_response='credits')
            film.update(title=args.title or data['title'], year=args.year or data['release_date'][:4],
                        tmdb={'type': 'movie', 'id': args.tmdb_id}, runtime=data.get('runtime'), original_title=data['original_title'],
                        directors=[{'id': p['id'], 'name': p['name']} for p in data['credits']['crew'] if p['job'] == 'Director'])
            people = json.loads((ROOT / 'directors.json').read_text())
            for person in film['directors']:
                if any(p['id'] == person['id'] for p in people):
                    continue
                credits = api.get(f'person/{person["id"]}/movie_credits')
                movies = {p['id']: {'tmdb_id': p['id'], 'title': p['title'], 'year': p.get('release_date', '')[:4]} for p in credits['crew'] if p['job'] == 'Director'}
                people.append(dict(person, filmography=list(movies.values())))
            save('directors', people)
        else:
            film['directors'] = [{'id': 'local-' + builder.slug(name), 'name': name} for name in args.director]
        if not film['title'] or not film['year']:
            parser.error('Provide --title and --year, or use a TMDB entry containing them')
        film['slug'] = builder.slug(film['title'] + '-' + film['year'])
        if any(f['slug'] == film['slug'] for f in films):
            parser.error('That title/year slug already exists; edit films.json for a distinct version')
        films.append(film)
        save('films', films)
        print(film['id'], film['slug'])
        return
    film = next((f for f in films if args.film in (f['id'], f['slug'])), None)
    if not film:
        parser.error('Film not found; use its ID or slug from cinema/films.json')
    if args.command == 'tag':
        try:
            current = builder.normalise_tags(film.get('tags', []))
            requested = builder.normalise_tags(args.tags)
        except ValueError as error:
            parser.error(str(error))
        if args.remove:
            removing = {tag.casefold() for tag in requested}
            film['tags'] = [tag for tag in current if tag.casefold() not in removing]
        else:
            film['tags'] = builder.normalise_tags(current + requested)
        save('films', films)
        print(film['title'] + ': ' + (', '.join(film['tags']) or 'no tags'))
        return
    datetime.date.fromisoformat(args.date)
    if args.command == 'watch':
        builder.rating(args.rating)
        viewing = {'id': 'local-' + uuid.uuid4().hex[:12], 'film': film['id'], 'date': args.date,
                   'rating': args.rating, 'rewatch': args.rewatch}
        viewings.append(viewing)
        save('viewings', viewings)
        print(viewing['id'])
    else:
        review_id = film['slug'] + '-' + args.date + '-' + uuid.uuid4().hex[:6]
        metadata = {'id': review_id, 'film': film['id'], 'title': args.title or film['title'], 'date': args.date, 'draft': True, 'spoilers': False}
        if args.viewing:
            viewing = next((v for v in viewings if v['id'] == args.viewing and v['film'] == film['id']), None)
            if not viewing:
                parser.error('Viewing not found for this film')
            metadata.update(viewing=viewing['id'], watched_date=viewing['date'], rating=viewing.get('rating'))
        path = review_path(ROOT / 'reviews', film['slug'], args.date)
        header = '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in metadata.items())
        path.write_text('---\n' + header + '\n---\n\n<!-- Write here; set draft to false when ready. -->\n')
        print(path.relative_to(builder.ROOT))


if __name__ == '__main__':
    main()
