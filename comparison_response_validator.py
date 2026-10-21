import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from context_router import ContextDomain


class ValidationStatus(str, Enum):
    PASS = "pass"
    RETRY = "retry"
    BLOCK = "block"


@dataclass
class ComparisonValidationResult:
    status: ValidationStatus
    issues: list[str]

    @property
    def valid(self) -> bool:
        return self.status == ValidationStatus.PASS


CLINICAL_PATTERNS = [
    r"\bhas\s+adhd\b",
    r"\bhas\s+autism\b",
    r"\bis\s+autistic\b",
    r"\bis\s+a\s+narcissist\b",
    r"\bis\s+narcissistic\b",
    r"\bhas\s+depression\b",
    r"\bhas\s+anxiety\b",
    r"\bhas\s+bipolar\b",
    r"\bpersonality\s+disorder\b",
    r"\bpsychopath\b",
    r"\bsociopath\b",
]


DETERMINISTIC_RELATIONSHIP_PATTERNS = [
    r"\bguarantees?\s+conflict\b",
    r"\bwill\s+always\s+conflict\b",
    r"\bwill\s+never\s+get\s+along\b",
    r"\bdefinitely\s+compatible\b",
    r"\bdefinitely\s+incompatible\b",
    r"\bcompletely\s+incompatible\b",
    r"\bperfect\s+match\b",
    r"\bbad\s+match\b",
    r"\bproves?\s+(?:that\s+)?they\b",
]


SUPERIORITY_PATTERNS = [
    r"\bbetter\s+person\b",
    r"\bworse\s+person\b",
    r"\bmore\s+intelligent\b",
    r"\bless\s+intelligent\b",
    r"\bmore\s+mature\b",
    r"\bless\s+mature\b",
    r"\bemotionally\s+superior\b",
    r"\bemotionally\s+inferior\b",
    r"\bsuperior\s+profile\b",
    r"\binferior\s+profile\b",
]


LEGACY_DRIVING_FORCE_LABELS = {
    "Theoretical",
    "Utilitarian",
    "Aesthetic",
    "Social",
    "Individualistic",
    "Traditional",
}


def _contains_pattern(
    text: str,
    patterns: list[str],
) -> str | None:
    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if match:
            return match.group(0)

    return None


def _validate_prohibited_claims(
    response: str,
    issues: list[str],
) -> None:
    clinical_match = _contains_pattern(
        response,
        CLINICAL_PATTERNS,
    )

    if clinical_match:
        issues.append(
            "Explicit clinical or diagnostic claim detected: "
            f"'{clinical_match}'."
        )

    relationship_match = _contains_pattern(
        response,
        DETERMINISTIC_RELATIONSHIP_PATTERNS,
    )

    if relationship_match:
        issues.append(
            "Deterministic relationship claim detected: "
            f"'{relationship_match}'."
        )

    superiority_match = _contains_pattern(
        response,
        SUPERIORITY_PATTERNS,
    )

    if superiority_match:
        issues.append(
            "Superiority claim detected: "
            f"'{superiority_match}'."
        )


def _comparison_people(
    context: dict[str, Any],
) -> dict[str, str]:
    return {
        "person_a": context[
            "people"
        ]["person_a"]["display_name"],
        "person_b": context[
            "people"
        ]["person_b"]["display_name"],
    }


def _explicit_score_patterns(
    person_name: str,
    metric_name: str,
) -> list[re.Pattern[str]]:
    """
    Match only unmistakable score claims.

    Examples:
    Samuel's Resourceful score is 81
    Samuel has a Resourceful score of 81
    Samuel: Resourceful = 81
    """

    person = re.escape(person_name)
    metric = re.escape(metric_name)

    return [
        re.compile(
            rf"\b{person}(?:'s)?\s+"
            rf"{metric}\s+score\s+"
            rf"(?:is|of|=|at)\s*"
            rf"(\d+(?:\.\d+)?)\b",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\b{person}\s+has\s+(?:an?\s+)?"
            rf"{metric}\s+score\s+"
            rf"(?:of|=|at|is)?\s*"
            rf"(\d+(?:\.\d+)?)\b",
            flags=re.IGNORECASE,
        ),
        re.compile(
            rf"\b{person}\s*[:\-]\s*"
            rf"{metric}\s*[:=]\s*"
            rf"(\d+(?:\.\d+)?)\b",
            flags=re.IGNORECASE,
        ),
    ]


