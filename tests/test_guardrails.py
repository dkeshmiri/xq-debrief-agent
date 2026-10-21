import unittest

from guardrails import (
    check_question_guardrails,
)


class TestQuestionGuardrails(
    unittest.TestCase
):

    def test_normal_question_allowed(
        self,
    ) -> None:

        result = (
            check_question_guardrails(
                "What strengths could this style bring?"
            )
        )

        self.assertTrue(
            result.allowed
        )

        self.assertEqual(
            result.category,
            "allowed",
        )

    def test_adhd_question_blocked(
        self,
    ) -> None:

        result = (
            check_question_guardrails(
                "Does this mean Samuel has ADHD?"
            )
        )

        self.assertFalse(
            result.allowed
        )

        self.assertEqual(
            result.category,
            "clinical_or_diagnostic",
        )

    def test_autism_question_blocked(
        self,
    ) -> None:

        result = (
            check_question_guardrails(
                "Is my son autistic?"
            )
        )

        self.assertFalse(
            result.allowed
        )

    def test_diagnosis_request_blocked(
        self,
    ) -> None:

        result = (
            check_question_guardrails(
                "Can you diagnose him from this assessment?"
            )
        )

        self.assertFalse(
            result.allowed
        )


if __name__ == "__main__":
    unittest.main()