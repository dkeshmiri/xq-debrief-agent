import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from comparison_engine import ComparisonEngine
from context_router import ContextDomain
from family_group import FamilyGroupEngine, validate_member_ids
from family_group_reasoner import FamilyGroupReasoner


def group_personas(count=4):
    people = [json.loads(Path(f'data/personas/{name}.json').read_text()) for name in ('samuel', 'jennifer')]
    for role, name in [('Son', 'Synthetic Son'), ('Daughter', 'Synthetic Daughter')]:
        person = copy.deepcopy(people[0])
        person['person'].update(person_id=f'test-{role}', display_name=name, family_role=role)
        people.append(person)
    return people[:count]


class FamilyGroupTests(unittest.TestCase):
    def test_two_three_four_members_have_all_exact_pairs_and_original_scores(self):
        for count in (2, 3, 4):
            with self.subTest(count=count):
                personas = group_personas(count)
                before = copy.deepcopy(personas)
                packet = FamilyGroupEngine().compare(personas)
                self.assertEqual(len(packet['members']), count)
                self.assertEqual(len(packet['pairs']), count * (count - 1) // 2)
                by_id = {p['person']['person_id']: p for p in personas}
                for pair in packet['pairs']:
                    a, b = [by_id[pid] for pid in pair['member_ids']]
                    self.assertEqual(pair['comparison'], ComparisonEngine().compare_personas(a, b))
                for persona in personas:
                    pid = persona['person']['person_id']
                    self.assertEqual(packet['assessments']['disc_natural']['D'][pid], persona['disc']['natural']['D'])
                packet['assessments']['disc_natural']['D'][personas[0]['person']['person_id']] = 0
                self.assertEqual(personas, before)

    def test_invalid_group_size_or_duplicate_ids_are_rejected(self):
        for ids in (None, [], ['a'], ['a', 'b', 'c', 'd', 'e'], ['a', 'a'], ['a', ''], ['a', 4]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                validate_member_ids(ids)

    def test_missing_assessment_scores_are_not_filled_in(self):
        personas = group_personas()
        personas[2]['eq']['scores'].pop('motivation')
        with self.assertRaises(ValueError):
            FamilyGroupEngine().compare(personas)


class FamilyGroupReasonerTests(unittest.TestCase):
    def setUp(self):
        self.personas = group_personas()
        self.ids = [p['person']['person_id'] for p in self.personas]
        self.requests = []
        self.output = {'observations': [{'member_ids': self.ids,
            'text': 'Different preferences may call for discussing pace and giving everyone a turn to speak.'}]}
        def create(**kwargs):
            self.requests.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(self.output))
        self.reasoner = FamilyGroupReasoner(client=SimpleNamespace(responses=SimpleNamespace(create=create)))

    def test_four_member_question_makes_one_call_and_has_no_experimental_context(self):
        self.personas[0]['person']['birth_order'] = 'SECRET_BIRTH_CONTEXT'
        self.personas[0]['person']['gender_role_experiences'] = ['SECRET_GENDER_CONTEXT']
        result = self.reasoner.answer_question('Compare our DISC preferences', self.personas)
        self.assertIsNone(result.validation_issues)
        self.assertEqual(len(self.requests), 1)
        context = json.loads(self.requests[0]['input'][1]['content'])['context']
        self.assertEqual(len(context['pairs']), 6)
        self.assertEqual({p['person_id'] for p in context['members']}, set(self.ids))
        self.assertNotIn('birth_order', context)
        self.assertNotIn('gender_role_experiences', context)
        self.assertNotIn('SECRET_BIRTH_CONTEXT', json.dumps(context))
        self.assertNotIn('SECRET_GENDER_CONTEXT', json.dumps(context))
        for persona in self.personas:
            self.assertIn(persona['person']['display_name'], result.response)

    def test_unknown_ids_omitted_members_and_bad_scores_are_rejected(self):
        cases = [
            {'member_ids': ['missing'], 'text': 'A possible preference.'},
            {'member_ids': self.ids[:2], 'text': 'Some possible differences.'},
            {'member_ids': self.ids, 'text': "Samuel's D score is 99."},
            {'member_ids': self.ids, 'text': 'They will never get along.'},
            {'member_ids': self.ids, 'text': 'Samuel has ADHD.'},
        ]
        for observation in cases:
            with self.subTest(observation=observation):
                self.output = {'observations': [observation]}
                result = self.reasoner.answer_question('Compare our DISC preferences', self.personas)
                self.assertTrue(result.validation_issues)

    def test_member_references_cannot_claim_another_selected_person(self):
        self.output = {'observations': [
            {'member_ids': self.ids[:2], 'text': 'Synthetic Daughter may prefer a slower pace.'},
            {'member_ids': self.ids[2:], 'text': 'Preferences may differ.'},
        ]}
        self.assertTrue(self.reasoner.answer_question('Compare DISC', self.personas).validation_issues)

    def test_unsupported_domain_does_not_call_model(self):
        with self.assertRaises(ValueError):
            self.reasoner.answer_question('What about us?', self.personas)
        self.assertEqual(self.requests, [])

    def test_malformed_model_output_is_not_published(self):
        self.output = {'answer': 'Unverified answer'}
        result = self.reasoner.answer_question('Compare EQ', self.personas)
        self.assertTrue(result.validation_issues)
        self.assertEqual(result.resolved_domain, ContextDomain.EQ)

    def test_integrated_question_has_all_domains_with_shared_knowledge(self):
        result = self.reasoner.answer_question('Compare our DISC, Driving Forces, and EQ together', self.personas)
        self.assertIsNone(result.validation_issues)
        context = json.loads(self.requests[0]['input'][1]['content'])['context']
        self.assertEqual(set(context['approved_knowledge']), {'disc', 'driving_forces', 'eq'})
        self.assertEqual(len(context['score_range_wording']), 4)
        self.assertEqual(len(context['pairs']), 6)
        self.assertNotIn('approved_knowledge', context['pairs'][0])
