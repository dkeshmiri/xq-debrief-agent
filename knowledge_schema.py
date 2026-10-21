import json
from pathlib import Path
from typing import Any


DISC_REQUIRED_DIMENSIONS = {"D", "I", "S", "C"}

DISC_REQUIRED_STYLES = {
    "Conductor",
    "Persuader",
    "Promoter",
    "Relater",
    "Supporter",
    "Coordinator",
    "Analyzer",
    "Implementor",
}

DRIVING_FORCES_REQUIRED = {
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

DRIVING_FORCE_PAIRS = {
    "Intellectual": "Instinctive",
    "Instinctive": "Intellectual",
    "Resourceful": "Selfless",
    "Selfless": "Resourceful",
    "Harmonious": "Objective",
    "Objective": "Harmonious",
    "Altruistic": "Intentional",
    "Intentional": "Altruistic",
    "Commanding": "Collaborative",
    "Collaborative": "Commanding",
    "Structured": "Receptive",
    "Receptive": "Structured",
}

LEGACY_DRIVING_FORCE_TERMS = {
    "Theoretical",
    "Utilitarian",
    "Aesthetic",
    "Social",
    "Individualistic",
    "Traditional",
}

EQ_REQUIRED_DIMENSIONS = {
    "self_awareness",
    "self_regulation",
    "motivation",
    "social_awareness",
    "social_regulation",
}


def load_json(path: str | Path) -> dict[str, Any]:
    json_path = Path(path)

    if not json_path.exists():
        raise ValueError(
            f"Knowledge file does not exist: {json_path}"
        )

    with json_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Knowledge JSON must contain a top-level object."
        )

    return data


def require_nonempty_string(
    value: Any,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )


def require_nonempty_list(
    value: Any,
    field_name: str,
) -> None:
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"{field_name} must be a non-empty list."
        )


def validate_disc_knowledge(
    data: dict[str, Any],
) -> None:

    if data.get("knowledge_domain") != "DISC":
        raise ValueError(
            "DISC knowledge_domain must be 'DISC'."
        )

    require_nonempty_string(
        data.get("schema_version"),
        "DISC schema_version",
    )

    dimensions = data.get("dimensions")

    if not isinstance(dimensions, dict):
        raise ValueError(
            "DISC dimensions must be an object."
        )

    if set(dimensions.keys()) != DISC_REQUIRED_DIMENSIONS:
        raise ValueError(
            "DISC must contain exactly D, I, S, and C dimensions."
        )

    for code, dimension in dimensions.items():

        if not isinstance(dimension, dict):
            raise ValueError(
                f"DISC dimension {code} must be an object."
            )

        require_nonempty_string(
            dimension.get("name"),
            f"DISC {code} name",
        )

        require_nonempty_string(
            dimension.get("core_focus"),
            f"DISC {code} core_focus",
        )

    styles = data.get("styles")

    if not isinstance(styles, dict):
        raise ValueError(
            "DISC styles must be an object."
        )

    if set(styles.keys()) != DISC_REQUIRED_STYLES:
        raise ValueError(
            "DISC must contain exactly the 8 approved XQ styles."
        )

    for style_name, style in styles.items():

        if not isinstance(style, dict):
            raise ValueError(
                f"DISC style {style_name} must be an object."
            )

        require_nonempty_string(
            style.get("code"),
            f"{style_name} code",
        )

        require_nonempty_string(
            style.get("definition"),
            f"{style_name} definition",
        )


