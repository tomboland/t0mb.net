"""Offline tests for the dedicated application and service."""
import copy
import curses
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cinema_service import Catalogue
from cinema_schema import validate
from cinema_editor import edit_review, validate_review
import cinema_tui as ui


class API:
    def search(self, query):
        return [{'id':10,'title':'Example','release_date':'2000-01-01'}]

    def get(self, path, **kwargs):
        if path == 'movie/10':
            return dict(id=10,title='Example',release_date='2000-01-01',origin_country=['GB'],credits={'crew':[dict(id=20,name='Director',job='Director')]})
        if path == 'person/20/movie_credits': return {'crew':[]}
        raise AssertionError(path)


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root/'cinema').mkdir()
        for name in ('films','viewings','directors'):
            (self.root/'cinema'/f'{name}.json').write_text('[]')
        (self.root/'cinema/collection.json').write_text(json.dumps(dict(schema_version=3,labels=[],editions=[],copies=[])))
        self.service = Catalogue(self.root, API(), lambda f:(f['id'],{'test':True}))
        self.selection = {'id':10}

    def add(self):
        return self.service.add_owned(self.selection,formats=['4K UHD'])

    def test_own_imports_metadata_without_viewing(self):
        self.add()
        state = self.service.snapshot()
        self.assertEqual(state['films'][0]['origin_country'],['GB'])
        self.assertNotIn('watched',state['films'][0])
        self.assertEqual(state['viewings'],[])
        self.assertEqual(len(state['collection']['copies']),1)
        self.assertEqual(len(state['artwork']),1)

    def test_invalid_release_saves_nothing(self):
        before = self.service.snapshot()
        with self.assertRaises(ValueError):
            self.service.add_owned(self.selection,formats=['4K UHD'],barcode='bad')
        self.assertEqual(before,self.service.snapshot())

    def test_existing_identity_reused_and_copy_reuses_edition(self):
        edition = self.add()
        self.service.add_copy(edition,'Shelf 2')
        self.service.add_owned(self.selection,formats=['DVD'])
        state = self.service.snapshot()
        self.assertEqual(len(state['films']),1)
        self.assertEqual(len(state['collection']['editions']),2)
        self.assertEqual(len(state['collection']['copies']),3)

    def test_edit_edition_with_blank_optional_fields(self):
        edition = self.add()
        values = dict(title='The Wizard of Oz', notes='85th Anniversary collector’s box.',
                      packaging='', barcode='', catalogue_number='', country='', release_date='')
        self.service.edit_edition(edition, values)
        result = self.service.read('collection')['editions'][0]
        self.assertEqual(result['title'], values['title'])
        self.assertEqual(result['notes'], values['notes'])
        for field in ('packaging', 'barcode', 'catalogue_number', 'country', 'release_date'):
            self.assertNotIn(field, result)

    def test_edit_edition_can_clear_optional_fields(self):
        edition = self.add()
        self.service.edit_edition(edition, dict(barcode='12345678', release_date='2024-01-01', notes='Keep this'))
        self.service.edit_edition(edition, dict(barcode='', release_date='   '))
        result = self.service.read('collection')['editions'][0]
        self.assertNotIn('barcode', result)
        self.assertNotIn('release_date', result)
        self.assertEqual(result['notes'], 'Keep this')

    def test_invalid_edition_edits_still_save_nothing(self):
        edition = self.add()
        before = self.service.snapshot()
        for values in ({'barcode': 'bad'}, {'release_date': '2024-02-30'}, {'title': ''}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.service.edit_edition(edition, values)
            self.assertEqual(self.service.snapshot(), before)

    def test_open_local_film_on_tmdb_without_catalogue_changes(self):
        self.add()
        before = self.service.snapshot()
        film = before['films'][0]
        choices = iter(['Open on TMDB', 'Back'])
        def choose(title, rows, *args, **kwargs):
            choice = next(choices)
            self.assertIn(choice, rows)
            return choice
        with patch.object(ui, 'select', side_effect=choose), patch.object(ui.webbrowser, 'open_new_tab', return_value=True) as browser:
            ui.actions(self.service, film['id'])
        browser.assert_called_once_with('https://www.themoviedb.org/movie/10')
        self.assertEqual(before, self.service.snapshot())

    def test_tmdb_links_for_search_results_and_unlinked_films(self):
        self.assertEqual(ui.tmdb_url(self.service, {'id': 51447}), 'https://www.themoviedb.org/movie/51447')
        film = self.service.add_film(title='Unlinked film')
        self.assertIsNone(ui.tmdb_url(self.service, film))
        self.assertIsNone(ui.tmdb_url(self.service, {'id': 'invalid'}))

    def test_browser_failure_shows_copyable_url(self):
        url = 'https://www.themoviedb.org/movie/51447'
        for outcome in (False, OSError('No browser available')):
            with patch.object(ui.webbrowser, 'open_new_tab', side_effect=[outcome]), patch.object(ui, 'notify') as notify:
                ui.open_tmdb(url)
                self.assertIn(url, notify.call_args.args[0])

    def test_original_title_is_visible_in_film_label(self):
        label = ui.movie_label({'title': 'Trophy Wife', 'original_title': 'Potiche'})
        self.assertIn('Trophy Wife (Potiche)', label)
        self.assertNotIn('(Alien)', ui.movie_label({'title': 'Alien', 'original_title': 'Alien'}))

    def test_edit_cut_and_clear_label(self):
        edition = self.add()
        film = self.service.read('films')[0]
        self.service.edit_cut(edition,film['id'],'4K77')
        self.service.edit_edition(edition,{'label':'Criterion'})
        self.service.edit_edition(edition,{'label':''})
        result = self.service.read('collection')['editions'][0]
        self.assertEqual(result['contents'][0]['cut'],'4K77')
        self.assertNotIn('label_id',result)

    def test_search_action_edits_existing_unknown_format(self):
        edition = self.service.add_owned(self.selection, formats=[])
        before = self.service.snapshot()
        choices = iter(['Edit collection entry', 'Edit format', '4K UHD', 'Save', 'Back', 'Back'])
        def choose(title, rows, *args, **kwargs):
            choice = next(choices)
            self.assertIn(choice, rows)
            return choice
        with patch.object(ui, 'select', side_effect=choose), patch.object(ui, 'notify'):
            ui.actions(self.service, self.selection)
        after = self.service.snapshot()
        self.assertEqual(after['collection']['editions'][0]['id'], edition)
        self.assertEqual(after['collection']['editions'][0]['formats'], ['4K UHD'])
        self.assertEqual(after['collection']['copies'], before['collection']['copies'])
        self.assertEqual(after['films'], before['films'])
        self.assertEqual(after['viewings'], before['viewings'])

    def test_local_search_selects_correct_edition_and_cancel_preserves_format(self):
        first = self.add()
        second = self.service.add_owned(self.selection, formats=['DVD'])
        film_id = self.service.read('films')[0]['id']
        before = self.service.snapshot()
        choices = iter(['Edit collection entry', second, 'Edit format', 'DVD', 'Cancel', 'Back', 'Back'])
        def choose(title, rows, *args, **kwargs):
            choice = next(choices)
            if title == 'Choose your edition':
                self.assertEqual({r['id'] for r in rows}, {first, second})
                return next(r for r in rows if r['id'] == choice)
            self.assertIn(choice, rows)
            return choice
        with patch.object(ui, 'select', side_effect=choose), patch.object(ui, 'notify'):
            ui.actions(self.service, film_id)
        self.assertEqual(before, self.service.snapshot())

    def test_collection_browser_and_editor_accept_imported_mixed_case_film_ids(self):
        edition_id = self.add()
        films = self.service.read('films')
        films.append({'id': 'lb-28Tm', 'slug': 'imported-film', 'title': 'Imported film'})
        (self.root/'cinema/films.json').write_text(json.dumps(films))
        before = self.service.snapshot()
        edition = self.service.read('collection')['editions'][0]
        choices = iter(['Collection', edition, 'Back', None, 'Exit'])
        with patch.object(ui, 'select', side_effect=lambda *args, **kwargs: next(choices)):
            ui.browse(self.service)
        with patch.object(ui, 'select', side_effect=['Edit format', 'DVD', 'Save', 'Back']), patch.object(ui, 'notify'):
            ui.edit_collection_entry(self.service, edition_id)
        after = self.service.snapshot()
        self.assertEqual(after['collection']['editions'][0]['formats'], ['4K UHD', 'DVD'])
        self.assertEqual(after['films'], before['films'])
        self.assertEqual(after['collection']['copies'], before['collection']['copies'])

    def test_invalid_copy_edit_preserves_data(self):
        self.add()
        before = self.service.snapshot()
        with self.assertRaises(ValueError):
            self.service.edit_copy(before['collection']['copies'][0]['id'],{'condition':'banana'})
        self.assertEqual(before,self.service.snapshot())

    def test_cancelled_review_has_no_side_effects(self):
        before = self.service.snapshot()
        result = self.service.log_review(self.selection,date='2026-10-23',editor=lambda text:None)
        self.assertIsNone(result)
        self.assertEqual(before,self.service.snapshot())
        self.assertFalse((self.root/'cinema/reviews').exists())

    def test_review_saved_with_matching_viewing(self):
        result = self.service.log_review(self.selection,date='2026-10-23',rating='4.5',editor=lambda text:text+'My review.\n')
        state = self.service.snapshot()
        self.assertTrue(result.exists())
        self.assertIn(state['viewings'][0]['id'],result.read_text())
        self.assertTrue(state['films'][0]['watched'])
        self.assertIn('draft: true',result.read_text())

    def test_invalid_review_identity_saves_nothing(self):
        before = self.service.snapshot()
        with self.assertRaises(ValueError):
            self.service.log_review(self.selection,date='2026-10-23',editor=lambda text:text.replace('draft: true','draft: false'))
        self.assertEqual(before,self.service.snapshot())

    def test_stale_snapshot_rejected(self):
        before = self.service.snapshot()
        self.add()
        with self.assertRaisesRegex(ValueError,'changed during editing'):
            self.service.commit(before,copy.deepcopy(before))

    def test_write_failure_rolls_back(self):
        before = self.service.snapshot()
        import collection_data
        write = collection_data.atomic_text
        calls = 0
        def fail_once(path,text):
            nonlocal calls
            calls += 1
            if calls == 2: raise OSError('simulated disk failure')
            write(path,text)
        with patch.object(collection_data,'atomic_text',side_effect=fail_once):
            with self.assertRaises(OSError): self.add()
        self.assertEqual(before,self.service.snapshot())

    def test_explicit_unknown_is_not_watched(self):
        self.assertEqual(ui.viewing_status({'id':'a'},[]),'Unknown')
        self.assertEqual(ui.viewing_status({'id':'a','watched':False},[]),'Unwatched')
        self.assertEqual(ui.viewing_status({'id':'a','watched':False},[{'film':'a'}]),'Watched')

    def test_empty_edition_does_not_break_ownership(self):
        data={'copies':[{'edition_id':'e'}],'editions':[{'id':'e','title':'Unknown contents'}]}
        self.assertEqual(ui.ownership({'id':'a'},data),'Not owned')


class EditorTests(unittest.TestCase):
    def template(self):
        return '---\nid: review-a\nfilm: film-a\ntitle: Example\ndate: "2026-10-23"\ndraft: true\nspoilers: false\nviewing: viewing-a\nwatched_date: "2026-10-23"\n---\n\nTemplate.\n'

    def test_editor_command_is_split_without_shell(self):
        import os
        import contextlib
        import io
        from types import SimpleNamespace
        paths = []
        def editor(argv):
            self.assertEqual(argv[:2],['my editor','--wait'])
            path = Path(argv[-1]); paths.append(path)
            path.write_text(path.read_text()+'New prose.')
            return SimpleNamespace(returncode=0)
        with patch.dict(os.environ,{'VISUAL':'"my editor" --wait'}), patch('cinema_editor.subprocess.run',side_effect=editor), contextlib.redirect_stdout(io.StringIO()):
            result = edit_review(self.template())
        self.assertIn('New prose.',result)
        self.assertTrue(paths[0].exists())
        paths[0].unlink()

    def test_editor_failure_retains_draft(self):
        import os
        import contextlib
        import io
        from types import SimpleNamespace
        paths = []
        def fail(argv):
            paths.append(Path(argv[-1]))
            return SimpleNamespace(returncode=1)
        with patch.dict(os.environ,{'VISUAL':'editor'}), patch('cinema_editor.subprocess.run',side_effect=fail), contextlib.redirect_stdout(io.StringIO()):
            self.assertIsNone(edit_review(self.template()))
        self.assertTrue(paths[0].exists())
        paths[0].unlink()

    def test_invalid_metadata_rejected(self):
        original = self.template()
        with self.assertRaises(ValueError): validate_review(original.replace('film-a','film-b'),original)
        with self.assertRaises(ValueError): validate_review(original.replace('spoilers: false','spoilers: maybe'),original)


class SelectorTests(unittest.TestCase):
    def test_text_input_waits_after_selector_and_can_cancel(self):
        class Screen:
            delay = -1
            editing = False
            keys = iter(['\n', 'w', 'h', '\n', '\x1b'])

            def timeout(self, delay): self.delay = delay
            def erase(self): pass
            def getmaxyx(self): return (24, 100)
            def addnstr(self, *args): pass
            def refresh(self): pass
            def move(self, *args): pass
            def get_wch(self):
                if self.editing and self.delay >= 0:
                    raise curses.error('no input')
                return next(self.keys)

        screen = Screen()
        with patch.object(ui, 'interactive', return_value=True), patch.object(curses, 'curs_set'), patch.object(curses, 'wrapper', side_effect=lambda fn: fn(screen)):
            self.assertEqual(ui.select('Menu', ['Search TMDB']), 'Search TMDB')
            screen.editing = True
            self.assertEqual(ui.text_input('Search TMDB'), 'wh')
            self.assertIsNone(ui.text_input('Search TMDB'))

    def choose(self, keys, rows):
        class Screen:
            def timeout(self,*a): pass
            def erase(self): pass
            def getmaxyx(self): return (24,100)
            def addnstr(self,*a): pass
            def refresh(self): pass
            def get_wch(self): return next(keys)
        with patch.object(ui,'interactive',return_value=True), patch.object(curses,'curs_set'), patch.object(curses,'wrapper',side_effect=lambda fn:fn(Screen())):
            return ui.select('Films',rows)

    def test_arrow_selects_second_item(self):
        self.assertEqual(self.choose(iter([curses.KEY_DOWN,'\n']),['one','two']),'two')

    def test_filter_and_cancel(self):
        self.assertEqual(self.choose(iter(['t','\n']),['one','two']),'two')
        self.assertIsNone(self.choose(iter(['\x1b']),[]))


if __name__ == '__main__': unittest.main()
