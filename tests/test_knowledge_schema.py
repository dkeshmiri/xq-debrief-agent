import copy
import json
import unittest
from pathlib import Path

from knowledge_schema import (
    validate_all_knowledge,
    validate_disc_knowledge,
    validate_driving_forces_knowledge,
    validate_eq_knowledge,
)


class TestKnowledgeSchema(
    unittest.TestCase
):

    def setUp(self) -> None:

        base = Path("knowledge")

        with (
            base
            / "disc_knowledge.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            self.disc = json.load(file)

        with (
            base
            / "driving_forces_knowledge.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            self.driving_forces = (
                json.load(file)
            )

        with (
            base
            / "eq_knowledge.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            self.eq = json.load(file)

    def test_all_knowledge_files_pass(
        self,
    ) -> None:

        validate_all_knowledge(
            "knowledge"
        )

    def test_disc_valid(
        self,
    ) -> None:

        validate_disc_knowledge(
            self.disc
        )

    def test_disc_missing_dimension_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.disc
        )

        del bad["dimensions"]["D"]

        with self.assertRaises(
            ValueError
        ):
            validate_disc_knowledge(
                bad
            )

    def test_disc_fake_style_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.disc
        )

        bad["styles"][
            "Super Persuader"
        ] = {
            "code": "XX",
            "definition": "Invalid test style"
        }

        with self.assertRaises(
            ValueError
        ):
            validate_disc_knowledge(
                bad
            )

    def test_driving_forces_valid(
        self,
    ) -> None:

        validate_driving_forces_knowledge(
            self.driving_forces
        )

    def test_driving_force_wrong_pair_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.driving_forces
        )

        bad["forces"][
            "Resourceful"
        ][
            "pair"
        ] = "Collaborative"

        with self.assertRaises(
            ValueError
        ):
            validate_driving_forces_knowledge(
                bad
            )

    def test_legacy_driving_force_name_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.driving_forces
        )

        bad["forces"][
            "Utilitarian"
        ] = bad[
            "forces"
        ].pop(
            "Resourceful"
        )

        with self.assertRaises(
            ValueError
        ):
            validate_driving_forces_knowledge(
                bad
            )

    def test_missing_driving_force_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.driving_forces
        )

        del bad[
            "forces"
        ][
            "Commanding"
        ]

        with self.assertRaises(
            ValueError
        ):
            validate_driving_forces_knowledge(
                bad
            )

    def test_eq_valid(
        self,
    ) -> None:

        validate_eq_knowledge(
            self.eq
        )

    def test_eq_missing_dimension_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.eq
        )

        del bad[
            "dimensions"
        ][
            "social_awareness"
        ]

        with self.assertRaises(
            ValueError
        ):
            validate_eq_knowledge(
                bad
            )

    def test_eq_bad_self_composite_fails(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.eq
        )

        bad[
            "composites"
        ][
            "SELF"
        ][
            "includes"
        ] = [
            "self_awareness",
            "social_awareness",
        ]

        with self.assertRaises(
            ValueError
        ):
            validate_eq_knowledge(
                bad
            )

    def test_eq_diagnosis_guardrail_required(
        self,
    ) -> None:

        bad = copy.deepcopy(
            self.eq
        )

        bad[
            "interpretation_rules"
        ][
            "do_not_diagnose"
        ] = False

        with self.assertRaises(
            ValueError
        ):
            validate_eq_knowledge(
                bad
            )


if __name__ == "__main__":
    unittest.main()