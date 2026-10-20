#!/usr/bin/env python3
"""Prepare TMDB candidates for unresolved collection works. Never auto-apply matches."""
import argparse,importlib.util,json,os,re
from pathlib import Path
import collection_data as db
spec=importlib.util.spec_from_file_location('tmdb',Path(__file__).with_name('match-tmdb.py'))
tmdb=importlib.util.module_from_spec(spec);spec.loader.exec_module(tmdb)

def search(api,work):
    media='tv' if work['kind']=='tv_series' else 'movie'
    params={'query':re.sub(r'\s*\(\d{4}\)$','',work['title']),'include_adult':'true'}
    # Do not year-filter the API: retain alternatives and differing release years for review.
    rows=api.get('search/'+media,**params).get('results',[])
    return [dict(tmdb={'type':media,'id':r['id']},title=r.get('title') or r.get('name'),
                 original_title=r.get('original_title') or r.get('original_name'),
                 year=(r.get('release_date') or r.get('first_air_date') or '')[:4],
                 overview=r.get('overview'),url=f"https://www.themoviedb.org/{media}/{r['id']}") for r in rows]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--token-file',type=Path,default=Path(os.environ.get('TMDB_TOKEN_FILE','~/.config/t0mb.net/tmdb-token')).expanduser())
    p.add_argument('--work',action='append',help='Restrict to these work IDs; repeatable')
    p.add_argument('--limit',type=int,default=100,help='Maximum works per run; saved results are resumed')
    p.add_argument('--output',type=Path,default=db.ROOT/'generated/collection-tmdb-candidates.json')
    a=p.parse_args()
    if not a.token_file.expanduser().is_file():p.error('TMDB token file missing; supply its path with --token-file. Never put the token in command arguments.')
    api=tmdb.API(a.token_file.expanduser().read_text().strip(),Path('/tmp/t0mb-tmdb-cache'))
    data=db.read();db.validate(data)
    report=json.loads(a.output.read_text()) if a.output.exists() else {'policy':'Candidates only; no identity matches or viewing history changed.','works':{}}
    done=0
    for w in data['works']:
        if w.get('catalogue_film_id') or w['kind']=='calibration' or (a.work and w['id'] not in a.work):continue
        old=report['works'].get(w['id'])
        if old and old['observed_work']==w:continue
        if done>=a.limit:break
        report['works'][w['id']]={'observed_work':w,'candidates':search(api,w)}
        db.atomic_text(a.output,json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        done+=1
    print(json.dumps({'searched':done,'saved_work_results':len(report['works']),'output':str(a.output)}))
if __name__=='__main__':main()
