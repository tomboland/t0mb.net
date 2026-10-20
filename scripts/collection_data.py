"""Edition-aware collection storage. Offline, atomic, and independent of viewing history."""
import csv
import datetime
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUSES = {'transcribed', 'researched', 'curated', 'needs_review', 'unidentified'}
KINDS = {'film', 'tv_series', 'tv_film', 'documentary', 'concert', 'short', 'unknown', 'calibration'}
FORMATS = {'DVD', 'Blu-ray', '4K UHD', 'Blu-ray 3D', 'CD', 'VHS', 'LaserDisc'}
FIELDS = ['id','title','kind','format','year','edition_notes','contents','source_photos','status','review_notes','catalogue_film_id']

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

def validate(data, root=ROOT, check_photos=True):
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported collection schema')
    labels, works, editions, copies = [index(data[k]) for k in ('labels','works','editions','copies')]
    films = {f['id']: f for f in json.loads((root/'cinema/films.json').read_text())}
    manifest = json.loads((root/'data/film-shelf/photos.json').read_text())
    photos = index(manifest['photos'])
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
        if not e.get('title', '').strip() or e.get('status') not in STATUSES: raise ValueError('Invalid edition')
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
        if e['status'] in {'needs_review','unidentified'} and not e.get('review_notes'): raise ValueError('Review note required')
    for c in copies.values():
        if c['edition_id'] not in editions: raise ValueError('Unknown edition in copy')
        if c.get('condition') not in {'unknown','good','damaged','faulty','missing_disc'}: raise ValueError('Invalid copy condition')
        if c.get('ownership') not in {'owned','loaned','sold','disposed','lost'}: raise ValueError('Invalid ownership')
        if not set(c['source_photos']) <= photos.keys(): raise ValueError('Unknown source photo')
        if not c['source_photos'] and not c.get('provenance'): raise ValueError('Photo or manual provenance required')
    if check_photos:
        for p in photos.values():
            if hashlib.sha256((root/p['path']).read_bytes()).hexdigest() != p['sha256']: raise ValueError(f'Photo changed: {p["id"]}')
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
    labels, works, editions, copies = validate(data, root)
    films = json.loads((root/'cinema/films.json').read_text())
    film_index = {f['id']:f for f in films}
    candidates = {}
    for f in films:
        for title in {f['title'], f.get('original_title') or f['title']}:
            candidates.setdefault(normalise(title), {})[f['id']] = {k:f.get(k) for k in ('id','title','year')}
    items, rows = [], []
    for c in copies.values():
        e = editions[c['edition_id']]; entries = e['contents']
        single = works[entries[0]['work_id']] if len(entries)==1 else None
        years = {works[x['work_id']].get('year') for x in entries}
        shared_year = next(iter(years)) if len(years)==1 and None not in years else None
        notes = e.get('notes','')
        if c.get('notes'): notes += (' | ' if notes else '') + c['notes']
        row = dict(id=c['id'],title=e['title'],kind=e['kind'],format='; '.join(e['formats']),
                   year=str(shared_year) if shared_year else '',edition_notes=notes,
                   contents='; '.join(x.get('display_title') or works[x['work_id']]['title'] for x in entries) if e.get('list_contents') else '',
                   source_photos='; '.join(c['source_photos']),status=e['status'],review_notes=e.get('review_notes',''),
                   catalogue_film_id=(single.get('catalogue_film_id') or '') if single else '')
        rows.append(row)
        item = dict(row, year=int(row['year']) if row['year'] else None,format=row['format'] or None,
                    contents=row['contents'].split('; ') if row['contents'] else [],source_photos=c['source_photos'],
                    catalogue_film_id=row['catalogue_film_id'] or None,edition_id=e['id'],
                    label=labels[e['label_id']]['name'] if e.get('label_id') else None,imprint=e.get('imprint'),
                    formats=e['formats'],barcode=e.get('barcode'),catalogue_number=e.get('catalogue_number'),
                    packaging=e.get('packaging'),condition=c['condition'],ownership=c['ownership'],location=c.get('location'),
                    work_ids=[x['work_id'] for x in entries],catalogue_candidates=list(candidates.get(normalise(e['title']),{}).values()))
        item['resolved_contents'] = [dict(work=resolved_work(works[x['work_id']],film_index), coverage=x['coverage'],cut=x['cut'],role=x['role']) for x in entries]
        if item['catalogue_film_id']: item['catalogue_candidates'] = []
        items.append(item)
    import io
    stream=io.StringIO(newline=''); writer=csv.DictWriter(stream,fieldnames=FIELDS+['edition_id','label','imprint','barcode','catalogue_number','packaging','condition','ownership','location'])
    writer.writeheader()
    for row,item in zip(rows,items):writer.writerow(dict(row,**{k:item[k] or '' for k in writer.fieldnames if k not in FIELDS}))
    atomic_text(root/'cinema/shelf.csv',stream.getvalue())
    atomic_text(root/'cinema/shelf.json',json.dumps(dict(schema_version=2,source='cinema/collection.json',scope='Owned packages/copies, not unique works or viewing history.',items=items),ensure_ascii=False,indent=2)+'\n')
    review=[i for i in items if i['status'] in {'needs_review','unidentified'}]
    incomplete=[i for i in items if not i['label'] or not i['formats']]
    lines=['# Collection review queue','','Generated by `python3 scripts/collection.py export`. Edit collection.json or use collection.py, not these exports.','',f'{len(items)} copies; {len(review)} identification questions. {len(incomplete)} copies have an unrecorded label and/or format. Missing metadata is not an unidentified film.','','## Identification questions','','| ID | Title | Question | Photos |','|---|---|---|---|']
    def esc(s): return str(s).replace('|','/').replace('\n',' ')
    def links(i): return ', '.join(f'[{p}](photos/{p}.jpg)' for p in i['source_photos']) or 'Manual entry'
    for i in review:lines.append(f"| {i['id']} | {esc(i['title'])} | {esc(i['review_notes'])} | {links(i)} |")
    lines+=['','## Edition metadata to enrich','','Unknown labels/formats remain blank rather than guessed. A recorded format does not imply companion discs or region compatibility.','','| ID | Title | Label | Formats | Photos |','|---|---|---|---|---|']
    for i in incomplete:lines.append(f"| {i['id']} | {esc(i['title'])} | {i['label'] or '—'} | {'; '.join(i['formats']) or '—'} | {links(i)} |")
    atomic_text(root/'data/film-shelf/review.md','\n'.join(lines)+'\n')
    return {'copies':len(copies),'editions':len(editions),'work_records':len(works),'identification_questions':len(review),'incomplete_edition_metadata':len(incomplete)}
