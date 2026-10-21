from dataclasses import dataclass
from typing import Any

from context_router import ContextDomain


@dataclass
class ValidationResult:
    valid: bool
    issues: list[str]


FORBIDDEN_TERMINOLOGY = {
    "Utilitarian": "Resourceful",
}


def validate_ai_response(
    response: str,
    resolved_domain: ContextDomain,
    persona_data: dict[str, Any],
) -> ValidationResult:

    issues: list[str] = []

    # -----------------------------------
    #        Terminology checks
    # -----------------------------------

    for forbidden_term, approved_term in (
        FORBIDDEN_TERMINOLOGY.items()
    ):

        if forbidden_term.lower() in response.lower():

            issues.append(
                f"Forbidden terminology '{forbidden_term}' "
                f"detected. Approved term is "
                f"'{approved_term}'."
            )

    # -----------------------------------
    # Cross-domain leakage checks (REMOVED - TOO FINICKY)
    # -----------------------------------

    # -----------------------------------
    #   Obvious over-certainty checks
    # -----------------------------------

    certainty_phrases = (
        "this proves",
        "definitely means",
        "will always",
        "guarantees that",
    )

    lowered = response.lower()

    for phrase in certainty_phrases:

        if phrase in lowered:

            issues.append(
                f"Overly certain language detected: "
                f"'{phrase}'."
            )

    return ValidationResult(
        valid=len(issues) == 0,
        issues=issues,
    )