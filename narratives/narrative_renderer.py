"""Deterministic family narration from reviewed score-range language."""
from score_formatting import format_score
import json
from pathlib import Path
from typing import Any
from workspace_experience import Experience

from .narrative_classifier import (
    classify_disc_score,
    classify_disc_shift,
    classify_driving_force_score,
    classify_eq_score,
    classify_eq_difference,
)


BASE_DIR = Path(__file__).resolve().parent

DISC_LIBRARY_PATH = (
    BASE_DIR
    / "disc_narrative.json"
)

DRIVING_FORCES_LIBRARY_PATH = (
    BASE_DIR
    / "driving_forces_narrative.json"
)

EQ_LIBRARY_PATH = (
    BASE_DIR
    /   "eq_narrative.json"
)

INTEGRATED_LIBRARY_PATH = (
    BASE_DIR
    / "integrated_narrative.json"
)

def load_narrative_library(
    path: Path,
) -> dict[str, Any]:
    """
    Load an approved narrative library from disk.
    """

    if not path.exists():
        raise FileNotFoundError(
            f"Narrative library not found: {path}"
        )

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        return json.load(file)


def render_disc_shift(
    trait: str,
    natural_score: int,
    adapted_score: int,
    library: dict[str, Any],
) -> str:
    """
    Describe Natural-to-Adapted score movement
    without assigning a cause to that movement.
    """

    shift = classify_disc_shift(
        natural_score,
        adapted_score,
    )

    if shift == "minimal_shift":
        return ""

    trait_name = library[
        "trait_names"
    ][trait]

    shift_text = library[
        "shifts"
    ][shift]

    return (
        f"Your {trait_name} score {shift_text}, "
        f"moving from {format_score(natural_score)} naturally "
        f"to {format_score(adapted_score)} in the adapted profile."
    )


#DISC
def render_disc_narrative(
    persona: dict[str, Any],
    experience: str = "family",
) -> str:
    """
    Produce a deterministic, conversational DISC narrative
    from canonical persona data and approved narrative atoms.
    """

    library = load_narrative_library(
        Experience(experience).narrative("disc_narrative.json") if experience == "business" else DISC_LIBRARY_PATH
    )

    person = persona["person"]
    disc = persona["disc"]

    name = person["display_name"]

    natural = disc["natural"]
    adapted = disc["adapted"]

    primary_style = disc[
        "primary_style"
    ]

    profile_library = library[
        "profiles"
    ]

    profile = profile_library.get(primary_style, {
        "opening": "We will use the individual scores to explore this reported pattern.",
        "family_presence": "The style name is retained as it appears in your assessment.",
        "strength": "Different combinations of preferences can support different team needs." if experience == "business" else "Different combinations of preferences can support different family needs.",
        "watchout": "A style label alone does not explain every response or situation.",
    })

    parts: list[str] = []

    # -----------------------------------
    # PERSONAL OPENING
    # -----------------------------------

    parts.append(
        (
            f"{name}, when we look beyond the individual "
            f"numbers, your DISC results form a "
            f"{primary_style} behavioral pattern."
        )
    )

    parts.append(
        profile["opening"]
    )

    parts.append(
        profile["family_presence"]
    )

    # -----------------------------------
    # EXACT SCORES
    # -----------------------------------

    parts.append(
        (
            f"Your natural DISC scores are "
            f"D {format_score(natural['D'])}, "
            f"I {format_score(natural['I'])}, "
            f"S {format_score(natural['S'])}, "
            f"and C {format_score(natural['C'])}."
        )
    )

    # -----------------------------------
    # TRAIT INTERPRETATION
    # -----------------------------------

    for trait in (
        "D",
        "I",
        "S",
        "C",
    ):
        score = natural[trait]

        level = classify_disc_score(
            score
        )

        atom = library[
            "traits"
        ][trait][level]

        parts.append(
            atom["strength"]
        )

        parts.append(
            atom["family_expression"]
        )

        parts.append(
            atom["watchout"]
        )

    # -----------------------------------
    # PROFILE STRENGTH / WATCHOUT
    # -----------------------------------

    parts.append(
        profile["strength"]
    )

    parts.append(
        profile["watchout"]
    )

    # -----------------------------------
    # NATURAL / ADAPTED MOVEMENT
    # -----------------------------------

    shift_parts: list[str] = []

    for trait in (
        "D",
        "I",
        "S",
        "C",
    ):
        shift_text = render_disc_shift(
            trait=trait,
            natural_score=natural[trait],
            adapted_score=adapted[trait],
            library=library,
        )

        if shift_text:
            shift_parts.append(
                shift_text
            )

    if shift_parts:
        parts.append(
            (
                "Your adapted pattern also gives us "
                "some additional context."
            )
        )

        parts.extend(
            shift_parts
        )

    for trait in ("D", "I", "S", "C"):
        label = library["trait_names"][trait]
        level = classify_disc_score(adapted[trait])
        parts.append(f"Your adapted {label} score is {format_score(adapted[trait])}.")
        if level == classify_disc_score(natural[trait]):
            parts.append("Its preference description is similar to your natural pattern.")
        else:
            parts.append("For this adapted pattern, the score suggests the following preferences.")
            parts.extend(library["traits"][trait][level].values())
    parts.append("Adapted scores describe a reported adjustment in behavior; they do not establish its cause.")

    # -----------------------------------
    # EXISTING PERSON-SPECIFIC CONTENT
    # -----------------------------------

    characteristics = disc.get(
        "behavioral_characteristics",
        [],
    )

    if characteristics:
        if experience == 'business':
            from narrative_perspective import legacy_participant_text
            characteristics = [legacy_participant_text(item, person) for item in characteristics]
        joined_characteristics = (" ".join(item.rstrip('. ') + '.' for item in characteristics)
                                  if experience == 'business' else ", ".join(characteristics))

        parts.append(
            (
                f"Your reported behavioral characteristics: "
                f"{joined_characteristics.rstrip('. ')}."
            )
        )

    family_values = disc.get(
        "value_to_family",
        [],
    )

    if family_values:
        if experience == 'business':
            from narrative_perspective import legacy_participant_text
            family_values = [legacy_participant_text(item, person) for item in family_values]
        joined_values = (" ".join(item.rstrip('. ') + '.' for item in family_values)
                         if experience == 'business' else "; ".join(family_values))

        parts.append(
            (
                f"Potential ways this can add value "
                f"within the {'team' if experience == 'business' else 'family'} include: "
                f"{joined_values.rstrip('. ')}."
            )
        )

    # -----------------------------------
    # CLOSING
    # -----------------------------------

    parts.extend(
        library["closing"]
    )

    return " ".join(parts)


