import unittest

from context_router import (
    ContextDomain,
    ContextTopic,
    resolve_domain_with_state,
    route_question,
)

from debrief_state import DebriefState


class TestContextRouter(
    unittest.TestCase
):

    def test_disc_question_routes_to_disc(
        self,
    ) -> None:

        route = route_question(
            "What does Persuader mean?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.DISC,
        )

    def test_resourceful_routes_to_driving_forces(
        self,
    ) -> None:

        route = route_question(
            "Why is Resourceful important?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.DRIVING_FORCES,
        )

    def test_eq_routes_to_eq(
        self,
    ) -> None:

        route = route_question(
            "What does Self-Regulation mean?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.EQ,
        )

    def test_communication_topic_detected(
        self,
    ) -> None:

        route = route_question(
            "How should I communicate with a Persuader?"
        )

        self.assertEqual(
            route.topic,
            ContextTopic.COMMUNICATION,
        )

    def test_stressor_topic_detected(
        self,
    ) -> None:

        route = route_question(
            "What tends to frustrate someone high in Resourceful?"
        )

        self.assertEqual(
            route.topic,
            ContextTopic.STRESSORS,
        )

    def test_strength_topic_detected(
        self,
    ) -> None:

        route = route_question(
            "What strengths could this style bring?"
        )

        self.assertEqual(
            route.topic,
            ContextTopic.STRENGTHS,
        )

    def test_general_question_uses_disc_state(
        self,
    ) -> None:

        route = route_question(
            "What does this mean?"
        )

        resolved = resolve_domain_with_state(
            route,
            DebriefState.DISC_STYLE,
        )

        self.assertEqual(
            resolved,
            ContextDomain.DISC,
        )

    def test_general_question_uses_driving_force_state(
        self,
    ) -> None:

        route = route_question(
            "Why does this matter?"
        )

        resolved = resolve_domain_with_state(
            route,
            DebriefState.DRIVING_FORCES_SCORES,
        )

        self.assertEqual(
            resolved,
            ContextDomain.DRIVING_FORCES,
        )

    def test_general_question_uses_eq_state(
        self,
    ) -> None:

        route = route_question(
            "How should I interpret this?"
        )

        resolved = resolve_domain_with_state(
            route,
            DebriefState.EQ_SCORES,
        )

        self.assertEqual(
            resolved,
            ContextDomain.EQ,
        )

    def test_two_domains_route_to_integrated(
        self,
    ) -> None:
        route = route_question(
            "How do my DISC style and Driving Forces work together?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.INTEGRATED,
        )


    def test_three_domains_route_to_integrated(
        self,
    ) -> None:
        route = route_question(
            "How do my DISC, Driving Forces, and EQ work together?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.INTEGRATED,
        )


    def test_complete_profile_routes_to_integrated(
        self,
    ) -> None:
        route = route_question(
            "What does my complete profile say about my family role?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.INTEGRATED,
        )


    def test_single_domain_remains_single_domain(
        self,
    ) -> None:
        route = route_question(
            "What is my Resourceful Driving Force score?"
        )

        self.assertEqual(
            route.domain,
            ContextDomain.DRIVING_FORCES,
        )


if __name__ == "__main__":
    unittest.main()