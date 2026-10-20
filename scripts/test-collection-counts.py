import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('counts',Path(__file__).with_name('count-collection.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Counts(unittest.TestCase):
    def test_copies_box_sets_shared_films_and_nonowned(self):
        films=[dict(id='film-a',title='Film'),dict(id='tv-a',title='TV',kind='tv_series'),dict(id='sold',title='Sold')]
        d=dict(editions=[dict(id='edition-a',contents=[dict(film='film-a'),dict(film='tv-a')]),dict(id='edition-b',contents=[dict(film='film-a')]),dict(id='edition-c',contents=[dict(film='sold')])],copies=[dict(id='copy-a',edition_id='edition-a'),dict(id='copy-b',edition_id='edition-a'),dict(id='copy-c',edition_id='edition-b',ownership='loaned'),dict(id='copy-d',edition_id='edition-c',ownership='sold')])
        r=m.counts(d,films)
        self.assertEqual(r['physical_packages'],3)
        self.assertEqual(r['distinct_editions'],2)
        self.assertEqual(r['catalogued_identities'],2)
        self.assertEqual(r['films_including_documentaries_and_tv_films'],1)
if __name__=='__main__':unittest.main()