#12DF
def render_driving_forces_narrative(
    persona: dict[str, Any],
    experience: str = "family",
) -> str:
    library = load_narrative_library(
        Experience(experience).narrative("driving_forces_narrative.json") if experience == "business" else DRIVING_FORCES_LIBRARY_PATH
    )

    person = persona["person"]
    driving_forces = persona[
        "driving_forces"
    ]

    name = person["display_name"]

    scores = driving_forces["scores"]

    primary = driving_forces[
        "primary_cluster"
    ]

    situational = driving_forces[
        "situational_cluster"
    ]

    indifferent = driving_forces[
        "indifferent_cluster"
    ]

    parts: list[str] = []

    # -----------------------------------
    # OPENING
    # -----------------------------------

    parts.append(
        (
            f"{name}, your Driving Forces help explain "
            f"something DISC does not: not simply how "
            f"you tend to behave, but what makes certain "
            f"choices and outcomes matter to you."
        )
    )

    # -----------------------------------
    # PRIMARY CLUSTER
    # -----------------------------------

    if primary:
        primary_names = ", ".join(
            primary
        )

        parts.append(
            (
                f"Your primary Driving Forces are "
                f"{primary_names}. "
                f"{library['clusters']['primary']}"
            )
        )

    # -----------------------------------
    # SITUATIONAL CLUSTER
    # -----------------------------------

    if situational:
        situational_names = ", ".join(
            situational
        )

        parts.append(
            (
                f"Your situational Driving Forces are "
                f"{situational_names}. "
                f"{library['clusters']['situational']}"
            )
        )

    # -----------------------------------
    # INDIFFERENT CLUSTER
    # -----------------------------------

    if indifferent:
        indifferent_names = ", ".join(
            indifferent
        )

        parts.append(
            (
                f"Your indifferent Driving Forces are "
                f"{indifferent_names}. "
                f"{library['clusters']['indifferent']}"
            )
        )

    # Explain every measured force, including situational and indifferent results.
    for force, score in scores.items():
        atom = library["forces"][force][classify_driving_force_score(score)]
        parts.append(f"Your {force} score is {format_score(score)}.")
        parts.extend(atom[key] for key in ("core", "family_expression", "strength", "watchout"))

    # -----------------------------------
    # MOTIVATIONAL CONTRASTS
    # -----------------------------------

    pairs = (
        ("Intellectual", "Instinctive"),
        ("Resourceful", "Selfless"),
        ("Harmonious", "Objective"),
        ("Altruistic", "Intentional"),
        ("Commanding", "Collaborative"),
        ("Structured", "Receptive"),
    )

    strongest_gap = 0
    strongest_pair = None

    for left, right in pairs:
        gap = abs(
            scores[left]
            - scores[right]
        )

        if gap > strongest_gap:
            strongest_gap = gap
            strongest_pair = (
                left,
                right,
            )

    if (
        strongest_pair
        and strongest_gap >= 20
    ):
        left, right = strongest_pair

        higher = (
            left
            if scores[left] > scores[right]
            else right
        )

        lower = (
            right
            if higher == left
            else left
        )

        parts.append(
            (
                f"One of the clearest motivational contrasts "
                f"in your profile is between {higher} "
                f"at {format_score(scores[higher])} and {lower} "
                f"at {format_score(scores[lower])}."
            )
        )

        parts.append(
            "That contrast can be particularly useful in understanding why your priorities may feel obvious to you "
            + ("while a colleague" if experience == "business" else "while another family member")
            + " can approach the same situation from a very different motivational starting point."
        )

    # -----------------------------------
    # CLOSING
    # -----------------------------------

    parts.extend(
        library["closing"]
    )

    return " ".join(parts)


