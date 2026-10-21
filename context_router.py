from dataclasses import dataclass
from enum import Enum

from debrief_state import DebriefState

import re

class ContextDomain(str, Enum):
    DISC = "disc"
    DRIVING_FORCES = "driving_forces"
    EQ = "eq"
    INTEGRATED = "integrated"
    GENERAL = "general"


class ContextTopic(str, Enum):
    SCORES = "scores"
    STYLE = "style"
    COMMUNICATION = "communication"
    BEHAVIOR = "behavior"
    VALUE_TO_FAMILY = "value_to_family"
    STRENGTHS = "strengths"
    DEVELOPMENT = "development"
    DEFINITION = "definition"
    ENERGIZERS = "energizers"
    STRESSORS = "stressors"
    CONFLICTS = "conflicts"
    FAMILY_IMPLICATIONS = "family_implications"
    GENERAL = "general"


@dataclass
class ContextRoute:
    domain: ContextDomain
    topic: ContextTopic
    matched_terms: list[str]


DISC_TERMS = {
    "disc",
    "behavior",
    "behaviour",
    "style",
    "conductor",
    "persuader",
    "promoter",
    "relater",
    "supporter",
    "coordinator",
    "analyzer",
    "implementor",
    "dominance",
    "influence",
    "steadiness",
    "compliance",
}

DRIVING_FORCE_TERMS = {
    "driving force",
    "driving forces",
    "intellectual",
    "instinctive",
    "resourceful",
    "selfless",
    "harmonious",
    "objective",
    "altruistic",
    "intentional",
    "commanding",
    "collaborative",
    "structured",
    "receptive",
}

EQ_TERMS = {
    "eq",
    "emotional intelligence",
    "self-awareness",
    "self awareness",
    "self-regulation",
    "self regulation",
    "motivation",
    "social awareness",
    "social regulation",
}

INTEGRATED_TERMS = {
    "integrated",
    "complete profile",
    "overall profile",
    "whole profile",
    "all my results",
    "all of my results",
    "work together",
    "works together",
    "fit together",
    "fits together",
    "combined",
    "combination",
    "connect",
    "connected",
    "interaction between",
    "interact with",
    "piece it together",
    "put it all together",
}

COMMUNICATION_TERMS = {
    "communicate",
    "communication",
    "talk to",
    "speak to",
    "approach",
    "conversation",
}

STRENGTH_TERMS = {
    "strength",
    "strengths",
    "good at",
    "advantage",
    "value",
}

DEVELOPMENT_TERMS = {
    "development",
    "improve",
    "improvement",
    "challenge",
    "challenges",
    "weakness",
    "weaknesses",
}

ENERGIZER_TERMS = {
    "energizer",
    "energizers",
    "energize",
    "motivates",
    "motivated",
    "energy",
}

STRESSOR_TERMS = {
    "stress",
    "stressor",
    "stressors",
    "frustrate",
    "frustrates",
    "frustrated",
    "frustrating",
    "frustration",
    "drain",
    "drains",
    "draining",
    "irritate",
    "irritates",
    "irritated",
    "irritating",
}

CONFLICT_TERMS = {
    "conflict",
    "conflicts",
    "clash",
    "clashes",
    "disagree",
    "disagreement",
    "tension",
}

SCORE_TERMS = {
    "score",
    "scores",
    "number",
    "rating",
}

DEFINITION_TERMS = {
    "mean",
    "means",
    "definition",
    "define",
    "what is",
}


def _find_matches(
    text: str,
    terms: set[str],
) -> list[str]:
    return [
        term
        for term in terms
        if term in text
    ]


def _matched_domain_count(
    disc_matches:list[str],
    driving_force_matches:list[str],
    eq_matches:list[str],
) -> int:
    return sum(
        bool(matches)
        for matches in (
            disc_matches,
            driving_force_matches,
            eq_matches,
        )
)


