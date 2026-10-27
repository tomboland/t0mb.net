"""Small terminal views over the existing catalogue operations; no server required."""
import curses
import collection_data as db
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor


def interactive():
    return sys.stdin.isatty() and sys.stdout.isatty()


def select(title, rows, label=str, detail=lambda row: '', enrich=None, state=None, allow_new=False):
    """Filterable arrow-key picker. Return the original selected object or None."""
    if not interactive():
        raise ValueError('Interactive selection needs a terminal; supply an explicit ID instead.')
    pool = ThreadPoolExecutor(max_workers=4) if enrich else None
    futures = {id(row): pool.submit(enrich, row.copy()) for row in rows} if pool else {}
    new_entry, clear_entry = object(), object()
    extras = {}
    state = state if state is not None else {}
    def screen(win):
        curses.curs_set(0)
        win.timeout(100)
        query, position = state.get('query', ''), state.get('position', 0)
        while True:
            for key, future in list(futures.items()):
                if future.done():
                    try:
                        extras[key] = future.result()
                    except Exception:
                        extras[key] = {'detail_error': 'Details unavailable'}
                    del futures[key]
            matches = [r for r in rows if query.casefold() in label(dict(r, **extras.get(id(r), {})) if isinstance(r, dict) else r).casefold()]
            if allow_new:
                if query.strip() and not any(query.strip().casefold() == str(r).casefold() for r in rows):
                    matches.append(new_entry)
                elif not query:
                    matches.append(clear_entry)
            position = min(position, max(0, len(matches)-1))
            win.erase()
            height, width = win.getmaxyx()
            def line(y, value, attr=0):
                if 0 <= y < height-1:
                    try:
                        win.addnstr(y, 0, value.replace('\n', ' '), max(0, width-1), attr)
                    except curses.error:
                        pass
            line(0, title, curses.A_BOLD)
            line(1, 'Type to filter: ' + query)
            visible = max(1, height-7)
            start = max(0, position-visible+1)
            for i, row in enumerate(matches[start:start+visible], start):
                value = dict(row, **extras.get(id(row), {})) if isinstance(row, dict) else row
                caption = ('Use new value: ' + query.strip() if row is new_entry else
                           'Clear value' if row is clear_entry else label(value))
                line(3+i-start, ('› ' if i == position else '  ') + caption, curses.A_REVERSE if i == position else 0)
            if not matches: line(3, 'No matching entries. Clear the filter or press Esc.')
            if matches:
                row = matches[position]
                line(height-3, detail(dict(row, **extras.get(id(row), {})) if isinstance(row, dict) else row))
            line(height-2, '↑↓ select · Enter continue · Esc back · Ctrl-U clear')
            win.refresh()
            try:
                key = win.get_wch()
            except curses.error:
                continue
            state.update(query=query, position=position)
            if key == '\x1b': return None
            if key in ('\n', '\r', curses.KEY_ENTER) and matches:
                selected = matches[position]
                return query.strip() if selected is new_entry else '' if selected is clear_entry else selected
            if key == curses.KEY_UP: position = max(0, position-1)
            elif key == curses.KEY_DOWN: position = min(len(matches)-1, position+1)
            elif key in (curses.KEY_BACKSPACE, '\b', '\x7f'): query, position = query[:-1], 0
            elif key == '\x15': query, position = '', 0
            elif isinstance(key, str) and key.isprintable(): query, position = query+key, 0
    try:
        return curses.wrapper(screen)
    finally:
        if pool: pool.shutdown(wait=False, cancel_futures=True)


def form(title, fields, choices=None, suggestions=None):
    """Edit a staged mapping; nothing is persisted until Save is selected."""
    values = dict(fields)
    while True:
        options = ['Save'] + list(values) + ['Cancel']
        field = select(title, options, lambda k: k + (': ' + str(values[k]) if k in values else ''))
        if field in (None, 'Cancel'):
            if values != dict(fields) and select('Unsaved changes', ['Keep editing', 'Discard changes']) != 'Discard changes':
                continue
            return None
        if field == 'Save': return values
        if suggestions and field in suggestions:
            options = sorted(set(suggestions[field]) | ({values[field]} if values[field] else set()), key=str.casefold)
            value = select(field + ' · choose an existing value or type a new one', options,
                           state={'position': options.index(values[field]) if values[field] in options else 0}, allow_new=True)
        else:
            value = (select(field, ordered_options(values[field], choices[field]))
                     if choices and field in choices else text_input(field, str(values[field])))
        if value is not None: values[field] = value


