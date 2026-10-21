from dataclasses import dataclass


@dataclass
class GuardrailResult:
    allowed: bool
    category: str
    response: str | None = None


CLINICAL_TERMS = {
    "adhd",
    "autism",
    "autistic",
    "depression",
    "depressed",
    "anxiety disorder",
    "bipolar",
    "narcissist",
    "narcissism",
    "personality disorder",
    "psychopath",
    "sociopath",
    "diagnosis",
    "diagnose",
    "mental illness",
}


def check_question_guardrails(
    question: str,
) -> GuardrailResult:
    """
    Pre-screen a user's question before it reaches the AI reasoner.
    """

    normalized = question.lower()

    for term in CLINICAL_TERMS:

        if term in normalized:

            return GuardrailResult(
                allowed=False,
                category="clinical_or_diagnostic",
                response=(
                    "These assessment results are not designed to "
                    "diagnose medical, psychological, psychiatric, "
                    "or developmental conditions. They can help "
                    "describe behavioral, motivational, and emotional "
                    "patterns, but questions about diagnosis should be "
                    "addressed with a qualified professional."
                ),
            )

    return GuardrailResult(
        allowed=True,
        category="allowed",
    )