def validate_driving_forces_knowledge(
    data: dict[str, Any],
) -> None:

    if data.get("knowledge_domain") != "Driving Forces":
        raise ValueError(
            "Driving Forces knowledge_domain must be "
            "'Driving Forces'."
        )

    require_nonempty_string(
        data.get("schema_version"),
        "Driving Forces schema_version",
    )

    forces = data.get("forces")

    if not isinstance(forces, dict):
        raise ValueError(
            "Driving Forces forces must be an object."
        )

    actual_names = set(forces.keys())

    if actual_names != DRIVING_FORCES_REQUIRED:
        raise ValueError(
            "Driving Forces must contain exactly the 12 "
            "approved force names."
        )

    legacy_found = (
        actual_names
        & LEGACY_DRIVING_FORCE_TERMS
    )

    if legacy_found:
        raise ValueError(
            "Legacy Motivator terminology found as canonical "
            f"Driving Force names: {sorted(legacy_found)}"
        )

    for force_name, force in forces.items():

        if not isinstance(force, dict):
            raise ValueError(
                f"{force_name} must be an object."
            )

        require_nonempty_string(
            force.get("pair"),
            f"{force_name} pair",
        )

        expected_pair = (
            DRIVING_FORCE_PAIRS[
                force_name
            ]
        )

        if force["pair"] != expected_pair:
            raise ValueError(
                f"{force_name} must be paired with "
                f"{expected_pair}, not {force['pair']}."
            )

        require_nonempty_string(
            force.get("dimension"),
            f"{force_name} dimension",
        )

        require_nonempty_string(
            force.get("definition"),
            f"{force_name} definition",
        )

    cluster_definitions = data.get(
        "cluster_definitions"
    )

    if not isinstance(
        cluster_definitions,
        dict,
    ):
        raise ValueError(
            "cluster_definitions must be an object."
        )

    required_clusters = {
        "primary",
        "situational",
        "indifferent",
    }

    if (
        set(cluster_definitions.keys())
        != required_clusters
    ):
        raise ValueError(
            "cluster_definitions must contain exactly "
            "primary, situational, and indifferent."
        )


def validate_eq_knowledge(
    data: dict[str, Any],
) -> None:

    if (
        data.get("knowledge_domain")
        != "Emotional Intelligence"
    ):
        raise ValueError(
            "EQ knowledge_domain must be "
            "'Emotional Intelligence'."
        )

    require_nonempty_string(
        data.get("schema_version"),
        "EQ schema_version",
    )

    dimensions = data.get("dimensions")

    if not isinstance(dimensions, dict):
        raise ValueError(
            "EQ dimensions must be an object."
        )

    if (
        set(dimensions.keys())
        != EQ_REQUIRED_DIMENSIONS
    ):
        raise ValueError(
            "EQ must contain exactly the 5 approved dimensions."
        )

    for dimension_name, dimension in dimensions.items():

        if not isinstance(dimension, dict):
            raise ValueError(
                f"{dimension_name} must be an object."
            )

        require_nonempty_string(
            dimension.get("display_name"),
            f"{dimension_name} display_name",
        )

        require_nonempty_string(
            dimension.get("category"),
            f"{dimension_name} category",
        )

        require_nonempty_string(
            dimension.get("definition"),
            f"{dimension_name} definition",
        )

    composites = data.get("composites")

    if not isinstance(composites, dict):
        raise ValueError(
            "EQ composites must be an object."
        )

    required_composites = {
        "SELF",
        "OTHERS",
        "TOTAL_EQ",
    }

    if (
        set(composites.keys())
        != required_composites
    ):
        raise ValueError(
            "EQ composites must contain exactly "
            "SELF, OTHERS, and TOTAL_EQ."
        )

    expected_self = {
        "self_awareness",
        "self_regulation",
        "motivation",
    }

    expected_others = {
        "social_awareness",
        "social_regulation",
    }

    if (
        set(composites["SELF"].get(
            "includes",
            [],
        ))
        != expected_self
    ):
        raise ValueError(
            "SELF composite contains invalid dimensions."
        )

    if (
        set(composites["OTHERS"].get(
            "includes",
            [],
        ))
        != expected_others
    ):
        raise ValueError(
            "OTHERS composite contains invalid dimensions."
        )

    if (
        set(composites["TOTAL_EQ"].get(
            "includes",
            [],
        ))
        != EQ_REQUIRED_DIMENSIONS
    ):
        raise ValueError(
            "TOTAL_EQ composite must contain all 5 dimensions."
        )

    interpretation_rules = data.get(
        "interpretation_rules"
    )

    if not isinstance(
        interpretation_rules,
        dict,
    ):
        raise ValueError(
            "EQ interpretation_rules must be an object."
        )

    if (
        interpretation_rules.get(
            "do_not_diagnose"
        )
        is not True
    ):
        raise ValueError(
            "EQ do_not_diagnose must be true."
        )


def validate_all_knowledge(
    knowledge_dir: str | Path = "knowledge",
) -> None:

    base = Path(knowledge_dir)

    validate_disc_knowledge(
        load_json(
            base / "disc_knowledge.json"
        )
    )

    validate_driving_forces_knowledge(
        load_json(
            base
            / "driving_forces_knowledge.json"
        )
    )

    validate_eq_knowledge(
        load_json(
            base / "eq_knowledge.json"
        )
    )