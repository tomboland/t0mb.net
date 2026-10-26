"""Application operations for the local cinema database, independent of any CLI/UI."""
import datetime
import fcntl
import importlib.util
import json
from pathlib import Path
import uuid

import collection_data as collection
from cinema_data import ROOT, slug, sparse, validate_rating, normalise_tags
from review_files import review_path


class Catalogue:
    def __init__(self, root=ROOT, api=None, artwork_loader=None):
        self.root = Path(root)
        self.directory = self.root / 'cinema'
        self.api = api
        self.artwork_loader = artwork_loader

    def read(self, name):
        path = self.directory / (name + '.json')
        if path.exists(): return json.loads(path.read_text())
        if name == 'collection': return dict(schema_version=3,labels=[],editions=[],copies=[])
        return {} if name == 'artwork' else []

    def snapshot(self):
        return {name: self.read(name) for name in ('films', 'directors', 'viewings', 'artwork', 'collection')}

    def search(self, query):
        if self.api is None:
            raise ValueError('TMDB access requires a token. Set TMDB_TOKEN_FILE or use --token-file.')
        return self.api.search(query)

    def movie_details(self, movie_id):
        if self.api is None:
            raise ValueError('TMDB access requires a token.')
        return self.api.get(f'movie/{movie_id}', append_to_response='credits')

    def resolve(self, selection, state):
        """Stage a local identity or TMDB result, with no source writes."""
        if isinstance(selection, str):
            film = next((f for f in state['films'] if selection in (f['id'], f['slug'])), None)
            if film is None: raise ValueError('Film no longer exists. Refresh the browser.')
            return film
        movie_id = selection['id']
        film = next((f for f in state['films'] if f.get('tmdb') == {'type': 'movie', 'id': movie_id}), None)
        if film: return film
        data = self.movie_details(movie_id)
        year = data.get('release_date', '')[:4]
        film_slug = slug(data['title'] + ('-' + year if year else ''))
        if any(f['slug'] == film_slug for f in state['films']):
            raise ValueError('This title/year already exists with another identity. Select the local record instead.')
        directors = [{'id': p['id'], 'name': p['name']} for p in data.get('credits', {}).get('crew', []) if p.get('job') == 'Director']
        film = sparse(dict(id='local-'+uuid.uuid4().hex[:12], slug=film_slug, title=data['title'], year=year,
                           tmdb={'type':'movie', 'id':movie_id}, original_title=data.get('original_title'),
                           runtime=data.get('runtime'), overview=data.get('overview'), directors=directors,
                           origin_country=data.get('origin_country', [])))
        for person in directors:
            if not any(p['id'] == person['id'] for p in state['directors']):
                credits = self.api.get(f"person/{person['id']}/movie_credits")
                movies = {p['id']: {'tmdb_id':p['id'], 'title':p['title'], 'year':p.get('release_date','')[:4]}
                          for p in credits.get('crew', []) if p.get('job') == 'Director'}
                state['directors'].append(dict(person, filmography=list(movies.values())))
        state['films'].append(film)
        return film

    def artwork(self, film, state):
        if not film.get('tmdb'): return
        existing = state['artwork'].get(film['id'])
        if existing:
            paths = [record[key] for kind in ('poster','backdrop') for record in [existing.get(kind,{})] for key in ('path','thumbnail') if record.get(key)]
            if all((self.root/path.lstrip('/')).is_file() for path in paths): return
        if self.artwork_loader:
            key, record = self.artwork_loader(film)
        else:
            spec = importlib.util.spec_from_file_location('cinema_artwork', Path(__file__).with_name('refresh-artwork.py'))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            key, record = module.fetch(film, self.api, self.root/'images/films/tmdb')
        state['artwork'][key] = record

    def commit(self, before, after, review=None):
        """Validate first, reject stale edits, and roll back ordinary write failures."""
        collection.validate(after['collection'], self.root, film_rows=after['films'])
        from cinema_schema import validate
        for name in ('films', 'viewings', 'collection'):
            validate(name, after[name])
        with (self.directory/'.collection.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.snapshot() != before:
                raise ValueError('The catalogue changed during editing. Refresh and try again.')
            updates = {}
            for name, value in after.items():
                if value == before[name]: continue
                # Collection's empty top-level arrays are required by its storage contract.
                cleaned = ({k: [sparse(row) for row in v] if isinstance(v, list) else v
                            for k, v in value.items()} if name == 'collection' else sparse(value))
                updates[self.directory/(name+'.json')] = json.dumps(cleaned, ensure_ascii=False, indent=2)+'\n'
            if review:
                path, content = review
                if path.exists(): raise ValueError('Review path now exists; retry to choose a new filename.')
                updates[path] = content
            originals = {p:p.read_text() if p.exists() else None for p in updates}
            written = []
            try:
                for path, content in updates.items():
                    collection.atomic_text(path, content)
                    written.append(path)
            except BaseException:
                for path in reversed(written):
                    if originals[path] is None: path.unlink(missing_ok=True)
                    else: collection.atomic_text(path, originals[path])
                raise

    def existing_editions(self, selection):
        films = self.read('films')
        film = next((f for f in films if (isinstance(selection, str) and selection in (f['id'],f['slug'])) or
                     (isinstance(selection, dict) and f.get('tmdb') == {'type':'movie','id':selection['id']})), None)
        return [] if film is None else [e for e in self.read('collection')['editions'] if any(c['film'] == film['id'] for c in e.get('contents', []))]

    def add_owned(self, selection, *, formats, title='', label='', cut='', location='', notes='', packaging='', barcode=''):
        import copy
        before = self.snapshot()
        state = copy.deepcopy(before)
        film = self.resolve(selection, state)
        data = state['collection']
        edition = dict(id=collection.new_id(data['editions'],'edition'), title=title or film['title'], formats=formats,
                       notes=notes, packaging=packaging, barcode=barcode,
                       contents=[dict(film=film['id'], role='main', cut=cut)])
        if label: edition['label_id'], edition['imprint'] = collection.resolve_label(data, label, None)
        data['editions'].append(sparse(edition))
        owned = sparse(dict(id=collection.new_id(data['copies'],'shelf'), edition_id=edition['id'], location=location))
        data['copies'].append(owned)
        collection.validate(data, self.root, film_rows=state['films'])
        self.artwork(film, state)
        self.commit(before, state)
        return edition['id']

    def mutate_collection(self, operation):
        import copy
        before = self.snapshot()
        state = copy.deepcopy(before)
        result = operation(state['collection'])
        self.commit(before, state)
        return result

    def add_copy(self, edition_id, location=''):
        def change(data):
            if edition_id not in collection.index(data['editions']): raise ValueError('Unknown edition')
            owned = sparse(dict(id=collection.new_id(data['copies'],'shelf'),edition_id=edition_id,location=location))
            data['copies'].append(owned)
            return owned['id']
        return self.mutate_collection(change)

    def edit_edition(self, edition_id, values):
        allowed = {'title','formats','notes','packaging','barcode','catalogue_number','country','release_date','label'}
        if not values.keys() <= allowed: raise ValueError('Unsupported edition field')
        def change(data):
            edition = collection.index(data['editions'])[edition_id]
            for key, value in values.items():
                if key == 'label':
                    if value: edition['label_id'], edition['imprint'] = collection.resolve_label(data, value, None)
                    else:
                        edition.pop('label_id', None)
                        edition.pop('imprint', None)
                elif key in {'notes', 'packaging', 'barcode', 'catalogue_number', 'country', 'release_date'} and isinstance(value, str) and not value.strip():
                    # Optional form fields must be absent before schema validation.
                    edition.pop(key, None)
                else: edition[key] = value
        self.mutate_collection(change)

    def edit_copy(self, copy_id, values):
        if not values.keys() <= {'location','notes','condition','ownership'}: raise ValueError('Unsupported copy field')
        self.mutate_collection(lambda data: collection.index(data['copies'])[copy_id].update(values))

    def edit_cut(self, edition_id, film_id, cut):
        def change(data):
            edition = collection.index(data['editions'])[edition_id]
            item = next((c for c in edition.get('contents', []) if c['film'] == film_id), None)
            if item is None: raise ValueError('Film is not in the edition')
            item['cut'] = cut
        self.mutate_collection(change)

    def edit_film(self, film_id, *, rating, tags, watched, liked=None):
        import copy
        validate_rating(rating)
        if watched not in ('Watched','Unwatched','Unknown'): raise ValueError('Invalid watched status')
        if liked is not None and not isinstance(liked, bool): raise ValueError('Liked must be true or false')
        before = self.snapshot()
        state = copy.deepcopy(before)
        film = self.resolve(film_id, state)
        if watched != 'Watched' and any(v['film'] == film_id for v in state['viewings']):
            raise ValueError('Recorded viewings establish watched status; edit those records separately.')
        film['rating'] = rating
        film['tags'] = normalise_tags(tags)
        if liked is not None: film['liked'] = liked
        if watched == 'Unknown': film.pop('watched', None)
        else: film['watched'] = watched == 'Watched'
        self.commit(before, state)

    def log_review(self, selection, *, date, rating='', rewatch=False, liked=False, editor=None):
        import copy
        from cinema_editor import validate_review
        datetime.date.fromisoformat(date)
        validate_rating(rating)
        before = self.snapshot()
        state = copy.deepcopy(before)
        film = self.resolve(selection, state)
        viewing = sparse(dict(id='local-'+uuid.uuid4().hex[:12],film=film['id'],date=date,rating=rating,rewatch=rewatch))
        today = str(datetime.date.today())
        meta = dict(id=film['slug']+'-'+today+'-'+uuid.uuid4().hex[:6],film=film['id'],title=film['title'],date=today,
                    spoilers=False,viewing=viewing['id'],watched_date=date)
        if rating: meta['rating'] = rating
        content = '---\n'+'\n'.join(f'{k}: {json.dumps(v,ensure_ascii=False)}' for k,v in meta.items())+'\n---\n\n<!-- Write your review here. -->\n'
        edited = editor(content) if editor else None
        if editor and edited is None: return None
        if edited: validate_review(edited, content)
        self.artwork(film, state)
        state['viewings'].append(viewing)
        film['watched'] = True
        if liked: film['liked'] = True
        path = review_path(self.directory/'reviews',film['slug'],today)
        self.commit(before, state, (path,edited) if edited else None)
        return path if edited else viewing['id']

    def add_film(self, selection=None, *, title='', year='', directors=(), kind='film', unwatched=False):
        import copy
        before = self.snapshot()
        state = copy.deepcopy(before)
        if selection is not None:
            film = self.resolve(selection, state)
            self.artwork(film, state)
        else:
            if not title.strip(): raise ValueError('A title is required')
            film_slug = slug(title + ('-'+str(year) if year else ''))
            if any(f['slug'] == film_slug for f in state['films']): raise ValueError('That title/year already exists')
            film = sparse(dict(id='local-'+uuid.uuid4().hex[:12],slug=film_slug,title=title,year=year,
                               directors=[{'id':'local-'+slug(n),'name':n} for n in directors],kind=kind))
            state['films'].append(film)
        if unwatched: film['watched'] = False
        self.commit(before, state)
        return film['id']

    def mark_seen(self, selection, *, rating='', liked=False):
        import copy
        validate_rating(rating)
        before = self.snapshot()
        state = copy.deepcopy(before)
        film = self.resolve(selection,state)
        film['watched'] = True
        if rating: film['rating'] = rating
        if liked: film['liked'] = True
        self.artwork(film,state)
        self.commit(before,state)
        return film['id']

    def tag(self, film_id, tags, remove=False):
        import copy
        before = self.snapshot()
        state = copy.deepcopy(before)
        film = self.resolve(film_id,state)
        current = normalise_tags(film.get('tags', []))
        wanted = normalise_tags(tags)
        film['tags'] = [t for t in current if t.casefold() not in {v.casefold() for v in wanted}] if remove else normalise_tags(current+wanted)
        self.commit(before,state)
        return film['id']
