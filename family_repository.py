import json
from pathlib import Path
from typing import Any

from family_schema import (
    load_family_manifest,
    validate_family_manifest,
)
from schemas import validate_persona


class FamilyRepository:
    """
    Loads and manages a validated family roster and its persona data.
    """

    def __init__(
        self,
        manifest_path: str | Path,
    ) -> None:
        self.manifest_path = Path(manifest_path)

        self.family_data = load_family_manifest(
            self.manifest_path
        )

        validate_family_manifest(
            self.family_data
        )

        self._members: dict[str, dict[str, Any]] = {}
        self._personas: dict[str, dict[str, Any]] = {}

        self._load_members()

        self.active_person_id = self.family_data[
            "default_person_id"
        ]

    def _load_members(self) -> None:
        for member in self.family_data["members"]:
            person_id = member["person_id"]
            persona_path = Path(member["persona_file"])

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

            if person["person_id"] != person_id:
                raise ValueError(
                    "Manifest person_id does not match "
                    f"persona file: {person_id}"
                )

            if (
                person["display_name"]
                != member["display_name"]
            ):
                raise ValueError(
                    "Manifest display_name does not match "
                    f"persona file: {person_id}"
                )

            if (
                person["family_role"]
                != member["family_role"]
            ):
                raise ValueError(
                    "Manifest family_role does not match "
                    f"persona file: {person_id}"
                )

            self._members[person_id] = member
            self._personas[person_id] = persona_data

    @property
    def family_id(self) -> str:
        return self.family_data["family_id"]

    @property
    def family_name(self) -> str:
        return self.family_data["family_name"]

    @property
    def default_person_id(self) -> str:
        return self.family_data["default_person_id"]

    def list_members(
        self,
        debrief_enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        members = list(self._members.values())

        if debrief_enabled_only:
            members = [
                member
                for member in members
                if member["debrief_enabled"]
            ]

        return [
            member.copy()
            for member in members
        ]

    def has_person(
        self,
        person_id: str,
    ) -> bool:
        return person_id in self._personas

    def get_member(
        self,
        person_id: str,
    ) -> dict[str, Any]:
        if person_id not in self._members:
            raise KeyError(
                f"Unknown family person_id: {person_id}"
            )

        return self._members[person_id].copy()

    def get_persona(
        self,
        person_id: str,
    ) -> dict[str, Any]:
        if person_id not in self._personas:
            raise KeyError(
                f"Unknown family person_id: {person_id}"
            )

        return self._personas[person_id]

    def get_default_persona(
        self,
    ) -> dict[str, Any]:
        return self.get_persona(
            self.default_person_id
        )

    def get_active_persona(
        self,
    ) -> dict[str, Any]:
        return self.get_persona(
            self.active_person_id
        )

    def get_active_member(
        self,
    ) -> dict[str, Any]:
        return self.get_member(
            self.active_person_id
        )

    def set_active_person(
        self,
        person_id: str,
    ) -> None:
        member = self.get_member(person_id)

        if not member["debrief_enabled"]:
            raise ValueError(
                f"Debrief is disabled for person_id: {person_id}"
            )

        self.active_person_id = person_id

    def reset_active_person(
        self,
    ) -> None:
        self.active_person_id = self.default_person_id