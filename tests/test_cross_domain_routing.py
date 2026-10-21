import json
import unittest
from pathlib import Path

from ai_reasoner import AIReasoner
from debrief_state import DebriefState


class TestCrossDomainRouting(unittest.TestCase):

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

    def test_eq_question_during_disc_uses_eq_context(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "What is Samuel's "
                "Self-Regulation score?"
            ),
            state=DebriefState.DISC_STYLE,
            persona_data=self.persona,
        )

        self.assertIn("eq", context)
        self.assertNotIn("disc", context)

        policy = context["routing_policy"]

        self.assertEqual(
            policy["current_domain"],
            "disc",
        )
        self.assertEqual(
            policy["resolved_domain"],
            "eq",
        )
        self.assertTrue(
            policy["is_cross_domain"]
        )

    def test_driving_force_question_during_eq(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question="What does Resourceful mean?",
            state=DebriefState.EQ_SCORES,
            persona_data=self.persona,
        )

        self.assertIn(
            "driving_forces",
            context,
        )
        self.assertNotIn(
            "eq",
            context,
        )

        self.assertTrue(
            context[
                "routing_policy"
            ][
                "is_cross_domain"
            ]
        )

    def test_ambiguous_question_stays_in_current_domain(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question="What does this mean?",
            state=DebriefState.DISC_STYLE,
            persona_data=self.persona,
        )

        self.assertIn("disc", context)

        self.assertFalse(
            context[
                "routing_policy"
            ][
                "is_cross_domain"
            ]
        )


if __name__ == "__main__":
    unittest.main()