def metadata_suggestions(data):
    """Keep distinct spellings visible so near-duplicates can be spotted."""
    return {
        'label': [label['name'] for label in data['labels']],
        'packaging': [e['packaging'] for e in data['editions'] if e.get('packaging')],
        'cut': [c['cut'] for e in data['editions'] for c in e.get('contents', []) if c.get('cut')],
        'location': [c['location'] for c in data['copies'] if c.get('location')],
    }


def text_input(title, initial=''):
    def screen(win):
        curses.curs_set(1)
        # stdscr can retain the selector's polling timeout across wrapper calls.
        win.timeout(-1)
        value, cursor = initial, len(initial)
        while True:
            win.erase()
            height, width = win.getmaxyx()
            if height < 5 or width < 12:
                raise ValueError('Please enlarge the terminal to edit fields.')
            offset = max(0, cursor-width+3)
            win.addnstr(0,0,title,width-1)
            win.addnstr(2,0,value[offset:],width-1)
            win.addnstr(height-2,0,'Enter accept · Esc cancel · Ctrl-U clear',width-1)
            win.move(2,cursor-offset)
            win.refresh()
            key = win.get_wch()
            if key in ('\n','\r',curses.KEY_ENTER): return value
            if key == '\x1b': return None
            if key == '\x15': value, cursor = '', 0
            elif key == curses.KEY_LEFT: cursor = max(0,cursor-1)
            elif key == curses.KEY_RIGHT: cursor = min(len(value),cursor+1)
            elif key == curses.KEY_HOME: cursor = 0
            elif key == curses.KEY_END: cursor = len(value)
            elif key in (curses.KEY_BACKSPACE,'\b','\x7f') and cursor:
                value, cursor = value[:cursor-1]+value[cursor:], cursor-1
            elif key == curses.KEY_DC: value = value[:cursor]+value[cursor+1:]
            elif isinstance(key,str) and key.isprintable():
                value, cursor = value[:cursor]+key+value[cursor:], cursor+1
    return curses.wrapper(screen)


def movie_label(row):
    directors = ', '.join(p['name'] for p in row.get('directors', [])) or '…'
    countries = ', '.join(row.get('origin_country', [])) or '—'
    title = row['title']
    original = row.get('original_title')
    if original and original.casefold() != title.casefold():
        title += f' ({original})'
    return f"{title} | {row.get('year') or row.get('release_date', '')[:4] or '?'} | {directors} | {countries} | {row.get('status', '')}"


def pick_movie(api, rows, films, data, state=None):
    for row in rows:
        local = next((f for f in films if f.get('tmdb') == {'type': 'movie', 'id': row['id']}), None)
        row['status'] = ownership(local, data) if local else ''
    def enrich(row):
        data = api.get(f"movie/{row['id']}", append_to_response='credits')
        return dict(directors=[p for p in data.get('credits', {}).get('crew', []) if p.get('job') == 'Director'],
                    origin_country=data.get('origin_country', []), overview=data.get('overview', ''))
    return select('TMDB films', rows, movie_label, lambda r: r.get('detail_error') or r.get('overview', 'Loading details…'), enrich, state=state)


def ownership(film, data):
    if not film: return ''
    owned = {c['edition_id'] for c in data['copies'] if c.get('ownership', 'owned') == 'owned'}
    formats = sorted({fmt for e in data['editions'] if e['id'] in owned and any(c['film'] == film['id'] for c in e.get('contents', [])) for fmt in e.get('formats', [])})
    has_copy = any(e['id'] in owned and any(c['film'] == film['id'] for c in e.get('contents', [])) for e in data['editions'])
    return ('Owned: ' + (', '.join(formats) or 'format unknown') if has_copy else 'Not owned')


def viewing_status(film, viewings):
    if film.get('watched') is True or any(v['film'] == film['id'] for v in viewings):
        return 'Watched'
    return 'Unwatched' if film.get('watched') is False else 'Unknown'


def ordered_options(current, options):
    return [current] + [value for value in options if value != current]


def notify(message):
    print(message)
    input('Press Enter to continue…')


def perform(operation):
    try:
        result = operation()
        notify('Saved'+(f': {result}' if result is not None else '.'))
    except (ValueError, OSError, RuntimeError, KeyError) as error:
        notify(str(error))


