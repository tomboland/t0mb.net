#!/usr/bin/env python3
"""Integration semantics and non-destructive reconciliation checks, using temp fixtures."""
import importlib.util,json,tempfile,unittest
from pathlib import Path
import collection_data as db

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(file));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
exporter=module('integration','export-cinema-integration.py');reconciler=module('reconciler','reconcile-cinema.py')

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        for d in ('cinema/reviews','data/film-shelf','data/cinema-reconciliation'):(self.root/d).mkdir(parents=True)
        self.write('cinema/films.json',[{'id':'lb-AbC','slug':'example-1990','title':'Example','year':'1990','watched':True,'tmdb':{'type':'movie','id':1}},{'id':'film-unwatched','slug':'unwatched-2000','title':'Unwatched','year':'2000','watched':False}])
        self.write('cinema/viewings.json',[{'id':'watch-1','film':'lb-AbC','date':'2020-01-01','letterboxd_url':'entry-1'}])
        self.write('data/film-shelf/photos.json',{'photos':[]})
        self.write('data/cinema-reconciliation/confirmed-links.json',{'links':[{'work_id':'work-1','film_id':'lb-AbC','year':1990,'evidence':'fixture','sources':[]}]})
        self.body='\nExact prose & formatting.\n\n- A list\n'
        (self.root/'cinema/reviews/a.md').write_text('---\nid: "review-1"\nfilm: "lb-AbC"\ntitle: "Example"\ndate: "2020-01-02"\nletterboxd_url: "entry-1"\ndraft: false\n---\n'+self.body)
        (self.root/'cinema/reviews/draft.md').write_text('---\nid: "draft-1"\nfilm: "lb-AbC"\ntitle: "Private draft"\ndate: "2020-01-02"\ndraft: true\n---\nSecret draft prose\n')
        self.data={'schema_version':1,'labels':[],'works':[{'id':'work-1','title':'Example','year':1990,'kind':'film','catalogue_film_id':None,'identity_status':'provisional'}],
          'editions':[{'id':'edition-1','title':'Example release','kind':'film','label_id':None,'formats':['Blu-ray'],'status':'transcribed','contents':[{'work_id':'work-1','role':'main','cut':None,'coverage':{}}]}],
          'copies':[{'id':'shelf-0001','edition_id':'edition-1','condition':'faulty','ownership':'owned','source_photos':[],'provenance':'manual','location':'Secret location','notes':'Private notes'}]}
        db.save(self.data,self.root)
    def write(self,p,value):(self.root/p).write_text(json.dumps(value))
    def test_reconcile_is_idempotent_preserves_prose_and_diary(self):
        original=(self.root/'cinema/viewings.json').read_bytes();film=(self.root/'cinema/films.json').read_bytes()
        self.assertEqual(reconciler.reconcile(self.root,True),{'work_links':1,'review_viewing_links':1})
        self.assertTrue((self.root/'cinema/reviews/a.md').read_text().endswith(self.body))
        self.assertEqual(reconciler.reconcile(self.root,True),{'work_links':0,'review_viewing_links':0})
        self.assertEqual((self.root/'cinema/viewings.json').read_bytes(),original);self.assertEqual((self.root/'cinema/films.json').read_bytes(),film)
    def test_projection_uses_canonical_id_hides_private_fields_and_drafts(self):
        reconciler.reconcile(self.root,True);d=exporter.build(self.root);r=d['works'][0]
        self.assertEqual(r['id'],'lb-AbC');self.assertTrue(r['owned']);self.assertEqual(len(r['physical_media']),1)
        self.assertEqual(r['reviews'][0]['viewing_id'],'watch-1');self.assertEqual(r['reviews'][0]['url'],'/films/example-1990/reviews/review-1/')
        for secret in ('Secret location','Private notes','draft-1','Secret draft prose'):self.assertNotIn(secret,json.dumps(d))
        self.assertIsNone(d['works'][1]['owned']);self.assertFalse(d['works'][1]['watched'])
    def test_conflicting_year_and_media_type_are_rejected(self):
        self.data['works'][0]['catalogue_film_id']='lb-AbC';self.data['works'][0]['year']=2000
        with self.assertRaises(ValueError):db.validate(self.data,self.root)
        self.data['works'][0]['year']=1990;self.data['works'][0]['kind']='tv_series'
        with self.assertRaises(ValueError):db.validate(self.data,self.root)
    def test_non_viewing_notes_preserve_review_relation_without_counting_watches(self):
        self.write('cinema/entries.json',[{'id':'note-1','film':'lb-AbC','date':'2020-01-02','kind':'note','note':'Flippant entry'}])
        p=self.root/'cinema/reviews/a.md'
        p.write_text(p.read_text().replace('letterboxd_url: "entry-1"','diary_entry: "note-1"'))
        d=exporter.build(self.root);r=d['works'][0]
        self.assertEqual(len(r['viewings']),1)
        self.assertEqual(r['diary_notes'][0]['id'],'note-1')
        self.assertEqual(r['reviews'][0]['diary_entry_id'],'note-1')
        self.assertIsNone(r['reviews'][0]['viewing_id'])

    def test_multiple_copies_share_one_release_in_projection(self):
        reconciler.reconcile(self.root,True);d=db.read(self.root);c=dict(d['copies'][0],id='shelf-0002');d['copies'].append(c);db.save(d,self.root)
        p=exporter.build(self.root)['works'][0]['physical_media'];self.assertEqual(len(p),1);self.assertEqual(p[0]['copy_count'],2)

if __name__=='__main__':unittest.main()
