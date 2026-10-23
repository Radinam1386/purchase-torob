"""Behavioral checks for consultation, real catalog pagination and geographic offers."""
import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from src.api import app
from src.core.config import settings
from src.core.agent import ShoppingAgent, _apply_constraints
from src.core.contract import ConversationState
from src.core.response import response_from_messages
from src.scripts.load_data import SCHEMA


class AcceptanceBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        db = Path(self.temp.name) / 'test.sqlite'
        connection = sqlite3.connect(db)
        connection.executescript(SCHEMA)
        for n in range(65):
            title = f'هدفون موسیقی {n}'
            connection.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)',
                (f'p{n}',title,title,None,'برند الف','هدفون','هدفون','[]','[]'))
        # p0's two prices straddle 40..60; it must NOT match that range.
        for n,lat,lng in [(0,35.7,51.4),(1,35.701,51.4),(2,None,None),(3,91,51.4),(4,36.7,51.4)]:
            connection.execute('INSERT INTO shops VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (f's{n}','نام ساختگی',0,None,None,lat,lng,'تهران، خیابان تست',None,None,None,'تهران','[]','[]',0,'{}'))
        offers = [('o0','s0','p0',10),('o1','s0','p0',100),('o2','s0','p1',50),
                  ('o3','s1','p1',55),('o4','s2','p1',None),('o5','s3','p1',52),('o6','s4','p1',54)]
        connection.executemany('INSERT INTO offers VALUES (?,?,?,?,?,?,?)',
            [(*row,None,None,None) for row in offers])
        connection.execute('INSERT INTO product_fts(product_id,title,brand,category) SELECT id,title,brand,category FROM products')
        connection.commit()
        connection.close()
        self.patcher = patch('src.core.database.settings', replace(settings,database_path=db))
        self.patcher.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.patcher.stop()
        self.temp.cleanup()

    def test_pagination_returns_every_result_once_and_true_total(self):
        seen=[]
        for page in (1,2,3):
            response=self.client.get('/api/products',params={'q':'هدفون','page':page,'page_size':24})
            self.assertEqual(response.status_code,200,response.text)
            data=response.json()
            self.assertEqual(data['total'],65)
            seen += [p['id'] for p in data['data']]
        self.assertEqual(len(set(seen)),65)
        self.assertEqual(len(seen),65)

    def test_price_bounds_match_one_offer_and_null_prices_sort_last(self):
        data=self.client.get('/api/products',params={'min_price':40,'max_price':60}).json()
        self.assertEqual([p['id'] for p in data['data']],['p1'])
        for sort in ['price_asc','price_desc']:
            data=self.client.get('/api/products',params={'sort':sort,'page_size':60}).json()
            self.assertTrue(all(p['minPrice'] is not None for p in data['data'][:2]))
            self.assertTrue(all(p['minPrice'] is None for p in data['data'][2:]))
        self.assertEqual(self.client.get('/api/products',params={'min_price':60,'max_price':40}).status_code,422)

    def test_scoped_catalog_does_not_scan_unrelated_offers_on_legacy_sqlite(self):
        import src.api as api
        from src.core.database import database
        from src.core.tools.common import haversine_km
        with database() as connection:
            connection.execute('INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?)',
                ('unrelated','دوربین','دوربین',None,None,'دوربین','دوربین','[]','[]'))
            connection.execute('INSERT INTO product_fts(product_id,title,brand,category) VALUES (?,?,?,?)',
                ('unrelated','دوربین','','دوربین'))
            connection.executemany('INSERT INTO offers VALUES (?,?,?,?,?,?,?)',
                [(f'unrelated-{n}','s0','unrelated',50,None,None,None) for n in range(2000)])
        original_scope=api._eligible_offer_scope
        parameters={'q':'هدفون','max_price':60,'lat':35.7,'lng':51.4,'radius_km':1}

        def measure(force_materialized=False):
            def scope_builder(*args, **kwargs):
                scope, values=original_scope(*args, **kwargs)
                if force_materialized:
                    scope=scope.replace(' AS NOT MATERIALIZED (',' AS MATERIALIZED (',1)
                # SQLite 3.40 materializes a multiply-referenced CTE by default.
                # Reproduce that planner choice on newer development SQLite too.
                if ' AS NOT MATERIALIZED (' not in scope and ' AS MATERIALIZED (' not in scope:
                    scope=scope.replace(' AS (',' AS MATERIALIZED (',1)
                return scope, values
            with patch('src.api._eligible_offer_scope',side_effect=scope_builder), \
                 patch('src.core.tools.common.haversine_km',wraps=haversine_km) as distance:
                response=self.client.get('/api/products',params=parameters)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['total'],2)
            return distance.call_count,response.json()

        checks,result=measure()
        self.assertLess(checks,100,'A product-scoped request must not evaluate geographic filters for unrelated offers')
        materialized_checks,materialized_result=measure(force_materialized=True)
        self.assertGreaterEqual(materialized_checks,2000)
        self.assertEqual(result,materialized_result)

    def test_agent_tool_and_results_page_share_the_exact_query_predicate(self):
        from src.core.tools.catalog import search_products
        for query in ['هدفون', 'هدفون روگوشی', 'هدفون موسیقی']:
            tool = search_products.invoke({'query':query,'max_price':60,'limit':8})['data']
            grid = self.client.get('/api/products',params={'q':query,'max_price':60,'page_size':24}).json()['data']
            self.assertEqual([p['id'] for p in tool],[p['id'] for p in grid][:8])

    def test_map_coordinates_radius_counts_and_no_fake_contacts(self):
        response=self.client.get('/api/map/offers',params={'q':'هدفون','lat':35.7,'lng':51.4,'radius_km':1})
        self.assertEqual(response.status_code,200,response.text)
        data=response.json()
        self.assertEqual(data['offer_count'],6)
        self.assertEqual(data['shop_count'],4)
        self.assertEqual(data['product_count'],2)
        self.assertEqual(data['missing_coordinates_count'],2)
        missing=[r for r in data['results'] if r['distanceKm'] is None]
        self.assertEqual({r['shop']['id'] for r in missing},{'s2','s3'})
        self.assertTrue(all(r['shop']['lat'] is None for r in missing))
        self.assertNotIn('phone',json.dumps(data))
        self.assertTrue(all(r['offer']['stock']=='unverified' for r in data['results']))
        self.assertNotIn('نام ساختگی',json.dumps(data,ensure_ascii=False))
        near=self.client.get('/api/map/offers',params={'product_ids':'p1','lat':35.7,'lng':51.4,'radius_km':0}).json()
        far=self.client.get('/api/map/offers',params={'product_ids':'p1','lat':35.7,'lng':51.4,'radius_km':100}).json()
        self.assertGreater(far['shop_count'],near['shop_count'])
        self.assertEqual(self.client.get('/api/map/offers',params={'q':'هدفون','city':'شیراز'}).json()['offer_count'],0)

    def test_map_uses_same_catalog_and_offer_filters(self):
        data=self.client.get('/api/map/offers',params={'q':'هدفون','lat':35.7,'lng':51.4,'radius_km':1,'min_price':40,'max_price':60}).json()
        self.assertEqual(data['product_count'],1)
        self.assertEqual(data['offer_count'],3)
        self.assertTrue(all(40<=r['offer']['price']<=60 for r in data['results']))
        self.assertEqual(self.client.get('/api/map/offers',params={'q':'هدفون','installment':True}).json()['offer_count'],0)

    def test_map_requires_a_product_scope_instead_of_loading_the_entire_catalog(self):
        for query in ('','برای موسیقی'):
            response=self.client.get('/api/map/offers',params={'q':query})
            self.assertEqual(response.status_code,422)
            self.assertIn('جست‌وجو',response.json()['detail'])

    def test_advisor_persists_use_and_plain_budget_and_summary_confirmation(self):
        first=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='هدفون می‌خوام')],'conversation':{}})
        second=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='برای گوش دادن به موسیقی')],'conversation':first['conversation']})
        self.assertIn('بودجه',second['clarification_question'])
        state=ConversationState.model_validate(second['conversation'])
        _apply_constraints(state,'۵ میلیون')
        self.assertEqual(state.budget,5_000_000)
        ready=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='۵ میلیون')],'conversation':state.model_dump(by_alias=True)})
        self.assertIn('خلاصه ترجیحات',ready['clarification_question'])
        self.assertIn('موسیقی',ready['clarification_question'])
        self.assertIn('5,000,000',ready['clarification_question'])
        confirmed=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='بله')],'conversation':ready['conversation']})
        self.assertNotIn('clarification_question',confirmed)
        self.assertEqual(confirmed['conversation']['preferences']['_advisor']['status'],'searching')

    def test_known_budget_is_not_requested_again_and_bypass_states_assumptions(self):
        first=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='هدفون می‌خوام')],'conversation':{'budget':5000000}})
        self.assertNotIn('بودجه',first['clarification_question'])
        bypass=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='همین الان جست‌وجو کن')],'conversation':first['conversation']})
        self.assertNotIn('clarification_question',bypass)
        self.assertTrue(bypass['conversation']['preferences']['_advisor']['assumptions'])

    def test_overear_never_changes_headphones_into_phones(self):
        from src.core.tools.catalog import _is_phone_query
        self.assertFalse(_is_phone_query('هدفون روگوشی'))
        self.assertFalse(_is_phone_query('هدفون رو گوشی'))
        first=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='هدفون میخوام')],'conversation':{}})
        followup=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='روگوشی برای موسیقی')],'conversation':first['conversation']})
        self.assertEqual(followup['conversation']['preferences']['_advisor']['category'],'هدفون')
        ready=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='هدفون روگوشی برای موسیقی تا ۳ میلیون')],'conversation':{}})
        self.assertEqual(ready['conversation']['preferences']['_advisor']['category'],'هدفون')
        self.assertEqual(ready['conversation']['budget'],3_000_000)

    def test_budget_in_initial_request_is_numeric_and_used_in_summary(self):
        state=ConversationState()
        _apply_constraints(state,'هدفون برای موسیقی ۵ میلیون')
        self.assertEqual(state.budget,5_000_000)
        ready=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='هدفون برای موسیقی ۵ میلیون')],'conversation':{}})
        self.assertEqual(ready['conversation']['budget'],5_000_000)
        self.assertIn('5,000,000',ready['clarification_question'])

    def test_any_descriptive_use_answer_is_saved_without_keyword_loop(self):
        first=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='لپ تاپ میخوام')],'conversation':{}})
        second=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='برای برنامه نویسی')],'conversation':first['conversation']})
        self.assertEqual(second['conversation']['preferences']['_advisor']['use'],'برای برنامه نویسی')
        self.assertIn('بودجه',second['clarification_question'])
        third=ShoppingAgent._advisor_gate({'messages':[HumanMessage(content='تا ۵۰ میلیون')],'conversation':second['conversation']})
        self.assertIn('خلاصه ترجیحات',third['clarification_question'])
        self.assertIn('برنامه نویسی',third['clarification_question'])

    def test_exact_search_query_survives_empty_search(self):
        response=response_from_messages([
            AIMessage(content='',tool_calls=[{'name':'search_products','args':{'query':'هدفون','category':'هدفون'},'id':'call1','type':'tool_call'}]),
            ToolMessage(content=json.dumps({'source':'dataset','data':[]}),tool_call_id='call1',name='search_products'),
            AIMessage(content=json.dumps({'text':'نتیجه‌ای نبود'}))])
        self.assertEqual(response.search_query,'هدفون')
        self.assertEqual(response.search_category,'هدفون')

    def test_generic_category_matches_taxonomy_children_in_tool_and_api(self):
        from src.core.database import database
        from src.core.tools.catalog import search_products
        with database() as connection:
            connection.execute("UPDATE products SET category='هدفون، هدست و هندزفری',category_norm='هدفون، هدست و هندزفری' WHERE id='p0'")
        tool=search_products.invoke({'query':'هدفون','category':'هدفون','limit':8})['data']
        grid=self.client.get('/api/products',params={'q':'هدفون','category':'هدفون'}).json()['data']
        self.assertIn('p0',[p['id'] for p in tool])
        self.assertEqual([p['id'] for p in tool],[p['id'] for p in grid][:8])

    def test_finished_empty_search_and_category_reset_are_persisted(self):
        from src.core.agent import _update_conversation
        state=ConversationState(selected_product_id='old-product',selected_shop_ids=['old-shop'],
                                selected_offer_ids=['old-offer'],preferences={'_advisor':{'status':'searching'}})
        _update_conversation(state,{'conversation':{'selectedProductId':None},'messages':[
            ToolMessage(content=json.dumps({'source':'dataset','data':[]}),tool_call_id='s1',name='search_products')]})
        self.assertIsNone(state.selected_product_id)
        self.assertEqual(state.selected_shop_ids,[])
        self.assertEqual(state.selected_offer_ids,[])
        self.assertEqual(state.preferences['_advisor']['status'],'showing_results')
        _update_conversation(state,{'conversation':{},'messages':[
            ToolMessage(content=json.dumps({'error':'search failed'}),tool_call_id='s2',name='search_products',status='error')]})
        self.assertEqual(state.preferences['_advisor']['status'],'ready_to_search')

    def test_confirmed_catalog_search_ends_without_extra_model_or_web_round(self):
        import asyncio
        class SearchOnlyModel:
            calls=0
            tools=[]
            choice=None
            def bind_tools(self, tools, **kwargs):
                self.tools=[tool.name for tool in tools]
                self.choice=kwargs.get('tool_choice')
                return self
            async def ainvoke(self, messages):
                self.calls+=1
                if self.calls>1:
                    raise AssertionError('No model round is needed after a successful catalog search')
                return AIMessage(content='',tool_calls=[{'name':'search_products','args':{'query':'هدفون'},'id':'search1','type':'tool_call'}])
        model=SearchOnlyModel()
        agent=object.__new__(ShoppingAgent)
        agent._system_prompt=''
        agent._model=model
        agent._model_with_tools=model
        agent._graph=agent._create_graph()
        state=ConversationState(budget=60,preferences={'_advisor':{'category':'هدفون','use':'موسیقی','status':'ready_to_search'}})
        response=asyncio.run(agent.run('بله',conversation=state))
        self.assertEqual(model.calls,1)
        self.assertEqual(model.tools,['search_products'])
        self.assertEqual(model.choice,{'type':'function','function':{'name':'search_products'}})
        self.assertEqual(response.search_query,'هدفون')
        self.assertTrue(response.cards)
        self.assertEqual(state.preferences['_advisor']['status'],'showing_results')

    def test_current_budget_overrides_stale_exact_model_tool_limits_even_when_cleared(self):
        import asyncio
        from unittest.mock import AsyncMock
        from types import SimpleNamespace
        for budget in (60,None):
            message=AIMessage(content='',tool_calls=[{'name':'search_products','args':{
                'query':'Samsung S24 FE','max_price':999,'filters':{'max_price':888}},'id':'s1','type':'tool_call'}])
            model=SimpleNamespace(ainvoke=AsyncMock(return_value=message))
            agent=object.__new__(ShoppingAgent)
            agent._system_prompt=''
            agent._model_with_tools=model
            result=asyncio.run(agent._call_model({'messages':[HumanMessage(content='جستجو کن')],
                'conversation':{'budget':budget,'preferences':{'_advisor':{'category':'گوشی','specific_model':'S24 FE'}}}}))
            args=result['messages'][0].tool_calls[0]['args']
            self.assertEqual(args['max_price'],budget)
            self.assertEqual(args['filters']['max_price'],budget)
            self.assertEqual(args['query'],'Samsung S24 FE')


if __name__=='__main__':
    unittest.main()

