"""Offline content/build regression tests; never writes production content."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import os
import re
import shutil
import subprocess
from urllib.parse import urljoin
import cinema_data

ROOT = Path(__file__).resolve().parents[1]
SITE = Path(os.environ.get('CINEMA_SITE', next(iter(ROOT.glob('dist-newstyle/build/*/ghc-*/t0mb-net-*/x/site/build/site/site')), ''))).resolve()


def tag_url(label):
    import hashlib
    key = cinema_data.normalise_tags([label])[0].casefold()
    return '/films/tags/' + (cinema_data.slug(key)[:60] or 'tag') + '-' + hashlib.sha256(key.encode()).hexdigest()[:12] + '/'


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
        self.write('directors', [{'id': 'local-person', 'name': 'Someone', 'filmography': [{'tmdb_id': 123, 'title': 'Undated film', 'year': ''}]}])
        for name in ('templates', 'content'):
            shutil.copytree(ROOT / name, self.root / name)

    def build(self):
        result = subprocess.run([str(SITE), 'build'], cwd=self.root, text=True, capture_output=True)
        if result.returncode:
            raise ValueError(result.stdout + result.stderr)
        pages = {}
        for path in (self.root / '_site').rglob('*.html'):
            route = path.relative_to(self.root / '_site').as_posix()
            # Normalize Hakyll's relative URLs to compare destinations.
            pages[route] = re.sub(r'(href|src)="([^"]*)"', lambda m: m[1] + '="' + urljoin('/' + route, m[2]) + '"', path.read_text())
        return pages

    def write(self, name, data):
        (self.data / (name + '.json')).write_text(json.dumps(data))

    def review(self, name, draft=False, featured=False, date="2026-01-02"):
        (self.data / 'reviews' / (name + '.md')).write_text('---\n' + '\n'.join(f'{k}: {json.dumps(v)}' for k, v in
            {'id': name, 'film': 'local-film', 'title': name, 'date': date, 'draft': draft, 'featured': featured, 'viewing': 'v2'}.items()) + '\n---\n\nActual writing.\n')

    def test_manual_films_and_optional_ratings(self):
        pages = self.build()
        film = pages['films/local-film-2000/index.html']
        self.assertIn('Local &lt;film&gt;', film)
        self.assertNotIn('Film details on TMDB', film)
        self.assertIn('4.5/5', film)
        cinema_data.validate_rating(None)
        diary = pages['films/diary/index.html']
        self.assertLess(diary.index('2026-01-01'), diary.index('2025-01-01'))

    def test_multiple_reviews_and_draft_removal(self):
        self.review('first'); self.review('second'); self.review('secret', True)
        pages = self.build()
        text = '\n'.join(pages.values())
        self.assertNotIn('secret', text)
        first = 'films/local-film-2000/reviews/first/index.html'
        self.assertIn('second', pages[first])
        # Unpublishing removes both generated source and any stale public output.
        output = self.root / '_site/films/local-film-2000/reviews/first/index.html'
        output.write_text('Previously published')
        self.review('first', True)
        self.build()
        self.assertFalse((self.root / first).exists())
        self.assertFalse(output.exists())

    def test_bad_links_and_ratings_fail(self):
        self.write('viewings', [{'id': 'v1', 'film': 'missing', 'date': '2026-01-01'}])
        with self.assertRaises(ValueError):
            self.build()
        with self.assertRaises(ValueError):
            cinema_data.validate_rating('0')

    def test_featured_selection_fallback_and_drafts(self):
        self.review('older-pick', featured=True, date='2025-01-01')
        self.review('newest', date='2026-01-03')
        self.review('recent', date='2026-01-02')
        self.review('left-out', date='2026-01-01')
        self.review('private-pick', draft=True, featured=True, date='2026-01-04')
        pages = self.build()
        home = pages['index.html']
        self.assertLess(home.index('older-pick'), home.index('newest'))
        self.assertLess(home.index('newest'), home.index('recent</span>'))
        self.assertEqual(home.count('class="review-entry"'), 3)
        self.assertEqual(home.count('>older-pick</span>'), 1)
        self.assertNotIn('private-pick', home)
        self.assertNotIn('left-out', home)
        writing = pages['films/reviews/index.html']
        self.assertLess(writing.index('newest'), writing.index('older-pick'))
        self.review('older-pick', featured=False, date='2025-01-01')
        home = self.build()['index.html']
        self.assertNotIn('older-pick', home)
        self.assertIn('left-out', home)

    def test_featured_limit_order_and_validation(self):
        for day in range(1, 5):
            self.review('pick-' + str(day), featured=True, date='2026-01-0' + str(day))
        self.review('private-pick', featured=True, draft=True)
        self.review('not-featured')
        home = self.build()['index.html']
        self.assertNotIn('private-pick', home)
        self.assertNotIn('not-featured', home)
        fallback, pool = home.split('<template id="featured-review-pool">', 1)
        self.assertNotIn('pick-1', fallback)
        self.assertEqual(fallback.count('class="review-entry"'), 3)
        self.assertIn('pick-1', pool)
        self.assertEqual(pool.count('class="review-entry"'), 4)
        self.assertLess(home.index('pick-4'), home.index('pick-3'))
        self.assertLess(home.index('pick-3'), home.index('pick-2'))
        self.review('bad', featured='true')
        with self.assertRaisesRegex(ValueError, 'featured must be true or false'):
            self.build()

    def test_home_navigation_and_review_dates(self):
        self.review('published')
        self.review('private', True)
        pages = self.build()
        self.assertIn('published', pages['index.html'])
        self.assertNotIn('private', pages['index.html'])
        review = pages['films/local-film-2000/reviews/published/index.html']
        self.assertIn('2026-01-02', review)
        self.assertRegex(review, r'href="/films/reviews/"[^>]*aria-current="page"')
        self.assertIn('← Film details:', review)
        self.assertRegex(pages['films/diary/index.html'], r'href="/films/diary/"[^>]*aria-current="page"')
        catalogue = pages['films/index.html']
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
        pages = self.build()
        for path in ['films/index', 'films/diary/index', 'films/reviews/index', 'directors/someone-local-person/index']:
            self.assertIn('/images/thumb.jpg', pages[path + '.html'])
        self.assertIn('/images/backdrop.jpg', pages['films/local-film-2000/index.html'])
        self.assertNotIn('/images/backdrop.jpg', pages['films/local-film-2000/reviews/review/index.html'])
        self.films[0].update(poster='/images/custom.jpg', image=False)
        self.write('films', self.films)
        pages = self.build()
        self.assertIn('/images/custom.jpg', pages['films/index.html'])
        self.assertNotIn('/images/thumb.jpg', pages['films/index.html'])
        self.assertNotIn('/images/backdrop.jpg', pages['films/local-film-2000/index.html'])
        self.films[0]['poster'] = '/images/missing.jpg'
        self.write('films', self.films)
        with self.assertRaises(ValueError):
            self.build()

    def test_film_tags_grouping_links_and_removal(self):
        self.films[0]['tags'] = ['Favourite', ' favourite ', 'slow cinema', 'slow-cinema', '<mood>', '映画']
        other = dict(self.films[0], id='another', slug='another-2001', title='Another film', year='2001', tags=['FAVOURITE'])
        self.write('films', self.films + [other])
        pages = self.build()
        url = tag_url('favourite')
        page = url.lstrip('/') + 'index.html'
        self.assertIn('2 films', pages[page])
        self.assertIn('Another film', pages[page])
        self.assertIn('Local &lt;film&gt;', pages[page])
        self.assertRegex(pages[page], r'href="/films/tags/"[^>]*aria-current="page"')
        self.assertIn(url, pages['films/local-film-2000/index.html'])
        self.assertIn(url, pages['films/index.html'])
        self.assertIn('&lt;mood&gt;', pages['films/tags/index.html'])
        self.assertNotEqual(tag_url('slow cinema'), tag_url('slow-cinema'))
        self.assertEqual(tag_url('FAVOURITE'), url)
        self.assertNotEqual(tag_url('映画'), tag_url('音楽'))
        published = self.root / '_site' / url.lstrip('/') / 'index.html'
        published.write_text('old tag page')
        self.films[0]['tags'] = []
        self.write('films', self.films)
        pages = self.build()
        self.assertNotIn(page, pages)
        self.assertFalse((self.root / page).exists())
        self.assertFalse(published.exists())
        self.assertIn('No films tagged yet', pages['films/tags/index.html'])
        for invalid in ['favourite', [None], [' ']]:
            with self.assertRaises(ValueError):
                cinema_data.normalise_tags(invalid)

    def test_numeric_ratings_and_false_optional_fields(self):
        self.films[0]['rating'] = 4.5
        self.write('films', self.films)
        self.review('review')
        source = self.data / 'reviews/review.md'
        source.write_text(source.read_text().replace('draft: false', 'draft: false\nspoilers: false\nimage: false'))
        pages = self.build()
        self.assertIn('4.5/5', pages['films/local-film-2000/index.html'])
        self.assertNotIn('Contains spoilers', pages['films/local-film-2000/reviews/review/index.html'])
        self.assertNotIn('film-image', pages['films/local-film-2000/reviews/review/index.html'])
        source.write_text(source.read_text().replace('Actual writing.', 'Updated **writing**.'))
        pages = self.build()
        self.assertIn('Updated <strong>writing</strong>', pages['films/local-film-2000/reviews/review/index.html'])
        self.assertIn('Updated <strong>writing</strong>', ET.parse(self.root / '_site/rss.xml').findtext('./channel/item/description'))

    def test_likes_across_pages_and_incremental_updates(self):
        self.review('liked-review')
        self.films[0]['liked'] = True
        self.films[0]['tags'] = ['favourite']
        self.write('films', self.films)
        pages = self.build()
        routes = ['index.html', 'films/index.html', 'films/diary/index.html',
                  'films/reviews/index.html', 'films/local-film-2000/index.html',
                  'films/local-film-2000/reviews/liked-review/index.html',
                  'directors/someone-local-person/index.html',
                  tag_url('favourite').lstrip('/') + 'index.html']
        for route in routes:
            self.assertIn('title="Liked film">♥</span>', pages[route], route)
        self.films[0]['liked'] = False
        self.write('films', self.films)
        pages = self.build()
        for route in routes:
            self.assertIn('title="Film not marked as liked">♡</span>', pages[route], route)
            self.assertNotIn('title="Liked film">♥</span>', pages[route], route)
        self.assertIn('favourite', pages['films/local-film-2000/index.html'])
        self.films[0]['liked'] = 'false'
        self.write('films', self.films)
        with self.assertRaisesRegex(ValueError, 'liked must be true or false'):
            self.build()

    def test_like_import_preserves_existing_data(self):
        import zipfile
        spec = importlib.util.spec_from_file_location('importer', ROOT / 'scripts/import-letterboxd.py')
        importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(importer)
        export = self.root / 'export.zip'
        with zipfile.ZipFile(export, 'w') as archive:
            archive.writestr('likes/films.csv', 'Name,Letterboxd URI\nFilm,https://boxd.it/liked\nOutside,https://boxd.it/outside\n')
            archive.writestr('likes/reviews.csv', 'Content\nhttps://boxd.it/unliked\n')
        records = [dict(self.films[0], id='liked', letterboxd_url='https://boxd.it/liked'),
                   dict(self.films[0], id='unliked', letterboxd_url='https://boxd.it/unliked'),
                   dict(self.films[0], id='edited', letterboxd_url='https://boxd.it/liked', liked=False),
                   dict(self.films[0], id='manual')]
        self.write('films', records)
        likes = importer.read_likes(export)
        path = self.data / 'films.json'
        importer.import_likes(path, likes)
        result = json.loads(path.read_text())
        self.assertEqual(result, [dict(records[0], liked=True), dict(records[1], liked=False), records[2], records[3]])
        importer.import_likes(path, likes)
        self.assertEqual(json.loads(path.read_text()), result)

    def test_film_themes_inherit_to_reviews_only(self):
        self.review('first')
        self.review('second')
        self.films[0]['theme'] = 'curated-amber'
        self.write('films', self.films)
        pages = self.build()
        themed = ['films/local-film-2000/index.html',
                  'films/local-film-2000/reviews/first/index.html',
                  'films/local-film-2000/reviews/second/index.html']
        for route, body in pages.items():
            self.assertEqual('data-film-theme="curated-amber"' in body, route in themed, route)
        del self.films[0]['theme']
        self.write('films', self.films)
        self.assertNotIn('data-film-theme=', self.build()[themed[0]])
        self.films[0]['theme'] = 'invalid theme'
        self.write('films', self.films)
        with self.assertRaisesRegex(ValueError, 'Film theme must'):
            self.build()

    def test_embedded_review_bodies_and_links(self):
        self.review('first', date='2026-01-01')
        self.review('second', date='2026-01-02')
        self.review('secret', draft=True)
        for name in ['first', 'second']:
            path = self.data / 'reviews' / (name + '.md')
            path.write_text(path.read_text().replace('Actual writing.',
                '**Readable writing** with a [relative link](notes.html) and a footnote.[^1]\n\n[^1]: A note.'))
        pages = self.build()
        film = pages['films/local-film-2000/index.html']
        self.assertEqual(film.count('class="embedded-review"'), 2)
        self.assertEqual(film.count('<strong>Readable writing</strong>'), 2)
        self.assertNotIn('secret', film)
        self.assertLess(film.index('review-second-heading'), film.index('review-first-heading'))
        for name in ['first', 'second']:
            self.assertIn('/films/local-film-2000/reviews/' + name + '/notes.html', film)
            self.assertIn('id="review-' + name + '-body-fn1"', film)
            self.assertIn('#review-' + name + '-body-fn1', film)
        path = self.data / 'reviews/second.md'
        path.write_text(path.read_text().replace('Readable writing', 'Revised writing'))
        film = self.build()['films/local-film-2000/index.html']
        self.assertIn('<strong>Revised writing</strong>', film)
        self.review('second', draft=True)
        film = self.build()['films/local-film-2000/index.html']
        self.assertNotIn('review-second-heading', film)

    def test_notes_pages_home_archive_and_feed(self):
        for day in range(1, 5):
            path = self.root / 'posts' / ('2026-02-0' + str(day) + '-note') / 'index.md'
            path.parent.mkdir(parents=True)
            path.write_text(f'---\ntitle: Note {day}\ndate: 2026-02-0{day}\n---\n\nEntry **{day}**.\n')
        pages = self.build()
        home = pages['index.html']
        self.assertIn('Recent notes', home)
        self.assertNotIn('Note 1', home)
        self.assertLess(home.index('Note 4'), home.index('Note 3'))
        self.assertLess(home.index('Note 3'), home.index('Note 2'))
        for day in range(1, 5):
            self.assertIn(f'Note {day}', pages['notes/index.html'])
            self.assertIn(f'Note {day}', pages['archive.html'])
            self.assertIn(f'<h1>Note {day}</h1>', pages[f'posts/2026-02-0{day}-note/index.html'])
        items = ET.parse(self.root / '_site/rss.xml').findall('./channel/item')
        self.assertEqual([i.findtext('title') for i in items], ['Note 4', 'Note 3', 'Note 2', 'Note 1'])
        self.assertIn('<strong>4</strong>', items[0].findtext('description'))
        path = self.root / 'posts/2026-02-04-note/index.md'
        path.write_text(path.read_text().replace('Entry **4**.', 'Updated entry.'))
        pages = self.build()
        self.assertIn('Updated entry.', pages['index.html'])
        self.assertIn('Updated entry.', pages['notes/index.html'])

    def test_post_tags_across_notes_reviews_and_incremental_removal(self):
        note = self.root / 'posts/2026-03-01-photo/index.md'
        note.parent.mkdir(parents=True)
        note.write_text('---\ntitle: A photo\ndate: 2026-03-01\ntags: [Photography, " photography ", "<sky>", "映画", "slow cinema", "slow-cinema"]\n---\n\nPhoto body.\n')
        self.review('tagged')
        review = self.data / 'reviews/tagged.md'
        review.write_text(review.read_text().replace('draft: false', 'draft: false\ntags: [PHOTOGRAPHY]'))
        self.review('secret', draft=True)
        secret = self.data / 'reviews/secret.md'
        secret.write_text(secret.read_text().replace('draft: true', 'draft: true\ntags: [private-topic, photography]'))
        self.films[0]['tags'] = ['film-only']
        self.write('films', self.films)
        url = tag_url('photography').replace('/films/tags/', '/tags/')
        route = url.lstrip('/') + 'index.html'
        pages = self.build()
        for location in ['index.html', 'notes/index.html', 'archive.html',
                         'posts/2026-03-01-photo/index.html',
                         'films/local-film-2000/reviews/tagged/index.html',
                         'films/local-film-2000/index.html']:
            self.assertIn(url, pages[location], location)
        self.assertLess(pages[route].index('>A photo</a>'), pages[route].index('>tagged</a>'))
        self.assertEqual(pages[route].count('>A photo</a>'), 1)
        self.assertNotIn('secret', pages[route])
        self.assertNotIn('private-topic', pages['tags/index.html'])
        self.assertNotIn('film-only', pages['tags/index.html'])
        self.assertIn('&lt;sky&gt;', pages['tags/index.html'])
        for tag in ['映画', 'slow cinema', 'slow-cinema']:
            path = tag_url(tag).replace('/films/tags/', '/tags/').lstrip('/') + 'index.html'
            self.assertIn('>A photo</a>', pages[path])
        feed = ET.parse(self.root / '_site/rss.xml')
        review_body = next(item.findtext('description') for item in feed.findall('./channel/item') if item.findtext('title') == 'tagged')
        self.assertIn('Actual writing.', review_body)
        self.assertNotIn('← Film details', review_body)
        self.assertNotIn('More of my writing', review_body)
        self.assertIn('https://t0mb.net' + url, review_body)
        note.write_text(note.read_text().replace('tags: [Photography, " photography ", "<sky>", "映画", "slow cinema", "slow-cinema"]', 'tags: [new-topic]'))
        pages = self.build()
        self.assertNotIn('>A photo</a>', pages[route])
        new_route = tag_url('new-topic').replace('/films/tags/', '/tags/').lstrip('/') + 'index.html'
        self.assertIn('>A photo</a>', pages[new_route])
        self.review('tagged', draft=True)
        pages = self.build()
        self.assertNotIn(route, pages)
        self.assertNotIn(url, pages['tags/index.html'])
        note.unlink()
        pages = self.build()
        self.assertNotIn(new_route, pages)
        self.assertNotIn('posts/2026-03-01-photo/index.html', pages)

    def test_invalid_post_tags_fail_with_source(self):
        note = self.root / 'posts/2026-03-01-note/index.md'
        note.parent.mkdir(parents=True)
        for tags in ['photography', '[null]', '[" "]']:
            note.write_text('---\ntitle: Invalid\ndate: 2026-03-01\ntags: ' + tags + '\n---\nText.\n')
            with self.assertRaisesRegex(ValueError, 'posts/2026-03-01-note/index.md: Tags must'):
                self.build()

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



if __name__ == '__main__':
    unittest.main()