def route_question(
    question: str,
) -> ContextRoute:

    normalized = question.lower().strip()

    disc_code_matches = []

    disc_code_patterns = {
        "D": r"\b(?:natural\s+|adapted\s+)?d\s+(?:score|trait|factor)\b",
        "I": r"\b(?:natural\s+|adapted\s+)?i\s+(?:score|trait|factor)\b",
        "S": r"\b(?:natural\s+|adapted\s+)?s\s+(?:score|trait|factor)\b",
        "C": r"\b(?:natural\s+|adapted\s+)?c\s+(?:score|trait|factor)\b",
    }

    for code, pattern in disc_code_patterns.items():
        if re.search(
            pattern,
            normalized,
            flags=re.IGNORECASE,
        ):
            disc_code_matches.append(code)

    disc_matches = _find_matches(
        normalized,
        DISC_TERMS,
    )

    disc_matches.extend(
        disc_code_matches
    )

    driving_force_matches = _find_matches(
        normalized,
        DRIVING_FORCE_TERMS,
    )

    eq_matches = _find_matches(
        normalized,
        EQ_TERMS,
    )

    integrated_matches = _find_matches(
        normalized,
        INTEGRATED_TERMS,
    )

    domain_count = sum(
        [
            bool(disc_matches),
            bool(driving_force_matches),
            bool(eq_matches),
        ]
    )

    # DOMAIN

    disc_term_matches = _find_matches(
        normalized,
        DISC_TERMS,
    )

    disc_term_matches.extend(
        disc_code_matches
    )

    driving_force_matches = _find_matches(
        normalized,
        DRIVING_FORCE_TERMS,
    )

    eq_matches = _find_matches(
        normalized,
        EQ_TERMS,
    )

    integrated_matches = _find_matches(
        normalized,
        INTEGRATED_TERMS,
    )

    matched_domains = []

    if disc_term_matches:
        matched_domains.append(
            ContextDomain.DISC
        )

    if driving_force_matches:
        matched_domains.append(
            ContextDomain.DRIVING_FORCES
        )

    if eq_matches:
        matched_domains.append(
            ContextDomain.EQ
        )

    # DOMAIN

    if integrated_matches or len(matched_domains) >= 2:
        domain = ContextDomain.INTEGRATED

        matched_terms = (
            integrated_matches
            + disc_term_matches
            + driving_force_matches
            + eq_matches
        )

    elif matched_domains:
        domain = matched_domains[0]

        if domain == ContextDomain.DISC:
            matched_terms = disc_term_matches

        elif domain == ContextDomain.DRIVING_FORCES:
            matched_terms = driving_force_matches

        elif domain == ContextDomain.EQ:
            matched_terms = eq_matches

        else:
            matched_terms = []

    else:
        domain = ContextDomain.GENERAL
        matched_terms = []

    # TOPIC

    if _find_matches(
        normalized,
        COMMUNICATION_TERMS,
    ):
        topic = ContextTopic.COMMUNICATION

    elif _find_matches(
        normalized,
        STRESSOR_TERMS,
    ):
        topic = ContextTopic.STRESSORS

    elif _find_matches(
        normalized,
        ENERGIZER_TERMS,
    ):
        topic = ContextTopic.ENERGIZERS

    elif _find_matches(
        normalized,
        CONFLICT_TERMS,
    ):
        topic = ContextTopic.CONFLICTS

    elif _find_matches(
        normalized,
        DEVELOPMENT_TERMS,
    ):
        topic = ContextTopic.DEVELOPMENT

    elif _find_matches(
        normalized,
        STRENGTH_TERMS,
    ):
        topic = ContextTopic.STRENGTHS

    elif _find_matches(
        normalized,
        SCORE_TERMS,
    ):
        topic = ContextTopic.SCORES

    elif _find_matches(
        normalized,
        DEFINITION_TERMS,
    ):
        topic = ContextTopic.DEFINITION

    else:
        topic = ContextTopic.GENERAL

    return ContextRoute(
        domain=domain,
        topic=topic,
        matched_terms=matched_terms,
    )

def resolve_domain_with_state(
    route: ContextRoute,
    state: DebriefState,
) -> ContextDomain:

    if route.domain != ContextDomain.GENERAL:
        return route.domain

    if state in (
        DebriefState.DISC_SCORES,
        DebriefState.DISC_STYLE,
        DebriefState.BEHAVIORAL_CHARACTERISTICS,
        DebriefState.VALUE_TO_FAMILY,
        DebriefState.DISC_NARRATIVE,
    ):
        return ContextDomain.DISC

    if state in (
        DebriefState.DRIVING_FORCES_SCORES,
        DebriefState.DRIVING_FORCES_CLUSTERS,
        DebriefState.DRIVING_FORCES_NARRATIVE,
    ):
        return ContextDomain.DRIVING_FORCES

    if state in (
        DebriefState.EQ_SCORES,
        DebriefState.EQ_NARRATIVE,
    ):
        return ContextDomain.EQ

    if state in(
        DebriefState.INTEGRATED_ANALYSIS,
        DebriefState.INTEGRATED_NARRATIVE,
    ):
        return ContextDomain.INTEGRATED

    return ContextDomain.GENERAL