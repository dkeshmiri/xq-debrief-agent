import copy
import json
from pathlib import Path
import unittest

from experiments.family_context import prepare_context


class ContextPrototypeTests(unittest.TestCase):
    def setUp(self):
        self.example = json.loads((Path(__file__).parents[1] / 'example.json').read_text())

    def prepare(self, **kwargs):
        return prepare_context(self.example['records'], self.example['selected_ids'], **kwargs)

    def test_master_and_request_options_are_required(self):
        self.assertFalse(self.prepare()['enabled'])
        self.assertFalse(self.prepare(options={'birth_order': True})['enabled'])
        self.assertFalse(self.prepare(experiment_enabled=True)['enabled'])
        self.assertEqual(self.prepare()['members'], [])

    def test_birth_context_keeps_upbringing_groups_separate_and_excludes_gender(self):
        data = self.prepare(experiment_enabled=True, options={'birth_order': True})
        self.assertEqual(len(data['members']), 2)
        self.assertNotEqual(data['members'][0]['birth_order']['upbringing_group_id'], data['members'][1]['birth_order']['upbringing_group_id'])
        self.assertNotIn('gender_role_experiences', data['members'][0])

    def test_gender_experiences_require_their_own_opt_in(self):
        data = self.prepare(experiment_enabled=True, options={'gender_role_experiences': True})
        self.assertEqual(len(data['members']), 1)
        self.assertNotIn('birth_order', data['members'][0])
        self.assertNotIn('experiences', data['members'][0])

    def test_unconfirmed_unselected_and_missing_context_is_excluded(self):
        self.example['records']['synthetic-parent']['confirmed'] = False
        self.example['selected_ids'] = ['synthetic-parent', 'missing']
        data = self.prepare(experiment_enabled=True, options={'birth_order': True})
        self.assertEqual(data['members'], [])
        self.assertEqual(data['missing_context_ids'], ['synthetic-parent', 'missing'])

    def test_invalid_ranks_and_score_fields_are_rejected(self):
        record = self.example['records']['synthetic-parent']
        record['birth_order']['rank'] = 4
        with self.assertRaises(ValueError):
            self.prepare(experiment_enabled=True, options={'birth_order': True})
        record['birth_order']['rank'] = 2
        record['disc'] = {'D': 80}
        with self.assertRaises(ValueError):
            self.prepare(experiment_enabled=True, options={'birth_order': True})

    def test_context_is_detached_and_does_not_infer_unknown_rank(self):
        record = self.example['records']['synthetic-parent']
        record['birth_order'].pop('rank')
        record['birth_order']['multiple_birth'] = True
        before = copy.deepcopy(self.example)
        data = self.prepare(experiment_enabled=True, options={'birth_order': True})
        self.assertNotIn('rank', data['members'][0]['birth_order'])
        data['members'][0]['experiences'].append('Changed locally')
        self.assertEqual(self.example, before)

    def test_string_switch_and_unsupported_trait_options_cannot_activate_module(self):
        with self.assertRaises(ValueError):
            self.prepare(experiment_enabled='false', options={'birth_order': True})
        with self.assertRaises(ValueError):
            self.prepare(experiment_enabled=True, options={'score_adjustment': True})
