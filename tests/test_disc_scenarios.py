import copy
import unittest
from concurrent.futures import Future
from fractions import Fraction
from pathlib import Path
from unittest.mock import Mock

from flask import Flask
import disc_pilot_scoring as frequency
import disc_scenario_scoring as ranking
from disc_pilot_routes import create_disc_pilot_blueprint


def answers(natural='DISC', adapted='CSID'):
    return {'version': ranking.VERSION, 'responses': {
        context: {item['id']: list(order) for item in ranking.ITEMS}
        for context, order in [('natural', natural), ('adapted', adapted)]}}


class RankingScoreTests(unittest.TestCase):
    def test_bank_has_16_matched_scenarios_with_distinct_work_wording(self):
        self.assertEqual(len(ranking.ITEMS), 16)
        self.assertEqual(len(ranking.ITEM_IDS), 16)
        for item in ranking.ITEMS:
            self.assertEqual(set(item['options']), set('DISC'))
            self.assertTrue(item['stem'])
            self.assertEqual(len(set(item['options'].values())), 4)
            adapted = item['adapted']
            self.assertNotEqual(item['stem'], adapted['stem'])
            self.assertEqual(set(adapted['options']), set('DISC'))
            self.assertEqual(len(set(adapted['options'].values())), 4)
            for dimension in 'DISC':
                self.assertNotEqual(item['options'][dimension], adapted['options'][dimension])

    def test_known_rankings_and_context_shift_match_report(self):
        result = ranking.score_assessment(answers())
        self.assertEqual([result['profiles']['natural'][d]['score'] for d in 'DISC'], [100, 67, 33, 0])
        self.assertEqual([result['profiles']['adapted'][d]['score'] for d in 'DISC'], [0, 33, 67, 100])
        self.assertEqual(result['profiles']['natural']['D']['firsts'], 16)
        self.assertEqual(result['profiles']['natural']['D']['raw_total'], 48)
        self.assertEqual(result['profiles']['natural']['C']['lasts'], 16)
        self.assertIn('Natural preference score is 100 out of 100', result['sections'][1]['text'])
        self.assertIn('first in 16 of 16 situations', result['sections'][1]['text'])
        self.assertIn('greater relative emphasis in your Natural preferences', result['sections'][1]['text'])
        self.assertIn('greater relative emphasis in your Adapted work choices', result['sections'][4]['text'])
        self.assertEqual(result['score_kind'], 'relative_preference_index')
        for context in ranking.CONTEXTS:
            rows = result['profiles'][context].values()
            self.assertEqual(sum(row['raw_total'] for row in rows), 0)
            self.assertEqual(sum(50 + Fraction(row['raw_total'] * 50, 48) for row in rows), 200)

    def test_balanced_rankings_and_ties_are_preserved(self):
        payload = answers()
        for context in ranking.CONTEXTS:
            for index, item in enumerate(ranking.ITEMS):
                order = 'DISC'; shift = index % 4
                payload['responses'][context][item['id']] = list(order[shift:] + order[:shift])
        result = ranking.score_assessment(payload)
        self.assertEqual([result['profiles']['natural'][d]['score'] for d in 'DISC'], [50] * 4)
        self.assertIn('equal emphasis across all four', result['summaries']['natural'])
        self.assertIn('equal relative emphasis in both contexts', result['sections'][1]['text'])
        for index, item in enumerate(ranking.ITEMS):
            payload['responses']['natural'][item['id']] = list('DISC' if index % 2 else 'IDSC')
        self.assertIn('direction and interaction', ranking.score_assessment(payload)['summaries']['natural'])

    def test_order_invariance_no_mutation_and_rounding(self):
        payload = answers(); original = copy.deepcopy(payload)
        reordered = copy.deepcopy(payload)
        reordered['responses']['natural'] = dict(reversed(list(reordered['responses']['natural'].items())))
        self.assertEqual(ranking.score_assessment(payload), ranking.score_assessment(reordered))
        self.assertEqual(payload, original)
        # Raw total 12 gives 62.5, displayed/spoken as 63, with exact raw data retained.
        for index, item in enumerate(ranking.ITEMS):
            payload['responses']['natural'][item['id']] = list('DISC' if index < 10 else 'CSID')
        result = ranking.score_assessment(payload)
        self.assertEqual(result['profiles']['natural']['D']['raw_total'], 12)
        self.assertEqual(result['profiles']['natural']['D']['score'], 63)
        self.assertIn('score is 63 out of 100', result['sections'][1]['text'])

    def test_duplicate_partial_and_invalid_rankings_are_rejected(self):
        for value in ([], ['D'], list('DDIC'), list('DISX'), 'DISC', [1, 2, 3, 4],
                      [True, 'I', 'S', 'C'], [[], 'I', 'S', 'C'], None, list('DISCC')):
            payload = answers(); payload['responses']['natural']['B01'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                ranking.score_assessment(payload)
        for mutate in (lambda p: p['responses']['natural'].pop('B01'),
                       lambda p: p['responses'].pop('adapted'),
                       lambda p: p['responses']['natural'].update(extra=list('DISC')),
                       lambda p: p.update(scores={'D': 100}),
                       lambda p: p.update(version=frequency.VERSION)):
            payload = answers(); mutate(payload)
            with self.assertRaises(ValueError):
                ranking.score_assessment(payload)

    def test_16_group_normalization_matches_a_doubled_32_group_reference(self):
        payload = answers()
        orders = ['DISC', 'IDCS', 'SCID', 'CDSI', 'DSIC']
        for context in ranking.CONTEXTS:
            for index, item in enumerate(ranking.ITEMS):
                payload['responses'][context][item['id']] = list(orders[index % len(orders)])
        result = ranking.score_assessment(payload)
        self.assertEqual(result['scoring']['groups_per_context'], 16)
        for context, rows in result['profiles'].items():
            for dimension, row in rows.items():
                # Equivalent positive rank points, independently computed on 32 groups.
                doubled = list(payload['responses'][context].values()) * 2
                points = sum(3 - order.index(dimension) for order in doubled)
                expected = Fraction(points * 100, 32 * 3)
                rounded = int(expected + Fraction(1, 2))
                self.assertEqual(row['score'], rounded)
                self.assertEqual(row['count'], 16)

    def test_old_version_and_64_group_payloads_cannot_be_silently_rescored(self):
        payload = answers(); payload['version'] = 'xq-disc-scenario-v1'
        with self.assertRaises(ValueError):
            ranking.score_assessment(payload)
        payload = answers()
        payload['responses'] = {context: {f'B{i:02d}': list('DISC') for i in range(1, 33)}
                                for context in ranking.CONTEXTS}
        with self.assertRaises(ValueError):
            ranking.score_assessment(payload)


class RankingRouteTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.app = Flask(__name__, template_folder=str(root / 'templates'))
        self.app.config.update(TESTING=True, DISC_PILOT_ENABLED=True)
        self.voice = Mock(); clip = Future(); clip.set_result(b'RIFF-test')
        self.voice.audio.return_value = clip
        for mode in ('frequency', 'ranking'):
            self.app.register_blueprint(create_disc_pilot_blueprint(self.voice, mode=mode))
        self.client = self.app.test_client()

    def test_both_pages_and_questionnaires_are_distinct(self):
        for path, version, scale in [('/pilot/disc', frequency.VERSION, b'RESPONSE FREQUENCY'),
                                     ('/pilot/disc/scenarios', ranking.VERSION, b'RELATIVE PREFERENCE')]:
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertIn(scale, page.data)
            self.assertIn(b'href="/pilot/disc/scenarios"', page.data)
            self.assertIn(b'href="/pilot/disc"', page.data)
            self.assertEqual(self.client.get(path + '/questionnaire').json['version'], version)
        self.assertNotIn(b'Never', self.client.get('/pilot/disc/scenarios').data)
        page = self.client.get('/pilot/disc/scenarios').data
        self.assertIn(b'16 Natural and 16 Adapted', page)
        self.assertIn(b'max="32"', page)
        bank = self.client.get('/pilot/disc/scenarios/questionnaire').json
        self.assertEqual(len(bank['items']), 16)
        self.assertIn('adapted', bank['items'][0])
        self.assertEqual(bank['contexts']['adapted'], 'Adapted')

    def test_instruments_reject_each_others_payloads(self):
        payload = {'version': frequency.VERSION, 'responses': {
            context: {item['id']: 2 for item in frequency.ITEMS} for context in frequency.CONTEXTS}}
        self.assertEqual(self.client.post('/pilot/disc/report', json=payload).status_code, 200)
        self.assertEqual(self.client.post('/pilot/disc/scenarios/report', json=payload).status_code, 400)
        self.assertEqual(self.client.post('/pilot/disc/report', json=answers()).status_code, 400)
        response = self.client.post('/pilot/disc/scenarios/report', json=answers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        self.voice.audio.assert_not_called()

    def test_audio_recomputes_the_same_scenario_feedback(self):
        payload = answers()
        response = self.client.post('/pilot/disc/scenarios/audio/D', json=payload)
        self.assertEqual(response.mimetype, 'audio/wav')
        self.voice.audio.assert_called_once_with(ranking.score_assessment(payload)['sections'][1]['text'])
        payload['text'] = 'Other text'
        self.assertEqual(self.client.post('/pilot/disc/scenarios/audio/D', json=payload).status_code, 400)
        self.voice.audio.assert_called_once()

    def test_feature_flag_hides_all_scenario_routes(self):
        self.app.config['DISC_PILOT_ENABLED'] = False
        for path in ('', '/questionnaire'):
            self.assertEqual(self.client.get('/pilot/disc/scenarios' + path).status_code, 404)
        for path in ('/report', '/audio/D'):
            self.assertEqual(self.client.post('/pilot/disc/scenarios' + path, json=answers()).status_code, 404)


if __name__ == '__main__':
    unittest.main()
