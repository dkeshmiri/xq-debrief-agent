import json
import unittest
from pathlib import Path

from debrief_state import DebriefState

from response_validator import (
    validate_ai_response,
)

from context_router import ContextDomain

class TestResponseValidator(
    unittest.TestCase
):

    def setUp(self) -> None:

        persona_path = Path(
            "data/personas/samuel.json"
        )

        with persona_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            self.persona = json.load(
                file
            )

    def test_normal_disc_response_passes(
        self,
    ) -> None:

        response = (
            "Samuel's Persuader style "
            "may contribute energy and direction "
            "in family interactions."
        )

        result = validate_ai_response(
            response=response,
            resolved_domain=ContextDomain.DISC,
            persona_data=self.persona,
        )

        self.assertTrue(
            result.valid
        )

    def test_utilitarian_term_blocked(
        self,
    ) -> None:

        response = (
            "Samuel's Utilitarian motivation "
            "may influence decision-making."
        )

        result = validate_ai_response(
            response=response,
            resolved_domain=ContextDomain.DRIVING_FORCES,
            persona_data=self.persona,
        )

        self.assertFalse(
            result.valid
        )

    def test_driving_force_term_allowed_during_disc_application(
    self,
) -> None:

        response = (
            "You may benefit from being more intentional "
            "about slowing the pace of the conversation."
        )

        result = validate_ai_response(
            response=response,
            resolved_domain=ContextDomain.DISC,
            persona_data=self.persona,
        )

        self.assertTrue(
            result.valid
        )

    def test_overcertainty_blocked(
        self,
    ) -> None:

        response = (
            "This proves Samuel will always "
            "behave this way."
        )

        result = validate_ai_response(
            response=response,
            resolved_domain=ContextDomain.DISC,
            persona_data=self.persona,
        )

        self.assertFalse(
            result.valid
        )


if __name__ == "__main__":
    unittest.main()