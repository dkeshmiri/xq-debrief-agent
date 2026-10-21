import copy
import json
import unittest
from pathlib import Path

from comparison_engine import ComparisonEngine


class TestComparisonEngine(unittest.TestCase):

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

        self.second_person["disc"]["natural"][
            "D"
        ] = 48

        self.second_person["disc"][
            "primary_style"
        ] = "Supporter"

        self.second_person[
            "driving_forces"
        ][
            "scores"
        ][
            "Resourceful"
        ] = 55

        self.second_person["eq"]["scores"][
            "self_regulation"
        ] = 80

        self.second_person["eq"][
            "self_composite"
        ] = 77

        self.engine = ComparisonEngine()

    def test_comparison_identifies_people(self) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        self.assertEqual(
            result["people"]["person_a"]["display_name"],
            "Samuel",
        )

        self.assertEqual(
            result["people"]["person_b"]["display_name"],
            "Test Person",
        )

    def test_disc_difference_is_exact(self) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        dominance = result["disc"]["natural"]["D"]

        self.assertEqual(
            dominance["person_a"],
            72,
        )

        self.assertEqual(
            dominance["person_b"],
            48,
        )

        self.assertEqual(
            dominance["difference_a_minus_b"],
            24,
        )

        self.assertEqual(
            dominance["higher"],
            "person_a",
        )

    def test_styles_are_kept_separate(self) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        styles = result["disc"]["primary_styles"]

        self.assertEqual(
            styles["person_a"],
            "Persuader",
        )

        self.assertEqual(
            styles["person_b"],
            "Supporter",
        )

        self.assertFalse(
            styles["same_style"]
        )

    def test_driving_force_difference(self) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        resourceful = result[
            "driving_forces"
        ][
            "scores"
        ][
            "Resourceful"
        ]

        self.assertEqual(
            resourceful["person_a"],
            81,
        )

        self.assertEqual(
            resourceful["person_b"],
            55,
        )

        self.assertEqual(
            resourceful["difference_a_minus_b"],
            26,
        )

    def test_eq_difference(self) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        regulation = result[
            "eq"
        ][
            "dimensions"
        ][
            "self_regulation"
        ]

        self.assertEqual(
            regulation["person_a"],
            68,
        )

        self.assertEqual(
            regulation["person_b"],
            80,
        )

        self.assertEqual(
            regulation["higher"],
            "person_b",
        )

    def test_same_person_comparison_fails(self) -> None:
        with self.assertRaises(ValueError):
            self.engine.compare_personas(
                self.samuel,
                self.samuel,
            )

    def test_source_personas_are_not_modified(self) -> None:
        samuel_before = copy.deepcopy(
            self.samuel
        )

        second_before = copy.deepcopy(
            self.second_person
        )

        self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        self.assertEqual(
            self.samuel,
            samuel_before,
        )

        self.assertEqual(
            self.second_person,
            second_before,
        )

    def test_packet_does_not_contain_full_personas(
        self,
    ) -> None:
        result = self.engine.compare_personas(
            self.samuel,
            self.second_person,
        )

        self.assertNotIn(
            "assessment",
            result,
        )

        self.assertNotIn(
            "integrated",
            result,
        )


if __name__ == "__main__":
    unittest.main()