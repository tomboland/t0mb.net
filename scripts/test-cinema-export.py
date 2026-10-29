"""Public exports: privacy, lossless review prose, shared references and content revision."""
import importlib.util,json,tempfile,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
import cinema_export
spec=importlib.util.spec_from_file_location('exporter',Path(__file__).with_name('export-cinema.py'))
exporter=importlib.util.module_from_spec(spec);spec.loader.exec_module(exporter)

class PublicExportTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        (self.root/'cinema/reviews').mkdir(parents=True)
        self.films=[dict(id='film-a',slug='a',title='A',year='2000',liked=False),dict(id='film-b',slug='b',title='B',watched=False)]
        self.write('films',self.films)
        self.write('viewings',[dict(id='v-a',film='film-a',date='2020-01-01'),dict(id='v-b',film='film-a',date='2020-01-01',rating=4)])
        self.write('entries',[dict(id='note-a',film='film-a',date='2020-01-01',note='PRIVATE NOTE PROSE')])
        self.collection=dict(schema_version=3,labels=[dict(id='label-a',name='Arrow')],editions=[dict(id='edition-a',title='Release A',label_id='label-a',formats=['Blu-ray'],barcode='1234567890123',notes='PRIVATE EDITION NOTE',contents=[dict(film='film-a',cut='Extended',coverage='Season 1',role='supplement')])],copies=[dict(id='copy-a',edition_id='edition-a',location='PRIVATE LOCATION',notes='PRIVATE COPY NOTE')])
        self.write('collection',self.collection)
        self.prose='\nExact prose — punctuation,\n\n- a list\n'
        self.review('review-a',viewing='v-b')
        self.review('review-b',diary_entry='note-a')
        self.review('secret-draft',draft=True)
    def write(self,name,data):(self.root/f'cinema/{name}.json').write_text(json.dumps(data))
    def review(self,ident,**extra):
        metadata=dict(id=ident,film='film-a',title=ident,date='2020-01-02',draft=False,**{})
        metadata.update(extra)
        (self.root/f'cinema/reviews/{ident}.md').write_text('---\n'+'\n'.join(k+': '+json.dumps(v) for k,v in metadata.items())+'\n---\n'+self.prose)
    def build(self):
        with patch.object(exporter,'ROOT',self.root):return cinema_export.build(self.root,exporter.read_review)
    def rows(self,packet,filename,key):
        obj=json.loads(packet['files'][filename])[key]
        return [dict(zip(obj['columns'],r)) for r in obj['rows']]
    def test_allowlist_and_review_associations_are_lossless(self):
        p=self.build();all_text=''.join(p['files'].values())
        self.assertNotIn('1234567890123',all_text);self.assertNotIn('PRIVATE',all_text);self.assertNotIn('secret-draft',all_text)
        reviews=self.rows(p,'reviews.json','reviews')
        self.assertEqual([r['body_markdown'] for r in reviews],[self.prose,self.prose])
        self.assertEqual(reviews[0]['viewing'],'v2');self.assertEqual(reviews[1]['note'],'n1')
        self.assertEqual(len(self.rows(p,'taste.json','viewings')),2)
        flags=[r['flags'] for r in self.rows(p,'taste.json','films')]
        self.assertEqual(flags,[['W','O','NL'],['NW']])
        self.assertIn('coverage=Season 1',p['files']['editions.txt'])
        self.assertIn('role=supplement',p['files']['editions.txt'])
    def test_revision_ignores_private_fields_but_tracks_public_changes(self):
        first=self.build()['view']['revision']
        self.collection['copies'][0]['notes']='DIFFERENT PRIVATE NOTES';self.write('collection',self.collection)
        self.review('secret-draft',draft=True,title_override='PRIVATE')
        self.assertEqual(self.build()['view']['revision'],first)
        self.films[0]['liked']=True;self.write('films',self.films)
        self.assertNotEqual(self.build()['view']['revision'],first)
    def test_single_attachment_is_complete_and_self_contained(self):
        p=self.build();context=p['files']['film-context.txt']
        self.assertIn('2 | B (?) |  | NW',context)
        self.assertIn('v1 | 1 | 2020-01-01',context)
        self.assertIn('v2 | 1 | 2020-01-01 | rating=4',context)
        self.assertEqual(context.count(self.prose),2)
        self.assertIn('viewing=v2',context)
        self.assertIn('note=n1',context)
        self.assertIn('n1 | 1 | 2020-01-01',context)
        self.assertIn('coverage=Season 1',context)
        self.assertIn('https://t0mb.net/films/a/reviews/review-a/',context)
        self.assertNotIn('Fetch taste.txt',context)
        self.assertEqual(context.count(cinema_export.GUIDE),1)
        self.assertIn('END COMPLETE FILM CONTEXT: revision '+p['view']['revision'],context)
        manifest=json.loads(p['files']['manifest.json'])
        self.assertEqual(manifest['single_file'],'film-context.txt')
    def test_manifest_checksums_and_parts_cover_every_review(self):
        p=self.build();manifest=json.loads(p['files']['manifest.json'])
        for name,meta in manifest['files'].items():
            content=p['files'][name].encode()
            self.assertEqual(meta['bytes'],len(content))
            self.assertEqual(meta['sha256'],hashlib.sha256(content).hexdigest())
            self.assertIn(manifest['revision'],p['files'][name])
        parts=''.join(p['files'][name] for name in manifest['fallback_parts']['reviews.txt'])
        self.assertEqual(parts.count('BEGIN REVIEW TEXT'),2)
        self.assertEqual(parts.count(self.prose),2)
    def test_yaml_tags_and_dates_match_website_metadata(self):
        p=self.root/'cinema/reviews/review-a.md'
        p.write_text(p.read_text().replace('draft: false','draft: false\ntags: [cinema, "slow cinema"]'))
        rows=self.rows(self.build(),'reviews.json','reviews')
        self.assertEqual(rows[0]['tags'],['cinema','slow cinema'])
        p.write_text(p.read_text().replace('draft: false','draft: false\ndraft: true'))
        with self.assertRaises(ValueError):self.build()

    def test_only_explicit_drafts_are_excluded(self):
        self.review('review-a',draft=True)
        p=self.root/'cinema/reviews/review-b.md';p.write_text(p.read_text().replace('draft: false\n',''))
        self.assertEqual(json.loads(self.build()['files']['manifest.json'])['counts']['reviews'],1)

if __name__=='__main__':unittest.main()
