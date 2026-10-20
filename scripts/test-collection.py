#!/usr/bin/env python3
"""Daily collection operations against isolated canonical-catalogue fixtures."""
import json,subprocess,sys,tempfile,unittest
from pathlib import Path
import collection_data as db
SCRIPT=Path(__file__).with_name('collection.py')

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'cinema').mkdir()
        self.films=[dict(id='film-a',slug='example-1990',title='Example',year='1990'),dict(id='film-b',slug='second-2000',title='Second',year='2000')]
        (self.root/'cinema/films.json').write_text(json.dumps(self.films))
        (self.root/'cinema/viewings.json').write_text('[]')
        db.save(dict(schema_version=3,labels=[],editions=[],copies=[]),self.root)
    def runcli(self,*args,ok=True):
        p=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr);return p
    def test_add_copy_and_edition_share_canonical_film(self):
        before=(self.root/'cinema/films.json').read_bytes()
        self.runcli('add','Example','--label','Kino','--format','4K UHD','--barcode','001234567890')
        self.runcli('copy','edition-0001','--condition','faulty')
        self.runcli('add','Example','--film','example-1990','--new-edition','--label','Arrow','--format','Blu-ray')
        d=db.read(self.root)
        self.assertNotIn('works',d)
        self.assertEqual([len(d[k]) for k in ('editions','copies')],[2,3])
        self.assertEqual(d['editions'][0]['contents'],[{'film':'film-a','role':'main'}])
        self.assertEqual(d['copies'][1]['condition'],'faulty')
        self.assertEqual(d['copies'][0],dict(id='shelf-0001',edition_id='edition-0001'))
        self.assertEqual(d['editions'][0]['barcode'],'001234567890')
        self.assertEqual((self.root/'cinema/films.json').read_bytes(),before)
        self.assertEqual((self.root/'cinema/viewings.json').read_text(),'[]')
    def test_duplicate_and_invalid_writes_leave_source_unchanged(self):
        self.runcli('add','Example','--barcode','001234567890')
        source=self.root/'cinema/collection.json';before=source.read_bytes()
        self.runcli('add','Example',ok=False)
        self.runcli('add','Second','--barcode','001234567890',ok=False)
        self.runcli('edit','edition-0001','--release-date','2026-99-12',ok=False)
        self.runcli('add','Unknown','--film','missing',ok=False)
        self.runcli('add','Not catalogued',ok=False)
        self.assertEqual(source.read_bytes(),before)
    def test_box_contents_create_one_copy_and_are_searchable(self):
        self.runcli('add','Double feature','--film','film-a','--film','film-b','--label','Arrow')
        d=db.read(self.root);self.assertEqual(len(d['copies']),1)
        self.assertEqual([x['film'] for x in d['editions'][0]['contents']],['film-a','film-b'])
        self.assertIn('Double feature',self.runcli('search','Second').stdout)
    def test_ambiguous_title_requires_explicit_identity(self):
        self.films.append(dict(id='remake',slug='example-2020',title='Example',year='2020'))
        (self.root/'cinema/films.json').write_text(json.dumps(self.films))
        self.runcli('add','Example',ok=False)
        self.runcli('add','Example','--year','2020')
        self.assertEqual(db.read(self.root)['editions'][0]['contents'][0]['film'],'remake')
    def test_defaults_and_optional_fields_round_trip(self):
        self.runcli('add','Example','--cut','Extended','--coverage','Part one')
        self.runcli('set-copy','shelf-0001','--condition','faulty','--ownership','loaned')
        self.runcli('set-copy','shelf-0001','--condition','unknown','--ownership','owned')
        d=db.read(self.root);self.assertEqual(d['copies'][0],dict(id='shelf-0001',edition_id='edition-0001'))
        self.assertEqual(d['editions'][0]['contents'][0]['coverage'],'Part one')
        self.runcli('export');p=self.root/'generated/collection/collection.json';first=p.read_bytes();self.runcli('export');self.assertEqual(first,p.read_bytes())
    def test_missing_references_are_rejected(self):
        self.runcli('add','Example');d=db.read(self.root);d['editions'][0]['contents'][0]['film']='missing'
        with self.assertRaises(ValueError):db.validate(d,self.root)

if __name__=='__main__':unittest.main()
