from enum import Enum, auto


class DebriefState(str, Enum):
    INTRODUCTION = "introduction"

    DISC_SCORES = "disc_scores"
    DISC_STYLE = "disc_style"
    BEHAVIORAL_CHARACTERISTICS = "behavioral_characteristics"
    VALUE_TO_FAMILY = "value_to_family"
    DISC_NARRATIVE = "disc_narrative"

    DRIVING_FORCES_SCORES = "driving_forces_scores"
    DRIVING_FORCES_CLUSTERS = "driving_forces_clusters"
    DRIVING_FORCES_NARRATIVE = "driving_forces_narrative"

    EQ_SCORES = "eq_scores"
    EQ_NARRATIVE = "eq_narrative"

    INTEGRATED_ANALYSIS = "integrated_analysis"
    INTEGRATED_NARRATIVE = "integrated_narrative"

    COMPLETE = "complete"


class InteractionMode(str, Enum):
    """
    Defines what the application is currently doing.
    """

    DEBRIEF = "debrief"
    QUESTION = "question"


DEBRIEF_SEQUENCE = [
    DebriefState.INTRODUCTION,
    DebriefState.DISC_NARRATIVE,
    DebriefState.DRIVING_FORCES_NARRATIVE,
    DebriefState.EQ_NARRATIVE,
    DebriefState.INTEGRATED_NARRATIVE,
    DebriefState.COMPLETE,
]