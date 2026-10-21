
import unittest

from conversation_orchestrator import (
    ConversationOrchestrator,
    ConversationPhase,
)
from debrief_state import DebriefState, InteractionMode


class FakeDebriefEngine:
    """
    Minimal stand-in for DebriefEngine.

    It exercises the orchestrator without OpenAI,
    Tavus, API keys, or real assessment data.
    """

    def __init__(self):
        self.current_state = DebriefState.DISC_NARRATIVE
        self.interaction_mode = InteractionMode.DEBRIEF
        self.paused_state = None

        self.narrative = (
            "Samuel's primary style is Persuader. "
            "His natural D score is 72. "
            "This may influence his family interactions."
        )

        self.questions_received = []

    def get_current_content(self):
        return self.narrative

    def get_current_state(self):
        return self.current_state

    def enter_question_mode(self):
        if self.interaction_mode == InteractionMode.QUESTION:
            return

        self.paused_state = self.current_state
        self.interaction_mode = InteractionMode.QUESTION

    def exit_question_mode(self):
        if self.interaction_mode != InteractionMode.QUESTION:
            return

        if self.paused_state is not None:
            self.current_state = self.paused_state

        self.paused_state = None
        self.interaction_mode = InteractionMode.DEBRIEF

    def answer_question(self, question):
        self.questions_received.append(question)

        return (
            "Samuel's natural D score is 72."
        )


class TestConversationOrchestrator(unittest.TestCase):

    def setUp(self):
        self.engine = FakeDebriefEngine()

        self.orchestrator = ConversationOrchestrator(
            engine=self.engine
        )

        self.orchestrator.load_current_section()

    def begin_second_sentence(self):
        """
        Finish sentence zero and begin sentence one.
        """

        first = self.orchestrator.next_narration()

        self.assertIsNotNone(first)

        self.assertTrue(
            self.orchestrator.narration_finished(
                first.utterance_id
            )
        )

        second = self.orchestrator.next_narration()

        self.assertIsNotNone(second)

        return second

    def test_loads_realistic_narrative(self):
        self.assertEqual(
            self.orchestrator.cursor.section,
            DebriefState.DISC_NARRATIVE,
        )

        self.assertEqual(
            len(self.orchestrator.cursor.sentences),
            3,
        )

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.NARRATING,
        )

    def test_cannot_interrupt_without_active_speech(self):
        with self.assertRaises(RuntimeError):
            self.orchestrator.interrupt()

    def test_interrupt_preserves_section_and_sentence(self):
        second = self.begin_second_sentence()

        self.orchestrator.interrupt()

        self.assertEqual(
            self.engine.current_state,
            DebriefState.DISC_NARRATIVE,
        )

        self.assertEqual(
            self.engine.interaction_mode,
            InteractionMode.QUESTION,
        )

        self.assertEqual(
            self.engine.paused_state,
            DebriefState.DISC_NARRATIVE,
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.QUESTION_READY,
        )

        # Completion of the interrupted utterance
        # must not advance the sentence bookmark.
        self.assertFalse(
            self.orchestrator.narration_finished(
                second.utterance_id
            )
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )

    def test_answer_does_not_resume_automatically(self):
        self.begin_second_sentence()

        self.orchestrator.interrupt()

        answer = self.orchestrator.ask_question(
            "What is my natural D score?"
        )

        self.assertEqual(
            answer,
            "Samuel's natural D score is 72.",
        )

        self.assertEqual(
            self.engine.questions_received,
            ["What is my natural D score?"],
        )

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.ANSWERING,
        )

        self.assertEqual(
            self.engine.interaction_mode,
            InteractionMode.QUESTION,
        )

        # Generating an answer is NOT proof
        # that the avatar has finished speaking.
        self.assertIsNone(
            self.orchestrator.next_narration()
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )

    def test_answer_completion_resumes_same_sentence(self):
        second = self.begin_second_sentence()

        self.orchestrator.interrupt()

        self.orchestrator.ask_question(
            "What is my natural D score?"
        )

        resumed = self.orchestrator.answer_finished()

        self.assertIsNotNone(resumed)

        self.assertEqual(
            resumed.text,
            "To continue where we left off... "
            "His natural D score is 72.",
        )

        # Resuming creates a new utterance ID.
        self.assertNotEqual(
            resumed.utterance_id,
            second.utterance_id,
        )

        self.assertEqual(
            self.engine.interaction_mode,
            InteractionMode.DEBRIEF,
        )

        self.assertIsNone(
            self.engine.paused_state
        )

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.NARRATING,
        )

        # An old event is still rejected
        # even after narration resumes.
        self.assertFalse(
            self.orchestrator.narration_finished(
                second.utterance_id
            )
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )

        self.assertTrue(
            self.orchestrator.narration_finished(
                resumed.utterance_id
            )
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            2,
        )

        next_turn = self.orchestrator.next_narration()

        self.assertEqual(
            next_turn.text,
            "This may influence his family interactions.",
        )

    def test_rejects_empty_question_without_losing_pause(self):
        self.begin_second_sentence()
        self.orchestrator.interrupt()

        with self.assertRaises(ValueError):
            self.orchestrator.ask_question("   ")

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.QUESTION_READY,
        )

        self.assertEqual(
            self.engine.interaction_mode,
            InteractionMode.QUESTION,
        )

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )

    def test_cannot_resume_before_answer(self):
        self.begin_second_sentence()
        self.orchestrator.interrupt()

        with self.assertRaises(RuntimeError):
            self.orchestrator.answer_finished()

        self.assertEqual(
            self.orchestrator.phase,
            ConversationPhase.QUESTION_READY,
        )

    def test_cannot_reload_section_during_question(self):
        self.begin_second_sentence()
        self.orchestrator.interrupt()

        with self.assertRaises(RuntimeError):
            self.orchestrator.load_current_section()

        self.assertEqual(
            self.orchestrator.cursor.sentence_index,
            1,
        )


if __name__ == "__main__":
    unittest.main()