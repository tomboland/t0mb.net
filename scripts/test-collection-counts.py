import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('counts',Path(__file__).with_name('count-collection.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class Counts(unittest.TestCase):
    def test_copies_box_sets_canonical_aliases_and_nonowned(self):
        d=dict(works=[dict(id='work-a',title='Film',kind='film',catalogue_film_id='lb-A'),dict(id='work-b',title='Alias',kind='film',catalogue_film_id='lb-A'),dict(id='work-c',title='TV',kind='tv_series'),dict(id='work-d',title='Sold',kind='film')],editions=[dict(id='edition-a',contents=[dict(work_id='work-a'),dict(work_id='work-c')]),dict(id='edition-b',contents=[dict(work_id='work-b')]),dict(id='edition-c',contents=[dict(work_id='work-d')])],copies=[dict(id='copy-a',edition_id='edition-a',ownership='owned'),dict(id='copy-b',edition_id='edition-a',ownership='owned'),dict(id='copy-c',edition_id='edition-b',ownership='loaned'),dict(id='copy-d',edition_id='edition-c',ownership='sold')])
        r=m.counts(d)
        self.assertEqual(r['physical_packages'],3)
        self.assertEqual(r['distinct_editions'],2)
        self.assertEqual(r['catalogued_identities'],2)
        self.assertEqual(r['films_including_documentaries_and_tv_films'],1)
if __name__=='__main__':unittest.main()
