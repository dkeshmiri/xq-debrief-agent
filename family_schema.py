import json
from pathlib import Path
from typing import Any

from schemas import validate_persona


REQUIRED_FAMILY_KEYS = {
    "schema_version",
    "family_id",
    "family_name",
    "members",
    "default_person_id",
}

REQUIRED_MEMBER_KEYS = {
    "person_id",
    "display_name",
    "family_role",
    "persona_file",
    "debrief_enabled",
}


def load_family_manifest(
    manifest_path: str | Path,
) -> dict[str, Any]:
    path = Path(manifest_path)

    if not path.exists():
        raise ValueError(
            f"Family manifest does not exist: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            "Family manifest must contain a top-level object."
        )

    return data


def _require_nonempty_string(
    value: Any,
    field_name: str,
) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )


def validate_family_manifest(
    data: dict[str, Any],
) -> None:
    missing_keys = REQUIRED_FAMILY_KEYS - set(data.keys())

    if missing_keys:
        raise ValueError(
            "Family manifest is missing required keys: "
            f"{sorted(missing_keys)}"
        )

    _require_nonempty_string(
        data["schema_version"],
        "schema_version",
    )
    _require_nonempty_string(
        data["family_id"],
        "family_id",
    )
    _require_nonempty_string(
        data["family_name"],
        "family_name",
    )
    _require_nonempty_string(
        data["default_person_id"],
        "default_person_id",
    )

    members = data["members"]

    if not isinstance(members, list) or not members:
        raise ValueError(
            "Family manifest must contain at least one member."
        )

    person_ids: set[str] = set()

    for index, member in enumerate(members):
        if not isinstance(member, dict):
            raise ValueError(
                f"Family member at index {index} must be an object."
            )

        missing_member_keys = (
            REQUIRED_MEMBER_KEYS - set(member.keys())
        )

        if missing_member_keys:
            raise ValueError(
                f"Family member at index {index} is missing keys: "
                f"{sorted(missing_member_keys)}"
            )

        for field in (
            "person_id",
            "display_name",
            "family_role",
            "persona_file",
        ):
            _require_nonempty_string(
                member[field],
                f"members[{index}].{field}",
            )

        if not isinstance(member["debrief_enabled"], bool):
            raise ValueError(
                f"members[{index}].debrief_enabled must be boolean."
            )

        person_id = member["person_id"]

        if person_id in person_ids:
            raise ValueError(
                f"Duplicate family person_id: {person_id}"
            )

        person_ids.add(person_id)

    if data["default_person_id"] not in person_ids:
        raise ValueError(
            "default_person_id must reference a family member."
        )


def validate_family_personas(
    family_data: dict[str, Any],
) -> None:
    """
    Validate every persona referenced by the family manifest and ensure
    manifest identity fields agree with the persona itself.
    """

    validate_family_manifest(family_data)

    for member in family_data["members"]:
        persona_path = Path(__file__).resolve().parent / member["persona_file"]

        if not persona_path.exists():
            raise ValueError(
                f"Persona file does not exist: {persona_path}"
            )

        with persona_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            persona_data = json.load(file)

        validate_persona(persona_data)

        person = persona_data["person"]

        if person["person_id"] != member["person_id"]:
            raise ValueError(
                "Manifest person_id does not match persona file: "
                f"{member['person_id']}"
            )

        if person["display_name"] != member["display_name"]:
            raise ValueError(
                "Manifest display_name does not match persona file: "
                f"{member['person_id']}"
            )

        if person["family_role"] != member["family_role"]:
            raise ValueError(
                "Manifest family_role does not match persona file: "
                f"{member['person_id']}"
            )
