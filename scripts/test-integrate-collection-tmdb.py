#!/usr/bin/env python3
import copy,importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('integration',Path(__file__).with_name('integrate-collection-tmdb.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class IntegrationTests(unittest.TestCase):
 def setUp(self):
  self.data={'works':[{'id':'work-1','title':'Example','kind':'film','year':None,'catalogue_film_id':None}]}
  self.decision={'work_id':'work-1','tmdb':{'type':'movie','id':123},'expected_year':'1982','expected_title':'Example','source':'https://www.themoviedb.org/movie/123','evidence':'Reviewed'}
  self.meta={('movie',123):{'id':123,'title':'Example','release_date':'1982-01-01','credits':{'crew':[]}}}
 def test_new_ownership_does_not_invent_watching(self):
  d,f,j=m.integrate(self.data,[],[self.decision],self.meta)
  self.assertIsNone(f[0]['watched']);self.assertIsNone(f[0]['rating']);self.assertIsNone(self.data['works'][0]['catalogue_film_id'])
  self.assertEqual(d['works'][0]['catalogue_film_id'],f[0]['id'])
 def test_existing_identity_preserves_history_and_is_idempotent(self):
  old={'id':'letterboxd','slug':'example','title':'Example','year':'1982','tmdb':{'type':'movie','id':123},'watched':True,'rating':5}
  d,f,j=m.integrate(self.data,[old],[self.decision],self.meta)
  self.assertEqual(f,[old]);self.assertEqual(j['new_canonical_ids'],[])
  self.assertEqual(m.integrate(d,f,[self.decision],self.meta)[2]['work_changes'],[])
 def test_multiple_editions_share_identity(self):
  self.data['works'].append(dict(self.data['works'][0],id='work-2'))
  d,f,j=m.integrate(self.data,[],[self.decision,dict(self.decision,work_id='work-2')],self.meta)
  self.assertEqual(len(f),1);self.assertEqual(len(j['work_changes']),2)
 def test_rejects_kind_and_year_conflicts(self):
  self.data['works'][0]['kind']='tv_series'
  with self.assertRaises(ValueError):m.integrate(self.data,[],[self.decision],self.meta)
  self.data['works'][0].update(kind='film',year=2000)
  with self.assertRaises(ValueError):m.integrate(self.data,[],[self.decision],self.meta)
if __name__=='__main__':unittest.main()
