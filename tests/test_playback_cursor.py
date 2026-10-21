
import unittest

from debrief_state import DebriefState
from playback_cursor import PlaybackCursor


class TestPlaybackCursor(unittest.TestCase):

    def setUp(self):
        self.cursor = PlaybackCursor()

        self.cursor.load_section(
            DebriefState.DISC_NARRATIVE,
            [
                "Samuel's primary style is Persuader.",
                "His natural D score is 72.",
                "This may influence his family interactions.",
            ],
        )

    def test_starts_at_first_sentence(self):
        utterance = self.cursor.start_next()

        self.assertIsNotNone(utterance)
        self.assertEqual(utterance.sentence_index, 0)
        self.assertEqual(
            utterance.text,
            "Samuel's primary style is Persuader.",
        )

    def test_does_not_advance_before_completion(self):
        first = self.cursor.start_next()

        self.assertEqual(self.cursor.sentence_index, 0)
        self.assertIsNone(self.cursor.start_next())

        self.assertTrue(self.cursor.complete(first.id))
        self.assertEqual(self.cursor.sentence_index, 1)

    def test_interruption_replays_same_sentence(self):
        first = self.cursor.start_next()
        self.cursor.complete(first.id)

        second = self.cursor.start_next()
        self.cursor.interrupt()

        self.assertEqual(self.cursor.sentence_index, 1)
        self.assertIsNone(self.cursor.start_next())

        resumed = self.cursor.resume()

        self.assertEqual(resumed.text, second.text)
        self.assertEqual(resumed.sentence_index, 1)
        self.assertNotEqual(resumed.id, second.id)

    def test_late_completion_cannot_advance(self):
        utterance = self.cursor.start_next()
        self.cursor.interrupt()

        self.assertFalse(self.cursor.complete(utterance.id))
        self.assertEqual(self.cursor.sentence_index, 0)

        resumed = self.cursor.resume()

        self.assertFalse(self.cursor.complete(utterance.id))
        self.assertEqual(self.cursor.sentence_index, 0)

        self.assertTrue(self.cursor.complete(resumed.id))
        self.assertEqual(self.cursor.sentence_index, 1)

    def test_finishes_only_after_final_completion(self):
        self.assertFalse(self.cursor.finished)

        for _ in range(3):
            utterance = self.cursor.start_next()

            self.assertIsNotNone(utterance)
            self.assertFalse(self.cursor.finished)
            self.assertTrue(self.cursor.complete(utterance.id))

        self.assertTrue(self.cursor.finished)
        self.assertIsNone(self.cursor.start_next())

    def test_cannot_replace_active_section(self):
        self.cursor.start_next()

        with self.assertRaises(RuntimeError):
            self.cursor.load_section(
                DebriefState.EQ_NARRATIVE,
                ["A new EQ sentence."],
            )

        self.assertEqual(
            self.cursor.section,
            DebriefState.DISC_NARRATIVE,
        )

    def test_new_section_does_not_reuse_utterance_id(self):
        old = self.cursor.start_next()
        self.cursor.interrupt()

        self.cursor.load_section(
            DebriefState.EQ_NARRATIVE,
            ["Samuel's total EQ score is 73."],
        )

        new = self.cursor.start_next()

        self.assertNotEqual(old.id, new.id)
        self.assertFalse(self.cursor.complete(old.id))
        self.assertEqual(self.cursor.sentence_index, 0)

        self.assertTrue(self.cursor.complete(new.id))
        self.assertTrue(self.cursor.finished)

    def test_rejects_empty_section(self):
        with self.assertRaises(ValueError):
            self.cursor.load_section(
                DebriefState.EQ_NARRATIVE,
                ["", "   "],
            )


if __name__ == "__main__":
    unittest.main()