def _record_score_mismatch(
    person_name: str,
    metric_name: str,
    claimed_value: float,
    valid_values: set[float],
    issues: list[str],
) -> None:
    if claimed_value in valid_values:
        return

    issues.append(
        "Verified score mismatch: "
        f"{person_name} was assigned "
        f"{metric_name} = {claimed_value:g}; "
        f"validated value(s): "
        f"{sorted(valid_values)}."
    )


def _validate_disc_scores(
    response: str,
    context: dict[str, Any],
    issues: list[str],
) -> None:
    people = _comparison_people(context)
    dimensions = context["disc"]["dimensions"]

    for person_key, person_name in people.items():
        for dimension_name, data in dimensions.items():
            natural = float(
                data["natural_comparison"][person_key]
            )

            adapted = float(
                data["adapted_comparison"][person_key]
            )

            generic_patterns = _explicit_score_patterns(
                person_name,
                dimension_name,
            )

            for pattern in generic_patterns:
                for match in pattern.finditer(response):
                    _record_score_mismatch(
                        person_name=person_name,
                        metric_name=dimension_name,
                        claimed_value=float(match.group(1)),
                        valid_values={
                            natural,
                            adapted,
                        },
                        issues=issues,
                    )

            for score_type, valid_value in (
                ("natural", natural),
                ("adapted", adapted),
            ):
                person = re.escape(person_name)
                dimension = re.escape(
                    dimension_name
                )

                pattern = re.compile(
                    rf"\b{person}(?:'s)?\s+"
                    rf"{score_type}\s+"
                    rf"{dimension}\s+score\s+"
                    rf"(?:is|of|=|at)\s*"
                    rf"(\d+(?:\.\d+)?)\b",
                    flags=re.IGNORECASE,
                )

                for match in pattern.finditer(response):
                    _record_score_mismatch(
                        person_name=person_name,
                        metric_name=(
                            f"{score_type} "
                            f"{dimension_name}"
                        ),
                        claimed_value=float(
                            match.group(1)
                        ),
                        valid_values={
                            valid_value
                        },
                        issues=issues,
                    )


def _validate_driving_force_scores(
    response: str,
    context: dict[str, Any],
    issues: list[str],
) -> None:
    people = _comparison_people(context)
    scores = context["driving_forces"]["scores"]

    for person_key, person_name in people.items():
        for force_name, data in scores.items():
            valid_value = float(
                data["comparison"][person_key]
            )

            for pattern in _explicit_score_patterns(
                person_name,
                force_name,
            ):
                for match in pattern.finditer(response):
                    _record_score_mismatch(
                        person_name=person_name,
                        metric_name=force_name,
                        claimed_value=float(
                            match.group(1)
                        ),
                        valid_values={
                            valid_value
                        },
                        issues=issues,
                    )


def _validate_eq_scores(
    response: str,
    context: dict[str, Any],
    issues: list[str],
) -> None:
    people = _comparison_people(context)

    metric_records: list[
        tuple[str, dict[str, Any]]
    ] = []

    for _, data in context["eq"][
        "dimensions"
    ].items():
        metric_records.append(
            (
                data["approved_knowledge"][
                    "display_name"
                ],
                data["comparison"],
            )
        )

    for metric_name, data in context["eq"][
        "composites"
    ].items():
        metric_records.append(
            (
                metric_name,
                data["comparison"],
            )
        )

    for person_key, person_name in people.items():
        for metric_name, comparison in metric_records:
            valid_value = float(
                comparison[person_key]
            )

            for pattern in _explicit_score_patterns(
                person_name,
                metric_name,
            ):
                for match in pattern.finditer(response):
                    _record_score_mismatch(
                        person_name=person_name,
                        metric_name=metric_name,
                        claimed_value=float(
                            match.group(1)
                        ),
                        valid_values={
                            valid_value
                        },
                        issues=issues,
                    )


