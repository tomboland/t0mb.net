#!/usr/bin/env python3
"""Count currently catalogued owned identities, not discs or packages.

Provisional identities remain provisional. Unlisted bonus features/shorts are not
inferred; remakes stay distinct and cuts of the same film share an identity.
"""
import collections,json
import collection_data as db

def counts(data):
    works=db.index(data['works']);editions=db.index(data['editions'])
    copies=[c for c in data['copies'] if c['ownership'] in {'owned','loaned'}]
    owned={c['edition_id'] for c in copies}
    ids={c['work_id'] for e in owned for c in editions[e]['contents']}
    identities={}
    for ident in sorted(ids):
        w=works[ident]
        key=w.get('catalogue_film_id') or ident
        if key in identities and identities[key]['kind']!=w['kind']:
            raise ValueError('Conflicting identity classifications: '+key)
        identities[key]=w
    kinds=collections.Counter(w['kind'] for w in identities.values())
    return dict(physical_packages=len(copies),distinct_editions=len(owned),
                catalogued_identities=len(identities),by_kind=dict(sorted(kinds.items())),
                films_including_documentaries_and_tv_films=sum(kinds[k] for k in ('film','documentary','tv_film')),
                caveat='Provisional count of enumerated works, not an exhaustive count of bonus films or shorts.',
                works=[dict(id=k,title=w['title'],kind=w['kind'],year=w.get('year')) for k,w in sorted(identities.items())])

if __name__=='__main__':
    data=db.read();db.validate(data)
    result=counts(data)
    db.atomic_text(db.ROOT/'generated/collection-counts.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='works'},indent=2))
