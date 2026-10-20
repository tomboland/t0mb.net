#!/usr/bin/env python3
"""Validate the current catalogue, reviews, viewing history and collection relationships."""
from collections import Counter,defaultdict
import importlib.util
import json
from pathlib import Path
import collection_data as collection

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('export_cinema',ROOT/'scripts/export-cinema.py')
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)

def audit(root=ROOT):
    reader.ROOT=root
    films=json.loads((root/'cinema/films.json').read_text())
    viewings=json.loads((root/'cinema/viewings.json').read_text())
    entries=json.loads((root/'cinema/entries.json').read_text()) if (root/'cinema/entries.json').exists() else []
    reviews=[reader.read_review(p) for p in sorted((root/'cinema/reviews').glob('*.md'))]
    data=collection.read(root)
    collection.validate(data,root)
    errors=[]
    def indexed(rows,label):
        counts=Counter(x.get('id') for x in rows)
        errors.extend(f'{label}: duplicate/empty ID {k}' for k,v in counts.items() if not k or v>1)
        return {x['id']:x for x in rows}
    fi=indexed(films,'films');vi=indexed(viewings,'viewings');indexed([r['metadata'] for r in reviews],'reviews')
    for key in ('slug',):
        errors.extend(f'films: duplicate/empty {key} {k}' for k,v in Counter(f.get(key) for f in films).items() if not k or v>1)
    aliases_path=root/'cinema/collection-redirects.json'
    if aliases_path.exists():
        for old, fid in json.loads(aliases_path.read_text()).items():
            if fid not in fi: errors.append(f'{old}: URL alias refers to missing film {fid}')
    ei=indexed(entries,'diary notes')
    for v in viewings+entries:
        if v['film'] not in fi:errors.append(f'{v["id"]}: missing film {v["film"]}')
    for r in reviews:
        m=r['metadata']
        if m['film'] not in fi:errors.append(f'{m["id"]}: missing film {m["film"]}')
        if m.get('diary_entry') and (m['diary_entry'] not in ei or ei[m['diary_entry']]['film']!=m['film']):errors.append(f'{m["id"]}: invalid diary note relationship')
        if m.get('viewing') and m.get('diary_entry'):errors.append(f'{m["id"]}: review has both viewing and diary note')
        if m.get('viewing'):
            if m['viewing'] not in vi or vi[m['viewing']]['film']!=m['film']:errors.append(f'{m["id"]}: invalid viewing relationship')
    ext=defaultdict(list)
    for f in films:
        if f.get('tmdb'):ext[(f['tmdb']['type'],str(f['tmdb']['id']))].append(f['id'])
    duplicate_external=[{'tmdb_type':k[0],'tmdb_id':k[1],'film_ids':v} for k,v in ext.items() if len(v)>1]
    for group in duplicate_external:errors.append('Duplicate TMDB identity: '+str(group))
    counts={'films':len(films),'viewings':len(viewings),'reviews':len(reviews),'owned_catalogue_entries':len({x['film'] for e in data['editions'] for x in e.get('contents', [])}),'editions':len(data['editions']),'copies':len(data['copies'])}
    return {'counts':counts,'errors':errors}

if __name__=='__main__':
    result=audit()
    print(json.dumps(result,indent=2))
    raise SystemExit(bool(result['errors']))
