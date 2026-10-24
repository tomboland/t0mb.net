"""Edition-aware collection storage. Offline, atomic, and independent of viewing history."""
import csv
import datetime
import json
import os
import re
import tempfile
import unicodedata
from cinema_data import sparse
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

def film_kind(film):
    return film.get('kind', 'tv_series' if film.get('tmdb', {}).get('type') == 'tv' else 'film')

def validate(data, root=ROOT, film_rows=None):
    if data.get('schema_version') != 3:
        raise ValueError('Unsupported collection schema')
    if 'works' in data:
        raise ValueError('Collection contents must reference canonical films directly')
    labels, editions, copies = [index(data[k]) for k in ('labels','editions','copies')]
    rows = film_rows if film_rows is not None else json.loads((root/'cinema/films.json').read_text())
    films = {f['id']: f for f in rows}
    if len(films) != len(rows): raise ValueError('Duplicate canonical film ID')
    for f in rows:
        if not f.get('id') or not f.get('title') or not f.get('slug'): raise ValueError('Film needs ID, title and slug')
        if film_kind(f) not in KINDS: raise ValueError('Invalid film kind')
    for label in labels.values():
        if not label.get('name'): raise ValueError('Label needs a name')
    barcodes = set()
    for e in editions.values():
        if not e.get('title', '').strip(): raise ValueError('Invalid edition')
        if e.get('label_id') and e['label_id'] not in labels: raise ValueError('Unknown label')
        if e.get('release_date'):
            try: datetime.date.fromisoformat(e['release_date'])
            except (TypeError, ValueError): raise ValueError('Release date must be YYYY-MM-DD')
        if not isinstance(e.get('formats', []), list) or not set(e.get('formats', [])) <= FORMATS: raise ValueError('Unknown format')
        if e.get('barcode'):
            code = e['barcode']
            if not isinstance(code, str) or not re.fullmatch(r'\d{8}|\d{12,14}', code): raise ValueError('Barcode must be an 8/12/13/14-digit string')
            if code in barcodes: raise ValueError('Barcode already used by another edition; reuse its edition ID')
            barcodes.add(code)
        if not isinstance(e.get('contents', []), list): raise ValueError('Contents must be a list')
        for c in e.get('contents', []):
            if c.get('film') not in films: raise ValueError('Unknown canonical film in edition')
            if 'work_id' in c: raise ValueError('Obsolete work reference')
            if c.get('role', 'unspecified') not in {'main','supplement','unspecified'}: raise ValueError('Invalid content role')
            if not isinstance(c.get('coverage', ''), str): raise ValueError('Coverage must be text')
    for c in copies.values():
        if c['edition_id'] not in editions: raise ValueError('Unknown edition in copy')
        if c.get('condition', 'unknown') not in {'unknown','good','damaged','faulty','missing_disc'}: raise ValueError('Invalid copy condition')
        if c.get('ownership', 'owned') not in {'owned','loaned','sold','disposed','lost'}: raise ValueError('Invalid ownership')
    return labels, films, editions, copies

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
    atomic_text(root/'cinema/collection.json', json.dumps({k: [sparse(row) for row in v] if isinstance(v, list) else v for k, v in data.items()}, ensure_ascii=False, indent=2)+'\n')

def export(data, root=ROOT):
    """Optional local CSV/JSON exports; never a second editable source."""
    labels, films, editions, copies = validate(data, root)
    rows=[]
    for c in copies.values():
        e=editions[c['edition_id']]
        rows.append(dict(copy_id=c['id'],edition_id=e['id'],title=e['title'],
            label=labels[e['label_id']]['name'] if e.get('label_id') else '',
            formats='; '.join(e.get('formats', [])),catalogue_number=e.get('catalogue_number') or '',
            barcode=e.get('barcode') or '',condition=c.get('condition', 'unknown'),ownership=c.get('ownership', 'owned'),
            location=c.get('location') or '',edition_notes=e.get('notes',''),copy_notes=c.get('notes',''),
            contents='; '.join(films[x['film']]['title'] for x in e.get('contents', []))))
    import io
    stream=io.StringIO(newline='')
    fields=['copy_id','edition_id','title','label','formats','catalogue_number','barcode','condition','ownership','location','edition_notes','copy_notes','contents']
    writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    dest=root/'generated/collection'
    atomic_text(dest/'collection.csv',stream.getvalue())
    atomic_text(dest/'collection.json',json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    return {'copies':len(copies),'editions':len(editions),'films':len({x['film'] for e in editions.values() for x in e.get('contents', [])}),'output':str(dest)}


ALIASES={'arrow':('Arrow Films','Arrow Video'),'arrow video':('Arrow Films','Arrow Video'),'arrow academy':('Arrow Films','Arrow Academy'),'kino':('Kino Lorber','KL Studio Classics'),'kino lorber':('Kino Lorber','KL Studio Classics'),'kino lorder':('Kino Lorber','KL Studio Classics'),'criterion':('Criterion','The Criterion Collection'),'eureka':('Eureka Entertainment',None),'bfi':('BFI',None)}

def new_id(items,prefix):
    ids={i['id'] for i in items};n=1
    while f'{prefix}-{n:04}' in ids:n+=1
    return f'{prefix}-{n:04}'

def resolve_label(data,name,imprint=None):
    if not name:return None,imprint
    name,default=ALIASES.get(name.casefold(),(name,None))
    for l in data['labels']:
        if name.casefold() in [l['name'].casefold()]+[a.casefold() for a in l.get('aliases',[])]:return l['id'],imprint or default
    ident='label-'+re.sub('[^a-z0-9]+','-',name.lower()).strip('-')
    if any(l['id']==ident for l in data['labels']):raise ValueError('Conflicting label ID')
    data['labels'].append(dict(id=ident,name=name));return ident,imprint or default
