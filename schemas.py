from typing import Any


REQUIRED_TOP_LEVEL_KEYS = {
    "schema_version",
    "person",
    "assessment",
    "disc",
    "driving_forces",
    "eq",
    "integrated",
}


def validate_persona(data: dict[str, Any]) -> None:
    """
    Validate the required structure of an XQ persona.

    Raises:
        ValueError: If required data is missing or invalid.
    """

    if not isinstance(data, dict):
        raise ValueError("Persona data must be a JSON object.")

    missing_keys = REQUIRED_TOP_LEVEL_KEYS - data.keys()

    if missing_keys:
        raise ValueError(
            "Persona is missing required sections: "
            + ", ".join(sorted(missing_keys))
        )

    validate_person(data["person"])
    validate_assessment(data["assessment"])
    validate_disc(data["disc"])
    validate_driving_forces(data["driving_forces"])
    validate_eq(data["eq"])
    validate_integrated(data["integrated"])


def validate_person(person: dict[str, Any]) -> None:
    required = {
        "person_id",
        "first_name",
        "display_name",
        "family_role",
    }

    if not isinstance(person, dict):
        raise ValueError("The 'person' section must be an object.")

    missing = required - person.keys()

    if missing:
        raise ValueError(
            "Person section missing fields: "
            + ", ".join(sorted(missing))
        )

    for field in ("person_id", "first_name", "display_name", "family_role"):
        value = person[field]

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Person field '{field}' must be a non-empty string."
            )

    if "age" in person:
        age = person["age"]

        if not isinstance(age, int) or isinstance(age, bool):
            raise ValueError("Person age must be a whole number.")

        if not 0 <= age <= 120:
            raise ValueError("Person age must be between 0 and 120.")


def validate_assessment(assessment: dict[str, Any]) -> None:
    required = {
        "assessment_id",
        "assessment_date",
        "source",
    }

    if not isinstance(assessment, dict):
        raise ValueError("The 'assessment' section must be an object.")

    missing = required - assessment.keys()

    if missing:
        raise ValueError(
            "Assessment section missing fields: "
            + ", ".join(sorted(missing))
        )


def validate_score(
    score: Any,
    label: str,
) -> None:
    """
    Validate a numeric assessment score from 0 through 100.
    """

    if isinstance(score, bool) or not isinstance(score, (int, float)):
        raise ValueError(
            f"{label} must be numeric."
        )

    if not 0 <= score <= 100:
        raise ValueError(
            f"{label} must be between 0 and 100."
        )


def validate_disc(disc: dict[str, Any]) -> None:
    if not isinstance(disc, dict):
        raise ValueError("The 'disc' section must be an object.")

    for profile_name in ("natural", "adapted"):

        if profile_name not in disc:
            raise ValueError(
                f"DISC section missing '{profile_name}' profile."
            )

        profile = disc[profile_name]

        if not isinstance(profile, dict):
            raise ValueError(
                f"DISC '{profile_name}' profile must be an object."
            )

        required_traits = {"D", "I", "S", "C"}

        missing_traits = required_traits - profile.keys()

        if missing_traits:
            raise ValueError(
                f"DISC {profile_name} profile missing traits: "
                + ", ".join(sorted(missing_traits))
            )

        for trait in ("D", "I", "S", "C"):
            validate_score(
                profile[trait],
                f"DISC {profile_name} score '{trait}'",
            )

    primary_style = disc.get("primary_style")

    if not isinstance(primary_style, str) or not primary_style.strip():
        raise ValueError(
            "DISC 'primary_style' must be a non-empty string."
        )


def validate_driving_forces(
    driving_forces: dict[str, Any],
) -> None:

    if not isinstance(driving_forces, dict):
        raise ValueError(
            "The 'driving_forces' section must be an object."
        )

    required_forces = {
        "Intellectual",
        "Instinctive",
        "Resourceful",
        "Selfless",
        "Harmonious",
        "Objective",
        "Altruistic",
        "Intentional",
        "Commanding",
        "Collaborative",
        "Structured",
        "Receptive",
    }

    scores = driving_forces.get("scores")

    if not isinstance(scores, dict):
        raise ValueError(
            "Driving Forces must contain a 'scores' object."
        )

    missing = required_forces - scores.keys()

    if missing:
        raise ValueError(
            "Driving Forces missing scores: "
            + ", ".join(sorted(missing))
        )

    unexpected = scores.keys() - required_forces

    if unexpected:
        raise ValueError(
            "Driving Forces contains unexpected score names: "
            + ", ".join(sorted(unexpected))
        )

    for force in required_forces:
        validate_score(
            scores[force],
            f"Driving Force '{force}'",
        )

    for cluster_name in (
        "primary_cluster",
        "situational_cluster",
        "indifferent_cluster",
    ):

        cluster = driving_forces.get(cluster_name)

        if not isinstance(cluster, list):
            raise ValueError(
                f"Driving Forces '{cluster_name}' must be a list."
            )

        for force in cluster:

            if force not in required_forces:
                raise ValueError(
                    f"Unknown Driving Force '{force}' "
                    f"in '{cluster_name}'."
                )


def validate_eq(eq: dict[str, Any]) -> None:

    if not isinstance(eq, dict):
        raise ValueError(
            "The 'eq' section must be an object."
        )

    required_scores = {
        "self_awareness",
        "self_regulation",
        "motivation",
        "social_awareness",
        "social_regulation",
    }

    scores = eq.get("scores")

    if not isinstance(scores, dict):
        raise ValueError(
            "EQ must contain a 'scores' object."
        )

    missing = required_scores - scores.keys()

    if missing:
        raise ValueError(
            "EQ section missing scores: "
            + ", ".join(sorted(missing))
        )

    for dimension in required_scores:
        validate_score(
            scores[dimension],
            f"EQ score '{dimension}'",
        )

    for composite in (
        "self_composite",
        "others_composite",
        "total_eq",
    ):

        if composite not in eq:
            raise ValueError(
                f"EQ section missing '{composite}'."
            )

        validate_score(
            eq[composite],
            f"EQ '{composite}'",
        )
def validate_integrated(
    integrated: dict[str, Any],
) -> None:
    """
    Validate the deterministic integrated-analysis section.
    """

    if not isinstance(integrated, dict):
        raise ValueError(
            "The 'integrated' section must be an object."
        )

    required_fields = {
        "overview",
        "strengths",
        "development_areas",
        "family_applications",
        "closing_summary",
    }

    missing = required_fields - integrated.keys()

    if missing:
        raise ValueError(
            "Integrated section missing fields: "
            + ", ".join(sorted(missing))
        )

    for field in (
        "overview",
        "closing_summary",
    ):
        value = integrated[field]

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"Integrated field '{field}' "
                "must be a non-empty string."
            )

    for field in (
        "strengths",
        "development_areas",
        "family_applications",
    ):
        value = integrated[field]

        if not isinstance(value, list) or not value:
            raise ValueError(
                f"Integrated field '{field}' "
                "must be a non-empty list."
            )

        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"Integrated field '{field}' "
                    "must contain only non-empty strings."
                )