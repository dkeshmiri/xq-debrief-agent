import json
import os
import tempfile
from uuid import uuid4
from pathlib import Path
from typing import Any

from family_schema import (
    load_family_manifest,
    validate_family_manifest,
)
from schemas import validate_persona

PROJECT_ROOT = Path(__file__).resolve().parent


def resolve_project_path(path: str | Path) -> Path:
    """Roster paths are project-relative; explicit external absolute paths remain valid."""
    return (PROJECT_ROOT / path).resolve()


class FamilyRepository:
    """
    Loads and manages a validated family roster and its persona data.
    """

    def __init__(
        self,
        manifest_path: str | Path,
    ) -> None:
        self.manifest_path = resolve_project_path(manifest_path)

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
            persona_path = resolve_project_path(member["persona_file"])

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

    def save_persona(self, persona: dict, directory: Path) -> str:
        """Publish a validated profile and roster entry; caller serializes writes."""
        validate_persona(persona)
        person = persona["person"]
        person_id = person["person_id"]
        if self.has_person(person_id):
            if self.get_persona(person_id) != persona:
                raise ValueError("A different profile already uses this person ID.")
            return Path(self.get_member(person_id)["persona_file"]).name
        directory = resolve_project_path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{uuid4().hex}.json"
        member = {key: person[key] for key in ("person_id", "display_name", "family_role")}
        stored_path = target.relative_to(PROJECT_ROOT) if target.is_relative_to(PROJECT_ROOT) else target
        member.update(persona_file=stored_path.as_posix(), debrief_enabled=True)
        updated = {**self.family_data, "members": [*self.family_data["members"], member]}
        if not updated['default_person_id']:
            updated['default_person_id'] = person_id
        validate_family_manifest(updated)
        temporary = None
        try:
            with target.open("x", encoding="utf-8") as stream:
                os.chmod(target, 0o600)
                json.dump(persona, stream, indent=2, allow_nan=False)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.manifest_path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(updated, stream, indent=2, allow_nan=False)
            temporary.replace(self.manifest_path)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.family_data = updated
        self._members[person_id] = member
        self._personas[person_id] = persona
        if self.active_person_id is None:
            self.active_person_id = person_id
        return target.name
