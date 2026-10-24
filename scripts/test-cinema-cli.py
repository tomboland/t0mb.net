"""Command adapter tests: the dedicated CLI calls services, never another CLI."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import cinema_app as app
from cinema_service import Catalogue


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'cinema').mkdir()
        for name in ('films','viewings','directors'):
            (self.root/'cinema'/f'{name}.json').write_text('[]')
        (self.root/'cinema/collection.json').write_text(json.dumps(dict(schema_version=3,labels=[],editions=[],copies=[])))
        self.service = Catalogue(self.root)
        self.film = self.service.add_film(title='Local Film',year='2000')

    def run_cli(self,*args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), patch.object(app,'api_from_file',return_value=None), patch.object(app.ui,'interactive',return_value=False):
            app.main(list(args),root=self.root)
        return output.getvalue()

    def test_plain_local_search_contains_slug(self):
        self.assertIn('local-film-2000',self.run_cli('search','Local','--local','--plain'))

    def test_default_search_uses_tmdb(self):
        with patch.object(Catalogue,'search',return_value=[{'id':42,'title':'Remote','release_date':'2001-01-01'}]) as search:
            self.assertIn('42 | Remote | 2001',self.run_cli('search','Remote','--plain'))
            search.assert_called_once_with('Remote')

    def test_add_owned_and_duplicate_guard(self):
        self.run_cli('own',self.film,'--format','4K UHD')
        with self.assertRaises(SystemExit): self.run_cli('own',self.film,'--format','DVD')
        self.run_cli('own',self.film,'--format','DVD','--new-edition')
        self.assertEqual(len(self.service.read('collection')['editions']),2)
        self.assertEqual(self.service.read('viewings'),[])

    def test_log_liked_and_rewatch(self):
        self.run_cli('log',self.film,'--date','2026-10-23','--rating','4.5','--liked')
        self.run_cli('log',self.film,'--rewatch')
        self.assertEqual(len(self.service.read('viewings')),2)
        self.assertTrue(self.service.read('films')[0]['liked'])

    def test_review_uses_editor_and_links_viewing(self):
        with patch('cinema_editor.edit_review',side_effect=lambda text:text+'Review prose.'):
            result = self.run_cli('review',self.film)
        self.assertIn('.md',result)
        self.assertEqual(len(self.service.read('viewings')),1)

    def test_cancel_review_leaves_no_viewing(self):
        with patch('cinema_editor.edit_review',return_value=None): self.run_cli('review',self.film)
        self.assertEqual(self.service.read('viewings'),[])

    def test_bad_date_and_rating_do_not_save(self):
        before = self.service.snapshot()
        for args in [('log',self.film,'--date','bad'),('log',self.film,'--rating','6')]:
            with self.assertRaises(SystemExit): self.run_cli(*args)
        self.assertEqual(before,self.service.snapshot())

    def test_seen_does_not_create_viewing(self):
        self.run_cli('seen',self.film)
        self.assertTrue(self.service.read('films')[0]['watched'])
        self.assertEqual(self.service.read('viewings'),[])

    def test_tag_deduplication_and_removal(self):
        self.run_cli('tag',self.film,'favourite','slow cinema')
        self.run_cli('tag',self.film,'FAVOURITE')
        self.run_cli('tag',self.film,'Favourite','--remove')
        self.assertEqual(self.service.read('films')[0]['tags'],['slow cinema'])

    def test_browser_requires_terminal(self):
        with self.assertRaises(SystemExit): self.run_cli('browse')

    def test_invalid_tmdb_id(self):
        with self.assertRaises(SystemExit): self.run_cli('own','--tmdb-id','-1','--format','DVD')


if __name__ == '__main__': unittest.main()
