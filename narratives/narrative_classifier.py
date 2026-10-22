from typing import Literal
from math import isfinite


def validate_score(score: float) -> None:
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not isfinite(score) or not 0 <= score <= 100:
        raise ValueError("Score must be a finite number between 0 and 100.")


ScoreLevel = Literal[
    "very_high",
    "high",
    "moderate",
    "low",
    "very_low",
]

ShiftLevel = Literal[
    "significant_increase",
    "moderate_increase",
    "minimal_shift",
    "moderate_decrease",
    "significant_decrease",
]


#DISC
def classify_disc_score(
    score: int,
) -> ScoreLevel:
    """
    Convert a DISC score into a narrative band.

    These bands control narrative wording only.
    They do not alter the canonical DISC score
    or primary behavioral style.
    """

    validate_score(score)
    if score >= 70:
        return "very_high"

    if score >= 60:
        return "high"

    if score >= 40:
        return "moderate"

    if score >= 30:
        return "low"

    return "very_low"


def classify_disc_shift(
    natural: int,
    adapted: int,
) -> ShiftLevel:
    """
    Classify the size and direction of a Natural-to-Adapted
    DISC movement.

    This describes score movement only. It does not infer
    why the movement occurred.
    """

    validate_score(natural)
    validate_score(adapted)
    difference = adapted - natural

    if difference >= 15:
        return "significant_increase"

    if difference >= 7:
        return "moderate_increase"

    if difference <= -15:
        return "significant_decrease"

    if difference <= -7:
        return "moderate_decrease"

    return "minimal_shift"


#12DF
def classify_driving_force_score(
    score: int,
) -> str:
    """
    Convert a Driving Force score into a narrative band.

    These bands control narrative wording only.
    They do not redefine the canonical assessment.
    """

    validate_score(score)
    if score >= 70:
        return "very_high"

    if score >= 60:
        return "high"

    if score >= 40:
        return "moderate"

    if score >= 30:
        return "low"

    return "very_low"


#EQ
def classify_eq_score(
    score: int,
) -> str:
    """
    Convert an EQ score into a narrative band.

    These bands control narrative wording only.
    They do not redefine the canonical assessment.
    """

    validate_score(score)
    if score >= 80:
        return "very_high"

    if score >= 70:
        return "high"

    if score >= 60:
        return "moderate"

    if score >= 50:
        return "developing"

    return "lower"

def classify_eq_difference(
    first: int,
    second: int,
) -> str:
    """
    Describe the size of the difference between two EQ dimensions.
    """

    validate_score(first)
    validate_score(second)
    difference = first - second

    if difference >= 15:
        return "much_higher"

    if difference >= 7:
        return "higher"

    if difference <= -15:
        return "much_lower"

    if difference <= -7:
        return "lower"

    return "similar"
