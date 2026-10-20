"""Edition-aware collection storage. Offline, atomic, and independent of viewing history."""
import csv
import datetime
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'film', 'tv_series', 'tv_film', 'documentary', 'concert', 'short', 'unknown', 'calibration'}
FORMATS = {'DVD', 'Blu-ray', '4K UHD', 'Blu-ray 3D', 'CD', 'VHS', 'LaserDisc'}

def normalise(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if c.isalnum())

def read(root=ROOT):
    return json.loads((root/'cinema/collection.json').read_text())

def index(items):
    result = {}
    for item in items:
        ident = item.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[a-z][a-z0-9-]+', ident) or ident in result:
            raise ValueError(f'Invalid or duplicate ID: {ident}')
        result[ident] = item
    return result

def validate(data, root=ROOT):
    if data.get('schema_version') != 2:
        raise ValueError('Unsupported collection schema')
    labels, works, editions, copies = [index(data[k]) for k in ('labels','works','editions','copies')]
    films = {f['id']: f for f in json.loads((root/'cinema/films.json').read_text())}
    for label in labels.values():
        if not label.get('name'): raise ValueError('Label needs a name')
    for w in works.values():
        if not w.get('title', '').strip() or w['kind'] not in KINDS:
            raise ValueError(f'Invalid work {w["id"]}')
        if w.get('year') is not None and (type(w['year']) is not int or not 1800 <= w['year'] <= 2200):
            raise ValueError('Work year must be an integer or null')
        if w.get('catalogue_film_id') and w['catalogue_film_id'] not in films:
            raise ValueError('Unknown diary catalogue link')
        if w.get('catalogue_film_id'):
            film = films[w['catalogue_film_id']]
            if w.get('year') is not None and str(w['year']) != str(film.get('year')):
                raise ValueError('Linked work year conflicts with canonical film')
            media_type = film.get('tmdb', {}).get('type')
            if (w['kind'] == 'tv_series' and media_type == 'movie') or (w['kind'] in {'film','short'} and media_type == 'tv'):
                raise ValueError('Linked work film/TV type conflicts with canonical identity')
        if w.get('identity_status') not in {'provisional','confirmed'}:
            raise ValueError('Invalid identity status')
    barcodes = set()
    for e in editions.values():
        if not e.get('title', '').strip(): raise ValueError('Invalid edition')
        if e.get('label_id') and e['label_id'] not in labels: raise ValueError('Unknown label')
        if e.get('kind') not in KINDS | {'box_set','short_collection'}: raise ValueError('Unknown edition kind')
        if e.get('release_date'):
            try: datetime.date.fromisoformat(e['release_date'])
            except (TypeError, ValueError): raise ValueError('Release date must be YYYY-MM-DD')
        if not isinstance(e['formats'], list) or not set(e['formats']) <= FORMATS: raise ValueError('Unknown format')
        if e.get('barcode'):
            code = e['barcode']
            if not isinstance(code, str) or not re.fullmatch(r'\d{8}|\d{12,14}', code): raise ValueError('Barcode must be an 8/12/13/14-digit string')
            if code in barcodes: raise ValueError('Barcode already used by another edition; reuse its edition ID')
            barcodes.add(code)
        if not isinstance(e['contents'], list): raise ValueError('Contents must be a list')
        for c in e['contents']:
            if c['work_id'] not in works: raise ValueError('Unknown work in edition')
            if c.get('role') not in {'main','supplement','unspecified'}: raise ValueError('Invalid content role')
            if not isinstance(c.get('coverage'), dict): raise ValueError('Coverage must be an object')
    for c in copies.values():
        if c['edition_id'] not in editions: raise ValueError('Unknown edition in copy')
        if c.get('condition') not in {'unknown','good','damaged','faulty','missing_disc'}: raise ValueError('Invalid copy condition')
        if c.get('ownership') not in {'owned','loaned','sold','disposed','lost'}: raise ValueError('Invalid ownership')
    return labels, works, editions, copies

def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)

def save(data, root=ROOT):
    validate(data, root)
    atomic_text(root/'cinema/collection.json', json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def resolved_work(work, films):
    """Canonical metadata wins once linked; observed package titles remain separate."""
    film = films.get(work.get('catalogue_film_id'))
    if film:
        return dict(id=film['id'], collection_work_id=work['id'], title=film['title'],
                    year=int(film['year']) if film.get('year') else None,
                    kind='tv_series' if film.get('tmdb', {}).get('type') == 'tv' else work['kind'],
                    tmdb=film.get('tmdb'), url='/films/'+film['slug']+'/', linked=True)
    return dict(id=work['id'], collection_work_id=work['id'], title=work['title'],
                year=work.get('year'),kind=work['kind'],tmdb=None,url=None,linked=False)

def export(data, root=ROOT):
    """Optional local CSV/JSON exports; never a second editable source."""
    labels, works, editions, copies = validate(data, root)
    films = {f['id']:f for f in json.loads((root/'cinema/films.json').read_text())}
    rows=[]
    for c in copies.values():
        e=editions[c['edition_id']]
        rows.append(dict(copy_id=c['id'],edition_id=e['id'],title=e['title'],
            label=labels[e['label_id']]['name'] if e.get('label_id') else '',
            formats='; '.join(e['formats']),catalogue_number=e.get('catalogue_number') or '',
            barcode=e.get('barcode') or '',condition=c['condition'],ownership=c['ownership'],
            location=c.get('location') or '',edition_notes=e.get('notes',''),copy_notes=c.get('notes',''),
            contents='; '.join(resolved_work(works[x['work_id']],films)['title'] for x in e['contents'])))
    import io
    stream=io.StringIO(newline='')
    fields=['copy_id','edition_id','title','label','formats','catalogue_number','barcode','condition','ownership','location','edition_notes','copy_notes','contents']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    dest=root/'generated/collection'
    atomic_text(dest/'collection.csv',stream.getvalue())
    atomic_text(dest/'collection.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return {'copies':len(copies),'editions':len(editions),'works':len(works),'output':str(dest)}
