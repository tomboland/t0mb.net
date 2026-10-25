"""Exercise native Open WebUI adapter, including asynchronous dispatch."""
import asyncio
import importlib.util
import json
from pathlib import Path
import unittest
from openwebui_cinema_tools import Tools

spec=importlib.util.spec_from_file_location('query_tests',Path(__file__).with_name('test-cinema-query.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)


class AdapterTests(fixture.QueryTests):
    def test_adapter_public_source_and_reuse(self):
        import hashlib
        from cinema_query import public_tables, VERSION
        tables=public_tables(self.root)
        checksum=hashlib.sha256(json.dumps(tables,ensure_ascii=False,separators=(',',':'),sort_keys=True).encode()).hexdigest()
        path=self.root/'query.json'
        path.write_text(json.dumps(dict(query_schema_version=VERSION,revision='public',tables=tables,tables_sha256=checksum)))
        tools=Tools()
        tools.valves.catalogue_root=str(Path(__file__).resolve().parents[1])
        tools.valves.snapshot_url=str(path)
        tools.valves.index_path=str(self.root/'tool-cache/index.sqlite')
        self.assertEqual(json.loads(tools._call('catalogue_info'))['counts']['films'],3)
        first=tools._query()
        self.assertIs(tools._query(),first)
        self.assertEqual(json.loads(tools._call('find_films',owned=True))['total_matches'],2)

    def test_adapter_matches_local_queries(self):
        tools=Tools()
        # Tool code loads from this checkout, fixture data is injected into its query factory.
        tools._query=lambda:self.q
        async def exercise():
            info=json.loads(await tools.catalogue_info())
            self.assertEqual(info['counts']['films'],3)
            result=json.loads(await tools.find_films('{"owned":true,"limit":1}'))
            self.assertEqual(result['total_matches'],2)
            self.assertFalse(result['complete'])
            schema=json.loads(await tools.query_schema())
            self.assertIn('viewings',schema['tables'])
            result=json.loads(await tools.query_sql('SELECT count(*) n FROM films'))
            self.assertEqual(result['rows'],[{'n':3}])
            denied=json.loads(await tools.query_sql('DELETE FROM films'))
            self.assertIn('error',denied)
            self.assertFalse(denied['complete'])
            self.assertIn('error',json.loads(await tools.find_films('[]')))
        asyncio.run(exercise())


if __name__=='__main__':unittest.main()
