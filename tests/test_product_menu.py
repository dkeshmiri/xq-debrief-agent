import unittest
from pathlib import Path
import app

class ProductMenuTests(unittest.TestCase):
    def test_product_selector_links_to_existing_profile_flows(self):
        client = app.app.test_client()
        page = client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'href="/profiles"', page.data)
        self.assertIn(b'href="/business/"', page.data)
        self.assertIn(b'XQ Family', page.data)
        self.assertIn(b'XQ Workplace', page.data)
        for route in ['/profiles', '/business/']:
            response = client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b'id="saved-profile"', response.data)
            self.assertIn(b'id="choose-new"', response.data)

    def test_logo_is_present_on_every_screen(self):
        client = app.app.test_client()
        for route in ['/', '/profiles', '/debrief', '/json-maker', '/family',
                      '/business/', '/business/debrief', '/business/json-maker', '/business/team']:
            with self.subTest(route=route):
                response = client.get(route)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'/static/xq-dev-logo.png', response.data)
                self.assertIn(b'XQ Innovation Dev', response.data)
        response = client.get('/static/xq-dev-logo.png')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'image/png')
        self.assertEqual(response.data, (Path(app.BASE_DIR) / 'static/xq-dev-logo.png').read_bytes())

    def test_family_navigation_returns_to_profiles(self):
        client = app.app.test_client()
        for route in ['/debrief','/json-maker','/family']:
            with self.subTest(route=route):
                self.assertIn(b'href="/profiles"', client.get(route).data)

