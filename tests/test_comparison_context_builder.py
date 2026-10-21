import copy
import json
import unittest
from pathlib import Path

from comparison_context_builder import (
    ComparisonContextBuilder,
)
from comparison_engine import ComparisonEngine
from context_router import ContextDomain


class TestComparisonContextBuilder(unittest.TestCase):

    def setUp(self) -> None:
        with Path(
            "data/personas/samuel.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            self.samuel = json.load(file)

        self.second_person = copy.deepcopy(
            self.samuel
        )

        self.second_person["person"].update(
            {
                "person_id": "test_person_002",
                "first_name": "Test",
                "display_name": "Test Person",
                "family_role": "Test Role",
            }
        )

        self.second_person["assessment"][
            "assessment_id"
        ] = "test_assessment_002"

        self.second_person["disc"][
            "primary_style"
        ] = "Supporter"

        self.second_person["disc"][
            "natural"
        ]["D"] = 48

        self.second_person[
            "driving_forces"
        ]["scores"]["Resourceful"] = 55

        self.second_person["eq"][
            "scores"
        ]["self_regulation"] = 80

        self.comparison = (
            ComparisonEngine().compare_personas(
                self.samuel,
                self.second_person,
            )
        )

        self.builder = ComparisonContextBuilder(
            "knowledge"
        )

    def test_disc_packet_contains_both_styles(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.DISC,
        )

        styles = context["disc"][
            "primary_styles"
        ]

        self.assertEqual(
            styles["person_a"]["name"],
            "Persuader",
        )

        self.assertEqual(
            styles["person_b"]["name"],
            "Supporter",
        )

        self.assertIsNotNone(
            styles[
                "person_a"
            ]["approved_knowledge"]["definition"]
        )

        self.assertIsNotNone(
            styles[
                "person_b"
            ]["approved_knowledge"]["definition"]
        )

    def test_disc_packet_excludes_other_domains(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.DISC,
        )

        self.assertIn("disc", context)
        self.assertNotIn(
            "driving_forces",
            context,
        )
        self.assertNotIn("eq", context)

    def test_driving_force_packet_is_grounded(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.DRIVING_FORCES,
        )

        resourceful = context[
            "driving_forces"
        ]["scores"]["Resourceful"]

        self.assertEqual(
            resourceful[
                "comparison"
            ]["person_a"],
            81,
        )

        self.assertEqual(
            resourceful[
                "comparison"
            ]["person_b"],
            55,
        )

        self.assertEqual(
            resourceful[
                "approved_knowledge"
            ]["pair"],
            "Selfless",
        )

    def test_eq_packet_contains_dimension_knowledge(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.EQ,
        )

        regulation = context["eq"][
            "dimensions"
        ]["self_regulation"]

        self.assertEqual(
            regulation[
                "comparison"
            ]["person_a"],
            68,
        )

        self.assertEqual(
            regulation[
                "comparison"
            ]["person_b"],
            80,
        )

        self.assertEqual(
            regulation[
                "approved_knowledge"
            ]["display_name"],
            "Self-Regulation",
        )

    def test_people_remain_correctly_labeled(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.DISC,
        )

        self.assertEqual(
            context[
                "people"
            ][
                "person_a"
            ][
                "display_name"
            ],
            "Samuel",
        )

        self.assertEqual(
            context[
                "people"
            ][
                "person_b"
            ][
                "display_name"
            ],
            "Test Person",
        )

    def test_interpretation_boundary_present(
        self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.DISC,
        )

        self.assertIn(
            "do not independently prove",
            context[
                "interpretation_boundary"
            ],
        )

    def test_integrated_disc_and_driving_forces_context(
    self,
    ) -> None:
        context = self.builder.build_context(
            comparison=self.comparison,
            domain=ContextDomain.INTEGRATED,
            included_domains=[
                ContextDomain.DISC,
                ContextDomain.DRIVING_FORCES,
            ],
        )

        self.assertEqual(
            context["domain"],
            "integrated",
        )

        self.assertIn(
            "disc",
            context["integrated"],
        )

        self.assertIn(
            "driving_forces",
            context["integrated"],
        )

        self.assertNotIn(
            "eq",
            context["integrated"],
        )

if __name__ == "__main__":
    unittest.main()