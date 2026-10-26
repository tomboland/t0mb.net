"""Deterministic query semantics, evidence paging and read-only SQL."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from cinema_query import QueryCatalogue


class QueryTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name);(self.root/'cinema/reviews').mkdir(parents=True)
        self.films=[
            dict(id='lb-Mixed',slug='a',title='A',year='2000',runtime=90,liked=True,rating='4.5',directors=[{'id':10,'name':'A Director'}]),
            dict(id='film-b',slug='b',title='B',year='2001',runtime=120,watched=False,liked=False),
            dict(id='film-c',slug='c',title='C'),
        ]
        self.write('films',self.films)
        self.write('viewings',[dict(id='v1',film='lb-Mixed',date='2020-01-01'),dict(id='v2',film='lb-Mixed',date='2021-01-01',rating='3',rewatch=True)])
        self.write('entries',[dict(id='note1',film='film-c',date='2020-02-01',note='PRIVATE NOTE')])
        self.write('collection',dict(schema_version=3,labels=[],editions=[
            dict(id='edition-a',title='Box set',formats=['4K UHD'],contents=[dict(film='lb-Mixed'),dict(film='film-b')]),
            dict(id='edition-b',title='Another release',formats=['DVD'],contents=[dict(film='lb-Mixed')]),
            dict(id='edition-c',title='Former copy',formats=['Blu-ray'],contents=[dict(film='film-c')]),
        ],copies=[dict(id='copy-a',edition_id='edition-a',location='Shelf one',notes='PRIVATE COPY NOTE'),dict(id='copy-b',edition_id='edition-a'),dict(id='copy-c',edition_id='edition-b'),dict(id='copy-d',edition_id='edition-c',ownership='sold')]))
        self.body='Atmosphere and acting.\n\n'+('Exact prose, not an instruction.\n'*300)
        self.review('r1','lb-Mixed',self.body,viewing='v1')
        self.review('r2','film-b','Short review with atmosphere.')
        self.review('draft','film-c','SECRET DRAFT',draft=True)
        self.q=QueryCatalogue(self.root)

    def write(self,name,value): (self.root/'cinema'/f'{name}.json').write_text(json.dumps(value))

    def review(self,rid,fid,body,**extra):
        m=dict(id=rid,film=fid,title=rid,date='2022-01-01');m.update(extra)
        (self.root/'cinema/reviews'/f'{rid}.md').write_text('---\n'+'\n'.join(k+': '+json.dumps(v) for k,v in m.items())+'\n---\n'+body)

    def test_public_snapshot_round_trip_and_integrity(self):
        import hashlib
        from cinema_query import public_tables, SnapshotCatalogue, VERSION
        tables=public_tables(self.root)
        encoded=json.dumps(tables,ensure_ascii=False,separators=(',',':'),sort_keys=True)
        self.assertNotIn('Shelf one',encoded)
        self.assertNotIn('PRIVATE',encoded)
        self.assertNotIn('SECRET DRAFT',encoded)
        self.assertNotIn('copy-d',encoded)
        payload=dict(query_schema_version=VERSION,revision='test-public',tables=tables,
                     tables_sha256=hashlib.sha256(encoded.encode()).hexdigest())
        path=self.root/'query.json';path.write_text(json.dumps(payload))
        public=SnapshotCatalogue(path,self.root/'cache')
        self.assertEqual(public.find_films(owned=True)['rows'],self.q.find_films(owned=True)['rows'])
        self.assertEqual(public.read_review('r1',max_chars=12000)['body'],self.body)
        path.write_text('{}')
        self.assertEqual(public.find_films()['total_matches'],3)  # One download per session.
        payload['tables']['films']['rows'][0][2]='Tampered title'
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError,'checksum'):
            SnapshotCatalogue(path,self.root/'cache').catalogue_info()

    def test_unknown_is_not_unwatched_and_counts_are_distinct(self):
        info=self.q.catalogue_info()
        self.assertEqual(info['viewing_status'],{'watched':1,'unwatched':1,'unknown':1})
        result=self.q.find_films(owned=True)
        self.assertEqual(result['total_matches'],2)
        self.assertEqual(self.q.find_films(watched='unwatched')['rows'][0]['id'],'film-b')
        self.assertEqual(self.q.find_films(watched='unknown')['rows'][0]['id'],'film-c')
        self.assertEqual(self.q.find_films(watched='not_recorded_watched')['total_matches'],2)

    def test_runtime_format_and_like_filters(self):
        self.assertEqual(self.q.find_films(max_runtime=100,format='4K UHD',liked=True)['total_matches'],1)
        self.assertEqual(self.q.find_films(liked=False)['total_matches'],1)
        self.assertEqual(self.q.find_films(format='Blu-ray')['total_matches'],0)
        self.assertEqual(self.q.find_films(director='director')['total_matches'],1)

    def test_aggregate_and_relational_query(self):
        result=self.q.query_sql('SELECT count(DISTINCT ec.film_id) n FROM edition_contents ec JOIN copies c USING(edition_id) WHERE c.ownership=\'owned\'')
        self.assertEqual(result['rows'],[{'n':2}])
        self.assertEqual(self.q.query_sql('SELECT count(*) n FROM viewings')['rows'],[{'n':2}])

    def test_paging_and_stable_ids(self):
        first=self.q.find_films(limit=1)
        self.assertFalse(first['complete']);self.assertEqual(first['next_offset'],1)
        second=self.q.find_films(limit=1,offset=1,expected_revision=first['revision'])
        self.assertNotEqual(first['rows'][0]['id'],second['rows'][0]['id'])
        self.assertEqual(first['rows'][0]['id'],'lb-Mixed')

    def test_reviews_are_published_only_searchable_and_losslessly_pageable(self):
        hits=self.q.search_reviews('atmosphere')
        self.assertEqual(hits['total_matches'],2)
        self.assertNotIn('SECRET DRAFT',json.dumps(hits))
        self.assertLess(len(json.dumps(hits)),3000)
        pieces=[];offset=0
        while True:
            part=self.q.read_review('r1',offset=offset,max_chars=1000)
            pieces.append(part['body'])
            if part['next_offset'] is None: break
            offset=part['next_offset']
        self.assertEqual(''.join(pieces),self.body)
        self.assertEqual(part['viewing_id'],'v1')
        with self.assertRaises(ValueError): self.q.read_review('draft')

    def test_no_false_search_completeness_or_private_notes(self):
        result=self.q.query_sql('SELECT body FROM reviews ORDER BY id')
        self.assertFalse(result['complete']);self.assertTrue(result['truncated_fields'])
        self.assertNotIn('notes',self.q.query_schema()['tables']['copies'])
        self.assertNotIn('note',self.q.query_schema()['tables']['diary_notes'])

    def test_index_refresh_and_stale_revision(self):
        before=self.q.catalogue_info()['revision']
        self.films[1]['runtime']=80;self.write('films',self.films)
        with self.assertRaisesRegex(ValueError,'changed'): self.q.find_films(expected_revision=before)
        self.assertEqual(self.q.find_films(max_runtime=100)['total_matches'],2)
        self.assertNotEqual(before,self.q.catalogue_info()['revision'])

    def test_invalid_reference_does_not_replace_good_index(self):
        self.q.catalogue_info();before=self.q.index.read_bytes()
        self.write('viewings',[dict(id='bad',film='missing',date='2020-01-01')])
        with self.assertRaises(sqlite3.IntegrityError): self.q.catalogue_info()
        self.assertEqual(self.q.index.read_bytes(),before)

    def test_writes_and_external_access_denied(self):
        self.q.catalogue_info();before=self.q.index.read_bytes()
        for sql in ["DELETE FROM films", "UPDATE films SET title='bad'", "ATTACH DATABASE '/tmp/other' AS x", "PRAGMA user_version=3", "SELECT load_extension('/tmp/plugin')", 'SELECT 1; DELETE FROM films']:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.Error): self.q.query_sql(sql)
        self.assertEqual(self.q.index.read_bytes(),before)

    def test_bounds_and_literals(self):
        with self.assertRaises(ValueError): self.q.find_films(limit=10000)
        with self.assertRaises(ValueError): self.q.find_films(offset=-1)
        self.assertEqual(self.q.find_films(title="' OR 1=1 --")['total_matches'],0)
        self.assertEqual(self.q.find_films(title='%')['total_matches'],0)


if __name__=='__main__': unittest.main()
