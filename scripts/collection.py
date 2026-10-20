#!/usr/bin/env python3
"""Manage physical releases and copies without adding viewings or changing reviews."""
import argparse
import copy
import fcntl
import json
import re
import sys
from pathlib import Path
import collection_data as db

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
    data['labels'].append(dict(id=ident,name=name,aliases=[]));return ident,imprint or default

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=db.ROOT,help=argparse.SUPPRESS)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('search',help='Search titles, labels, barcodes and catalogue numbers');s.add_argument('query')
    s=sub.add_parser('show');s.add_argument('id')
    sub.add_parser('export');sub.add_parser('validate')
    s=sub.add_parser('add',help='Add a release and an owned copy; never log a viewing')
    s.add_argument('title');s.add_argument('--year',type=int);s.add_argument('--kind',choices=sorted(db.KINDS),default='film')
    s.add_argument('--work',action='append',default=[],help='Existing work ID; repeat for a box set')
    s.add_argument('--contains',action='append',default=[],metavar='TITLE',help='New constituent work title; repeat for a box set without creating separate owned copies')
    s.add_argument('--coverage',help='Season/episode coverage for a single TV work')
    s.add_argument('--cut',help='Cut/version of a single work, e.g. theatrical or director cut')
    s.add_argument('--new-edition',action='store_true',help='Explicitly allow another edition with an existing title')
    s.add_argument('--location');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc'],default='unknown')
    edition_args(s)
    s=sub.add_parser('edit',help='Update an edition’s release metadata');s.add_argument('edition_id');edition_args(s)
    s=sub.add_parser('copy',help='Add another owned copy of an existing edition');s.add_argument('edition_id');s.add_argument('--location');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc'],default='unknown');s.add_argument('--notes',default='')
    s=sub.add_parser('set-copy',help='Change condition/location without changing the edition');s.add_argument('copy_id');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc']);s.add_argument('--location');s.add_argument('--notes');s.add_argument('--ownership',choices=['owned','loaned','sold','disposed','lost'])
    s=sub.add_parser('link',help='Explicitly link a work to an existing diary film identity');s.add_argument('work_id');s.add_argument('catalogue_film_id')
    s=sub.add_parser('merge-works',help='Explicitly merge two confirmed-identical work records; preserves all editions/copies');s.add_argument('source_id');s.add_argument('target_id')
    return p

def edition_args(s):
    s.add_argument('--label');s.add_argument('--imprint');s.add_argument('--format',action='append',choices=sorted(db.FORMATS),dest='formats')
    s.add_argument('--barcode');s.add_argument('--catalogue-number');s.add_argument('--packaging');s.add_argument('--country');s.add_argument('--release-date');s.add_argument('--notes')

