#!/usr/bin/env python3
"""Manage physical releases and copies without adding viewings or changing reviews."""
import argparse
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
    data['labels'].append(dict(id=ident,name=name));return ident,imprint or default

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=db.ROOT,help=argparse.SUPPRESS)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('search',help='Search titles, labels, barcodes and catalogue numbers');s.add_argument('query')
    s=sub.add_parser('show');s.add_argument('id')
    sub.add_parser('export');sub.add_parser('validate')
    s=sub.add_parser('add',help='Add a release and an owned copy; never log a viewing')
    s.add_argument('title');s.add_argument('--year',type=int,help='Narrow a canonical title match')
    s.add_argument('--film',action='append',default=[],help='Canonical film ID or slug; repeat for a box set')
    s.add_argument('--coverage',help='Season/episode coverage for a single TV series')
    s.add_argument('--cut',help='Cut/version of a single film, e.g. theatrical or director cut')
    s.add_argument('--new-edition',action='store_true',help='Explicitly allow another edition with an existing title')
    s.add_argument('--location');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc'],default='unknown')
    edition_args(s)
    s=sub.add_parser('edit',help='Update an edition’s release metadata');s.add_argument('edition_id');edition_args(s)
    s=sub.add_parser('copy',help='Add another owned copy of an existing edition');s.add_argument('edition_id');s.add_argument('--location');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc'],default='unknown');s.add_argument('--notes',default='')
    s=sub.add_parser('set-copy',help='Change condition/location without changing the edition');s.add_argument('copy_id');s.add_argument('--condition',choices=['unknown','good','damaged','faulty','missing_disc']);s.add_argument('--location');s.add_argument('--notes');s.add_argument('--ownership',choices=['owned','loaned','sold','disposed','lost'])
    return p

def edition_args(s):
    s.add_argument('--label');s.add_argument('--imprint');s.add_argument('--format',action='append',choices=sorted(db.FORMATS),dest='formats')
    s.add_argument('--barcode');s.add_argument('--catalogue-number');s.add_argument('--packaging');s.add_argument('--country');s.add_argument('--release-date');s.add_argument('--notes')

def apply(data,args,films):
    editions=db.index(data['editions']);copies=db.index(data['copies'])
    if args.command=='add':
        same=[e for e in editions.values() if db.normalise(e['title'])==db.normalise(args.title)]
        if same and not args.new_edition:raise ValueError('Already present: '+', '.join(e['id'] for e in same)+'. Use copy EDITION_ID for another copy, or --new-edition for a distinct release.')
        selected=[]
        for key in args.film:
            matches=[f for f in films.values() if key in (f['id'],f['slug'])]
            if len(matches)!=1: raise ValueError('Unknown or ambiguous film ID/slug: '+key)
            selected.append(matches[0]['id'])
        if not selected:
            matches=[f for f in films.values() if db.normalise(f['title'])==db.normalise(args.title)
                     and (args.year is None or str(f.get('year'))==str(args.year))]
            if len(matches)!=1:
                choices=', '.join(f['id'] for f in matches)
                raise ValueError('Choose --film ID: '+choices if matches else
                                 'Add this title to the canonical catalogue first with cinema.py film --title TITLE --year YEAR --unwatched; then use --film ID.')
            selected=[matches[0]['id']]
        if len(selected)!=len(set(selected)): raise ValueError('Repeated --film ID')
        if args.year is not None and any(str(films[k].get('year'))!=str(args.year) for k in selected):
            raise ValueError('--year conflicts with selected film')
        if len(selected)>1 and (args.coverage or args.cut):
            raise ValueError('Set coverage/cuts per constituent in collection.json for multi-film editions')
        e=dict(id=new_id(data['editions'],'edition'),title=args.title,
               contents=[db.sparse(dict(film=k,role='main',cut=args.cut,coverage=args.coverage)) for k in selected])
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
        c=db.sparse(dict(id=new_id(data['copies'],'shelf'),edition_id=args.edition_id,
                        condition=args.condition if args.condition!='unknown' else None,location=args.location,
                        notes=args.notes if args.command=='copy' else None))
        data['copies'].append(c);return c['id']+' / '+args.edition_id
    if args.command=='set-copy':
        c=copies.get(args.copy_id)
        if c is None:raise ValueError('Unknown copy ID')
        for k in ('condition','location','notes','ownership'):
            if getattr(args,k) is not None:
                value=getattr(args,k)
                if (k,value) in {('condition','unknown'),('ownership','owned')} or value=='':c.pop(k,None)
                else:c[k]=value
        return c['id']
    raise ValueError('Unknown mutation')

def main(argv=None):
    args=parser().parse_args(argv);root=args.root.resolve()
    # Serialise CLI writers; the one source JSON is replaced atomically.
    lock=root/'cinema/.collection.lock'
    with lock.open('a') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        data=db.read(root);_,films,_,_=db.validate(data,root)
        if args.command=='validate':print('Collection valid');return
        if args.command=='export':print(json.dumps(db.export(data,root)));return
        if args.command=='show':
            if args.id in films:print(json.dumps(films[args.id],ensure_ascii=False,indent=2));return
            for key in ('editions','copies','labels'):
                for item in data[key]:
                    if item['id']==args.id:print(json.dumps(item,ensure_ascii=False,indent=2));return
            raise ValueError('Unknown ID')
        if args.command=='search':
            labels=db.index(data['labels'])
            for e in data['editions']:
                name=labels[e['label_id']]['name'] if e.get('label_id') else '?'
                text=' '.join(str(e.get(k) or '') for k in ('title','barcode','catalogue_number','imprint'))+' '+name+' '+' '.join(films[x['film']]['title'] for x in e.get('contents', []))
                if db.normalise(args.query) in db.normalise(text):
                    count=sum(c['edition_id']==e['id'] and c.get('ownership','owned')=='owned' for c in data['copies'])
                    print(f"{e['id']} | {e['title']} | {name} | {', '.join(e.get('formats', [])) or '?'} | {count} owned | films: {', '.join(c['film'] for c in e.get('contents', []))}")
            return
        result=apply(data,args,films);db.save(data,root);db.export(data,root);print('Saved '+result)

if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,OSError) as exc:print('Error: '+str(exc),file=sys.stderr);sys.exit(1)
