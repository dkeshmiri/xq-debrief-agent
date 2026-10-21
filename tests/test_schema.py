import copy
import json
import unittest
from pathlib import Path

from schemas import validate_persona


class TestPersonaSchema(unittest.TestCase):

    def setUp(self) -> None:

        persona_path = Path("data/personas/samuel.json")

        with persona_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            self.persona = json.load(file)

    def test_valid_persona_passes(self) -> None:

        validate_persona(self.persona)

    def test_missing_top_level_section_fails(self) -> None:

        bad_persona = copy.deepcopy(
            self.persona
        )

        del bad_persona["disc"]

        with self.assertRaises(
            ValueError
        ):
            validate_persona(
                bad_persona
            )

    def test_invalid_disc_score_fails(self) -> None:

        bad_persona = copy.deepcopy(
            self.persona
        )

        bad_persona[
            "disc"
        ][
            "natural"
        ][
            "D"
        ] = 150

        with self.assertRaises(
            ValueError
        ):
            validate_persona(
                bad_persona
            )

    def test_fake_driving_force_fails(self) -> None:

        bad_persona = copy.deepcopy(
            self.persona
        )

        scores = bad_persona[
            "driving_forces"
        ][
            "scores"
        ]

        scores["Utilitarian"] = (
            scores.pop("Resourceful")
        )

        with self.assertRaises(
            ValueError
        ):
            validate_persona(
                bad_persona
            )

    def test_missing_eq_dimension_fails(self) -> None:

        bad_persona = copy.deepcopy(
            self.persona
        )

        del bad_persona[
            "eq"
        ][
            "scores"
        ][
            "self_awareness"
        ]

        with self.assertRaises(
            ValueError
        ):
            validate_persona(
                bad_persona
            )
    def test_missing_integrated_field_fails(self) -> None:
        bad = copy.deepcopy(self.persona)

        del bad["integrated"]["overview"]

        with self.assertRaises(ValueError):
            validate_persona(bad)


    def test_empty_integrated_list_fails(self) -> None:
        bad = copy.deepcopy(self.persona)

        bad["integrated"]["strengths"] = []

        with self.assertRaises(ValueError):
            validate_persona(bad)


    def test_valid_integrated_section_passes(self) -> None:
        validate_persona(self.persona)

if __name__ == "__main__":
    unittest.main()