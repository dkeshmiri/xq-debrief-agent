import copy
import unittest
from concurrent.futures import Future
from pathlib import Path
from unittest.mock import Mock

from flask import Flask

import disc_hybrid_scoring as hybrid
import disc_pilot_scoring as frequency
import disc_scenario_scoring as ranking
from disc_pilot_routes import create_disc_pilot_blueprint


def answers(value=4, first='D'):
    return {'version': hybrid.VERSION, 'responses': {
        context: {item['id']: {'ratings': dict.fromkeys('DISC', value), 'first': first}
                  for item in hybrid.ITEMS} for context in hybrid.CONTEXTS}}


class HybridScoreTests(unittest.TestCase):
    def test_short_bank_balances_dimensions_and_has_distinct_context_wording(self):
        self.assertEqual(len(hybrid.ITEMS), 4)
        self.assertEqual(len(hybrid.ITEM_IDS), 4)
        self.assertEqual(hybrid._SOURCE['version'], hybrid.VERSION)
        for item in hybrid.ITEMS:
            self.assertEqual(set(item['options']), set('DISC'))
            self.assertEqual(set(item['adapted']['options']), set('DISC'))
            self.assertNotEqual(item['stem'], item['adapted']['stem'])
            for dimension in 'DISC':
                self.assertNotEqual(item['options'][dimension], item['adapted']['options'][dimension])

    def test_every_dimension_can_reach_all_five_anchors_independently(self):
        for rating, expected in enumerate([0, 25, 50, 75, 100]):
            result = hybrid.score_assessment(answers(rating))
            for context in hybrid.CONTEXTS:
                self.assertEqual([result['profiles'][context][d]['score'] for d in 'DISC'], [expected] * 4)
                self.assertEqual(result['profiles'][context]['C']['firsts'], 0)
            self.assertIn(f'Natural frequency score is {expected} out of 100', result['sections'][4]['text'])

    def test_high_d_and_c_without_any_c_first_choices(self):
        payload = answers()
        payload['responses']['natural'][hybrid.ITEMS[0]['id']]['ratings']['C'] = 3
        result = hybrid.score_assessment(payload)
        self.assertEqual(result['profiles']['natural']['D']['score'], 100)
        self.assertEqual(result['profiles']['natural']['C']['score'], 94)
        self.assertEqual(result['profiles']['natural']['C']['firsts'], 0)
        self.assertIn('Natural frequency score is 94 out of 100', result['sections'][4]['text'])
        self.assertIn('first in 0 of 4 Natural situations', result['sections'][4]['text'])

    def test_choice_changes_counts_and_narration_but_never_frequency_scores(self):
        first, second = hybrid.score_assessment(answers(first='D')), hybrid.score_assessment(answers(first='C'))
        for context in hybrid.CONTEXTS:
            for dimension in 'DISC':
                for key in ('score', 'total', 'frequency', 'count'):
                    self.assertEqual(first['profiles'][context][dimension][key], second['profiles'][context][dimension][key])
            self.assertEqual(second['profiles'][context]['C']['firsts'], 4)
            self.assertEqual(sum(row['firsts'] for row in second['profiles'][context].values()), 4)
        self.assertIn('precision first most often', second['summaries']['natural'])

    def test_rating_changes_do_not_affect_other_dimensions_or_choices(self):
        payload = answers(2)
        before = hybrid.score_assessment(payload)
        payload['responses']['natural'][hybrid.ITEMS[0]['id']]['ratings']['D'] = 4
        after = hybrid.score_assessment(payload)
        self.assertEqual(after['profiles']['natural']['D']['score'], 63)  # 62.5 rounds half up.
        self.assertIn('score is 63 out of 100', after['sections'][1]['text'])
        self.assertIn('more often in your Natural everyday responses', after['sections'][1]['text'])
        for dimension in 'ISC':
            self.assertEqual(before['profiles']['natural'][dimension], after['profiles']['natural'][dimension])
        self.assertEqual(before['profiles']['adapted'], after['profiles']['adapted'])
        self.assertEqual(before['summaries'], after['summaries'])

    def test_ties_and_context_comparisons_preserve_both_kinds_of_evidence(self):
        payload = answers(0)
        for context in hybrid.CONTEXTS:
            for index, answer in enumerate(payload['responses'][context].values()):
                answer['first'] = 'DISC'[index]
        result = hybrid.score_assessment(payload)
        self.assertIn('each approach first equally often', result['summaries']['natural'])
        self.assertIn('same average frequency', result['sections'][1]['text'])
        for index, answer in enumerate(payload['responses']['adapted'].values()):
            answer['first'] = 'D' if index < 2 else 'C'
            answer['ratings']['D'] = 3
        result = hybrid.score_assessment(payload)
        self.assertIn('direction and precision first most often: 2 of 4 situations each', result['summaries']['adapted'])
        self.assertIn('more often in your Adapted work responses', result['sections'][1]['text'])

    def test_scoring_does_not_mutate_answers_or_depend_on_submission_order(self):
        payload = answers()
        original = copy.deepcopy(payload)
        expected = hybrid.score_assessment(payload)
        self.assertEqual(payload, original)
        for context in hybrid.CONTEXTS:
            payload['responses'][context] = dict(reversed(list(payload['responses'][context].items())))
        self.assertEqual(expected, hybrid.score_assessment(payload))

    def test_invalid_ratings_and_choices_are_rejected(self):
        for value in (True, 4.0, -1, 5, '4', None, [], {}):
            payload = answers()
            payload['responses']['natural']['H01']['ratings']['D'] = value
            with self.subTest(rating=value), self.assertRaises(ValueError):
                hybrid.score_assessment(payload)
        for value in ('', 'X', None, [], {}, True, ['D']):
            payload = answers()
            payload['responses']['natural']['H01']['first'] = value
            with self.subTest(first=value), self.assertRaises(ValueError):
                hybrid.score_assessment(payload)

    def test_incomplete_extra_and_cross_version_answers_are_rejected(self):
        malformed = [None, [], {}, {'version': hybrid.VERSION, 'responses': []}]
        for path in [('responses', 'adapted'), ('responses', 'natural', 'H01'),
                     ('responses', 'natural', 'H01', 'ratings'),
                     ('responses', 'natural', 'H01', 'ratings', 'D'),
                     ('responses', 'natural', 'H01', 'first')]:
            payload = answers(); target = payload
            for key in path[:-1]:
                target = target[key]
            del target[path[-1]]
            malformed.append(payload)
        for path in [(), ('responses',), ('responses', 'natural'),
                     ('responses', 'natural', 'H01'), ('responses', 'natural', 'H01', 'ratings')]:
            payload = answers(); target = payload
            for key in path:
                target = target[key]
            target['unexpected'] = 4
            malformed.append(payload)
        for version in (frequency.VERSION, ranking.VERSION, 'xq-disc-hybrid-v0'):
            payload = answers(); payload['version'] = version; malformed.append(payload)
        for payload in malformed:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                hybrid.score_assessment(payload)


class HybridRouteTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'))
        self.app.config.update(TESTING=True, DISC_PILOT_ENABLED=True)
        self.voice = Mock(); clip = Future(); clip.set_result(b'RIFF-test')
        self.voice.audio.return_value = clip
        for mode in ('frequency', 'ranking', 'hybrid'):
            self.app.register_blueprint(create_disc_pilot_blueprint(self.voice, mode=mode))
        self.client = self.app.test_client()

    def test_page_questionnaire_and_report_work_without_speech(self):
        page = self.client.get('/pilot/disc/hybrid')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'data-mode="hybrid"', page.data)
        self.assertIn(b'32 quick ratings and eight first choices', page.data)
        self.assertIn(b'XQ Innovation Dev', page.data)
        self.assertIn(b'BEHAVIOR FREQUENCY', page.data)
        self.assertIn(b'max="8"', page.data)
        bank = self.client.get('/pilot/disc/hybrid/questionnaire').json
        self.assertEqual(bank['version'], hybrid.VERSION)
        self.assertEqual(len(bank['items']), 4)
        result = self.client.post('/pilot/disc/hybrid/report', json=answers())
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers['Cache-Control'], 'no-store')
        self.assertEqual(result.json, self.app.json.loads(self.app.json.dumps(hybrid.score_assessment(answers()))))
        self.voice.audio.assert_not_called()

    def test_every_audio_section_uses_the_exact_report_text(self):
        payload = answers()
        payload['responses']['natural']['H01']['ratings']['C'] = 3
        result = self.client.post('/pilot/disc/hybrid/report', json=payload).json
        for section in result['sections']:
            response = self.client.post('/pilot/disc/hybrid/audio/' + section['id'], json=payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, 'audio/wav')
            self.voice.audio.assert_called_with(section['text'])
        calls = self.voice.audio.call_count
        self.assertEqual(self.client.post('/pilot/disc/hybrid/audio/unknown', json=payload).status_code, 404)
        payload['text'] = 'Unrelated text'
        self.assertEqual(self.client.post('/pilot/disc/hybrid/audio/D', json=payload).status_code, 400)
        self.assertEqual(self.voice.audio.call_count, calls)

    def test_hybrid_payloads_are_isolated_and_gated(self):
        for path in ('/pilot/disc', '/pilot/disc/scenarios'):
            self.assertEqual(self.client.post(path + '/report', json=answers()).status_code, 400)
            self.assertIn(b'href="/pilot/disc/hybrid"', self.client.get(path).data)
        self.assertEqual(self.client.post('/pilot/disc/hybrid/report', data='x' * 17000).status_code, 413)
        self.app.config['DISC_PILOT_ENABLED'] = False
        for path in ('', '/questionnaire'):
            self.assertEqual(self.client.get('/pilot/disc/hybrid' + path).status_code, 404)
        for path in ('/report', '/audio/D'):
            self.assertEqual(self.client.post('/pilot/disc/hybrid' + path, json=answers()).status_code, 404)
        self.voice.audio.assert_not_called()


if __name__ == '__main__':
    unittest.main()
