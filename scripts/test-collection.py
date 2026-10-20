#!/usr/bin/env python3
"""Behavioural checks against isolated fixtures; never edits the real collection."""
import copy,hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
import collection_data as db
SCRIPT=Path(__file__).with_name('collection.py')

class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        (self.root/'cinema').mkdir()
        (self.root/'cinema/films.json').write_text('[{"id":"existing-film","title":"Known film","year":1990}]')
        (self.root/'cinema/viewings.json').write_text('[]')
        self.d={'schema_version':2,'labels':[],'works':[],'editions':[],'copies':[]};db.save(self.d,self.root)
    def runcli(self,*args,ok=True):
        p=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),*args],capture_output=True,text=True)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr);return p
    def test_add_copy_and_edition_are_distinct_and_diary_untouched(self):
        before=(self.root/'cinema/films.json').read_bytes()
        self.runcli('add','Example','--year','1990','--label','Kino','--format','4K UHD','--barcode','001234567890')
        self.runcli('copy','edition-0001','--condition','faulty')
        self.runcli('add','Example','--work','work-0001','--new-edition','--label','Arrow','--format','Blu-ray')
        d=db.read(self.root);self.assertEqual([len(d[k]) for k in ('works','editions','copies')],[1,2,3])
        self.assertEqual(d['copies'][1]['condition'],'faulty');self.assertEqual(d['copies'][0]['condition'],'unknown')
        self.assertEqual(d['editions'][0]['barcode'],'001234567890');self.assertEqual(d['labels'][0]['name'],'Kino Lorber')
        self.assertEqual((self.root/'cinema/films.json').read_bytes(),before)
        self.assertEqual((self.root/'cinema/viewings.json').read_text(),'[]')
    def test_duplicate_and_invalid_writes_leave_source_unchanged(self):
        self.runcli('add','Example','--year','1990','--barcode','001234567890')
        source=self.root/'cinema/collection.json';before=source.read_bytes()
        self.runcli('add','Example',ok=False)
        self.runcli('add','Other','--barcode','001234567890',ok=False)
        self.runcli('edit','edition-0001','--release-date','2026-99-12',ok=False)
        self.runcli('link','work-0001','missing-film',ok=False)
        self.assertEqual(source.read_bytes(),before)
    def test_box_contents_can_share_work_without_extra_owned_copies(self):
        self.runcli('add','First');self.runcli('add','Second')
        self.runcli('add','Double feature','--work','work-0001','--work','work-0002','--label','Arrow')
        d=db.read(self.root);self.assertEqual(len(d['works']),2);self.assertEqual(len(d['copies']),3)
        self.assertEqual(len(d['editions'][2]['contents']),2)
    def test_new_box_constituents_do_not_create_phantom_copies(self):
        self.runcli('add','New double','--contains','Alpha','--contains','Beta')
        d=db.read(self.root);self.assertEqual(len(d['works']),2);self.assertEqual(len(d['copies']),1)
        self.assertEqual(d['editions'][0]['kind'],'box_set')
    def test_manual_entries_need_no_photo_and_export_is_regenerable(self):
        self.runcli('add','No photograph','--kind','tv_series')
        self.runcli('export');p=self.root/'generated/collection/collection.json';first=p.read_bytes();self.runcli('export');self.assertEqual(first,p.read_bytes())
        self.assertNotIn('source_photos',db.read(self.root)['copies'][0])
    def test_references_are_validated(self):
        self.runcli('add','Example');d=db.read(self.root);d['copies'][0]['edition_id']='missing'
        with self.assertRaises(ValueError):db.validate(d,self.root)

if __name__=='__main__':unittest.main()
