import unittest

from debrief_engine import (
    DebriefEngine,
)

from debrief_state import (
    DebriefState,
    InteractionMode,
)

from ai_reasoner import AIReasoningResult

from ai_reasoner import AIReasoningResult


class FakeAIReasoner:
    def answer_question(
        self,
        question,
        state,
        persona_data,
    ):
        return AIReasoningResult(
            response="This is a safe simulated AI response.",
            resolved_domain="disc",
            is_cross_domain=False,
        )


class TestDebriefEngine(
    unittest.TestCase
):

    def setUp(self) -> None:

        self.engine = DebriefEngine(
            "data/personas/samuel.json",
            ai_reasoner=FakeAIReasoner(),
        )

    def test_persona_loads(
        self,
    ) -> None:

        self.assertEqual(
            self.engine.display_name,
            "Samuel",
        )

    def test_initial_state(
        self,
    ) -> None:

        self.assertEqual(
            self.engine.get_current_state(),
            DebriefState.INTRODUCTION,
        )

    def test_advance_moves_one_state(
        self,
    ) -> None:

        self.engine.advance()

        self.assertEqual(
            self.engine.get_current_state(),
            DebriefState.DISC_NARRATIVE,
        )

    def test_repeat_does_not_change_state(
        self,
    ) -> None:

        before = (
            self.engine
            .get_current_state()
        )

        self.engine.get_current_content()

        after = (
            self.engine
            .get_current_state()
        )

        self.assertEqual(
            before,
            after,
        )

    def test_question_mode_preserves_state(
        self,
    ) -> None:

        self.engine.advance()
        self.engine.advance()

        before = (
            self.engine
            .get_current_state()
        )

        self.engine.enter_question_mode()

        self.assertEqual(
            self.engine
            .get_interaction_mode(),
            InteractionMode.QUESTION,
        )

        self.engine.exit_question_mode()

        self.assertEqual(
            self.engine
            .get_current_state(),
            before,
        )

    def test_cannot_advance_during_question_mode(
        self,
    ) -> None:

        self.engine.enter_question_mode()

        with self.assertRaises(
            RuntimeError
        ):
            self.engine.advance()

    def test_reset_returns_to_intro(
        self,
    ) -> None:

        self.engine.advance()
        self.engine.advance()
        self.engine.advance()

        self.engine.reset()

        self.assertEqual(
            self.engine
            .get_current_state(),
            DebriefState.INTRODUCTION,
        )

    def test_complete_cannot_advance(
        self,
    ) -> None:

        while (
            self.engine.get_current_state()
            != DebriefState.COMPLETE
        ):
            self.engine.advance()

        self.engine.advance()

        self.assertEqual(
            self.engine
            .get_current_state(),
            DebriefState.COMPLETE,
        )

    def test_clinical_question_redirected(
        self,
    ) -> None:

        response = (
            self.engine.answer_question(
                "Does Samuel have ADHD?"
            )
        )

        self.assertIn(
            "not designed to diagnose",
            response,
        )

    def test_normal_question_uses_fake_ai(
        self,
    ) -> None:

        response = (
            self.engine.answer_question(
                "What strengths might this bring?"
            )
        )

        self.assertEqual(
            response,
            "This is a safe simulated "
            "AI response.",
        )

    def test_eq_advances_to_integrated_analysis(
        self,
    ) -> None:
        engine = DebriefEngine(
            "data/personas/samuel.json",
            ai_reasoner=FakeAIReasoner(),
        )

        engine.current_state = DebriefState.EQ_NARRATIVE

        new_state = engine.advance()

        self.assertEqual(
            new_state,
            DebriefState.INTEGRATED_NARRATIVE,
        )

    def test_integrated_narrative_content(self) -> None:
        engine = DebriefEngine(
            "data/personas/samuel.json",
            ai_reasoner=FakeAIReasoner(),
        )

        engine.current_state = (
            DebriefState.INTEGRATED_ANALYSIS
        )

        content = engine.get_current_content()

        self.assertIn(
            "Your Integrated Analysis",
            content,
        )

        self.assertIn(
            "Combined Strengths:",
            content,
        )

        self.assertIn(
            "Potential Development Areas:",
            content,
        )

        self.assertIn(
            "Family Applications:",
            content,
        )

    def test_integrated_narrative_advances_to_complete(
        self,
    ) -> None:
        engine = DebriefEngine(
            "data/personas/samuel.json",
            ai_reasoner=FakeAIReasoner(),
        )

        engine.current_state = (
            DebriefState.INTEGRATED_NARRATIVE
        )

        new_state = engine.advance()

        self.assertEqual(
            new_state,
            DebriefState.COMPLETE,
        )

if __name__ == "__main__":
    unittest.main()