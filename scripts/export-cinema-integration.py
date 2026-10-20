#!/usr/bin/env python3
"""Build an offline, public-safe joined graph; does not publish or change source data."""
import argparse,importlib.util,json
from pathlib import Path
import collection_data as db

spec=importlib.util.spec_from_file_location('audit',Path(__file__).with_name('audit-cinema-relations.py'))
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

def build(root=db.ROOT):
    checks=audit.audit(root)
    if checks['errors']:raise ValueError(str(checks['errors']))
    data=db.read(root);labels,works,editions,copies=db.validate(data,root)
    films=json.loads((root/'cinema/films.json').read_text());viewings=json.loads((root/'cinema/viewings.json').read_text())
    reviews=[audit.reader.read_review(p)['metadata'] for p in sorted((root/'cinema/reviews').glob('*.md'))]
    records={f['id']:{'id':f['id'],'title':f['title'],'year':f.get('year'),'tmdb':f.get('tmdb'),'url':'/films/'+f['slug']+'/',
                         'watched':f.get('watched') is True or any(v['film']==f['id'] for v in viewings),
                         'viewings':[{'id':v['id'],'date':v['date'],'rating':v.get('rating'),'rewatch':v.get('rewatch',False)} for v in viewings if v['film']==f['id']],
                         'reviews':[],'diary_notes':[],'physical_media':[]} for f in films}
    notes=json.loads((root/'cinema/entries.json').read_text()) if (root/'cinema/entries.json').exists() else []
    for note in notes:
        records[note['film']]['diary_notes'].append({k:note.get(k) for k in ('id','date','kind','note')})
    for review in reviews:
        if review.get('draft') is True:continue
        record=records[review['film']]
        record['reviews'].append({'id':review['id'],'title':review['title'],'date':review['date'],'viewing_id':review.get('viewing'),'diary_entry_id':review.get('diary_entry'),
                                  'url':record['url']+'reviews/'+review['id']+'/'})
    for edition in editions.values():
        # Loaned copies remain owned; sold/disposed/lost copies are not currently available holdings.
        holdings=[c for c in copies.values() if c['edition_id']==edition['id'] and c['ownership'] in {'owned','loaned'}]
        if not holdings:continue
        per_work={}
        for content in edition['contents']:
            work=works[content['work_id']];fid=work.get('catalogue_film_id')
            if not fid:continue
            per_work.setdefault(fid,[]).append({'cut':content['cut'],'coverage':content['coverage'],'role':content['role']})
        for fid,versions in per_work.items():
            # Explicit allowlist: no purchase data, locations, copy notes or photo paths.
            records[fid]['physical_media'].append({'edition_id':edition['id'],'title':edition['title'],
                 'label':labels[edition['label_id']]['name'] if edition.get('label_id') else None,'imprint':edition.get('imprint'),
                 'formats':edition['formats'],'catalogue_number':edition.get('catalogue_number'),'packaging':edition.get('packaging'),
                 'copy_count':len(holdings),'versions':versions})
    for record in records.values():record['owned']=True if record['physical_media'] else None;record['reviewed']=bool(record['reviews'])
    return {'schema_version':1,'policy':'Confirmed collection links only. Missing physical_media means no confirmed linked holding, NOT proof a film is unowned. Private copy fields and drafts excluded. Existing IDs and URLs preserved.',
            'summary':dict(checks['counts'],canonical_records_with_linked_holdings=sum(r['owned'] is True for r in records.values())),
            'works':list(records.values())}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,default=db.ROOT/'generated/cinema-integration.json');args=p.parse_args()
    data=build();db.atomic_text(args.output,json.dumps(data,ensure_ascii=False,indent=2)+'\n');print(json.dumps(data['summary'],indent=2))