def own(service, selection):
    editions = service.existing_editions(selection)
    if editions:
        choice = select('Already in your collection', ['New edition', *editions],
                        lambda e: e if isinstance(e, str) else 'Another copy: '+e['title']+' | '+', '.join(e.get('formats', [])))
        if choice is None: return
        if isinstance(choice, dict):
            values = form('New copy', {'location': ''}, suggestions=metadata_suggestions(service.read('collection')))
            if values is not None: perform(lambda: service.add_copy(choice['id'], **values))
            return
    fmt = select('Disc format', sorted(db.FORMATS))
    if fmt is None: return
    values = form('Edition details · optional fields', {'title': '', 'label': '', 'cut': '', 'notes': '', 'location': '', 'packaging': '', 'barcode': ''}, suggestions=metadata_suggestions(service.read('collection')))
    if values is not None: perform(lambda: service.add_owned(selection, formats=[fmt], **values))


def tmdb_url(service, selection):
    if isinstance(selection, str):
        film = next((f for f in service.read('films') if selection in (f['id'], f.get('slug'))), {})
        identity = film.get('tmdb') or {}
    else:
        identity = {'type': 'movie', 'id': selection.get('id')}
    kind, movie_id = identity.get('type'), identity.get('id')
    if kind in ('movie', 'tv') and type(movie_id) is int and movie_id > 0:
        return f'https://www.themoviedb.org/{kind}/{movie_id}'
    return None


def open_tmdb(url):
    try:
        if webbrowser.open_new_tab(url):
            return
    except (webbrowser.Error, OSError):
        pass
    notify('Could not open a browser. Open this URL: ' + url)


def actions(service, selection):
    while True:
        editions = service.existing_editions(selection)
        options = (['Edit collection entry'] if editions else []) + ['Add to collection', 'Log viewing and write review']
        if isinstance(selection, str): options += ['Edit film details']
        url = tmdb_url(service, selection)
        if url: options += ['Open on TMDB']
        action = select('Film actions', options+['Back'])
        if action in (None, 'Back'): return
        if action == 'Open on TMDB':
            open_tmdb(url)
        elif action == 'Edit collection entry':
            edition = editions[0] if len(editions) == 1 else select('Choose your edition', editions,
                lambda e: e['title']+' | '+(', '.join(e.get('formats', [])) or 'format unknown')+' | '+e['id'])
            if edition is not None: edit_collection_entry(service, edition['id'])
        elif action == 'Add to collection':
            own(service, selection)
        elif action == 'Edit film details':
            film = next(f for f in service.read('films') if f['id'] == selection)
            liked = 'Yes' if film.get('liked') is True else 'No'
            values = form('Film details', {'Liked': liked, 'rating': film.get('rating', ''), 'tags (comma separated)': ', '.join(film.get('tags', []))}, choices={'Liked': ['Yes', 'No']})
            status = select('Watched status', ordered_options(viewing_status(film, service.read('viewings')), ['Watched', 'Unwatched', 'Unknown'])) if values is not None else None
            if status:
                perform(lambda: service.edit_film(selection, rating=values['rating'], tags=[t.strip() for t in values['tags (comma separated)'].split(',') if t.strip()], watched=status, liked=(values['Liked'] == 'Yes') if values['Liked'] != liked else None))
        else:
            import datetime
            from cinema_editor import edit_review
            values = form('Viewing', {'date': str(datetime.date.today()), 'rating': '', 'rewatch (yes/no)': 'no'})
            if values is not None:
                try:
                    if values['rewatch (yes/no)'].lower() not in ('yes','no'): raise ValueError('Rewatch must be yes or no.')
                    path = service.log_review(selection, date=values['date'], rating=values['rating'], rewatch=values['rewatch (yes/no)'].lower() == 'yes', editor=edit_review)
                    notify(f'Saved review: {path}' if path else 'Cancelled; no viewing saved.')
                except (ValueError, OSError, RuntimeError) as error:
                    notify(str(error))


def search(service, query, year=None):
    try:
        rows = service.search(query)
        if year: rows = [r for r in rows if r.get('release_date','')[:4] == year]
    except (ValueError, OSError, RuntimeError) as error:
        notify(str(error))
        return
    picker_state = {}
    while True:
        selected = pick_movie(service.api, rows, service.read('films'), service.read('collection'), picker_state)
        if selected is None: return
        actions(service, selected)


