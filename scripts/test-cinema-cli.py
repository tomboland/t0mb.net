"""Offline authoring regression checks: python3 scripts/test-cinema-cli.py."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


cli = load('cinema_cli', 'cinema.py')
art = load('film_images', 'import-film-images.py')


class FakeAPI:
    def __init__(self):
        self.results = [{'id': 31217, 'title': 'The Human Condition I: No Greater Love',
                         'original_title': '人間の條件', 'release_date': '1959-01-15'}]
        self.calls = []

    def search(self, title, year=None):
        self.calls.append(('search', title, year))
        return self.results

    def get(self, path, **params):
        self.calls.append((path, params))
        if path == 'person/76978/movie_credits':
            return {'crew': [{'id': 31217, 'title': self.results[0]['title'], 'release_date': '1959-01-15', 'job': 'Director'}]}
        if path == 'movie/31217':
            return dict(self.results[0], runtime=208, credits={'crew': [{'id': 76978, 'name': 'Masaki Kobayashi', 'job': 'Director'}]},
                        poster_path='/poster.jpg', backdrop_path='/backdrop.jpg')
        raise AssertionError(path)


class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cinema = self.root / 'cinema'
        (self.cinema / 'reviews').mkdir(parents=True)
        for name in ['films', 'viewings', 'directors']:
            (self.cinema / (name + '.json')).write_text('[]\n')
        self.api = FakeAPI()
        for mock in [patch.object(cli, 'ROOT', self.cinema), patch.object(cli, 'api_for', return_value=self.api),
                     patch.object(art.urllib.request, 'urlopen', side_effect=lambda *a, **kw: io.BytesIO(b'\xff\xd8\xfffixture'))]:
            mock.start()
            self.addCleanup(mock.stop)

    def read(self, name):
        return json.loads((self.cinema / (name + '.json')).read_text())

    def run_cli(self, *args):
        output = io.StringIO()
        with patch('sys.argv', ['cinema.py', *args]), contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            cli.main()
        return output.getvalue()

    def snapshot(self):
        return {p.relative_to(self.cinema): p.read_bytes() for p in self.cinema.rglob('*') if p.is_file()}

    def test_title_log_adds_film_viewing_director_and_artwork(self):
        output = self.run_cli('log', 'The Human Condition I: No Greater Love', '--year', '1959', '--date', '2026-10-02', '--rating', '4.5')
        film, = self.read('films')
        viewing, = self.read('viewings')
        self.assertEqual(film['tmdb'], {'type': 'movie', 'id': 31217})
        self.assertEqual(viewing['film'], film['id'])
        self.assertEqual(viewing['rating'], '4.5')
        self.assertEqual(viewing['date'], '2026-10-02')
        self.assertEqual(self.read('directors')[0]['name'], 'Masaki Kobayashi')
        self.assertEqual(list((self.cinema / 'reviews').iterdir()), [])
        images = self.read('artwork')[film['id']]
        for path in [images['poster']['path'], images['poster']['thumbnail'], images['backdrop']['path']]:
            self.assertTrue((self.root / path.lstrip('/')).is_file())
        self.assertIn('Logged The Human Condition', output)

    def test_existing_film_logs_offline_without_overwriting_metadata(self):
        self.run_cli('log', '--tmdb-id', '31217')
        films = self.read('films')
        films[0].update(title='My title', liked=True, tags=['favourite'], image=False)
        (self.cinema / 'films.json').write_text(json.dumps(films))
        original_art = self.read('artwork')
        with patch.object(self.api, 'get', side_effect=AssertionError('Unexpected network request')):
            self.run_cli('log', films[0]['slug'], '--rewatch')
        self.assertEqual(self.read('films'), films)
        self.assertEqual(self.read('artwork'), original_art)
        self.assertEqual(len(self.read('viewings')), 2)
        self.assertTrue(self.read('viewings')[-1]['rewatch'])

    def test_linked_draft_and_completed_review(self):
        self.run_cli('log', '--tmdb-id', '31217', '--date', '2020-01-01', '--rating', '5', '--review')
        first = next((self.cinema / 'reviews').glob('*.md'))
        before = first.read_text()
        self.assertIn('draft: true', before)
        self.assertIn('watched_date: "2020-01-01"', before)
        self.assertIn('rating: "5"', before)
        self.assertIn('viewing: "' + self.read('viewings')[0]['id'] + '"', before)
        self.run_cli('log', '--tmdb-id', '31217', '--review', 'A **remarkable** film.')
        reviews = list((self.cinema / 'reviews').glob('*.md'))
        self.assertEqual(len(reviews), 2)
        self.assertEqual(first.read_text(), before)
        second = next(p for p in reviews if p != first).read_text()
        self.assertIn('draft: false', second)
        self.assertIn('A **remarkable** film.', second)
        self.assertIn('viewing: "' + self.read('viewings')[1]['id'] + '"', second)
        self.assertEqual(len(self.read('films')), 1)

    def test_invalid_inputs_do_not_change_sources(self):
        initial = self.snapshot()
        for options in [('--date', 'nonsense'), ('--rating', '6'), ('--rating', 'nan'), ('--review', '<!-- only a comment -->')]:
            with self.assertRaises(SystemExit):
                self.run_cli('log', '--tmdb-id', '31217', *options)
            self.assertEqual(self.snapshot(), initial)
        self.assertEqual(self.api.calls, [])

    def test_download_failure_can_be_retried_without_duplicate_viewing(self):
        initial = self.snapshot()
        with patch.object(art.urllib.request, 'urlopen', return_value=io.BytesIO(b'not an image')):
            with self.assertRaises(SystemExit):
                self.run_cli('log', '--tmdb-id', '31217', '--review')
        self.assertEqual(self.snapshot(), initial)
        self.run_cli('log', '--tmdb-id', '31217', '--review')
        self.assertEqual(len(self.read('films')), 1)
        self.assertEqual(len(self.read('viewings')), 1)
        self.assertEqual(len(list((self.cinema / 'reviews').glob('*.md'))), 1)

    def test_ambiguous_search_requires_selection(self):
        self.api.results.append(dict(self.api.results[0], id=999, release_date='2000-01-01'))
        initial = self.snapshot()
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(SystemExit):
            self.run_cli('log', 'The Human Condition I: No Greater Love')
        self.assertEqual(self.snapshot(), initial)
        self.assertEqual(len(self.api.calls), 1)
        with patch('sys.stdin.isatty', return_value=True), patch('builtins.input', return_value='1'):
            self.run_cli('log', 'The Human Condition I: No Greater Love')
        self.assertEqual(self.read('films')[0]['tmdb']['id'], 31217)

    def test_title_search_reuses_existing_tmdb_identity(self):
        self.run_cli('log', '--tmdb-id', '31217')
        self.api.results[0]['title'] = 'An alternative title'
        self.run_cli('log', 'An alternative title')
        self.assertEqual(len(self.read('films')), 1)
        self.assertEqual(len(self.read('viewings')), 2)

    def test_local_title_collision_and_slug_collision_do_not_guess(self):
        self.run_cli('log', '--tmdb-id', '31217')
        films = self.read('films')
        films.append(dict(films[0], id='another', slug='another-film', tmdb={'type': 'movie', 'id': 999}))
        (self.cinema / 'films.json').write_text(json.dumps(films))
        initial = self.snapshot()
        with patch('sys.stdin.isatty', return_value=False), self.assertRaises(SystemExit):
            self.run_cli('log', films[0]['title'])
        self.assertEqual(self.snapshot(), initial)
        films[0].pop('tmdb')
        (self.cinema / 'films.json').write_text(json.dumps(films))
        initial = self.snapshot()
        with self.assertRaises(SystemExit):
            self.run_cli('log', '--tmdb-id', '31217')
        self.assertEqual(self.snapshot(), initial)

    def test_missing_artwork_downloaded_for_existing_film(self):
        self.run_cli('log', '--tmdb-id', '31217')
        film = self.read('films')[0]
        path = self.root / self.read('artwork')[film['id']]['poster']['thumbnail'].lstrip('/')
        path.unlink()
        self.run_cli('log', '--tmdb-id', '31217')
        self.assertTrue(path.is_file())
        self.assertEqual(len(self.read('films')), 1)

    def test_film_command_also_imports_artwork(self):
        self.run_cli('film', '--tmdb-id', '31217')
        film = self.read('films')[0]
        self.assertIn('poster', self.read('artwork')[film['id']])
        self.assertEqual(self.read('viewings'), [])

    def test_metadata_failure_leaves_no_diary_entry(self):
        initial = self.snapshot()
        with patch.object(self.api, 'get', side_effect=RuntimeError('TMDB HTTP 401 for movie/31217')):
            with self.assertRaises(SystemExit):
                self.run_cli('log', '--tmdb-id', '31217', '--review')
        self.assertEqual(self.snapshot(), initial)

    def test_film_without_tmdb_images_still_logs(self):
        original = self.api.get
        def no_images(path, **params):
            result = original(path, **params)
            result.pop('poster_path', None)
            result.pop('backdrop_path', None)
            return result
        with patch.object(self.api, 'get', side_effect=no_images):
            self.run_cli('log', '--tmdb-id', '31217')
        self.assertEqual(len(self.read('viewings')), 1)
        self.assertEqual(self.read('artwork')[self.read('films')[0]['id']], {'tmdb': {'type': 'movie', 'id': 31217}})

    def test_generated_records_render_in_hakyll(self):
        project = Path(__file__).resolve().parents[1]
        binary = next(project.glob('dist-newstyle/build/*/ghc-*/t0mb-net-*/x/site/build/site/site'), None)
        if binary is None:
            self.skipTest('Compile the Hakyll site executable to check rendering')
        self.run_cli('log', '--tmdb-id', '31217', '--date', '2026-10-02', '--rating', '4.5', '--review', 'A **remarkable** film.')
        for directory in ['templates', 'content']:
            shutil.copytree(project / directory, self.root / directory)
        built = subprocess.run([str(binary), 'build'], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        film = self.read('films')[0]
        page = (self.root / '_site/films' / film['slug'] / 'index.html').read_text()
        self.assertIn('A <strong>remarkable</strong> film.', page)
        self.assertIn('4.5/5', page)
        diary = (self.root / '_site/films/diary/index.html').read_text()
        self.assertIn('The Human Condition I', diary)
        self.assertIn('2026-10-02', diary)

    def test_manual_film_can_be_logged_without_tmdb(self):
        self.run_cli('film', '--title', 'Home movie', '--year', '2026', '--director', 'Me')
        with patch.object(self.api, 'get', side_effect=AssertionError('Unexpected network request')):
            output = self.run_cli('log', 'Home movie', '--review')
        self.assertEqual(len(self.read('viewings')), 1)
        self.assertIn('No TMDB reference', output)


if __name__ == '__main__':
    unittest.main()
