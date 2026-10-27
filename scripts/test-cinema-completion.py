"""Exercise real Carapace output with an isolated config and catalogue."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

from cinema_app import parser
from cinema_completion import spec


@unittest.skipUnless(shutil.which('carapace'), 'Carapace is not installed')
class CompletionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.data = self.root / 'catalogue with spaces' / 'cinema'
        self.data.mkdir(parents=True)
        self.films = [dict(id='local-1', slug='a-film-2000', title='A Film', year='2000',
                           tags=['slow cinema'], tmdb={'id': 123}),
                      dict(id='local-2', slug='other-2001', title='Other', tags=['other tag'])]
        (self.data / 'films.json').write_text(json.dumps(self.films))
        self.config = self.root / 'config'
        specs = self.config / 'carapace' / 'specs'
        specs.mkdir(parents=True)
        (specs / 'cinema.yaml').write_text(yaml.safe_dump(spec(parser(), self.data.parent)))
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(self.config),
                        XDG_CACHE_HOME=str(self.root / 'cache'))

    def complete(self, *args, shell='nushell'):
        result = subprocess.run(['carapace', 'cinema', shell, 'cinema', *args],
                                env=self.env, text=True, capture_output=True, check=True)
        return json.loads(result.stdout)

    def test_commands_and_options_have_descriptions(self):
        commands = self.complete('')
        self.assertIn('review', [r['display'] for r in commands])
        self.assertTrue(all(r.get('description') for r in commands))
        flags = self.complete('own', '--')
        self.assertIn('--edition-title', [r['display'] for r in flags])
        self.assertTrue(all(r.get('description') for r in flags))

    def test_live_films_and_quotes(self):
        self.assertEqual(self.complete('review', 'a-')[0]['description'], 'A Film (2000)')
        self.assertEqual(self.complete('search', 'A')[0]['value'], '"A Film" ')
        self.films[0]['slug'] = 'changed'
        (self.data / 'films.json').write_text(json.dumps(self.films))
        self.assertEqual(self.complete('review', 'changed')[0]['display'], 'changed')

    def test_repeatable_formats_and_rating(self):
        rows = self.complete('own', '--format', 'DVD', '--format', '')
        self.assertIn('"4K UHD" ', [r['value'] for r in rows])
        self.assertEqual(len(self.complete('log', 'a-film-2000', '--rating', '')), 10)

    def test_tags_and_remove_filter(self):
        self.assertEqual(len(self.complete('tag', 'a-film-2000', '')), 2)
        rows = self.complete('tag', '--remove', 'a-film-2000', '')
        self.assertEqual([r['display'] for r in rows], ['slow cinema'])
        self.assertEqual(self.complete('tag', 'a-film-2000', 'new', 'slow')[0]['value'], '"slow cinema" ')

    def test_root_override_and_missing_catalogue(self):
        other = self.root / 'other'
        (other / 'cinema').mkdir(parents=True)
        (other / 'cinema' / 'films.json').write_text(json.dumps([dict(id='unique', title='Unique')]))
        self.assertEqual(self.complete('--root', str(other), 'review', '')[0]['display'], 'unique')
        (other / 'cinema' / 'films.json').unlink()
        self.assertEqual(self.complete('--root', str(other), 'review', ''), [])

    def test_file_completion_and_equals(self):
        token = self.root / 'token file'
        token.touch()
        rows = self.complete('search', 'anything', '--token-file', str(self.root / 'token'))
        self.assertIn('token file', rows[0]['value'])
        self.assertTrue(self.complete('own', '--format=Bl'))

    def test_launcher_runs_cli_from_another_directory(self):
        launcher = self.root / 'cinema'
        launcher.symlink_to(Path(__file__).with_name('cinema').resolve())
        result = subprocess.run([str(launcher), '--root', str(self.data.parent),
                                 'search', 'A Film', '--local', '--plain'],
                                cwd=self.root, env=self.env, check=True,
                                text=True, capture_output=True)
        self.assertIn('local-1 | A Film | 2000 | a-film-2000', result.stdout)


if __name__ == '__main__':
    unittest.main()
