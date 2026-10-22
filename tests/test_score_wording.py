import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

from context_builder import ContextBuilder
from comparison_reasoner import ComparisonReasoner
from context_router import ContextDomain, ContextRoute, ContextTopic
from conversation_orchestrator import ConversationOrchestrator
from debrief_engine import DebriefEngine
from debrief_state import DebriefState
from narratives.narrative_classifier import (
    classify_disc_score, classify_driving_force_score, classify_eq_score,
    classify_disc_shift, classify_eq_difference,
)
from narratives.narrative_renderer import (
    render_disc_narrative, render_driving_forces_narrative, render_eq_narrative,
)
from narratives.score_wording import score_wording
from playback_coordinator import PlaybackCoordinator
from playback_event_tracker import PlaybackEventTracker
from tavus_client import TavusClient

BASE = Path(__file__).resolve().parents[1]


class ScoreWordingTests(unittest.TestCase):
    def setUp(self):
        self.persona = json.loads((BASE / "data/personas/samuel.json").read_text())

    def at_score(self, score):
        persona = copy.deepcopy(self.persona)
        persona["disc"]["natural"] = dict.fromkeys("DISC", score)
        persona["disc"]["adapted"] = dict.fromkeys("DISC", 100 - score)
        persona["driving_forces"]["scores"] = dict.fromkeys(persona["driving_forces"]["scores"], score)
        persona["eq"]["scores"] = dict.fromkeys(persona["eq"]["scores"], score)
        for key in ("self_composite", "others_composite", "total_eq"):
            persona["eq"][key] = score
        return persona

    def test_every_tenth_of_a_point_maps_to_the_expected_band(self):
        for classifier, boundaries, bands in (
            (classify_disc_score, (30, 40, 60, 70), ("very_low", "low", "moderate", "high", "very_high")),
            (classify_driving_force_score, (30, 40, 60, 70), ("very_low", "low", "moderate", "high", "very_high")),
            (classify_eq_score, (50, 60, 70, 80), ("lower", "developing", "moderate", "high", "very_high")),
        ):
            for tenth in range(1001):
                score = tenth / 10
                with self.subTest(classifier=classifier.__name__, score=score):
                    self.assertEqual(classifier(score), bands[sum(score >= edge for edge in boundaries)])

    def test_invalid_numbers_are_never_interpreted(self):
        for value in (None, True, False, "50", -0.1, 100.1, float("nan"), float("inf")):
            for classifier in (classify_disc_score, classify_driving_force_score, classify_eq_score):
                with self.subTest(value=value, classifier=classifier), self.assertRaises(ValueError):
                    classifier(value)
            for classifier in (classify_disc_shift, classify_eq_difference):
                with self.assertRaises(ValueError):
                    classifier(50, value)

    def test_every_dimension_and_band_has_distinct_nonempty_language(self):
        for filename, section, names, bands, fields in (
            ("disc_narrative.json", "traits", set("DISC"), ("very_low", "low", "moderate", "high", "very_high"), ("strength", "family_expression", "watchout")),
            ("driving_forces_narrative.json", "forces", set(self.persona["driving_forces"]["scores"]), ("very_low", "low", "moderate", "high", "very_high"), ("core", "strength", "family_expression", "watchout")),
            ("eq_narrative.json", "dimensions", set(self.persona["eq"]["scores"]), ("lower", "developing", "moderate", "high", "very_high"), ("core", "strength", "family_expression", "watchout")),
            ("eq_narrative.json", "composite_ranges", {"self", "others", "total"}, ("lower", "developing", "moderate", "high", "very_high"), ("core", "family_expression", "watchout")),
        ):
            library = json.loads((BASE / "narratives" / filename).read_text())[section]
            self.assertEqual(set(library), names)
            for name in names:
                self.assertEqual(len({json.dumps(library[name][band], sort_keys=True) for band in bands}), 5)
                for band in bands:
                    for field in fields:
                        self.assertTrue(library[name][band][field].strip(), (name, band, field))

    def test_renderer_emits_all_dimensions_including_nonprimary_and_composites(self):
        for score in (0, 29.9, 30, 39.9, 40, 49.9, 50, 59.9, 60, 69.9, 70, 79.9, 80, 100):
            persona = self.at_score(score)
            for domain, render in (("disc", render_disc_narrative), ("driving_forces", render_driving_forces_narrative), ("eq", render_eq_narrative)):
                narration = render(persona)
                wording = score_wording(persona, domain)
                self.assertEqual(len(wording), {"disc": 8, "driving_forces": 12, "eq": 8}[domain])
                for path, item in wording.items():
                    for sentence in item["wording"].values():
                        with self.subTest(domain=domain, score=score, path=path):
                            self.assertIn(sentence, narration)

    def test_compound_reported_disc_style_does_not_block_narration(self):
        self.persona["disc"]["primary_style"] = "Conducting Implementor"
        narration = render_disc_narrative(self.persona)
        self.assertIn("Conducting Implementor", narration)
        self.assertIn("individual scores", narration)

    def test_question_context_uses_same_score_specific_wording(self):
        builder = ContextBuilder(BASE / "knowledge")
        for score in (0, 35, 45, 55, 65, 75, 100):
            persona = self.at_score(score)
            for domain in (ContextDomain.DISC, ContextDomain.DRIVING_FORCES, ContextDomain.EQ, ContextDomain.INTEGRATED):
                route = ContextRoute(domain, ContextTopic.GENERAL, [])
                context = builder.build_context(route, domain, persona)
                self.assertEqual(context["score_range_wording"], score_wording(persona, domain.value))
                self.assertIn("not validated population norms", context["score_range_policy"])

    def test_comparison_keeps_each_person_and_domain_wording_separate(self):
        other = self.at_score(0)
        other["person"]["person_id"] = "other-person"
        other["disc"]["primary_style"] = "Conducting Implementor"
        reasoner = ComparisonReasoner(client=Mock(), knowledge_dir=BASE / "knowledge")
        for domain, question in (("disc", "Compare our DISC"), ("driving_forces", "Compare our Driving Forces"), ("eq", "Compare our EQ")):
            context = reasoner.build_context(question, self.persona, other)
            self.assertEqual(set(context["score_range_wording"]["person_a"]), {domain})
            self.assertEqual(context["score_range_wording"]["person_a"][domain], score_wording(self.persona, domain))
            self.assertEqual(context["score_range_wording"]["person_b"][domain], score_wording(other, domain))

    def test_unknown_and_zero_scores_have_different_wording(self):
        self.persona["eq"]["total_eq"] = None
        self.persona["eq"]["self_composite"] = 0
        wording = score_wording(self.persona, "eq")
        self.assertIsNone(wording["total_eq"]["band"])
        self.assertEqual(wording["self_composite"]["band"], "lower")

    def test_every_band_survives_engine_sentence_tracking_and_echo_transport(self):
        engine = DebriefEngine(BASE / "data/personas/samuel.json", ai_reasoner=Mock())
        for score in (0, 35, 45, 55, 65, 75, 85, 100):
            engine.data = self.at_score(score)
            for state in (DebriefState.DISC_NARRATIVE, DebriefState.DRIVING_FORCES_NARRATIVE, DebriefState.EQ_NARRATIVE):
                engine.current_state = state
                expected = engine.get_current_content()
                orchestrator = ConversationOrchestrator(engine)
                orchestrator.load_current_section()
                tracker = PlaybackEventTracker()
                coordinator = PlaybackCoordinator(orchestrator, tracker)
                client = TavusClient()
                client.connected = True
                client.conversation_id = "test-only"
                client.call_client = Mock()
                spoken = []
                with contextlib.redirect_stdout(io.StringIO()):
                    while (turn := orchestrator.next_narration()) is not None:
                        coordinator.register_utterance(turn.utterance_id)
                        client.speak(turn.text)
                        message = client.call_client.send_app_message.call_args.args[0]
                        spoken.append(message["properties"]["text"])
                        self.assertTrue(message["properties"]["done"])
                        inference = str(turn.utterance_id)
                        coordinator.handle_playback_event({"event_type": tracker.STARTED, "inference_id": inference})
                        self.assertTrue(coordinator.handle_playback_event({"event_type": tracker.STOPPED, "inference_id": inference, "properties": {"interrupted": False}}))
                self.assertEqual(" ".join(spoken), expected)
                self.assertTrue(orchestrator.cursor.finished)