def _validate_explicit_scores(
    response: str,
    context: dict[str, Any],
    domain: ContextDomain,
    issues: list[str],
) -> None:
    if domain == ContextDomain.DISC:
        _validate_disc_scores(
            response=response,
            context=context,
            issues=issues,
        )

    elif domain == ContextDomain.DRIVING_FORCES:
        _validate_driving_force_scores(
            response=response,
            context=context,
            issues=issues,
        )

    elif domain == ContextDomain.EQ:
        _validate_eq_scores(
            response=response,
            context=context,
            issues=issues,
        )

    elif domain == ContextDomain.INTEGRATED:
        integrated = context.get(
            "integrated",
            {},
        )

        included_domains = set(
            context.get(
                "included_domains",
                [],
            )
        )

        validation_context = {
            "people": context["people"],
        }

        if (
            ContextDomain.DISC.value
            in included_domains
            and "disc" in integrated
        ):
            validation_context["disc"] = (
                integrated["disc"]
            )

            _validate_disc_scores(
                response=response,
                context=validation_context,
                issues=issues,
            )

        if (
            ContextDomain.DRIVING_FORCES.value
            in included_domains
            and "driving_forces" in integrated
        ):
            validation_context[
                "driving_forces"
            ] = integrated[
                "driving_forces"
            ]

            _validate_driving_force_scores(
                response=response,
                context=validation_context,
                issues=issues,
            )

        if (
            ContextDomain.EQ.value
            in included_domains
            and "eq" in integrated
        ):
            validation_context["eq"] = (
                integrated["eq"]
            )

            _validate_eq_scores(
                response=response,
                context=validation_context,
                issues=issues,
            )

def validate_comparison_response(
    response: str,
    context: dict[str, Any],
    resolved_domain: ContextDomain,
) -> ComparisonValidationResult:
    if not isinstance(response, str):
        return ComparisonValidationResult(
            status=ValidationStatus.RETRY,
            issues=[
                "Comparison response was not text."
            ],
        )

    response = response.strip()

    if not response:
        return ComparisonValidationResult(
            status=ValidationStatus.RETRY,
            issues=[
                "Comparison response was empty."
            ],
        )

    blocking_issues: list[str] = []

    _validate_prohibited_claims(
        response=response,
        issues=blocking_issues,
    )

    _validate_legacy_driving_force_labels(
        response=response,
        domain=resolved_domain,
        context=context,
        issues=blocking_issues,
    )

    _validate_explicit_scores(
        response=response,
        context=context,
        domain=resolved_domain,
        issues=blocking_issues,
    )

    if blocking_issues:
        return ComparisonValidationResult(
            status=ValidationStatus.BLOCK,
            issues=blocking_issues,
        )

    return ComparisonValidationResult(
        status=ValidationStatus.PASS,
        issues=[],
    )

def _validate_legacy_driving_force_labels(
    response: str,
    domain: ContextDomain,
    context: dict[str, Any],
    issues: list[str],
) -> None:
    """
    Detect legacy Motivator terminology only in Driving Forces
    comparison responses.

    Unambiguous legacy labels can use broader detection.
    Ambiguous ordinary-language labels require explicit
    assessment context.
    """

    driving_forces_allowed = (
        domain == ContextDomain.DRIVING_FORCES
    )

    if domain == ContextDomain.INTEGRATED:
        driving_forces_allowed = (
            ContextDomain.DRIVING_FORCES.value
            in context.get(
                "included_domains",
                [],
            )
        )

    if not driving_forces_allowed:
        return

    unambiguous_labels = {
        "Theoretical",
        "Utilitarian",
        "Individualistic",
    }

    ambiguous_labels = {
        "Aesthetic",
        "Social",
        "Traditional",
    }

    for label in unambiguous_labels:
        escaped = re.escape(label)

        patterns = [
            rf"\b{escaped}\s+motivator\b",
            rf"\b{escaped}\s+motivation\b",
            rf"\b{escaped}\s+driving\s+force\b",
            rf"\b{escaped}\s+score\b",
            rf"\b{escaped}\s*[:=]\s*\d+(?:\.\d+)?\b",
        ]

        match = _contains_pattern(
            response,
            patterns,
        )

        if match:
            issues.append(
                "Legacy Driving Forces terminology detected: "
                f"'{match}'."
            )

    for label in ambiguous_labels:
        escaped = re.escape(label)

        patterns = [
            rf"\b{escaped}\s+motivator\b",
            rf"\b{escaped}\s+motivator\s+score\b",
            rf"\b{escaped}\s+motivation\s+score\b",
            rf"\b{escaped}\s+driving\s+force\b",
            rf"\b{escaped}\s*[:=]\s*\d+(?:\.\d+)?\b",
        ]

        match = _contains_pattern(
            response,
            patterns,
        )

        if match:
            issues.append(
                "Legacy Driving Forces terminology detected: "
                f"'{match}'."
            )
