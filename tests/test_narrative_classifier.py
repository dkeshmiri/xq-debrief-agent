import unittest

from narratives.narrative_classifier import (
    classify_disc_score,
    classify_disc_shift,
)


class NarrativeClassifierTests(
    unittest.TestCase
):

    def test_disc_score_very_high(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_score(70),
            "very_high",
        )

    def test_disc_score_high(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_score(60),
            "high",
        )

    def test_disc_score_moderate(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_score(40),
            "moderate",
        )

    def test_disc_score_low(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_score(30),
            "low",
        )

    def test_disc_score_very_low(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_score(29),
            "very_low",
        )

    def test_moderate_increase(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_shift(
                50,
                57,
            ),
            "moderate_increase",
        )

    def test_significant_increase(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_shift(
                50,
                65,
            ),
            "significant_increase",
        )

    def test_moderate_decrease(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_shift(
                57,
                50,
            ),
            "moderate_decrease",
        )

    def test_significant_decrease(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_shift(
                65,
                50,
            ),
            "significant_decrease",
        )

    def test_minimal_shift(
        self,
    ) -> None:
        self.assertEqual(
            classify_disc_shift(
                50,
                56,
            ),
            "minimal_shift",
        )

    def test_invalid_score(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            classify_disc_score(
                101
            )


if __name__ == "__main__":
    unittest.main()