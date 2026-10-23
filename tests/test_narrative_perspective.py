import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from ai_reasoner import AIReasoner
from assessment_importer import AssessmentImporter, ImportServiceError
from debrief_engine import DebriefEngine
from debrief_state import DebriefState, DEBRIEF_SEQUENCE
from narrative_perspective import language_issues, legacy_participant_text, perspective_issues
from test_assessment_importer import fixtures
from test_business_workspace import business_profile


class PerspectiveTests(unittest.TestCase):
    def test_workplace_library_prose_addresses_you_in_every_sentence(self):
        root = Path(__file__).resolve().parent.parent / 'content/business/narratives'

        def check(value, path):
            if isinstance(value, dict):
                for key, child in value.items():
                    if key not in ('trait_names', 'label', 'shifts', 'range_policy', 'range_thresholds'):
                        check(child, path + '.' + key)
            elif isinstance(value, list):
                for i, child in enumerate(value):
                    check(child, path + f'[{i}]')
            elif isinstance(value, str):
                self.assertFalse(perspective_issues(value, {}), path)

        for file in root.glob('*.json'):
            check(json.loads(file.read_text()), file.name)

    def test_each_sentence_and_item_must_address_participant(self):
        person = {'first_name': 'Alex', 'display_name': 'Alex'}
        for text in ('Alex may lead change.', 'His directness may help your team.',
                     'You may lead change. They tend to decide quickly.', 'Clear goals.',
                     'The participant may clarify your team priorities.'):
            with self.subTest(text=text):
                self.assertTrue(perspective_issues(text, person))
        self.assertFalse(perspective_issues(
            'Your colleagues may need time before they share your confidence.', person))
        self.assertFalse(perspective_issues('Alex, your priorities may differ from your colleagues’ priorities.', person))

    def test_names_that_are_common_words_do_not_rewrite_modals(self):
        person = {'first_name': 'Will', 'display_name': 'Will'}
        self.assertEqual(legacy_participant_text('Will may lead; your team will respond.', person),
                         'You may lead; your team will respond.')
        self.assertFalse(perspective_issues('You will have time to reflect.', person))
        self.assertFalse(perspective_issues('Your report has gaps.', {'first_name': None, 'display_name': None}))

    def test_legacy_female_subject_possessive_and_object_agree(self):
        self.assertEqual(legacy_participant_text(
            'She is direct. Her awareness may help her notice her reactions under pressure.', {}),
            'You are direct. Your awareness may help you notice your reactions under pressure.')

    def test_empty_live_answer_keeps_reasoning_result_contract(self):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text='')
        result = AIReasoner(client=client, experience='business').answer_question(
            'How can I give feedback?', DebriefState.INTRODUCTION, business_profile())
        self.assertIn('Your question', result.response)
        self.assertEqual(result.resolved_domain, 'integrated')

    def test_json_generation_retries_then_uses_valid_language_in_both_workspaces(self):
        for experience in ('family', 'business'):
            extraction, good = fixtures()
            bad = good.model_copy(deep=True)
            bad.integrated.overview = 'He may lead change.'
            service = AssessmentImporter(experience=experience)
            service._parse = Mock(side_effect=[bad, good])
            result = service.generate(extraction, 'Team lead')
            self.assertEqual(service._parse.call_count, 2)
            self.assertEqual(result['persona']['eq'], extraction.facts.eq.model_dump())
            self.assertIn('PERSPECTIVE IS A REQUIRED OUTPUT CONTRACT', service._parse.call_args_list[0].args[1])
            self.assertIn('integrated.overview', service._parse.call_args.args[1])
            self.assertFalse(language_issues(good, extraction.facts.person.model_dump()))

    def test_repeated_invalid_json_cannot_be_published_and_facts_are_unchanged(self):
        extraction, language = fixtures()
        original = extraction.model_dump()
        language.disc.communication_do = ['Ask him to decide.']
        service = AssessmentImporter()
        service._parse = Mock(return_value=language)
        with self.assertRaisesRegex(ImportServiceError, 'No profile was generated'):
            service.generate(extraction, 'Parent')
        self.assertEqual(service._parse.call_count, 2)
        self.assertEqual(extraction.model_dump(), original)

    def test_extraction_evidence_is_not_rewritten(self):
        extraction, _ = fixtures()
        service = AssessmentImporter()
        service._parse = Mock(return_value=extraction)
        self.assertIs(service.extract([('report.pdf', b'%PDF-test')]), extraction)
        self.assertNotIn('PERSPECTIVE IS A REQUIRED OUTPUT CONTRACT', service._parse.call_args.args[1])

    def test_live_answer_retries_and_never_returns_invalid_prose(self):
        persona = business_profile()
        client = Mock()
        client.responses.create.side_effect = [SimpleNamespace(output_text='He may lead change.'),
                                               SimpleNamespace(output_text='You may lead change by asking your team for feedback.')]
        reasoner = AIReasoner(client=client, experience='business')
        result = reasoner.answer_question('How can I give feedback?', DebriefState.INTRODUCTION, persona)
        self.assertEqual(client.responses.create.call_count, 2)
        self.assertTrue(result.response.startswith('You may'))
        client.responses.create.side_effect = None
        client.responses.create.return_value = SimpleNamespace(output_text='His style is direct.')
        result = reasoner.answer_question('How can I give feedback?', DebriefState.INTRODUCTION, persona)
        self.assertNotIn('His style', result.response)
        self.assertIn('your question', result.response)

    def test_saved_workplace_profile_is_adapted_without_changing_scores_or_disk(self):
        profile = business_profile()
        name = profile['person']['display_name']
        profile['disc']['behavioral_characteristics'] = [f'{name} is direct.', 'He may initiate change.',
                                                       'His colleagues may need time before they share his confidence.']
        profile['disc']['value_to_family'] = [f'{name} may help the team decide.']
        profile['integrated']['overview'] = f'{name} has a direct style. He may lead change.'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'profile.json'
            original = json.dumps(profile)
            path.write_text(original)
            engine = DebriefEngine(path, ai_reasoner=object(), experience='business')
            self.assertEqual(engine.data['disc']['natural'], profile['disc']['natural'])
            self.assertEqual(engine.person, profile['person'])
            self.assertEqual(path.read_text(), original)
            for state in DEBRIEF_SEQUENCE:
                engine.current_state = state
                text = engine.get_current_content()
                self.assertNotRegex(text, r"\b(?:He|His|She|Her)\b")
                self.assertNotIn(f"{name}'s", text)
            self.assertIn('You are direct.', engine.get_disc_narrative())
            self.assertIn('they share your confidence', engine.get_disc_narrative())
            self.assertIn('You have a direct style.', engine.get_integrated_analysis())
            for method in (engine.get_disc_scores, engine.get_primary_disc_style,
                           engine.get_behavioral_characteristics, engine.get_value_to_family,
                           engine.get_driving_force_scores, engine.get_eq_scores):
                self.assertTrue(method().startswith('Your'))
