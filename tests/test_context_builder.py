import json
import unittest
from pathlib import Path

from context_builder import ContextBuilder

from context_router import (
    ContextDomain,
    ContextTopic,
    route_question,
)


class TestContextBuilder(
    unittest.TestCase
):

    def setUp(self) -> None:

        with Path(
            "data/personas/samuel.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:

            self.persona = json.load(file)

        self.builder = ContextBuilder(
            "knowledge"
        )

    def test_disc_communication_context(
        self,
    ) -> None:

        route = route_question(
            "How should I communicate "
            "with a Persuader?"
        )

        context = (
            self.builder.build_context(
                route=route,
                resolved_domain=(
                    ContextDomain.DISC
                ),
                persona_data=self.persona,
            )
        )

        disc = context["disc"]

        self.assertEqual(
            disc["primary_style"],
            "Persuader",
        )

        self.assertIn(
            "communication_do",
            disc,
        )

        self.assertIn(
            "communication_dont",
            disc,
        )

        self.assertIsNotNone(
            disc["approved_style_definition"]
        )

        self.assertNotIn(
            "driving_forces",
            context,
        )

        self.assertNotIn(
            "eq",
            context,
        )

    def test_resourceful_stressor_context(
        self,
    ) -> None:

        route = route_question(
            "What frustrates someone "
            "high in Resourceful?"
        )

        context = (
            self.builder.build_context(
                route=route,
                resolved_domain=(
                    ContextDomain
                    .DRIVING_FORCES
                ),
                persona_data=self.persona,
            )
        )

        df = context[
            "driving_forces"
        ]

        self.assertIn(
            "Resourceful",
            df["matched_forces"],
        )

        self.assertEqual(
            df[
                "matched_forces"
            ][
                "Resourceful"
            ][
                "score"
            ],
            81,
        )

        self.assertIn(
            "person_stressors",
            df,
        )

        self.assertNotIn(
            "disc",
            context,
        )

    def test_eq_dimension_context(
        self,
    ) -> None:

        route = route_question(
            "What does Self-Regulation mean?"
        )

        context = (
            self.builder.build_context(
                route=route,
                resolved_domain=(
                    ContextDomain.EQ
                ),
                persona_data=self.persona,
            )
        )

        eq = context["eq"]

        self.assertIn(
            "self_regulation",
            eq[
                "matched_dimensions"
            ],
        )

        self.assertEqual(
            eq[
                "matched_dimensions"
            ][
                "self_regulation"
            ][
                "score"
            ],
            68,
        )

    def test_context_always_contains_person(
        self,
    ) -> None:

        route = route_question(
            "What strengths could "
            "this style bring?"
        )

        context = (
            self.builder.build_context(
                route=route,
                resolved_domain=(
                    ContextDomain.DISC
                ),
                persona_data=self.persona,
            )
        )

        self.assertEqual(
            context[
                "person"
            ][
                "display_name"
            ],
            "Samuel",
        )

        self.assertEqual(
            context[
                "person"
            ][
                "family_role"
            ],
            "Father",
        )

    def test_integrated_context_contains_all_domains(
        self,
    ) -> None:
        route = route_question(
            "How do my DISC, Driving Forces, and EQ work together?"
        )

        context = self.builder.build_context(
            route=route,
            resolved_domain=ContextDomain.INTEGRATED,
            persona_data=self.persona,
        )

        integrated = context["integrated"]

        self.assertIn("disc", integrated)
        self.assertIn(
            "driving_forces",
            integrated,
        )
        self.assertIn("eq", integrated)

        self.assertIn(
            "approved_integrated_analysis",
            integrated,
        )


    def test_integrated_context_uses_exact_style(
        self,
    ) -> None:
        route = route_question(
            "How does my overall profile fit together?"
        )

        context = self.builder.build_context(
            route=route,
            resolved_domain=ContextDomain.INTEGRATED,
            persona_data=self.persona,
        )

        self.assertEqual(
            context[
                "integrated"
            ][
                "disc"
            ][
                "primary_style"
            ],
            "Persuader",
        )


if __name__ == "__main__":
    unittest.main()