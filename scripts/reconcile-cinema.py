#!/usr/bin/env python3
"""Apply only reviewed work links and unambiguous imported review/viewing links.

Dry-run by default. Preserves review text, all existing fields/IDs, and diary data.
"""
import argparse,copy,datetime,hashlib,importlib.util,json
from pathlib import Path
import collection_data as db

spec=importlib.util.spec_from_file_location('relations',Path(__file__).with_name('audit-cinema-relations.py'))
audit_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit_module)

def reconcile(root,apply=False):
    report=audit_module.audit(root)
    if report['errors']:raise ValueError(str(report['errors']))
    data=db.read(root);works=db.index(data['works']);films={f['id']:f for f in json.loads((root/'cinema/films.json').read_text())}
    decisions=json.loads((root/'data/cinema-reconciliation/confirmed-links.json').read_text())['links']
    work_changes=[];review_changes=[]
    aliases={m['source']['id']:m['target_id'] for m in data.get('work_merge_history',[])}
    for decision in decisions:
        work_id=decision['work_id'];seen=set()
        while work_id in aliases:
            if work_id in seen:raise ValueError('Cyclic work merge history')
            seen.add(work_id);work_id=aliases[work_id]
        w=works[work_id];f=films[decision['film_id']]
        if str(f.get('year'))!=str(decision['year']):raise ValueError('Reviewed film year changed')
        if w.get('year') is not None and str(w['year'])!=str(decision['year']):raise ValueError('Conflicting work year')
        if w.get('catalogue_film_id') and w['catalogue_film_id']!=f['id']:raise ValueError('Existing different canonical link')
        if w.get('catalogue_film_id')==f['id']:continue
        before=copy.deepcopy(w)
        w.update(catalogue_film_id=f['id'],year=decision['year'],identity_status='confirmed')
        w['identity_evidence']={'type':'researched','evidence':decision['evidence'],'sources':decision['sources'],'confirmed_on':'2026-10-19'}
        work_changes.append({'id':w['id'],'before':before,'after':copy.deepcopy(w)})
    for c in report['review_viewing_candidates']:
        if c['date_conflict']:continue
        path=root/c['file'];before=path.read_text();lines=before.splitlines(keepends=True)
        end=next(i for i in range(1,len(lines)) if lines[i].strip()=='---')
        after=''.join(lines[:end])+f'viewing: {json.dumps(c["viewing_id"])}\n'+''.join(lines[end:])
        # Never rewrite/re-serialize existing front matter or Markdown body.
        review_changes.append({'file':c['file'],'review_id':c['review_id'],'viewing_id':c['viewing_id'],'before_sha256':hashlib.sha256(before.encode()).hexdigest(),'before':before,'after':after})
    db.validate(data,root)
    summary={'work_links':len(work_changes),'review_viewing_links':len(review_changes)}
    if apply and (work_changes or review_changes):
        journal=root/'data/cinema-reconciliation/applied.json'
        history=json.loads(journal.read_text()) if journal.exists() else {'batches':[]}
        # Persist recovery evidence first, before any source mutation.
        history['batches'].append({'date':'2026-10-19','summary':summary,'work_changes':work_changes,'review_changes':review_changes})
        db.atomic_text(journal,json.dumps(history,ensure_ascii=False,indent=2)+'\n')
        db.save(data,root)
        for c in review_changes:db.atomic_text(root/c['file'],c['after'])
        db.export(data,root)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--apply',action='store_true');args=p.parse_args()
    import fcntl
    with (db.ROOT/'cinema/.collection.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        print(json.dumps(reconcile(db.ROOT,args.apply),indent=2))
