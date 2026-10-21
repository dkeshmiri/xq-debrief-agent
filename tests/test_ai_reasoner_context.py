import json
import unittest
from pathlib import Path

from ai_reasoner import AIReasoner
from debrief_state import DebriefState


class TestAIReasonerContext(unittest.TestCase):

    def setUp(self) -> None:
        with Path("data/personas/samuel.json").open(
            "r",
            encoding="utf-8",
        ) as file:
            self.persona = json.load(file)

        self.reasoner = AIReasoner(
            client=object(),
            knowledge_dir="knowledge",
        )

    def test_disc_communication_packet(self) -> None:
        context = self.reasoner.build_context(
            question=(
                "How should another family member "
                "communicate with Samuel?"
            ),
            state=DebriefState.DISC_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertIn("disc", context)
        self.assertNotIn("driving_forces", context)
        self.assertNotIn("eq", context)

        disc = context["disc"]

        self.assertEqual(
            disc["primary_style"],
            "Persuader",
        )

        self.assertIsNotNone(
            disc["approved_style_definition"]
        )

        self.assertIn(
            "communication_do",
            disc,
        )

    def test_resourceful_stressor_packet(self) -> None:
        context = self.reasoner.build_context(
            question=(
                "What might frustrate Samuel's "
                "Resourceful side?"
            ),
            state=DebriefState.DRIVING_FORCES_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertIn(
            "driving_forces",
            context,
        )

        forces = context["driving_forces"]

        self.assertIn(
            "Resourceful",
            forces["matched_forces"],
        )

        self.assertEqual(
            forces["matched_forces"]["Resourceful"]["score"],
            81,
        )

        self.assertIn(
            "person_stressors",
            forces,
        )

    def test_eq_state_resolves_ambiguous_question(self) -> None:
        context = self.reasoner.build_context(
            question="What does this mean?",
            state=DebriefState.EQ_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertIn("eq", context)
        self.assertNotIn("disc", context)
        self.assertNotIn("driving_forces", context)

    def test_context_records_current_state(self) -> None:
        context = self.reasoner.build_context(
            question="What strengths could this style bring?",
            state=DebriefState.DISC_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertEqual(
            context["debrief_state"],
            "disc_narrative",
        )

    def test_integrated_question_builds_integrated_packet(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How do my DISC style, Driving Forces, "
                "and EQ work together?"
            ),
            state=DebriefState.DISC_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertEqual(
            context[
                "routing_policy"
            ][
                "resolved_domain"
            ],
            "integrated",
        )

        self.assertIn(
            "integrated",
            context,
        )

        self.assertIn(
            "disc",
            context["integrated"],
        )

        self.assertIn(
            "driving_forces",
            context["integrated"],
        )

        self.assertIn(
            "eq",
            context["integrated"],
        )

    def test_integrated_question_does_not_change_state(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How does my complete profile "
                "affect my family role?"
            ),
            state=DebriefState.DISC_NARRATIVE,
            persona_data=self.persona,
        )

        self.assertEqual(
            context["debrief_state"],
            "disc_narrative",
        )

    def test_explicit_disc_question_from_introduction(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question="What is my natural D score?",
            state=DebriefState.INTRODUCTION,
            persona_data=self.persona,
        )

        self.assertEqual(
            context["routing_policy"]["resolved_domain"],
            "disc",
        )

        self.assertIn(
            "disc",
            context,
        )

        self.assertEqual(
            context["disc"]["natural"]["D"],
            72,
        )

    def test_explicit_eq_question_from_introduction(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question="What is my total EQ score?",
            state=DebriefState.INTRODUCTION,
            persona_data=self.persona,
        )

        self.assertEqual(
            context["routing_policy"]["resolved_domain"],
            "eq",
        )

        self.assertIn(
            "eq",
            context,
        ) 

    def test_ambiguous_question_from_introduction_stays_general(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question="What does this mean?",
            state=DebriefState.INTRODUCTION,
            persona_data=self.persona,
        )

        self.assertEqual(
            context["routing_policy"]["resolved_domain"],
            "general",
        )

if __name__ == "__main__":
    unittest.main()