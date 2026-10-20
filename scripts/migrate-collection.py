#!/usr/bin/env python3
"""One-time, lossless source migration. Refuses to replace an existing collection."""
import csv,json,re
from pathlib import Path
import collection_data as db

def migrate(root=db.ROOT):
    target=root/'cinema/collection.json'
    if target.exists(): raise ValueError('collection.json already exists; migration will not overwrite it')
    evidence=root/'data/film-shelf'
    rows=list(csv.DictReader((evidence/'imports/shelf-transcription.csv').open()))
    additions={r['shelf_id']:r for r in json.loads((evidence/'imports/favourite-editions.json').read_text())}
    data=dict(schema_version=1,labels=[],works=[],editions=[],copies=[],migration={'source':'data/film-shelf/imports/shelf-transcription.csv','date':'2026-10-19','policy':'No title-only deduplication or diary links. Provisional work records can be merged after identity confirmation.'})
    labels={}
    def label_id(name):
        if not name:return None
        if name not in labels:
            ident='label-'+re.sub('[^a-z0-9]+','-',name.lower()).strip('-')
            labels[name]=ident;data['labels'].append(dict(id=ident,name=name,aliases=[]))
        return labels[name]
    known=[('Arrow Academy','Arrow Films','Arrow Academy'),('Arrow','Arrow Films','Arrow Video'),('Kino Lorber','Kino Lorber','KL Studio Classics'),('Criterion','Criterion','The Criterion Collection'),('Eureka','Eureka Entertainment',None),('BFI','BFI',None),('Lionsgate','Lionsgate',None),('Universal','Universal Pictures',None),('HBO','Warner Bros.','HBO')]
    for r in rows:
        n=r['id'].split('-')[1];x=additions.get(r['id'],{})
        name=x.get('label','');imprint=x.get('imprint') or None
        if not x:
            for token,l,imp in known:
                if token in r['edition_notes']:
                    name,imprint=l,imp;break
        # Film-studio logos on fan-made packaging are not the releasing label.
        if 'Despecialized' in r['edition_notes']:name='';imprint=None
        formats=[s.strip() for s in re.split(r'[;+]', r['format']) if s.strip() in db.FORMATS]
        wid='work-'+n;eid='edition-'+n
        titles=[t.strip() for t in r['contents'].split(';') if t.strip()] if r['kind'] in {'box_set','short_collection'} else [r['title']]
        contents=[]
        for j,title in enumerate(titles):
            work_id=wid+(f'-{j+1}' if len(titles)>1 else '')
            kind=r['kind'] if r['kind'] in db.KINDS else 'unknown'
            # A collection title string alone is insufficient evidence of work type/year.
            work=dict(id=work_id,title=title,kind=kind,year=int(r['year']) if r['year'] and (len(titles)==1 or r['id']=='shelf-0525') else None,
                      catalogue_film_id=r['catalogue_film_id'] or None,identity_status='confirmed' if r['status']=='curated' and r['kind'] not in {'box_set','short_collection'} else 'provisional',external_ids={})
            data['works'].append(work)
            coverage={'description':r['contents']} if r['kind']=='tv_series' and r['contents'] else {}
            contents.append(dict(work_id=work_id,display_title=title,role='unspecified' if r['kind'] in {'box_set','short_collection'} else 'main',cut=None,coverage=coverage))
        notes=r['edition_notes'];packaging='steelbook' if 'steelbook' in notes.lower() else None
        catalog=x.get('catalogue_number') or None
        if not catalog:
            m=re.search(r'\b(?:FCD|OPTBD|LGB|EKA|MTBD)\d+\b',notes)
            if m:catalog=m.group()
        edition=dict(id=eid,title=r['title'],kind=r['kind'],label_id=label_id(name),imprint=imprint,formats=formats,
                     catalogue_number=catalog,barcode=None,packaging=packaging,country=None,release_date=None,
                     discs=[],contents=contents,list_contents=bool(r['contents']),notes=notes,status=r['status'],review_notes=r['review_notes'],
                     evidence={'source_photos':r['source_photos'].split(';'),'description':'Imported photo transcription / research / owner confirmations; status does not verify every edition field.'})
        copy=dict(id=r['id'],edition_id=eid,condition='faulty' if r['id']=='shelf-0604' else 'unknown',ownership='owned',
                  location='Favourite film shelf' if x else None,acquired_on=None,notes='',source_photos=[p.strip() for p in r['source_photos'].split(';')],provenance='Shelf photographs and recorded owner confirmations')
        if r['id']=='shelf-0604':
            copy['notes']=notes;edition['notes']='Second Lifeboat copy; exact release not established.'
        data['editions'].append(edition);data['copies'].append(copy)
    db.save(data,root)
    return db.export(data,root)

if __name__=='__main__':print(migrate())
