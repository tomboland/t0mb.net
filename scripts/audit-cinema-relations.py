#!/usr/bin/env python3
"""Read-only cross-catalogue integrity audit and proposed identity links. No auto-matching writes."""
import argparse
import csv
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
    ei=indexed(entries,'diary notes')
    for v in viewings+entries:
        if v['film'] not in fi:errors.append(f'{v["id"]}: missing film {v["film"]}')
    watch_links=[];url_index=defaultdict(list)
    for v in viewings:
        if v.get('letterboxd_url'):url_index[v['letterboxd_url']].append(v)
    for r in reviews:
        m=r['metadata']
        if m['film'] not in fi:errors.append(f'{m["id"]}: missing film {m["film"]}')
        if m.get('diary_entry') and (m['diary_entry'] not in ei or ei[m['diary_entry']]['film']!=m['film']):errors.append(f'{m["id"]}: invalid diary note relationship')
        if m.get('viewing') and m.get('diary_entry'):errors.append(f'{m["id"]}: review has both viewing and diary note')
        if m.get('viewing'):
            if m['viewing'] not in vi or vi[m['viewing']]['film']!=m['film']:errors.append(f'{m["id"]}: invalid viewing relationship')
        elif m.get('letterboxd_url'):
            matches=[v for v in url_index[m['letterboxd_url']] if v['film']==m['film']]
            if len(matches)==1:watch_links.append({'review_id':m['id'],'viewing_id':matches[0]['id'],'file':r['source_file'],'basis':'same film ID and identical Letterboxd entry URL','date_conflict':bool(m.get('watched_date') and m['watched_date']!=matches[0]['date'])})
    titles=defaultdict(dict)
    for f in films:
        for t in {f['title'],f.get('original_title') or f['title']}:
            titles[collection.normalise(t)][f['id']]=f
    links=[];no_candidates=[];linked=0
    for w in data['works']:
        if w.get('catalogue_film_id'):
            linked+=1;continue
        candidates=list(titles.get(collection.normalise(w['title']),{}).values())
        if not candidates:no_candidates.append(w['id']);continue
        sameyear=[f for f in candidates if w.get('year') is not None and str(f.get('year'))==str(w['year'])]
        basis='title_and_year' if len(sameyear)==1 and w['kind'] in {'film','documentary','tv_film','short'} else 'title_only_or_type_unresolved'
        links.append({'work_id':w['id'],'title':w['title'],'year':w['year'],'kind':w['kind'],'basis':basis,'candidates':[{'id':f['id'],'title':f['title'],'year':f.get('year')} for f in (sameyear if basis=='title_and_year' else candidates)]})
    duplicates=defaultdict(list)
    for w in data['works']:duplicates[collection.normalise(w['title'])].append(w['id'])
    groups=[dict(normalised_title=t,work_ids=ids) for t,ids in duplicates.items() if len(ids)>1]
    ext=defaultdict(list)
    for f in films:
        if f.get('tmdb'):ext[(f['tmdb']['type'],str(f['tmdb']['id']))].append(f['id'])
    duplicate_external=[{'tmdb_type':k[0],'tmdb_id':k[1],'film_ids':v} for k,v in ext.items() if len(v)>1]
    viewed={v['film'] for v in viewings};reviewed={r['metadata']['film'] for r in reviews}
    counts={'catalogue_films':len(films),'viewings':len(viewings),'reviews':len(reviews),'published_reviews':sum(r['metadata'].get('draft') is not True for r in reviews),'reviews_with_explicit_viewing':sum(bool(r['metadata'].get('viewing')) for r in reviews),'review_viewing_url_candidates':len(watch_links),'collection_work_records':len(data['works']),'editions':len(data['editions']),'copies':len(data['copies']),'linked_collection_works':linked,'title_year_candidates':sum(x['basis']=='title_and_year' for x in links),'title_only_candidates':sum(x['basis']!='title_and_year' for x in links),'works_without_exact_title_candidate':len(no_candidates),'repeated_collection_title_groups':len(groups),'watched_flag_without_dated_viewing':sum(bool(f.get('watched')) and f['id'] not in viewed for f in films),'duplicate_tmdb_groups':len(duplicate_external)}
    return dict(counts=counts,errors=errors,policy='Candidate matches only; names, years and unknown types do not constitute automatic identity confirmation. No source mutations.',work_link_candidates=links,review_viewing_candidates=watch_links,repeated_work_titles=groups,works_without_exact_title_candidate=no_candidates,duplicate_external_identities=duplicate_external)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'generated/cinema-relations');args=p.parse_args()
    result=audit();args.output_dir.mkdir(parents=True,exist_ok=True)
    (args.output_dir/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    data=collection.read();by_work={w['id']:w for w in data['works']}
    candidates={x['work_id']:x for x in result['work_link_candidates']}
    memberships=defaultdict(list)
    for e in data['editions']:
        for c in e['contents']:memberships[c['work_id']].append(e)
    with (args.output_dir/'unlinked-works.csv').open('w',newline='') as handle:
        fields=['work_id','title','year','kind','edition_ids','edition_titles','photo_ids','catalogue_numbers','candidate_film_ids','candidate_titles_years']
        writer=csv.DictWriter(handle,fieldnames=fields);writer.writeheader()
        for w in by_work.values():
            if w.get('catalogue_film_id'):continue
            es=memberships[w['id']];cs=candidates.get(w['id'],{}).get('candidates',[])
            writer.writerow(dict(work_id=w['id'],title=w['title'],year=w['year'] or '',kind=w['kind'],
                edition_ids='; '.join(e['id'] for e in es),edition_titles='; '.join(e['title'] for e in es),
                photo_ids='; '.join(sorted({p for e in es for p in e.get('evidence',{}).get('source_photos',[])})),
                catalogue_numbers='; '.join(e.get('catalogue_number') or '' for e in es),
                candidate_film_ids='; '.join(c['id'] for c in cs),candidate_titles_years='; '.join(c['title']+' ('+str(c['year'])+')' for c in cs)))
    lines=['# Cinema relationship audit','','Read-only audit; candidates are not confirmed links.','']
    lines+=['| Metric | Count |','|---|---|']+[f'| {k} | {v} |' for k,v in result['counts'].items()]
    lines+=['','## Integrity errors','']+(result['errors'] or ['None found in the checked IDs/foreign keys.'])
    lines+=['','## Title/year candidates (still subject to identity confirmation)','','| Work | Title | Year | Catalogue candidate |','|---|---|---|---|']
    for x in result['work_link_candidates']:
        if x['basis']=='title_and_year':lines.append(f"| {x['work_id']} | {x['title'].replace('|','/')} | {x['year']} | {x['candidates'][0]['id']} |")
    lines+=['','Full candidates, repeated title groups and review/viewing links are in `audit.json`.']
    (args.output_dir/'audit.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(result['counts'],indent=2));print('Integrity errors:',len(result['errors']));print(args.output_dir)
    if result['errors']:raise SystemExit(1)

if __name__=='__main__':main()
