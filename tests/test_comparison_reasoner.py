import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from comparison_reasoner import ComparisonReasoner
from context_router import ContextDomain


class FakeResponses:
    def __init__(self) -> None:
        self.last_request = None

    def create(self, **kwargs):
        self.last_request = kwargs

        return SimpleNamespace(
            output_text=(
                "The two profiles may approach the "
                "situation differently."
            )
        )


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


class TestComparisonReasoner(unittest.TestCase):

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

        self.fake_client = FakeClient()

        self.reasoner = ComparisonReasoner(
            client=self.fake_client,
            knowledge_dir="knowledge",
        )

    def test_disc_question_builds_disc_context(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How might their DISC styles "
                "affect communication?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertEqual(
            context["question_domain"],
            "disc",
        )

        self.assertIn("disc", context)
        self.assertNotIn("driving_forces", context)
        self.assertNotIn("eq", context)

    def test_driving_forces_question_builds_correct_context(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How might their Resourceful "
                "Driving Force scores differ?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertEqual(
            context["question_domain"],
            "driving_forces",
        )

        self.assertIn(
            "driving_forces",
            context,
        )

        self.assertNotIn("disc", context)
        self.assertNotIn("eq", context)

    def test_eq_question_builds_eq_context(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How might their EQ "
                "Self-Regulation scores differ?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertEqual(
            context["question_domain"],
            "eq",
        )

        self.assertIn("eq", context)
        self.assertNotIn("disc", context)

    def test_ambiguous_question_fails(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.reasoner.build_context(
                question="How might they interact?",
                persona_a=self.samuel,
                persona_b=self.second_person,
            )

    def test_same_person_comparison_fails(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            self.reasoner.build_context(
                question=(
                    "How might their DISC "
                    "styles interact?"
                ),
                persona_a=self.samuel,
                persona_b=self.samuel,
            )

    def test_fake_client_returns_result(
        self,
    ) -> None:
        result = self.reasoner.answer_question(
            question=(
                "How might their DISC "
                "styles affect communication?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertEqual(
            result.response,
            (
                "The two profiles may approach the "
                "situation differently."
            ),
        )

        self.assertEqual(
            result.resolved_domain,
            ContextDomain.DISC,
        )

        self.assertIsNotNone(
            self.fake_client.responses.last_request
        )

    def test_prompt_contains_both_people(
        self,
    ) -> None:
        self.reasoner.answer_question(
            question=(
                "How might their DISC "
                "styles affect communication?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        request = (
            self.fake_client
            .responses
            .last_request
        )

        user_content = request["input"][1]["content"]

        self.assertIn(
            '"display_name": "Samuel"',
            user_content,
        )

        self.assertIn(
            '"display_name": "Test Person"',
            user_content,
        )

    def test_comparison_question_detects_two_domains(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How do our views differ through "
                "DISC and Driving Forces?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertEqual(
            context["question_domain"],
            "integrated",
        )

        self.assertEqual(
            set(context["included_domains"]),
            {
                "disc",
                "driving_forces",
            },
        )

    def test_three_domain_comparison_packet(
        self,
    ) -> None:
        context = self.reasoner.build_context(
            question=(
                "How do our DISC, Driving Forces, "
                "and EQ results work together?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        integrated = context["integrated"]

        self.assertIn("disc", integrated)
        self.assertIn(
            "driving_forces",
            integrated,
        )
        self.assertIn("eq", integrated)

class UnsafeFakeResponses:
    def create(self, **kwargs):
        return SimpleNamespace(
            output_text=(
                "Samuel is clearly the more mature person."
            )
        )


class UnsafeFakeClient:
    def __init__(self) -> None:
        self.responses = UnsafeFakeResponses()

    def test_unsafe_response_is_blocked(self) -> None:
        reasoner = ComparisonReasoner(
            client=UnsafeFakeClient(),
            knowledge_dir="knowledge",
        )

        result = reasoner.answer_question(
            question=(
                "How might their DISC styles "
                "affect communication?"
            ),
            persona_a=self.samuel,
            persona_b=self.second_person,
        )

        self.assertIn(
            "did not pass",
            result.response,
        )

        self.assertIsNotNone(
            result.validation_issues
        )        

if __name__ == "__main__":
    unittest.main()