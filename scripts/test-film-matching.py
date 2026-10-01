"""Offline regression checks: python3 scripts/test-film-matching.py."""
import importlib.util
from pathlib import Path
import unittest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load('audit', 'audit-film-matches.py')
matcher = load('matcher', 'match-tmdb.py')


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.film = {'Name': 'Example', 'Year': '2000', 'Letterboxd URI': 'https://boxd.it/film'}
        self.review = dict(self.film, **{'Letterboxd URI': 'https://boxd.it/review', 'Date': '2026-10-01', 'Watched Date': '2026-09-30'})
        self.match = {'title': 'Example', 'year': '2000', 'letterboxd_uri': 'https://boxd.it/film', 'tmdb_type': 'movie', 'tmdb_id': 123}

    def test_repeated_reviews_preserved(self):
        second = dict(self.review, **{'Letterboxd URI': 'https://boxd.it/review2'})
        _, rows = audit.audit([self.film], [self.review, second], {'matches': [self.match]})
        self.assertEqual([r['tmdb_id'] for r in rows], [123, 123])
        self.assertEqual(len({r['review_uri'] for r in rows}), 2)

    def test_exclusion_applies_to_reviews(self):
        films, reviews = audit.audit([self.film], [self.review], {'matches': [], 'excluded': [self.match]})
        self.assertEqual((films, reviews), ([], []))

    def test_title_collision_does_not_guess(self):
        collision = dict(self.film, **{'Letterboxd URI': 'https://boxd.it/another'})
        _, rows = audit.audit([self.film, collision], [self.review], {'matches': [self.match]})
        self.assertEqual(rows[0]['film_join'], 'ambiguous')
        self.assertEqual(rows[0]['tmdb_id'], '')

    def test_stale_mapping_rejected(self):
        with self.assertRaises(ValueError):
            audit.audit([self.film], [], {'matches': [dict(self.match, year='2001')]})

    def test_search_collision_not_accepted(self):
        class FakeAPI:
            def search(self, title, year=None):
                return [{'id': i, 'title': title, 'original_title': title, 'release_date': '2000-01-01'} for i in (1, 2)]
        result = matcher.match_film(self.film, {}, FakeAPI())
        self.assertEqual(result['status'], 'needs_review')
        self.assertNotIn('tmdb_id', result)


if __name__ == '__main__':
    unittest.main()
