#!/usr/bin/env python3
"""Count currently catalogued owned identities, not discs or packages.

Provisional identities remain provisional. Unlisted bonus features/shorts are not
inferred; remakes stay distinct and cuts of the same film share an identity.
"""
import collections,json
import collection_data as db

def counts(data, films):
    catalogue={f['id']:f for f in films};editions=db.index(data['editions'])
    copies=[c for c in data['copies'] if c.get('ownership','owned') in {'owned','loaned'}]
    owned={c['edition_id'] for c in copies}
    ids={c['film'] for e in owned for c in editions[e].get('contents', [])}
    identities={key:dict(catalogue[key],kind=db.film_kind(catalogue[key])) for key in ids}
    kinds=collections.Counter(w['kind'] for w in identities.values())
    return dict(physical_packages=len(copies),distinct_editions=len(owned),
                catalogued_identities=len(identities),by_kind=dict(sorted(kinds.items())),
                films_including_documentaries_and_tv_films=sum(kinds[k] for k in ('film','documentary','tv_film')),
                caveat='Provisional count of enumerated works, not an exhaustive count of bonus films or shorts.',
                works=[dict(id=k,title=w['title'],kind=w['kind'],year=w.get('year')) for k,w in sorted(identities.items())])

if __name__=='__main__':
    data=db.read();db.validate(data)
    result=counts(data,json.loads((db.ROOT/'cinema/films.json').read_text()))
    db.atomic_text(db.ROOT/'generated/collection-counts.json',json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='works'},indent=2))