def browse(service):
    while True:
        view = select('Local cinema database', ['Films', 'Collection', 'Search TMDB', 'Exit'])
        if view in (None, 'Exit'): return
        if view == 'Search TMDB':
            query = text_input('Search TMDB')
            if query: search(service, query)
            continue
        picker_state = {}
        film_filter = 'All films'
        if view == 'Films':
            film_filter = select('Film filter', ['All films', 'Owned', 'Not owned', 'Watched', 'Unwatched', 'Unknown viewing status', 'Owned without a recorded viewing'])
            if film_filter is None: continue
        while True:
            films = service.read('films')
            data = service.read('collection')
            if view == 'Films':
                viewings = service.read('viewings')
                rows = []
                for f in films:
                    owned, status = ownership(f, data), viewing_status(f, viewings)
                    if film_filter == 'Owned' and not owned.startswith('Owned:'): continue
                    if film_filter == 'Not owned' and owned != 'Not owned': continue
                    if film_filter in ('Watched', 'Unwatched') and status != film_filter: continue
                    if film_filter == 'Unknown viewing status' and status != 'Unknown': continue
                    if film_filter == 'Owned without a recorded viewing' and (not owned.startswith('Owned:') or status == 'Watched'): continue
                    rows.append(dict(f, status=owned+' | '+status))
                film = select('Films · filter title, director, format or watched status', rows, movie_label, state=picker_state)
                if film is None: break
                actions(service, film['id'])
            else:
                labels = db.index(data['labels'])
                film_index = {film['id']: film for film in films}
                rows = [dict(e, summary=' | '.join([e['title'], ', '.join(e.get('formats', [])), labels.get(e.get('label_id'), {}).get('name', ''), '; '.join(film_index[c['film']]['title'] for c in e.get('contents', [])), '; '.join(c.get('location', '') for c in data['copies'] if c['edition_id'] == e['id'])])) for e in data['editions']]
                edition = select('Collection · filter title, label, format or location', rows, lambda e: e['summary'], state=picker_state)
                if edition is None: break
                edit_collection_entry(service, edition['id'])


def edit_collection_entry(service, edition_id):
    while True:
        data = service.read('collection')
        edition = db.index(data['editions'])[edition_id]
        labels = db.index(data['labels'])
        film_index = {film['id']: film for film in service.read('films')}
        action = select(edition['title'], ['Edit edition', 'Edit format', 'Edit label', 'Edit cut/version', 'Edit owned copy', 'Films in this edition', 'Back'])
        if action in (None, 'Back'): return
        if action == 'Edit edition':
            fields = {k: edition.get(k, '') for k in ('title', 'notes', 'packaging', 'barcode', 'catalogue_number', 'country', 'release_date')}
            values = form(edition['title'], fields, suggestions=metadata_suggestions(data))
            if values is not None: perform(lambda: service.edit_edition(edition['id'], values))
        elif action == 'Edit format':
            formats = list(edition.get('formats', []))
            while True:
                fmt = select('Select formats · '+(', '.join(formats) or 'unknown'), sorted(db.FORMATS)+['Save', 'Cancel'],
                    lambda value: ('[x] ' if value in formats else '[ ] ')+value if value in db.FORMATS else value)
                if fmt in (None, 'Cancel'): break
                if fmt == 'Save':
                    perform(lambda: service.edit_edition(edition['id'], {'formats': formats}))
                    break
                if fmt in formats: formats.remove(fmt)
                else: formats.append(fmt)
        elif action == 'Edit label':
            values = form('Label', {'label': labels.get(edition.get('label_id'), {}).get('name', '')}, suggestions=metadata_suggestions(data))
            if values is not None: perform(lambda: service.edit_edition(edition['id'], values))
        elif action == 'Edit cut/version':
            constituent = select('Choose film', edition.get('contents', []), lambda c: film_index[c['film']]['title']+' | '+c.get('cut', ''))
            if constituent:
                values = form('Cut/version', {'cut': constituent.get('cut', '')}, suggestions=metadata_suggestions(data))
                if values is not None: perform(lambda: service.edit_cut(edition['id'], constituent['film'], values['cut']))
        elif action == 'Edit owned copy':
            copies = [c for c in data['copies'] if c['edition_id'] == edition['id']]
            owned = select('Copies', copies, lambda c: f"{c['id']} | {c.get('location', '')} | {c.get('condition', 'unknown')} | {c.get('ownership', 'owned')}")
            if owned:
                values = form('Copy details', {k: owned.get(k, '') for k in ('location','notes')}, suggestions=metadata_suggestions(data))
                condition = select('Condition', ordered_options(owned.get('condition','unknown'), ['unknown','good','damaged','faulty','missing_disc'])) if values is not None else None
                state = select('Ownership', ordered_options(owned.get('ownership','owned'), ['owned','loaned','sold','disposed','lost'])) if condition else None
                if state: perform(lambda: service.edit_copy(owned['id'], dict(values, condition=condition, ownership=state)))
        elif action == 'Films in this edition':
            film = select('Films', [film_index[c['film']] for c in edition.get('contents', [])], movie_label)
            if film: actions(service, film['id'])