#EQ
def render_eq_narrative(
    persona: dict[str, Any],
    experience: str = "family",
) -> str:
    library = load_narrative_library(
        Experience(experience).narrative("eq_narrative.json") if experience == "business" else EQ_LIBRARY_PATH
    )

    person = persona["person"]
    eq = persona["eq"]

    name = person["display_name"]

    scores = eq["scores"]

    self_composite = eq[
        "self_composite"
    ]

    others_composite = eq[
        "others_composite"
    ]

    total_eq = eq[
        "total_eq"
    ]

    parts: list[str] = []

    # -----------------------------------
    # OPENING
    # -----------------------------------

    parts.append(
        (
            f"{name}, your Emotional Quotient results "
            f"help us understand how you recognize, manage, "
            f"and respond to emotional information — both "
            f"within yourself and in your relationships."
        )
    )

    # -----------------------------------
    # DIMENSION SCORES
    # -----------------------------------

    dimension_order = (
        "self_awareness",
        "self_regulation",
        "motivation",
        "social_awareness",
        "social_regulation",
    )

    for dimension in dimension_order:
        score = scores[dimension]

        level = classify_eq_score(
            score
        )

        atom = library[
            "dimensions"
        ][dimension][level]

        label = library[
            "dimensions"
        ][dimension]["label"]

        parts.append(
            (
                f"Your {label} score is {format_score(score)}."
            )
        )

        parts.append(
            atom["core"]
        )

        parts.append(
            atom["family_expression"]
        )

        parts.append(
            atom["strength"]
        )

        parts.append(
            atom["watchout"]
        )

    # -----------------------------------
    # SELF-AWARENESS VS SELF-REGULATION
    # -----------------------------------

    awareness = scores[
        "self_awareness"
    ]

    regulation = scores[
        "self_regulation"
    ]

    awareness_vs_regulation = (
        classify_eq_difference(
            awareness,
            regulation,
        )
    )

    if awareness_vs_regulation in (
        "higher",
        "much_higher",
    ):
        parts.append(
            (
                "One useful distinction appears between "
                "your Self-Awareness and Self-Regulation. "
                "You may recognize an emotional reaction "
                "before you have fully determined how you "
                "want to manage or express it."
            )
        )

    elif awareness_vs_regulation in (
        "lower",
        "much_lower",
    ):
        parts.append(
            (
                "Your Self-Regulation is stronger than "
                "your Self-Awareness. This can mean that "
                "you are often capable of controlling a "
                "reaction even when understanding exactly "
                "what produced it requires additional reflection."
            )
        )

    # -----------------------------------
    # SOCIAL AWARENESS / REGULATION
    # -----------------------------------

    social_awareness = scores[
        "social_awareness"
    ]

    social_regulation = scores[
        "social_regulation"
    ]

    if (
        social_awareness >= 70
        and social_regulation >= 70
    ):
        parts.append(
            (
                "Your Social Awareness and Social Regulation "
                "also reinforce one another. You tend not only "
                "to notice emotional information from other "
                "people, but also to have a relatively strong "
                "ability to adjust your response to that information."
            )
        )

    # -----------------------------------
    # MOTIVATION VS REGULATION
    # -----------------------------------

    motivation = scores[
        "motivation"
    ]

    motivation_vs_regulation = (
        classify_eq_difference(
            motivation,
            regulation,
        )
    )

    if motivation_vs_regulation in (
        "higher",
        "much_higher",
    ):
        parts.append(
            (
                "Your internal Motivation is also stronger "
                "than your Self-Regulation. In practice, "
                "that can create considerable persistence "
                "and forward drive, while making emotional "
                "pacing especially important when frustration rises."
            )
        )

    # -----------------------------------
    # COMPOSITES
    # -----------------------------------

    for key, label, score in (
        ("self", "Self Composite", self_composite),
        ("others", "Others Composite", others_composite),
        ("total", "Total EQ", total_eq),
    ):
        parts.append(f"Your {label} is {format_score(score)}. {library['composites'][key]}")
        atom = library["composite_ranges"][key][classify_eq_score(score)]
        parts.extend(atom.values())

    # -----------------------------------
    # SELF VS OTHERS COMPOSITE
    # -----------------------------------

    composite_difference = (
        classify_eq_difference(
            others_composite,
            self_composite,
        )
    )

    if composite_difference in (
        "higher",
        "much_higher",
    ):
        parts.append(
            (
                "Your Others Composite is notably stronger "
                "than your Self Composite. That pattern suggests "
                "that reading and navigating the emotional needs "
                "of other people may currently be a particular "
                "strength within your overall EQ profile."
            )
        )

    elif composite_difference in (
        "lower",
        "much_lower",
    ):
        parts.append(
            (
                "Your Self Composite is notably stronger "
                "than your Others Composite. That pattern suggests "
                "that managing your own internal emotional world "
                "may currently be more developed than navigating "
                "the emotional dynamics surrounding other people."
            )
        )

    # -----------------------------------
    # CLOSING
    # -----------------------------------

    parts.extend(
        library["closing"]
    )

    return " ".join(parts)

