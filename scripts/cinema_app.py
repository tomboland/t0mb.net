"""Terminal application and optional command interface over cinema_service."""
import argparse
import datetime
import os
from pathlib import Path

from cinema_data import ROOT
from cinema_service import Catalogue
from tmdb_api import API, normalized
import cinema_tui as ui


def api_from_file(path):
    path = path.expanduser()
    return API(path.read_text().strip(), Path('/tmp/t0mb-tmdb-cache')) if path.exists() else None


def parser():
    result = argparse.ArgumentParser(description='Browse, curate and review your local film collection.')
    result.add_argument('--root',type=Path,default=ROOT,help=argparse.SUPPRESS)
    commands = result.add_subparsers(dest='command')
    commands.add_parser('browse',help='Open the local database browser (default)')
    search = commands.add_parser('search',help='Search TMDB; select with arrow keys')
    search.add_argument('query')
    search.add_argument('--local',action='store_true',help='Search offline')
    search.add_argument('--plain',action='store_true',help='Print results instead of opening the selector')
    search.add_argument('--year')
    for name in ('own','review','log','add','seen'):
        action = commands.add_parser(name,help={'own':'Add a disc','review':'Log a viewing and write a review in VISUAL','log':'Log a viewing, optionally with a review','add':'Add catalogue metadata','seen':'Mark watched with no viewing date'}[name])
        identity = action.add_mutually_exclusive_group(required=True)
        identity.add_argument('film',nargs='?',help='Local ID/slug or TMDB title search')
        identity.add_argument('--tmdb-id',type=int)
        action.add_argument('--year')
        if name == 'own':
            action.add_argument('--format',action='append',dest='formats',choices=sorted(ui.db.FORMATS))
            for field in ('title','label','cut','location','notes','packaging','barcode'):
                action.add_argument('--edition-title' if field == 'title' else '--'+field,dest=field,default='')
            action.add_argument('--new-edition',action='store_true')
        if name in ('review','log','seen'):
            action.add_argument('--rating',default='')
            action.add_argument('--liked',action='store_true')
        if name in ('review','log'):
            action.add_argument('--date',default=str(datetime.date.today()))
            action.add_argument('--rewatch',action='store_true')
        if name == 'log': action.add_argument('--review',action='store_true')
    manual = commands.add_parser('film',help='Add a manual catalogue record')
    manual.add_argument('--title',required=True)
    manual.add_argument('--year',default='')
    manual.add_argument('--director',action='append',default=[])
    manual.add_argument('--kind',default='film',choices=sorted(ui.db.KINDS))
    manual.add_argument('--unwatched',action='store_true')
    tag = commands.add_parser('tag',help='Add or remove local film tags')
    tag.add_argument('film')
    tag.add_argument('tags',nargs='+')
    tag.add_argument('--remove',action='store_true')
    for action in (search, *[commands.choices[n] for n in ('own','review','log','add','seen')]):
        action.add_argument('--token-file',type=Path,default=Path(os.environ.get('TMDB_TOKEN_FILE','~/.config/t0mb.net/tmdb-token')).expanduser())
    return result


def resolve(service, args):
    if args.tmdb_id is not None:
        if args.tmdb_id <= 0: raise ValueError('TMDB ID must be positive')
        return {'id':args.tmdb_id}
    films = service.read('films')
    direct = next((f for f in films if args.film in (f['id'],f['slug'])),None)
    if direct: return direct['id']
    matches = [f for f in films if normalized(f['title']) == normalized(args.film) and (not args.year or str(f.get('year')) == args.year)]
    if len(matches) == 1: return matches[0]['id']
    rows = service.search(args.film)
    if args.year: rows = [r for r in rows if r.get('release_date','')[:4] == args.year]
    if ui.interactive():
        selected = ui.pick_movie(service.api,rows,films,service.read('collection'))
        return selected
    raise ValueError('Use --tmdb-id or a local ID/slug for unattended commands. Search with --plain to find IDs.')


def main(argv=None, root=None):
    argparser = parser()
    if root is not None: argparser.set_defaults(root=root)
    args = argparser.parse_args(argv)
    service = Catalogue(args.root, api_from_file(args.token_file) if hasattr(args,'token_file') else None)
    try:
        if args.command in (None,'browse'):
            if not ui.interactive(): raise ValueError('The browser needs an interactive terminal.')
            service.api = api_from_file(Path(os.environ.get('TMDB_TOKEN_FILE','~/.config/t0mb.net/tmdb-token')))
            return ui.browse(service)
        if args.command == 'search':
            if args.local:
                query = normalized(args.query)
                rows = [f for f in service.read('films') if any(query in normalized(str(f.get(k,''))) for k in ('title','original_title','slug','id')) and (not args.year or str(f.get('year')) == args.year)]
                if ui.interactive() and not args.plain:
                    while True:
                        selected = ui.select('Local films',rows,ui.movie_label)
                        if selected is None: return
                        ui.actions(service,selected['id'])
            else:
                if ui.interactive() and not args.plain: return ui.search(service,args.query,args.year)
                rows = service.search(args.query)
                if args.year: rows = [r for r in rows if r.get('release_date','')[:4] == args.year]
            for row in rows:
                print(f"{row['id']} | {row['title']} | {row.get('year') or row.get('release_date','')[:4] or '?'} | {row.get('slug','')}")
            if not rows: print('No matching films.')
            return
        if args.command == 'film':
            print(service.add_film(title=args.title,year=args.year,directors=args.director,kind=args.kind,unwatched=args.unwatched))
            return
        if args.command == 'tag':
            print(service.tag(args.film,args.tags,args.remove))
            return
        selection = resolve(service,args)
        if selection is None: return
        if args.command == 'own':
            if not args.formats:
                if not ui.interactive(): raise ValueError('Specify --format for unattended ownership commands.')
                return ui.own(service,selection)
            if service.existing_editions(selection) and not args.new_edition:
                raise ValueError('Existing editions found. Use the browser to add another copy, or --new-edition for a different release.')
            print(service.add_owned(selection,formats=args.formats,**{k:getattr(args,k) for k in ('title','label','cut','location','notes','packaging','barcode')}))
        elif args.command in ('review','log'):
            from cinema_editor import edit_review
            editor = edit_review if args.command == 'review' or args.review else None
            print(service.log_review(selection,date=args.date,rating=args.rating,rewatch=args.rewatch,liked=args.liked,editor=editor) or 'Cancelled; nothing saved.')
        elif args.command == 'seen': print(service.mark_seen(selection,rating=args.rating,liked=args.liked))
        else: print(service.add_film(selection))
    except (ValueError,OSError,RuntimeError) as error:
        argparser.error(str(error))
    except (KeyboardInterrupt,EOFError):
        print('\nCancelled.')
