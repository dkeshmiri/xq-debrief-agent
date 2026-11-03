import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from flask import Flask
from presentation import create_presentation_blueprint
from presentation_access import COOKIE


class PresentationAccessTests(unittest.TestCase):
    def setUp(self):
        self.pin = patch.dict('os.environ', {'XQ_PRESENTATION_PIN':'2020'})
        self.pin.start()
        self.addCleanup(self.pin.stop)
        self.app = Flask(__name__, template_folder=str(Path(__file__).resolve().parents[1]/'templates'))
        self.presentation = Mock()
        self.presentation.status.return_value = {'active':False}
        self.app.register_blueprint(create_presentation_blueprint(self.presentation))
        self.client = self.app.test_client()

    def unlock(self, pin='2020'):
        return self.client.post('/api/presentation/unlock', json={'pin':pin})

    def test_locked_page_redirects_and_all_presentation_actions_are_denied(self):
        response = self.client.get('/presentation')
        self.assertEqual(response.status_code,302)
        self.assertEqual(response.location,'/#presentation-access')
        self.assertEqual(self.client.get('/api/presentation/status').status_code,403)
        for action in ('start','play','next','repeat','end','source'):
            self.assertEqual(self.client.post('/api/presentation/'+action,json={}).status_code,403)
        self.assertEqual(self.presentation.mock_calls,[])

    def test_correct_pin_unlocks_only_this_browser_and_sets_private_cookie(self):
        self.assertFalse(self.client.get('/api/presentation/access').json['unlocked'])
        response = self.unlock()
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['Set-Cookie'])
        self.assertIn('SameSite=Strict',response.headers['Set-Cookie'])
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertEqual(self.client.get('/presentation').status_code,200)
        self.assertEqual(self.client.get('/api/presentation/status').status_code,200)
        self.assertEqual(self.client.post('/api/presentation/play').status_code,200)
        self.presentation.play.assert_called_once_with('play')
        self.assertEqual(self.app.test_client().get('/api/presentation/status').status_code,403)

    def test_wrong_pin_and_forged_cookie_do_not_unlock(self):
        for pin in ('wrong',None,2020):
            self.assertEqual(self.unlock(pin).status_code,403)
        self.client.set_cookie(COOKIE,'operator')
        self.assertEqual(self.client.get('/api/presentation/status').status_code,403)
        self.assertEqual(self.client.post('/api/presentation/unlock',data={'pin':'2020'}).status_code,415)

    def test_grant_expires_and_restarting_app_invalidates_it(self):
        self.unlock()
        token = self.client.get_cookie(COOKIE).value
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=4000000000):
            self.assertEqual(self.client.get('/api/presentation/status').status_code,403)
        other_app = Flask('fresh')
        other_app.register_blueprint(create_presentation_blueprint(Mock()))
        other = other_app.test_client()
        other.set_cookie(COOKIE,token)
        self.assertEqual(other.get('/api/presentation/status').status_code,403)

    def test_repeated_failures_are_temporarily_limited(self):
        with patch('presentation_access.monotonic',return_value=100):
            for _ in range(5):
                self.assertEqual(self.unlock('wrong').status_code,403)
            self.assertEqual(self.unlock().status_code,429)
        with patch('presentation_access.monotonic',return_value=161):
            self.assertEqual(self.unlock().status_code,200)
