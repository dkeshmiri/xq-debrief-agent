import unittest

from family_repository import FamilyRepository


class TestFamilyRepository(unittest.TestCase):

    def setUp(self) -> None:
        self.repository = FamilyRepository(
            "data/families/demo_family.json"
        )

    def test_family_identity(self) -> None:
        self.assertEqual(
            self.repository.family_id,
            "demo_family_001",
        )

        self.assertEqual(
            self.repository.family_name,
            "Demo Family",
        )

    def test_default_person_loaded(self) -> None:
        self.assertEqual(
            self.repository.default_person_id,
            "samuel_demo_001",
        )

        persona = (
            self.repository
            .get_default_persona()
        )

        self.assertEqual(
            persona["person"]["display_name"],
            "Samuel",
        )

    def test_active_person_starts_as_default(
        self,
    ) -> None:
        self.assertEqual(
            self.repository.active_person_id,
            "samuel_demo_001",
        )

    def test_list_members(self) -> None:
        members = self.repository.list_members()

        self.assertEqual(
            len(members),
            2,
        )

        member_names = {
            member["display_name"]
            for member in members
        }

        self.assertEqual(
            member_names,
            {
            "Samuel",
            "Jennifer",
            },
        )

    def test_debrief_enabled_filter(self) -> None:
        members = self.repository.list_members(
            debrief_enabled_only=True
        )

        self.assertEqual(
            len(members),
            2,
        )

    def test_has_person(self) -> None:
        self.assertTrue(
            self.repository.has_person(
                "samuel_demo_001"
            )
        )

        self.assertFalse(
            self.repository.has_person(
                "missing_person"
            )
        )

    def test_unknown_person_fails(self) -> None:
        with self.assertRaises(KeyError):
            self.repository.get_persona(
                "missing_person"
            )

    def test_set_active_person(self) -> None:
        self.repository.set_active_person(
            "jennifer_demo_001"
        )

        self.assertEqual(
            self.repository.active_person_id,
            "jennifer_demo_001",
        )

        active_persona = (
            self.repository.get_active_persona()
        )

        self.assertEqual(
            active_persona["person"]["display_name"],
            "Jennifer",
        )


    def test_reset_active_person(self) -> None:
        self.repository.set_active_person(
            "jennifer_demo_001"
        )

        self.repository.reset_active_person()

        self.assertEqual(
            self.repository.active_person_id,
            "samuel_demo_001",
        )

        active_persona = (
            self.repository.get_active_persona()
        )

        self.assertEqual(
            active_persona["person"]["display_name"],
        "Samuel",
        )


    def test_returned_member_copy_does_not_mutate_repository(
        self,
    ) -> None:
        member = self.repository.get_member(
            "samuel_demo_001"
        )

        member["display_name"] = "Changed"

        stored_member = self.repository.get_member(
            "samuel_demo_001"
        )

        self.assertEqual(
            stored_member["display_name"],
            "Samuel",
        )


    def test_jennifer_is_loaded(self) -> None:
        self.assertTrue(
            self.repository.has_person(
                "jennifer_demo_001"
            )
        )

        persona = self.repository.get_persona(
            "jennifer_demo_001"
        )

        self.assertEqual(
            persona["person"]["display_name"],
            "Jennifer",
        )

        self.assertEqual(
            persona["disc"]["primary_style"],
            "Supporter",
        )


    def test_jennifer_family_role_matches_manifest(
        self,
    ) -> None:
        member = self.repository.get_member(
            "jennifer_demo_001"
        )

        persona = self.repository.get_persona(
            "jennifer_demo_001"
        )

        self.assertEqual(
            member["family_role"],
            "Mother",
        )

        self.assertEqual(
            persona["person"]["family_role"],
            "Mother",
        )


if __name__ == "__main__":
    unittest.main()