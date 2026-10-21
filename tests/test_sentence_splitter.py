
import unittest

from sentence_splitter import split_sentences


class TestSentenceSplitter(unittest.TestCase):

    def test_splits_basic_narrative(self):
        text = (
            "Samuel's primary style is Persuader. "
            "His natural D score is 72. "
            "This may influence his family interactions."
        )

        self.assertEqual(
            split_sentences(text),
            [
                "Samuel's primary style is Persuader.",
                "His natural D score is 72.",
                "This may influence his family interactions.",
            ],
        )

    def test_preserves_decimal_numbers(self):
        self.assertEqual(
            split_sentences(
                "His score is 72.5. This is a sample."
            ),
            [
                "His score is 72.5.",
                "This is a sample.",
            ],
        )

    def test_preserves_common_abbreviations(self):
        self.assertEqual(
            split_sentences(
                "Dr. Smith reviewed the report. "
                "She discussed the results."
            ),
            [
                "Dr. Smith reviewed the report.",
                "She discussed the results.",
            ],
        )

    def test_preserves_closing_quotes(self):
        self.assertEqual(
            split_sentences(
                'He said, "Let me explain." '
                "Then he continued."
            ),
            [
                'He said, "Let me explain."',
                "Then he continued.",
            ],
        )

    def test_handles_empty_input(self):
        self.assertEqual(split_sentences(""), [])
        self.assertEqual(split_sentences("   "), [])

    def test_keeps_unpunctuated_text_together(self):
        self.assertEqual(
            split_sentences(
                "Primary Driving Forces\n"
                "Resourceful\n"
                "Intellectual"
            ),
            [
                "Primary Driving Forces\n"
                "Resourceful\n"
                "Intellectual"
            ],
        )


if __name__ == "__main__":
    unittest.main()