#Integrated
#Helpers
def _disc_score(
    persona: dict[str, Any],
    trait: str,
) -> int:
    return persona["disc"]["natural"][trait]


def _eq_score(
    persona: dict[str, Any],
    dimension: str,
) -> int:
    return persona["eq"]["scores"][dimension]


def _has_primary_force(
    persona: dict[str, Any],
    force: str,
) -> bool:
    return force in persona[
        "driving_forces"
    ][
        "primary_cluster"
    ]


def _has_situational_force(
    persona: dict[str, Any],
    force: str,
) -> bool:
    return force in persona[
        "driving_forces"
    ][
        "situational_cluster"
    ]

#Actual renderer
def render_integrated_narrative(
    persona: dict[str, Any],
    experience: str = "family",
) -> str:
    library = load_narrative_library(
        Experience(experience).narrative("integrated_narrative.json") if experience == "business" else INTEGRATED_LIBRARY_PATH
    )

    person = persona["person"]
    disc = persona["disc"]
    forces = persona["driving_forces"]
    eq = persona["eq"]

    name = person["display_name"]
    style = disc["primary_style"]

    primary_forces = forces[
        "primary_cluster"
    ]

    patterns = library["patterns"]

    parts: list[str] = []

    parts.append(
        (
            f"{name}, {library['openings'][0]} "
            f"Your primary DISC style is {style}, "
            f"your strongest Driving Forces are "
            f"{', '.join(primary_forces)}, "
            f"and your Total EQ is {format_score(eq['total_eq'])}."
        )
    )

    # -----------------------------------
    # DECISIVENESS + COMMANDING
    # -----------------------------------

    if (
        _disc_score(
            persona,
            "D",
        ) >= 60
        and _has_primary_force(
            persona,
            "Commanding",
        )
    ):
        parts.append(
            patterns[
                "decisive_influence"
            ]["text"]
        )

    # -----------------------------------
    # HIGH D + HIGH MOTIVATION
    # -----------------------------------

    if (
        _disc_score(
            persona,
            "D",
        ) >= 60
        and _eq_score(
            persona,
            "motivation",
        ) >= 70
    ):
        parts.append(
            patterns[
                "driven_momentum"
            ]["text"]
        )

    # -----------------------------------
    # HIGH C + INTELLECTUAL
    # -----------------------------------

    if (
        _disc_score(
            persona,
            "C",
        ) >= 60
        and (
            _has_primary_force(
                persona,
                "Intellectual",
            )
            or _has_situational_force(
                persona,
                "Intellectual",
            )
        )
    ):
        parts.append(
            patterns[
                "analytical_learning"
            ]["text"]
        )

    # -----------------------------------
    # HIGH S + ALTRUISTIC
    # -----------------------------------

    if (
        _disc_score(
            persona,
            "S",
        ) >= 60
        and _has_primary_force(
            persona,
            "Altruistic",
        )
    ):
        parts.append(
            patterns[
                "relational_support"
            ]["text"]
        )

    # -----------------------------------
    # COLLABORATIVE + SOCIAL AWARENESS
    # -----------------------------------

    if (
        _has_primary_force(
            persona,
            "Collaborative",
        )
        and _eq_score(
            persona,
            "social_awareness",
        ) >= 70
    ):
        parts.append(
            patterns[
                "collaborative_awareness"
            ]["text"]
        )

    # -----------------------------------
    # STRUCTURED + SELF REGULATION
    # -----------------------------------

    if (
        (
            _has_primary_force(
                persona,
                "Structured",
            )
            or _has_situational_force(
                persona,
                "Structured",
            )
        )
        and _eq_score(
            persona,
            "self_regulation",
        ) >= 70
    ):
        parts.append(
            patterns[
                "structured_regulation"
            ]["text"]
        )

    # -----------------------------------
    # RECEPTIVE + SOCIAL REGULATION
    # -----------------------------------

    if (
        (
            _has_primary_force(
                persona,
                "Receptive",
            )
            or _has_situational_force(
                persona,
                "Receptive",
            )
        )
        and _eq_score(
            persona,
            "social_regulation",
        ) >= 70
    ):
        parts.append(
            patterns[
                "adaptive_openness"
            ]["text"]
        )

    # -----------------------------------
    # MOTIVATION > SELF REGULATION
    # -----------------------------------

    motivation = _eq_score(
        persona,
        "motivation",
    )

    self_regulation = _eq_score(
        persona,
        "self_regulation",
    )

    if (
        motivation
        - self_regulation
        >= 10
    ):
        parts.append(
            patterns[
                "high_drive_regulation_gap"
            ]["text"]
        )

    # -----------------------------------
    # SELF AWARENESS > SELF REGULATION
    # -----------------------------------

    self_awareness = _eq_score(
        persona,
        "self_awareness",
    )

    if (
        self_awareness
        - self_regulation
        >= 7
    ):
        parts.append(
            patterns[
                "awareness_before_regulation"
            ]["text"]
        )

    # -----------------------------------
    # INTERPERSONAL EQ
    # -----------------------------------

    if (
        _eq_score(
            persona,
            "social_awareness",
        ) >= 70
        and _eq_score(
            persona,
            "social_regulation",
        ) >= 70
    ):
        parts.append(
            patterns[
                "strong_interpersonal_eq"
            ]["text"]
        )

    # -----------------------------------
    # FALLBACK
    # -----------------------------------

    if len(parts) == 1:
        parts.append(
            (
                "Your profile does not rely on one dominant "
                "cross-domain pattern. Instead, your behavior, "
                "motivation, and emotional intelligence appear "
                "to contribute in a more balanced way depending "
                "on the situation."
            )
        )

    # -----------------------------------
    # CLOSE
    # -----------------------------------

    parts.extend(
        library["closings"]
    )

    return " ".join(parts)
