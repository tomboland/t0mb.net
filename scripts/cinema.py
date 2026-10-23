#!/usr/bin/env python3
"""Log films and reviews locally, importing metadata and artwork when needed."""
import argparse
import copy
import datetime
import fcntl
import importlib.util
import json
import os
import sys
from pathlib import Path
import uuid
from review_files import review_path


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


import cinema_data as helpers
ROOT = helpers.ROOT / 'cinema'


def save(name, value):
    (ROOT / (name + '.json')).write_text(json.dumps(helpers.sparse(value), ensure_ascii=False, indent=2) + '\n')


def token_path():
    return Path(os.environ.get('TMDB_TOKEN_FILE', '~/.config/t0mb.net/tmdb-token')).expanduser()


def api_for(args):
    matcher = module('matcher', 'tmdb_api.py')
    path = args.token_file.expanduser()
    token = path.read_text().strip() if path.exists() else ''
    return matcher.API(token, Path('/tmp/t0mb-tmdb-cache'))


def new_film(args, films, people, api):
    film = {'id': 'local-' + uuid.uuid4().hex[:12], 'title': args.title, 'year': args.year,
            'watched': not getattr(args, 'unwatched', False), 'rating': None, 'directors': []}
    if args.tmdb_id:
        data = api.get(f'movie/{args.tmdb_id}', append_to_response='credits')
        film.update(title=args.title or data['title'], year=args.year or data.get('release_date', '')[:4],
                    tmdb={'type': 'movie', 'id': args.tmdb_id}, runtime=data.get('runtime'),
                    original_title=data.get('original_title'),
                    directors=[{'id': p['id'], 'name': p['name']} for p in data['credits']['crew'] if p['job'] == 'Director'])
    else:
        film['directors'] = [{'id': 'local-' + helpers.slug(name), 'name': name} for name in args.director]
    if not film['title']:
        raise ValueError('Provide --title, or use a TMDB entry containing it')
    if getattr(args, 'kind', 'film') != 'film':film['kind']=args.kind
    film['slug'] = helpers.slug(film['title'] + ('-' + str(film['year']) if film.get('year') else ''))
    if any(f['slug'] == film['slug'] for f in films):
        raise ValueError('That title/year slug already exists; use its local ID or resolve the film identity in films.json')
    for person in film['directors'] if args.tmdb_id else []:
        if any(p['id'] == person['id'] for p in people):
            continue
        credits = api.get(f'person/{person["id"]}/movie_credits')
        movies = {p['id']: {'tmdb_id': p['id'], 'title': p['title'], 'year': p.get('release_date', '')[:4]}
                  for p in credits['crew'] if p['job'] == 'Director'}
        people.append(dict(person, filmography=list(movies.values())))
    return film


def import_artwork(film, api):
    """Stage metadata; downloading succeeds before a viewing is written."""
    target = ROOT / 'artwork.json'
    artwork = json.loads(target.read_text()) if target.exists() else {}
    existing = artwork.get(film['id'])
    if existing and existing.get('tmdb') == film.get('tmdb'):
        paths = [record[key] for kind in ('poster', 'backdrop')
                 for record in [existing.get(kind, {})] for key in ('path', 'thumbnail') if record.get(key)]
        if all((ROOT.parent / path.lstrip('/')).is_file() for path in paths):
            return artwork
    importer = module('film_images', 'refresh-artwork.py')
    key, record = importer.fetch(film, api, ROOT.parent / 'images/films/tmdb')
    artwork[key] = record
    return artwork


def make_review(film, date, viewing=None, title=None):
    metadata = {'id': film['slug'] + '-' + date + '-' + uuid.uuid4().hex[:6],
                'film': film['id'], 'title': title or film['title'], 'date': date,
                'draft': True, 'spoilers': False}
    if viewing:
        metadata.update(viewing=viewing['id'], watched_date=viewing['date'], rating=viewing.get('rating'))
    path = review_path(ROOT / 'reviews', film['slug'], date)
    header = '\n'.join(f'{key}: {json.dumps(value, ensure_ascii=False)}' for key, value in metadata.items())
    body = '<!-- Write here; set draft to false when ready. -->'
    return path, '---\n' + header + '\n---\n\n' + body + '\n'


def choose(rows, label):
    if not rows:
        raise ValueError('No matching film found. Try another title or --tmdb-id.')
    print(label)
    for n, row in enumerate(rows, 1):
        print(f"  {n}. {row['title']} ({row.get('year') or row.get('release_date', '')[:4] or 'unknown year'}) [ID: {row['id']}]")
    if not sys.stdin.isatty():
        raise ValueError('Multiple or inexact matches; specify a local film ID or --tmdb-id from the list above')
    try:
        selection = int(input('Choose a film number (q or Ctrl-C to cancel): '))
        if 1 <= selection <= len(rows):
            return rows[selection - 1]
    except (ValueError, EOFError, KeyboardInterrupt):
        pass
    raise ValueError('No film selected; nothing saved')


