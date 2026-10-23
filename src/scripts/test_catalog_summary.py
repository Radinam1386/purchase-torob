"""The product cards expose only aggregates derived from their actual offers."""
import unittest
import json
from src.core.database import database
from src.scripts import test_acceptance_backend as fixtures


class CatalogSummaryTests(unittest.TestCase):
    setUp = fixtures.AcceptanceBackendTests.setUp
    tearDown = fixtures.AcceptanceBackendTests.tearDown

    def test_lower_budget_bound_is_shared_by_agent_search_and_grid(self):
        from src.core.tools.catalog import search_products
        tool = search_products.invoke({'query': 'هدفون', 'max_price': 60, 'filters': {'min_price': 40}})['data']
        self.assertEqual([item['id'] for item in tool], ['p1'])
    def test_card_aggregates_count_offers_and_shops_separately(self):
        data = self.client.get('/api/products', params={'q': 'هدفون'}).json()['data']
        item = next(product for product in data if product['id'] == 'p0')
        self.assertEqual(item['offerCount'], 2)
        self.assertEqual(item['shopCount'], 1)
        self.assertEqual(item['minPrice'], 10)
        self.assertEqual(item['maxPrice'], 100)
        self.assertIsNone(item['priceUpdatedAt'])
        self.assertEqual(item['specHighlights'], [])

    def test_aggregates_use_the_same_price_range_as_the_search(self):
        data = self.client.get('/api/products', params={'q': 'هدفون', 'min_price': 40, 'max_price': 60}).json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['offerCount'], 4)
        self.assertEqual(data[0]['shopCount'], 4)
        self.assertEqual(data[0]['minPrice'], 50)
        self.assertEqual(data[0]['maxPrice'], 55)

    def test_grid_and_map_share_geography_city_services_and_price_eligibility(self):
        all_day = json.dumps({day: {'status': 'declared', 'shifts': [{'start_time': '00:00', 'end_time': '23:59'}]}
                              for day in ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']})
        with database() as connection:
            connection.execute("UPDATE shops SET payment_options=?,fast_delivery=1,weekly_hours=? WHERE id='s0'",
                               (json.dumps([{'channel': 'in_person'}]), all_day))
            connection.execute("UPDATE shops SET fast_delivery=1 WHERE id='s1'")
            connection.execute("UPDATE shops SET payment_options=?,weekly_hours=? WHERE id='s2'",
                               (json.dumps([{'channel': 'in_person'}]), all_day))
            connection.execute("UPDATE offers SET price_updated_at='2026-01-01' WHERE id='o2'")
            connection.execute("UPDATE offers SET price_updated_at='2026-03-01' WHERE id='o5'")
        cases = [{}, {'radius_km': 0}, {'radius_km': 0, 'min_price': 40, 'max_price': 60},
                 {'installment': True}, {'express': True}, {'open_now': True},
                 {'city': 'تهران'}, {'city': 'شیراز'}, {'min_price': 55, 'max_price': 60, 'installment': True},
                 {'lat': 0, 'lng': 0, 'radius_km': 0}]
        for filters in cases:
            params = {'q': 'هدفون', 'lat': 35.7, 'lng': 51.4, 'radius_km': 1, **filters}
            with self.subTest(filters=filters):
                grid_response = self.client.get('/api/products', params={**params, 'page_size': 60})
                map_response = self.client.get('/api/map/offers', params=params)
                self.assertEqual(grid_response.status_code, 200, grid_response.text)
                self.assertEqual(map_response.status_code, 200, map_response.text)
                grid, mapped = grid_response.json(), map_response.json()
                self.assertEqual({item['id'] for item in grid['data']}, {item['id'] for item in mapped['products']})
                self.assertEqual(grid['total'], mapped['product_count'])
                for product in grid['data']:
                    offers = [item['offer'] for item in mapped['results'] if item['offer']['productId'] == product['id']]
                    prices = [offer['price'] for offer in offers if offer['price'] is not None]
                    dates = [offer['priceUpdatedAt'] for offer in offers if offer['priceUpdatedAt'] is not None]
                    self.assertEqual(product['offerCount'], len(offers))
                    self.assertEqual(product['shopCount'], len({offer['shopId'] for offer in offers}))
                    self.assertEqual(product['minPrice'], min(prices) if prices else None)
                    self.assertEqual(product['maxPrice'], max(prices) if prices else None)
                    self.assertEqual(product['priceUpdatedAt'], max(dates) if dates else None)
        bounded = self.client.get('/api/products', params={'q': 'هدفون', 'lat': 35.7, 'lng': 51.4,
            'radius_km': 0, 'min_price': 40, 'max_price': 60}).json()['data'][0]
        self.assertEqual((bounded['offerCount'], bounded['minPrice'], bounded['maxPrice'], bounded['priceUpdatedAt']),
                         (2, 50, 52, '2026-03-01'))

    def test_far_center_yields_zero_without_unlocated_matching_offers(self):
        params = {'q': 'هدفون موسیقی 0', 'lat': 0, 'lng': 0, 'radius_km': 0}
        self.assertEqual(self.client.get('/api/products', params=params).json()['total'], 0)
        self.assertEqual(self.client.get('/api/map/offers', params=params).json()['product_count'], 0)

    def test_scoped_price_sorting_and_pagination_use_matching_offers(self):
        params = {'q': 'هدفون', 'lat': 35.7, 'lng': 51.4, 'radius_km': 0, 'page_size': 1}
        first = self.client.get('/api/products', params={**params, 'sort': 'price_asc'}).json()
        second = self.client.get('/api/products', params={**params, 'sort': 'price_asc', 'page': 2}).json()
        descending = self.client.get('/api/products', params={**params, 'sort': 'price_desc'}).json()
        self.assertEqual(first['total'], 2)
        self.assertEqual(first['data'][0]['id'], 'p0')
        self.assertEqual(second['data'][0]['id'], 'p1')
        self.assertEqual(descending['data'][0]['id'], 'p1')


if __name__ == '__main__':
    unittest.main()