def apply(data,args):
    works=db.index(data['works']);editions=db.index(data['editions']);copies=db.index(data['copies'])
    if args.command=='add':
        same=[e for e in editions.values() if db.normalise(e['title'])==db.normalise(args.title)]
        if same and not args.new_edition:raise ValueError('Already present: '+', '.join(e['id'] for e in same)+'. Use copy EDITION_ID for another copy, or --new-edition for a distinct release.')
        if any(w not in works for w in args.work):raise ValueError('Unknown --work ID')
        if len(args.work) != len(set(args.work)):raise ValueError('Repeated --work ID')
        if args.work and args.year is not None and any(works[w]['year'] != args.year for w in args.work):raise ValueError('--year conflicts with selected work; edit its identity separately')
        if args.contains and args.year is not None:raise ValueError('Set constituent release years separately; --year is not a box-set release year')
        for title in args.contains:
            matching=[w for w in data['works'] if db.normalise(w['title'])==db.normalise(title)]
            if matching:raise ValueError('Constituent already exists: '+', '.join(w['id'] for w in matching)+'. Use --work ID for it.')
            w=dict(id=new_id(data['works'],'work'),title=title,kind=args.kind,year=None,catalogue_film_id=None,identity_status='provisional',external_ids={})
            data['works'].append(w);args.work.append(w['id'])
        if len(args.work)>1 and (args.coverage or args.cut):raise ValueError('Set coverage/cuts per constituent in collection.json for multi-work editions')
        if not args.work:
            matching=[w for w in works.values() if db.normalise(w['title'])==db.normalise(args.title) and (args.year is None or w['year']==args.year)]
            if matching:raise ValueError('Possible existing work: '+', '.join(w['id'] for w in matching)+'. Select explicitly with --work ID (avoids merging remakes).')
            w=dict(id=new_id(data['works'],'work'),title=args.title,kind=args.kind,year=args.year,catalogue_film_id=None,identity_status='provisional',external_ids={})
            data['works'].append(w);args.work=[w['id']]
        e=dict(id=new_id(data['editions'],'edition'),title=args.title,kind='box_set' if len(args.work)>1 else works.get(args.work[0],{'kind':args.kind})['kind'],label_id=None,imprint=None,formats=[],catalogue_number=None,barcode=None,packaging=None,country=None,release_date=None,discs=[],contents=[dict(work_id=w,display_title=None,role='main',cut=args.cut,coverage={'description':args.coverage} if args.coverage else {}) for w in args.work],list_contents=len(args.work)>1,notes='',status='curated',review_notes='',evidence={'description':'Manual entry; only supplied fields are confirmed.'})
        data['editions'].append(e);args.edition_id=e['id']
    if args.command in {'add','edit'}:
        e=next((e for e in data['editions'] if e['id']==args.edition_id),None)
        if e is None:raise ValueError('Unknown edition ID')
        if args.label:e['label_id'],e['imprint']=resolve_label(data,args.label,args.imprint)
        elif args.imprint is not None:e['imprint']=args.imprint
        for k in ('formats','barcode','catalogue_number','packaging','country','release_date','notes'):
            if getattr(args,k) is not None:e[k]=getattr(args,k)
        if args.command=='edit':return e['id']
    if args.command in {'add','copy'}:
        if not any(e['id']==args.edition_id for e in data['editions']):raise ValueError('Unknown edition ID')
        c=dict(id=new_id(data['copies'],'shelf'),edition_id=args.edition_id,condition=args.condition,ownership='owned',location=args.location,acquired_on=None,notes=(args.notes or '') if args.command=='copy' else '',source_photos=[],provenance='Manual addition via collection.py')
        data['copies'].append(c);return c['id']+' / '+args.edition_id
    if args.command=='set-copy':
        c=copies.get(args.copy_id)
        if c is None:raise ValueError('Unknown copy ID')
        for k in ('condition','location','notes','ownership'):
            if getattr(args,k) is not None:c[k]=getattr(args,k)
        return c['id']
    if args.command=='link':
        if args.work_id not in works:raise ValueError('Unknown work ID')
        works[args.work_id]['catalogue_film_id']=args.catalogue_film_id;works[args.work_id]['identity_status']='confirmed';return args.work_id
    if args.command=='merge-works':
        if args.source_id==args.target_id or args.source_id not in works or args.target_id not in works:raise ValueError('Choose two different existing work IDs')
        source,target=works[args.source_id],works[args.target_id]
        for key in ('year','catalogue_film_id'):
            if source.get(key) and target.get(key) and source[key]!=target[key]:raise ValueError('Conflicting '+key+'; resolve before merging')
            if not target.get(key):target[key]=source.get(key)
        if source['kind']!=target['kind'] and 'unknown' not in {source['kind'],target['kind']}:raise ValueError('Conflicting work kinds')
        if target['kind']=='unknown':target['kind']=source['kind']
        for key,value in source.get('external_ids',{}).items():
            if key in target['external_ids'] and target['external_ids'][key]!=value:raise ValueError('Conflicting external identity')
            target['external_ids'][key]=value
        for e in data['editions']:
            for item in e['contents']:
                if item['work_id']==args.source_id:item['work_id']=args.target_id
        data.setdefault('work_merge_history',[]).append({'source':copy.deepcopy(source),'target_id':args.target_id})
        data['works']=[w for w in data['works'] if w['id']!=args.source_id];return args.target_id
    raise ValueError('Unknown mutation')

def main(argv=None):
    args=parser().parse_args(argv);root=args.root.resolve()
    # Serialise CLI writers; the one source JSON is replaced atomically.
    lock=root/'cinema/.collection.lock'
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        data=db.read(root);db.validate(data,root)
        if args.command=='validate':print('Collection valid');return
        if args.command=='export':print(json.dumps(db.export(data,root)));return
        if args.command=='show':
            for key in ('works','editions','copies','labels'):
                for item in data[key]:
                    if item['id']==args.id:print(json.dumps(item,ensure_ascii=False,indent=2));return
            raise ValueError('Unknown ID')
        if args.command=='search':
            labels=db.index(data['labels'])
            for e in data['editions']:
                name=labels[e['label_id']]['name'] if e.get('label_id') else '?'
                text=' '.join(str(e.get(k) or '') for k in ('title','barcode','catalogue_number','imprint'))+' '+name
                if db.normalise(args.query) in db.normalise(text):
                    count=sum(c['edition_id']==e['id'] and c['ownership']=='owned' for c in data['copies'])
                    print(f"{e['id']} | {e['title']} | {name} | {', '.join(e['formats']) or '?'} | {count} owned | works: {', '.join(c['work_id'] for c in e['contents'])}")
            return
        result=apply(data,args);db.save(data,root);db.export(data,root);print('Saved '+result)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError) as exc:print('Error: '+str(exc),file=sys.stderr);sys.exit(1)
