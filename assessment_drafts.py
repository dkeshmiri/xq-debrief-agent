"""Local, revisioned review drafts. Never stores PDFs, API keys, or override PINs."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from assessment_schema import Extraction, Facts, validate_review

_LOCK = RLock()


class DraftConflict(ValueError):
    pass


class DraftStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, draft_id):
        try:
            if str(UUID(draft_id)) != draft_id:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise KeyError("Assessment draft not found.") from None
        return self.directory / f"{draft_id}.json"

    def create(self, extraction, family_role):
        draft = {"id": str(uuid4()), "revision": 1, "family_role": family_role,
                 "extraction": extraction.model_dump(), "overrides": []}
        with _LOCK:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._write(draft)
        return draft

    def get(self, draft_id):
        with _LOCK:
            try:
                return json.loads(self._path(draft_id).read_text())
            except FileNotFoundError:
                raise KeyError("Assessment draft not found.") from None

    def _write(self, draft):
        target = self._path(draft["id"])
        temporary = target.with_suffix(".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                os.chmod(temporary, 0o600)
                json.dump(draft, stream, indent=2, allow_nan=False)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def override(self, draft_id, revision, facts, family_role):
        validate_review(facts)
        family_role = family_role.strip()
        if not family_role or len(family_role) > 100:
            raise ValueError("Enter a family role of 1–100 characters.")
        with _LOCK:
            draft = self.get(draft_id)
            if draft["revision"] != revision:
                raise DraftConflict("This draft changed in another window. Reload the saved review before editing.")
            previous = {"facts": draft["extraction"]["facts"], "family_role": draft["family_role"]}
            updated = {"facts": facts.model_dump(), "family_role": family_role}
            changes = []

            def compare(before, after, path=""):
                if isinstance(before, dict):
                    for key in before:
                        compare(before[key], after[key], f"{path}.{key}".lstrip("."))
                elif before != after:
                    changes.append({"field": path, "before": before, "after": after})

            compare(previous, updated)
            if changes:
                draft.pop("generated", None)
                draft["extraction"]["facts"] = updated["facts"]
                draft["family_role"] = family_role
                draft["revision"] += 1
                draft["overrides"].append({"at": datetime.now(timezone.utc).isoformat(), "changes": changes})
                self._write(draft)
            return draft

    def save_generated(self, draft_id, revision, result):
        with _LOCK:
            draft = self.get(draft_id)
            if draft["revision"] != revision:
                raise DraftConflict("The review changed during generation. Generate again from the saved review.")
            draft["generated"] = result
            self._write(draft)

    def publish(self, draft_id, revision, save_persona):
        with _LOCK:
            draft = self.get(draft_id)
            if draft["revision"] != revision:
                raise DraftConflict("The saved review changed. Generate again before saving a profile.")
            result = draft.get("generated", {})
            if not result.get("ready_for_debrief"):
                raise ValueError("Generate a complete, reviewed persona before saving it to the app.")
            return save_persona(result["persona"])
