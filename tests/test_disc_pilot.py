import copy
import unittest
from concurrent.futures import Future, TimeoutError
from pathlib import Path
from unittest.mock import Mock

from flask import Flask

from disc_pilot_routes import create_disc_pilot_blueprint
from disc_pilot_scoring import ITEMS, VERSION, score_assessment


def answers(natural=2, adapted=3):
    return {'version': VERSION, 'responses': {
        'natural': {item['id']: natural for item in ITEMS},
        'adapted': {item['id']: adapted for item in ITEMS},
    }}


class ScoringTests(unittest.TestCase):
    def test_known_answers_align_scores_graph_anchors_and_spoken_feedback(self):
        result = score_assessment(answers())
        self.assertEqual(result['scale']['anchors'][50], 'Sometimes')
        self.assertEqual(result['scale']['anchors'][75], 'Often')
        for dimension in 'DISC':
            natural = result['profiles']['natural'][dimension]
            self.assertEqual(natural, {'total': 12, 'count': 6, 'score': 50, 'frequency': 'sometimes'})
            self.assertEqual(result['profiles']['adapted'][dimension]['score'], 75)
            text = next(section['text'] for section in result['sections'] if section['id'] == dimension)
            self.assertIn('Everyday score is 50 out of 100; your answers average sometimes', text)
            self.assertIn('At work score is 75 out of 100; your answers average often', text)
            self.assertIn('more often at work than in everyday life', text)

    def test_dimensions_are_independent_and_extremes_are_valid(self):
        for value in range(5):
            result = score_assessment(answers(value, value))
            self.assertEqual([row['score'] for row in result['profiles']['natural'].values()], [value * 25] * 4)
            self.assertIn('same average frequency', result['sections'][1]['text'])

    def test_rounding_retains_exact_totals_and_uses_response_anchor_wording(self):
        payload = answers(0, 0)
        payload['responses']['natural']['D1'] = 3
        result = score_assessment(payload)
        self.assertEqual(result['profiles']['natural']['D'], {
            'total': 3, 'count': 6, 'score': 13, 'frequency': 'between never and rarely'})
        self.assertIn('more often in everyday life than at work', result['sections'][1]['text'])
        self.assertNotIn('13.0', result['sections'][1]['text'])

    def test_order_does_not_affect_scoring_and_input_is_unchanged(self):
        payload = answers()
        original = copy.deepcopy(payload)
        shuffled = copy.deepcopy(payload)
        shuffled['responses'] = {context: dict(reversed(list(values.items())))
                                 for context, values in reversed(list(payload['responses'].items()))}
        self.assertEqual(score_assessment(payload), score_assessment(shuffled))
        self.assertEqual(payload, original)

    def test_rejects_missing_extra_out_of_range_and_non_integer_answers(self):
        for value in (True, None, 2.0, '2', -1, 5, [], {}):
            with self.subTest(value=value):
                payload = answers()
                payload['responses']['natural']['D1'] = value
                with self.assertRaises(ValueError):
                    score_assessment(payload)
        mutations = [
            lambda p: p.update(version='old'),
            lambda p: p.update(score=100),
            lambda p: p['responses'].pop('adapted'),
            lambda p: p['responses']['natural'].pop('D1'),
            lambda p: p['responses']['natural'].update(extra=2),
        ]
        for mutate in mutations:
            payload = answers(); mutate(payload)
            with self.assertRaises(ValueError):
                score_assessment(payload)
        for payload in (None, [], {}, {'version': VERSION, 'responses': []}):
            with self.assertRaises(ValueError):
                score_assessment(payload)


class RouteTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'))
        self.app.config.update(TESTING=True, DISC_PILOT_ENABLED=True)
        self.speech = Mock()
        future = Future(); future.set_result(b'RIFF-test-audio')
        self.speech.audio.return_value = future
        self.app.register_blueprint(create_disc_pilot_blueprint(self.speech))
        self.client = self.app.test_client()

    def test_page_and_report_need_no_speech_or_external_service(self):
        page = self.client.get('/pilot/disc')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'XQ Innovation Dev', page.data)
        bank = self.client.get('/pilot/disc/questionnaire').json
        self.assertEqual(len(bank['items']), 24)
        self.assertEqual(bank['version'], VERSION)
        self.assertEqual(bank['dimension_order'], list('DISC'))
        response = self.client.post('/pilot/disc/report', json=answers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.assertEqual(response.json['profiles']['natural']['D']['score'], 50)
        self.speech.audio.assert_not_called()

    def test_audio_is_recomputed_from_answers_and_matches_visible_report(self):
        payload = answers()
        expected = score_assessment(payload)['sections'][1]['text']
        audio = self.client.post('/pilot/disc/audio/D', json=payload)
        self.assertEqual(audio.status_code, 200)
        self.assertEqual(audio.mimetype, 'audio/wav')
        self.speech.audio.assert_called_once_with(expected)
        self.assertEqual(self.client.post('/pilot/disc/audio/unknown', json=payload).status_code, 404)
        payload['text'] = 'Speak unrelated text'
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=payload).status_code, 400)
        self.speech.audio.assert_called_once()

    def test_flag_disables_entire_surface(self):
        self.app.config['DISC_PILOT_ENABLED'] = False
        for path in ('', '/questionnaire', '/report', '/audio/D'):
            response = (self.client.post('/pilot/disc' + path, json=answers()) if path in ('/report', '/audio/D')
                        else self.client.get('/pilot/disc' + path))
            self.assertEqual(response.status_code, 404)
        self.speech.audio.assert_not_called()

    def test_invalid_submissions_are_rejected_before_synthesis(self):
        for body in (None, [], {}, {'version': VERSION}):
            response = self.client.post('/pilot/disc/audio/D', json=body)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post('/pilot/disc/report', data='x' * 17000).status_code, 413)
        self.speech.audio.assert_not_called()

    def test_synthesis_error_releases_slot_for_retry(self):
        good = self.speech.audio.return_value
        self.speech.audio.side_effect = [RuntimeError('Unavailable'), good]
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=answers()).status_code, 503)
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=answers()).status_code, 200)

    def test_timeout_holds_slot_until_pending_audio_finishes(self):
        pending = Mock()
        pending.result.side_effect = TimeoutError()
        self.speech.audio.return_value = pending
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=answers()).status_code, 503)
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=answers()).status_code, 409)
        pending.add_done_callback.call_args.args[0](pending)
        ready = Future(); ready.set_result(b'RIFF')
        self.speech.audio.return_value = ready
        self.assertEqual(self.client.post('/pilot/disc/audio/D', json=answers()).status_code, 200)


if __name__ == '__main__':
    unittest.main()
