import copy
import unittest

from family_schema import (
    load_family_manifest,
    validate_family_manifest,
    validate_family_personas,
)


class TestFamilySchema(unittest.TestCase):

    def setUp(self) -> None:
        self.family = load_family_manifest(
            "data/families/demo_family.json"
        )

    def test_valid_family_manifest_passes(self) -> None:
        validate_family_manifest(self.family)

    def test_all_referenced_personas_pass(self) -> None:
        validate_family_personas(self.family)

    def test_duplicate_person_id_fails(self) -> None:
        bad = copy.deepcopy(self.family)

        bad["members"].append(
            copy.deepcopy(bad["members"][0])
        )

        with self.assertRaises(ValueError):
            validate_family_manifest(bad)

    def test_invalid_default_person_fails(self) -> None:
        bad = copy.deepcopy(self.family)
        bad["default_person_id"] = "missing_person"

        with self.assertRaises(ValueError):
            validate_family_manifest(bad)

    def test_missing_persona_file_fails(self) -> None:
        bad = copy.deepcopy(self.family)
        bad["members"][0]["persona_file"] = (
            "data/personas/missing.json"
        )

        with self.assertRaises(ValueError):
            validate_family_personas(bad)

    def test_manifest_identity_mismatch_fails(self) -> None:
        bad = copy.deepcopy(self.family)
        bad["members"][0]["display_name"] = "Not Samuel"

        with self.assertRaises(ValueError):
            validate_family_personas(bad)


if __name__ == "__main__":
    unittest.main()