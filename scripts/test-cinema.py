"""Offline content/build regression tests; never writes production content."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('builder', Path(__file__).with_name('build-films.py'))
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class CinemaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = self.root / 'cinema'
        (self.data / 'reviews').mkdir(parents=True)
        self.films = [{'id': 'local-film', 'slug': 'local-film-2000', 'title': 'Local <film>', 'year': '2000', 'rating': None,
                       'directors': [{'id': 'local-person', 'name': 'Someone'}]}]
        self.write('films', self.films)
        self.write('viewings', [{'id': 'v1', 'film': 'local-film', 'date': '2025-01-01', 'rating': None},
                                {'id': 'v2', 'film': 'local-film', 'date': '2026-01-01', 'rating': '4.5', 'rewatch': True}])
        self.write('directors', [])

    def write(self, name, data):
        (self.data / (name + '.json')).write_text(json.dumps(data))

    def review(self, name, draft=False, featured=False, date="2026-01-02"):
        (self.data / 'reviews' / (name + '.md')).write_text('---\n' + '\n'.join(f'{k}: {json.dumps(v)}' for k, v in
            {'id': name, 'film': 'local-film', 'title': name, 'date': date, 'draft': draft, 'featured': featured, 'viewing': 'v2'}.items()) + '\n---\n\nActual writing.\n')

    def test_manual_films_and_optional_ratings(self):
        pages = builder.build(self.root)
        film = pages['generated/films/local-film-2000/index.md']
        self.assertIn('Local &lt;film&gt;', film)
        self.assertNotIn('Film details on TMDB', film)
        self.assertIn('4.5/5', film)
        self.assertEqual(builder.rating(None), '')
        diary = pages['generated/films/diary/index.md']
        self.assertLess(diary.index('2026-01-01'), diary.index('2025-01-01'))

    def test_multiple_reviews_and_draft_removal(self):
        self.review('first'); self.review('second'); self.review('secret', True)
        pages = builder.build(self.root)
        text = '\n'.join(pages.values())
        self.assertNotIn('secret', text)
        first = 'generated/films/local-film-2000/reviews/first/index.md'
        self.assertIn('second', pages[first])
        # Unpublishing removes both generated source and any stale public output.
        output = self.root / '_site/films/local-film-2000/reviews/first/index.html'
        output.parent.mkdir(parents=True); output.write_text('Previously published')
        self.review('first', True)
        builder.build(self.root)
        self.assertFalse((self.root / first).exists())
        self.assertFalse(output.exists())

    def test_bad_links_and_ratings_fail(self):
        self.write('viewings', [{'id': 'v1', 'film': 'missing', 'date': '2026-01-01'}])
        with self.assertRaises(ValueError):
            builder.build(self.root)
        with self.assertRaises(ValueError):
            builder.rating('0')

    def test_featured_selection_fallback_and_drafts(self):
        self.review('older-pick', featured=True, date='2025-01-01')
        self.review('newest', date='2026-01-03')
        self.review('recent', date='2026-01-02')
        self.review('left-out', date='2026-01-01')
        self.review('private-pick', draft=True, featured=True, date='2026-01-04')
        pages = builder.build(self.root)
        home = pages['generated/home.html']
        self.assertLess(home.index('older-pick'), home.index('newest'))
        self.assertLess(home.index('newest'), home.index('recent</span>'))
        self.assertEqual(home.count('class="review-entry"'), 3)
        self.assertEqual(home.count('>older-pick</span>'), 1)
        self.assertNotIn('private-pick', home)
        self.assertNotIn('left-out', home)
        writing = pages['generated/films/reviews/index.md']
        self.assertLess(writing.index('newest'), writing.index('older-pick'))
        self.review('older-pick', featured=False, date='2025-01-01')
        home = builder.build(self.root)['generated/home.html']
        self.assertNotIn('older-pick', home)
        self.assertIn('left-out', home)

    def test_featured_limit_order_and_validation(self):
        for day in range(1, 5):
            self.review('pick-' + str(day), featured=True, date='2026-01-0' + str(day))
        home = builder.build(self.root)['generated/home.html']
        self.assertNotIn('pick-1', home)
        self.assertLess(home.index('pick-4'), home.index('pick-3'))
        self.assertLess(home.index('pick-3'), home.index('pick-2'))
        self.review('bad', featured='true')
        with self.assertRaisesRegex(ValueError, 'featured must be true or false'):
            builder.build(self.root)

    def test_home_navigation_and_review_dates(self):
        self.review('published')
        self.review('private', True)
        pages = builder.build(self.root)
        self.assertIn('published', pages['generated/home.html'])
        self.assertNotIn('private', pages['generated/home.html'])
        review = pages['generated/films/local-film-2000/reviews/published/index.md']
        self.assertIn('date: "2026-01-02"', review)
        self.assertIn('nav_writing: true', review)
        self.assertIn('← Film details:', review)
        self.assertIn('nav_diary: true', pages['generated/films/diary/index.md'])
        catalogue = pages['generated/films/index.md']
        self.assertLess(catalogue.index('id="film-search"'), catalogue.index('Recent writing'))
        self.assertIn('data-label="Film"', catalogue)

    def test_artwork_lists_overrides_and_review_separation(self):
        images = self.root / 'images'
        images.mkdir()
        for name in ('poster.jpg', 'thumb.jpg', 'backdrop.jpg', 'custom.jpg'):
            (images / name).write_bytes(b'fixture')
        self.write('artwork', {'local-film': {
            'poster': {'path': '/images/poster.jpg', 'thumbnail': '/images/thumb.jpg', 'alt': 'Poster'},
            'backdrop': {'path': '/images/backdrop.jpg', 'alt': 'Backdrop'}}})
        self.review('review')
        pages = builder.build(self.root)
        for path in ['films/index', 'films/diary/index', 'films/reviews/index', 'directors/someone-local-person/index']:
            self.assertIn('/images/thumb.jpg', pages['generated/' + path + '.md'])
        self.assertIn('/images/backdrop.jpg', pages['generated/films/local-film-2000/index.md'])
        self.assertNotIn('/images/backdrop.jpg', pages['generated/films/local-film-2000/reviews/review/index.md'])
        self.films[0].update(poster='/images/custom.jpg', image=False)
        self.write('films', self.films)
        pages = builder.build(self.root)
        self.assertIn('/images/custom.jpg', pages['generated/films/index.md'])
        self.assertNotIn('/images/thumb.jpg', pages['generated/films/index.md'])
        self.assertNotIn('/images/backdrop.jpg', pages['generated/films/local-film-2000/index.md'])
        self.films[0]['poster'] = '/images/missing.jpg'
        self.write('films', self.films)
        with self.assertRaises(ValueError):
            builder.build(self.root)

    def test_film_tags_grouping_links_and_removal(self):
        self.films[0]['tags'] = ['Favourite', ' favourite ', 'slow cinema', 'slow-cinema', '<mood>', '映画']
        other = dict(self.films[0], id='another', slug='another-2001', title='Another film', year='2001', tags=['FAVOURITE'])
        self.write('films', self.films + [other])
        pages = builder.build(self.root)
        url = builder.tag_url('favourite')
        page = 'generated' + url + 'index.md'
        self.assertIn('2 films', pages[page])
        self.assertIn('Another film', pages[page])
        self.assertIn('Local &lt;film&gt;', pages[page])
        self.assertIn('nav_tags: true', pages[page])
        self.assertIn(url, pages['generated/films/local-film-2000/index.md'])
        self.assertIn(url, pages['generated/films/index.md'])
        self.assertIn('&lt;mood&gt;', pages['generated/films/tags/index.md'])
        self.assertNotEqual(builder.tag_url('slow cinema'), builder.tag_url('slow-cinema'))
        self.assertEqual(builder.tag_url('FAVOURITE'), url)
        self.assertNotEqual(builder.tag_url('映画'), builder.tag_url('音楽'))
        published = self.root / '_site' / url.lstrip('/') / 'index.html'
        published.parent.mkdir(parents=True)
        published.write_text('old tag page')
        self.films[0]['tags'] = []
        self.write('films', self.films)
        pages = builder.build(self.root)
        self.assertNotIn(page, pages)
        self.assertFalse((self.root / page).exists())
        self.assertFalse(published.exists())
        self.assertIn('No films tagged yet', pages['generated/films/tags/index.md'])
        for invalid in ['favourite', [None], [' ']]:
            with self.assertRaises(ValueError):
                builder.normalise_tags(invalid)

    def test_tag_command_add_remove_and_deduplicate(self):
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('cinema_cli', Path(__file__).with_name('cinema.py'))
        cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cli)
        with patch.object(cli, 'ROOT', self.data):
            with patch('sys.argv', ['cinema.py', 'tag', 'local-film-2000', 'favourite', 'slow cinema']):
                cli.main()
            with patch('sys.argv', ['cinema.py', 'tag', 'local-film', 'FAVOURITE']):
                cli.main()
            self.assertEqual(json.loads((self.data / 'films.json').read_text())[0]['tags'], ['favourite', 'slow cinema'])
            with patch('sys.argv', ['cinema.py', 'tag', 'local-film', 'Favourite', '--remove']):
                cli.main()
            self.assertEqual(json.loads((self.data / 'films.json').read_text())[0]['tags'], ['slow cinema'])

    def test_real_import(self):
        films, viewings, people, reviews = builder.load_content()
        ids = {f['id'] for f in films}
        self.assertEqual(len(ids), len(films))
        self.assertTrue(all(v['film'] in ids for v in viewings))
        self.assertTrue(all(r['film'] in ids and not r.get('draft') for r in reviews))


if __name__ == '__main__':
    unittest.main()