def resolve_film(args, films, api):
    matcher = module('matcher', 'tmdb_api.py')
    if args.tmdb_id:
        return next((f for f in films if f.get('tmdb') == {'type': 'movie', 'id': args.tmdb_id}), None)
    direct = next((f for f in films if args.film in (f['id'], f['slug'])), None)
    if direct and not getattr(args, 'tmdb', False):
        return direct
    matches = [f for f in films if (not args.year or str(f.get('year', '')) == args.year)
               and matcher.normalized(args.film) in {matcher.normalized(f['title']), matcher.normalized(f.get('original_title') or '')}]
    if matches and not getattr(args, 'tmdb', False):
        return matches[0] if len(matches) == 1 else choose(matches, 'Matching films in your catalogue:')
    candidates = api.search(args.film, args.year)
    exact = [f for f in candidates if matcher.normalized(args.film) in
             {matcher.normalized(f['title']), matcher.normalized(f.get('original_title') or '')}]
    selected = exact[0] if len(exact) == 1 and not sys.stdin.isatty() else choose(exact or candidates, 'Matching films on TMDB:')
    args.tmdb_id = selected['id']
    return next((f for f in films if f.get('tmdb') == {'type': 'movie', 'id': args.tmdb_id}), None)


def catalogue_action(args, films):
    """Resolve a title and stage all changes before saving catalogue/ownership."""
    if args.command == 'seen':
        helpers.validate_rating(args.rating)
    api = api_for(args)
    film = resolve_film(args, films, api)
    people = json.loads((ROOT / 'directors.json').read_text())
    added = film is None
    if added:
        args.title = None
        args.unwatched = True
        film = new_film(args, films, people, api)
        film.pop('watched', None)
        films = films + [film]
    if args.command == 'seen':
        film['watched'] = True
        if args.liked:
            film['liked'] = True
        if args.rating is not None:
            helpers.validate_rating(args.rating)
            film['rating'] = args.rating

    def save_catalogue():
        artwork = import_artwork(film, api) if added and film.get('tmdb') else None
        save('films', films)
        if added:
            save('directors', people)
        if artwork is not None:
            save('artwork', artwork)

    if args.command == 'own':
        import collection as collection_cli
        db = collection_cli.db
        with (ROOT / '.collection.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = db.read(ROOT.parent)
            db.validate(data, ROOT.parent)
            release = copy.copy(args)
            release.command = 'add'
            release.title = args.edition_title or film['title']
            release.film = [film['id']]
            release.year = None
            existing = [e for e in data['editions']
                        if any(c['film'] == film['id'] for c in e.get('contents', []))]
            if existing and not args.new_edition:
                print('Existing editions:')
                labels = db.index(data['labels'])
                for n, edition in enumerate(existing, 1):
                    label = labels.get(edition.get('label_id'), {}).get('name', 'label unknown')
                    print(f"  {n}. {edition['title']} | {label} | {', '.join(edition.get('formats', [])) or 'format unknown'} | {edition['id']}")
                if not sys.stdin.isatty():
                    raise ValueError('Use --new-edition for a different release, or collection.py copy EDITION_ID for another copy.')
                try:
                    answer = input('Enter a number for another copy, n for a new edition, or q to cancel: ').strip().lower()
                    if answer == 'n':
                        release.new_edition = True
                    elif answer.isdigit() and 1 <= int(answer) <= len(existing):
                        release.command = 'copy'
                        release.edition_id = existing[int(answer) - 1]['id']
                        release.notes = ''
                    else:
                        raise ValueError('Cancelled; nothing saved')
                except (EOFError, KeyboardInterrupt):
                    raise ValueError('Cancelled; nothing saved') from None
            result = collection_cli.apply(data, release, db.index(films))
            db.validate(data, ROOT.parent, film_rows=films)
            save_catalogue()
            db.save(data, ROOT.parent)
        print(f"Owned: {film['title']} — {result}. No viewing recorded.")
    else:
        save_catalogue()
        if args.command == 'seen':
            print(f"Marked {film['title']} as watched (date unknown). No dated viewing or ownership added.")
        else:
            print(f"{'Added' if added else 'Already in catalogue'}: {film['title']} [{film['slug']}]")


def title_arguments(parser):
    identity = parser.add_mutually_exclusive_group(required=True)
    identity.add_argument('film', nargs='?', help='Title, local ID or slug; missing titles are looked up on TMDB')
    identity.add_argument('--tmdb-id', type=int, help='Exact TMDB movie ID')
    parser.add_argument('--year', help='Release year')
    parser.add_argument('--tmdb', action='store_true', help='Search TMDB even if a local title matches')
    parser.add_argument('--token-file', type=Path, default=token_path())


def log_film(args, films, viewings):
    datetime.date.fromisoformat(args.date)
    helpers.validate_rating(args.rating)
    api = api_for(args)
    film = resolve_film(args, films, api)
    people = json.loads((ROOT / 'directors.json').read_text())
    added = film is None
    if added:
        args.title = None
        film = new_film(args, films, people, api)
    artwork = import_artwork(film, api) if film.get('tmdb') else None
    viewing = {'id': 'local-' + uuid.uuid4().hex[:12], 'film': film['id'], 'date': args.date,
               'rating': args.rating, 'rewatch': args.rewatch}
    draft = make_review(film, str(datetime.date.today()), viewing) if args.review else None
    # All remote work and input validation have completed before source writes.
    if args.liked:
        film['liked'] = True
    if added or args.liked:
        save('films', films + [film] if added else films)
    if added:
        save('directors', people)
    if artwork is not None:
        save('artwork', artwork)
    save('viewings', viewings + [viewing])
    if draft:
        path, content = draft
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    print(f"Logged {film['title']} ({film.get('year', 'unknown year')}) on {args.date}.")
    if added:
        print('Added film: ' + film['slug'])
    if not film.get('tmdb'):
        print('No TMDB reference on this local film; artwork was left unchanged.')
    if draft:
        print(f'Review draft: {draft[0]}')
    print('Review your changes, commit, then run bash deploy.sh when ready.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name, description in (
        ('add', 'Add a film to the catalogue without asserting watched status or ownership'),
        ('seen', 'Mark a film watched when the viewing date is unknown'),
        ('own', 'Find a film and add a physical release and owned copy'),
    ):
        action = commands.add_parser(name, help=description)
        title_arguments(action)
        if name == 'seen':
            action.add_argument('--liked', action='store_true')
            action.add_argument('--rating', help='Optional overall film rating, 0.5–5 in half steps')
        if name == 'own':
            import collection as collection_cli
            collection_cli.edition_args(action)
            action.add_argument('--edition-title', help='Release title if different from the film title')
            action.add_argument('--new-edition', action='store_true')
            action.add_argument('--cut')
            action.add_argument('--coverage')
            action.add_argument('--location')
            action.add_argument('--condition', choices=['unknown', 'good', 'damaged', 'faulty', 'missing_disc'], default='unknown')
    add = commands.add_parser('film', help='Add a film manually or using a TMDB movie ID')
    add.add_argument('--unwatched', action='store_true', help='Add catalogue metadata without asserting a viewing, e.g. for an owned disc')
    add.add_argument('--kind', choices=['film','tv_series','tv_film','documentary','concert','short','calibration'], default='film')
    add.add_argument('--title')
    add.add_argument('--year')
    add.add_argument('--director', action='append', default=[])
    add.add_argument('--tmdb-id', type=int)
    add.add_argument('--token-file', type=Path, default=token_path())
    log = commands.add_parser('log', help='Log a viewing, implicitly adding the film and its artwork')
    identity = log.add_mutually_exclusive_group(required=True)
    identity.add_argument('film', nargs='?', help='Film title, local ID or slug')
    identity.add_argument('--tmdb-id', type=int, help='Exact TMDB movie ID')
    log.add_argument('--year', help='Release year to disambiguate a title')
    log.add_argument('--tmdb', action='store_true', help='Search TMDB even if a local title matches')
    log.add_argument('--date', default=str(datetime.date.today()), help='Viewing date; defaults to today')
    log.add_argument('--rating', help='Optional rating from 0.5 to 5, in half steps')
    log.add_argument('--rewatch', action='store_true')
    log.add_argument('--liked', action='store_true', help='Mark the film as liked; omission preserves its current like status')
    log.add_argument('--review', action='store_true', help='Create a linked Markdown review draft')
    log.add_argument('--token-file', type=Path, default=token_path(),
                     help='TMDB token file; defaults to TMDB_TOKEN_FILE or ~/.config/t0mb.net/tmdb-token')
    watch = commands.add_parser('watch', help='Log a dated viewing; rating is optional')
    watch.add_argument('film', help='Local film ID or slug')
    watch.add_argument('--date', required=True)
    watch.add_argument('--rating')
    watch.add_argument('--rewatch', action='store_true')
    watch.add_argument('--liked', action='store_true', help='Mark the film as liked; omission preserves its current like status')
    review = commands.add_parser('review', help='Create an unpublished Markdown review')
    review.add_argument('film', help='Local film ID or slug')
    review.add_argument('--title')
    review.add_argument('--date', default=str(datetime.date.today()))
    review.add_argument('--viewing', help='Optional local viewing ID')
    tag = commands.add_parser('tag', help='Add or remove film tags')
    tag.add_argument('film', help='Local film ID or slug')
    tag.add_argument('tags', nargs='+', help='Quote tags containing spaces')
    tag.add_argument('--remove', action='store_true', help='Remove these tags')
    search = commands.add_parser('search', help='Find local films, or search TMDB with --tmdb')
    search.add_argument('query')
    search.add_argument('--tmdb', action='store_true', help='Search TMDB movies without adding or logging anything')
    search.add_argument('--year', help='Release year to narrow the search')
    search.add_argument('--token-file', type=Path, default=token_path())
    args = parser.parse_args()
    films = json.loads((ROOT / 'films.json').read_text())
    if args.command == 'search':
        if args.tmdb:
            try:
                rows = api_for(args).search(args.query, args.year)
            except (ValueError, OSError, RuntimeError) as error:
                parser.error(f'{error}\nCheck TMDB access; set TMDB_TOKEN_FILE or use --token-file PATH.')
            for row in rows:
                local = next((f for f in films if f.get('tmdb') == {'type': 'movie', 'id': row['id']}), None)
                suffix = f" | already in catalogue: {local['slug']}" if local else ''
                print(f"{row['id']} | {row['title']} | {row.get('release_date', '')[:4] or '?'}{suffix}")
            if rows:
                print('Add a result without recording a viewing: python3 scripts/cinema.py film --tmdb-id ID --unwatched')
            else:
                print('No TMDB films matched. Try another title or omit --year.')
        else:
            from tmdb_api import normalized
            query = normalized(args.query)
            matches = [film for film in films
                       if (not args.year or str(film.get('year', '')) == args.year)
                       and any(query in normalized(str(film.get(k) or ''))
                               for k in ('title', 'original_title', 'id', 'slug'))]
            for film in matches:
                print(f"{film['id']} | {film['title']} | {film.get('year', '?')} | {film['slug']}")
            if not matches:
                print('No local films matched. Search TMDB with: cinema.py search "TITLE" --tmdb')
        return
    viewings = json.loads((ROOT / 'viewings.json').read_text())
    if args.command in ('film', 'log', 'add', 'seen', 'own'):
        try:
            if args.tmdb_id is not None and args.tmdb_id <= 0:
                raise ValueError('--tmdb-id must be a positive movie ID')
            if args.command in ('add', 'seen', 'own'):
                catalogue_action(args, films)
            elif args.command == 'log':
                log_film(args, films, viewings)
            else:
                if args.tmdb_id and any(f.get('tmdb') == {'type': 'movie', 'id': args.tmdb_id} for f in films):
                    raise ValueError('That TMDB movie is already in the catalogue; use log to record a viewing')
                api = api_for(args) if args.tmdb_id else None
                people = json.loads((ROOT / 'directors.json').read_text())
                film = new_film(args, films, people, api)
                artwork = import_artwork(film, api) if args.tmdb_id else None
                save('films', films + [film])
                save('directors', people)
                if artwork is not None:
                    save('artwork', artwork)
                print(film['id'], film['slug'])
        except (ValueError, OSError, RuntimeError) as error:
            message = str(error)
            if isinstance(error, RuntimeError) and message.startswith('TMDB'):
                message += '\nCheck TMDB access; set TMDB_TOKEN_FILE or use --token-file PATH.'
            parser.error(message)
        return
    film = next((f for f in films if args.film in (f['id'], f['slug'])), None)
    if not film:
        parser.error('Film not found; use its ID or slug from cinema/films.json')
    if args.command == 'tag':
        try:
            current = helpers.normalise_tags(film.get('tags', []))
            requested = helpers.normalise_tags(args.tags)
        except ValueError as error:
            parser.error(str(error))
        if args.remove:
            removing = {tag.casefold() for tag in requested}
            film['tags'] = [tag for tag in current if tag.casefold() not in removing]
        else:
            film['tags'] = helpers.normalise_tags(current + requested)
        save('films', films)
        print(film['title'] + ': ' + (', '.join(film['tags']) or 'no tags'))
        return
    datetime.date.fromisoformat(args.date)
    if args.command == 'watch':
        helpers.validate_rating(args.rating)
        viewing = {'id': 'local-' + uuid.uuid4().hex[:12], 'film': film['id'], 'date': args.date,
                   'rating': args.rating, 'rewatch': args.rewatch}
        viewings.append(viewing)
        if args.liked:
            film['liked'] = True
            save('films', films)
        save('viewings', viewings)
        print(viewing['id'])
    else:
        viewing = None
        if args.viewing:
            viewing = next((v for v in viewings if v['id'] == args.viewing and v['film'] == film['id']), None)
            if not viewing:
                parser.error('Viewing not found for this film')
        path, content = make_review(film, args.date, viewing, args.title)
        path.write_text(content)
        print(path.relative_to(helpers.ROOT))



if __name__ == '__main__':
    main()
