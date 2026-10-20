#!/usr/bin/env python3
"""Import explicitly reviewed TMDB identities; dry-run by default, never invent watches."""
import argparse,copy,fcntl,hashlib,importlib.util,json,os,tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import collection_data as db
import cinema_data
spec=importlib.util.spec_from_file_location('tmdb',Path(__file__).with_name('match-tmdb.py'))
tmdb=importlib.util.module_from_spec(spec);spec.loader.exec_module(tmdb)

def integrate(data,films,decisions,metadata):
    data=copy.deepcopy(data);films=copy.deepcopy(films);works=db.index(data['works'])
    by_external={(f['tmdb']['type'],int(f['tmdb']['id'])):f for f in films if f.get('tmdb')}
    by_id={f['id']:f for f in films};slugs={f['slug'] for f in films};changes=[];added=[]
    for decision in decisions:
        w=works[decision['work_id']];key=(decision['tmdb']['type'],int(decision['tmdb']['id']))
        if w.get('catalogue_film_id'):
            f=by_id[w['catalogue_film_id']]
            if f.get('tmdb')!=decision['tmdb']:raise ValueError('Existing different identity: '+w['id'])
            continue
        if (w['kind']=='tv_series')!=(key[0]=='tv'):raise ValueError('Film/TV mismatch: '+w['id'])
        m=metadata[key]
        if (m.get('title') or m.get('name'))!=decision['expected_title']:raise ValueError('TMDB title changed: '+w['id'])
        year=(m.get('release_date') or m.get('first_air_date') or '')[:4]
        if not year or year!=str(decision['expected_year']):raise ValueError('TMDB year changed/missing: '+w['id'])
        if key not in by_external:
            fid=f'tmdb-{key[0]}-{key[1]}'
            if fid in by_id:raise ValueError('Conflicting canonical ID: '+fid)
            title=m.get('title') or m.get('name');slug=cinema_data.slug(title+'-'+year)
            if slug in slugs:slug+='-'+fid
            # Unknown viewing status is deliberately null, not a claim of unwatched.
            f=dict(id=fid,slug=slug,title=title,year=year,original_title=m.get('original_title') or m.get('original_name'),
                   tmdb=decision['tmdb'],kind=decision.get('reviewed_kind',w['kind']),watched=None,rating=None,directors=[],
                   overview=m.get('overview'),metadata_source=decision['source'])
            if key[0]=='movie':
                f['runtime']=m.get('runtime');f['directors']=[{'id':p['id'],'name':p['name']} for p in m.get('credits',{}).get('crew',[]) if p.get('job')=='Director']
            films.append(f);added.append(fid);by_id[fid]=f;by_external[key]=f;slugs.add(slug)
        f=by_external[key]
        if w.get('year') is not None and w['year']!=int(f['year']):
            raise ValueError('Existing shelf year conflicts: '+w['id'])
        before=copy.deepcopy(w)
        if decision.get('reviewed_work_title'):w['title']=decision['reviewed_work_title']
        if decision.get('reviewed_kind'):w['kind']=decision['reviewed_kind']
        w.update(catalogue_film_id=f['id'],year=int(f['year']),identity_status='confirmed',identity_evidence={'type':'reviewed_tmdb','evidence':decision['evidence'],'sources':[decision['source']]})
        changes.append({'before':before,'after':copy.deepcopy(w)})
    return data,films,{'new_canonical_ids':added,'work_changes':changes}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file',type=Path,default=Path(os.environ.get('TMDB_TOKEN_FILE','~/.config/t0mb.net/tmdb-token')).expanduser())
    p.add_argument('--decisions',type=Path,default=db.ROOT/'data/cinema-reconciliation/tmdb-reviewed.json')
    p.add_argument('--apply',action='store_true');a=p.parse_args()
    if not a.token_file.expanduser().is_file():p.error('TMDB token file missing')
    decisions=list(json.loads(a.decisions.read_text())['decisions'].values())
    api=tmdb.API(a.token_file.expanduser().read_text().strip(),Path('/tmp/t0mb-tmdb-cache'))
    keys=sorted({(d['tmdb']['type'],int(d['tmdb']['id'])) for d in decisions})
    def fetch(key):return key,api.get(f'{key[0]}/{key[1]}',append_to_response='credits')
    with ThreadPoolExecutor(max_workers=4) as pool:metadata=dict(pool.map(fetch,keys))
    with (db.ROOT/'cinema/.collection.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        original=db.read();old_films=json.loads((db.ROOT/'cinema/films.json').read_text());db.validate(original)
        data,films,journal=integrate(original,old_films,decisions,metadata)
        # Validate against the proposed canonical table, before writing either source.
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'cinema').mkdir();(root/'data/film-shelf').mkdir(parents=True)
            (root/'cinema/films.json').write_text(json.dumps(films))
            (root/'data/film-shelf/photos.json').symlink_to(db.ROOT/'data/film-shelf/photos.json')
            db.validate(data,root,check_photos=False)
        summary={'reviewed_decisions':len(decisions),'new_canonical_films':len(journal['new_canonical_ids']),'new_links':len(journal['work_changes']),'applied':a.apply}
        if a.apply and journal['work_changes']:
            journal.update(before_collection=original,before_films=old_films,decisions=decisions)
            digest=hashlib.sha256(json.dumps(decisions,sort_keys=True).encode()).hexdigest()[:12]
            target=db.ROOT/f'data/cinema-reconciliation/tmdb-applied-{digest}.json'
            if target.exists():raise ValueError('Recovery journal already exists; inspect before repeating')
            db.atomic_text(target,json.dumps(journal,ensure_ascii=False,indent=2)+'\n')
            db.atomic_text(db.ROOT/'cinema/films.json',json.dumps(films,ensure_ascii=False,indent=2)+'\n')
            try:db.save(data)
            except Exception:
                db.atomic_text(db.ROOT/'cinema/films.json',json.dumps(old_films,ensure_ascii=False,indent=2)+'\n');raise
        print(json.dumps(summary))
if __name__=='__main__':main()
