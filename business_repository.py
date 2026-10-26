"""Separate workplace roster using the existing validated profile storage contract."""
from pathlib import Path

from family_repository import FamilyRepository, resolve_project_path
from debrief_state import DebriefState, InteractionMode


class BusinessRepository(FamilyRepository):
    def __init__(self, manifest_path):
        path = resolve_project_path(manifest_path)
        if path.exists():
            super().__init__(path)
            for persona in self._personas.values():
                if persona.get('experience') != 'business':
                    raise ValueError('The workplace roster contains a non-business profile.')
            return
        self.manifest_path = path
        self.family_data = {'schema_version': '1.0', 'family_id': 'workplace',
                            'family_name': 'Your workplace', 'members': [], 'default_person_id': ''}
        self._members = {}
        self._personas = {}
        self.active_person_id = None

    def save_persona(self, persona, directory):
        if persona.get('experience') != 'business':
            raise ValueError('Only business-scoped profiles can be saved to this workspace.')
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        return super().save_persona(persona, directory)


class UnselectedEngine:
    """Empty workspace state, never a fabricated assessment."""
    display_name = 'No profile selected'
    def get_current_state(self):
        return DebriefState.INTRODUCTION
    def get_current_content(self):
        return 'Choose or import a workplace profile to begin your debrief.'
    def get_interaction_mode(self):
        return InteractionMode.DEBRIEF
    def exit_question_mode(self):
        pass
