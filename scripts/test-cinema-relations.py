#!/usr/bin/env python3
"""Check cross-catalogue validation without import files or network access."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('validator', Path(__file__).with_name('validate-cinema.py'))
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

class RelationsTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root/'cinema/reviews').mkdir(parents=True)
        self.films = [{'id':'film-1','slug':'example-1990','title':'Example','year':1990,'tmdb':{'type':'movie','id':1}}]
        self.write('films', self.films)
        self.write('viewings', [{'id':'view-1','film':'film-1','date':'2020-01-01'}])
        self.write('entries', [{'id':'note-1','film':'film-1','kind':'note'}])
        self.write('collection', {'schema_version':3,'labels':[], 'editions':[], 'copies':[]})
        self.review = self.root/'cinema/reviews/example.md'
        self.review.write_text('---\nid: review-1\nfilm: film-1\ntitle: Example\ndiary_entry: note-1\ndraft: false\n---\nOriginal writing.\n')
    def write(self, name, data):
        (self.root/f'cinema/{name}.json').write_text(json.dumps(data))
    def test_non_viewing_review_is_valid_without_inventing_viewings(self):
        before = self.review.read_bytes()
        result = validator.audit(self.root)
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['counts']['viewings'], 1)
        self.assertEqual(self.review.read_bytes(), before)
    def test_missing_and_conflicting_review_relationships(self):
        self.review.write_text(self.review.read_text().replace('diary_entry: note-1','diary_entry: missing\nviewing: view-1'))
        errors = validator.audit(self.root)['errors']
        self.assertTrue(any('invalid diary note' in e for e in errors))
        self.assertTrue(any('both viewing and diary note' in e for e in errors))
    def test_duplicate_typed_tmdb_identity_is_rejected(self):
        self.write('films', self.films + [dict(self.films[0], id='film-2', slug='other')])
        self.assertTrue(any('Duplicate TMDB' in e for e in validator.audit(self.root)['errors']))
    def test_movie_and_tv_ids_are_separate_namespaces(self):
        self.write('films', self.films + [dict(self.films[0], id='film-2', slug='other', tmdb={'type':'tv','id':1})])
        self.assertEqual(validator.audit(self.root)['errors'], [])
    def test_missing_viewing_film_is_rejected(self):
        self.write('viewings', [{'id':'view-1','film':'missing'}])
        self.assertTrue(any('missing film' in e for e in validator.audit(self.root)['errors']))

if __name__ == '__main__':
    unittest.main()
