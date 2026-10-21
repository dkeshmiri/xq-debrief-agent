import unittest

from context_router import ContextDomain
from debrief_state import DebriefState
from routing_policy import (
    domain_for_state,
    evaluate_routing_policy,
)


class TestRoutingPolicy(unittest.TestCase):

    def test_disc_state_maps_to_disc(self) -> None:
        domain = domain_for_state(
            DebriefState.DISC_STYLE
        )

        self.assertEqual(
            domain,
            ContextDomain.DISC,
        )

    def test_driving_forces_state_maps_correctly(
        self,
    ) -> None:
        domain = domain_for_state(
            DebriefState.DRIVING_FORCES_SCORES
        )

        self.assertEqual(
            domain,
            ContextDomain.DRIVING_FORCES,
        )

    def test_eq_state_maps_to_eq(self) -> None:
        domain = domain_for_state(
            DebriefState.EQ_SCORES
        )

        self.assertEqual(
            domain,
            ContextDomain.EQ,
        )

    def test_same_domain_question_not_cross_domain(
        self,
    ) -> None:
        decision = evaluate_routing_policy(
            question="What does Persuader mean?",
            state=DebriefState.DISC_STYLE,
        )

        self.assertFalse(
            decision.is_cross_domain
        )

        self.assertEqual(
            decision.resolved_domain,
            ContextDomain.DISC,
        )

    def test_explicit_eq_question_during_disc(
        self,
    ) -> None:
        decision = evaluate_routing_policy(
            question=(
                "What is Samuel's "
                "Self-Regulation score?"
            ),
            state=DebriefState.DISC_STYLE,
        )

        self.assertTrue(
            decision.is_cross_domain
        )

        self.assertEqual(
            decision.current_domain,
            ContextDomain.DISC,
        )

        self.assertEqual(
            decision.resolved_domain,
            ContextDomain.EQ,
        )

        self.assertTrue(
            decision.allowed
        )

    def test_ambiguous_question_uses_current_state(
        self,
    ) -> None:
        decision = evaluate_routing_policy(
            question="What does this mean?",
            state=DebriefState.DISC_STYLE,
        )

        self.assertFalse(
            decision.is_cross_domain
        )

        self.assertEqual(
            decision.resolved_domain,
            ContextDomain.DISC,
        )

    def test_driving_force_question_during_eq(
        self,
    ) -> None:
        decision = evaluate_routing_policy(
            question=(
                "What does Resourceful mean?"
            ),
            state=DebriefState.EQ_SCORES,
        )

        self.assertTrue(
            decision.is_cross_domain
        )

        self.assertEqual(
            decision.resolved_domain,
            ContextDomain.DRIVING_FORCES,
        )


if __name__ == "__main__":
    unittest.main()