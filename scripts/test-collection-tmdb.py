import importlib.util,unittest
from pathlib import Path
s=importlib.util.spec_from_file_location('matcher',Path(__file__).with_name('match-collection-tmdb.py'))
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
class API:
    def get(self,path,**params):
        self.path,self.params=path,params
        return {'results':[{'id':12,'name':'Dune','first_air_date':'2000-12-03'}]}
class Candidates(unittest.TestCase):
    def test_tv_is_not_searched_as_movie(self):
        api=API();r=m.search(api,dict(title='Dune',kind='tv_series',year=2000))
        self.assertEqual(api.path,'search/tv');self.assertEqual(r[0]['tmdb'],{'type':'tv','id':12})
        self.assertEqual(r[0]['year'],'2000')
    def test_year_annotation_removed_without_hiding_other_versions(self):
        api=API();m.search(api,dict(title='Dune (2021)',kind='film',year=2021))
        self.assertEqual(api.path,'search/movie');self.assertEqual(api.params['query'],'Dune')
        self.assertNotIn('year',api.params)
if __name__=='__main__':unittest.main()
