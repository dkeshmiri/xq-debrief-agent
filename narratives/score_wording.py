"""Expose the narration's exact score-specific language to question answering."""
from .narrative_classifier import classify_disc_score, classify_driving_force_score, classify_eq_score
from .narrative_renderer import (
    DISC_LIBRARY_PATH, DRIVING_FORCES_LIBRARY_PATH, EQ_LIBRARY_PATH,
    load_narrative_library,
)

RANGE_POLICY = (
    "These are application wording bands, not validated population norms or diagnoses. "
    "Use the wording matching the actual score; general domain definitions do not "
    "establish a high score. Low DISC or Driving Forces scores are preferences, not "
    "deficits. Preserve reported clusters and never infer an opposing force's score. "
    "EQ composites summarize results and do not prove the same level in every dimension."
)


def score_wording(persona, domain, experience='family'):
    from workspace_experience import Experience
    profile = Experience(experience)
    def library_path(path):
        return profile.narrative(path.name) if profile.business else path
    if domain == "integrated":
        return {key: score_wording(persona, key, experience) for key in ("disc", "driving_forces", "eq")}
    result = {}

    def add(path, score, classifier, atoms):
        if score is None:
            result[path] = {"score": None, "band": None, "wording": {"core": "This result is unknown; no score-range interpretation is available."}}
            return
        band = classifier(score)
        result[path] = {"score": score, "band": band, "wording": atoms[band]}

    if domain == "disc":
        library = load_narrative_library(library_path(DISC_LIBRARY_PATH))
        for profile in ("natural", "adapted"):
            for trait, score in persona["disc"][profile].items():
                add(f"{profile}.{trait}", score, classify_disc_score, library["traits"][trait])
    elif domain == "driving_forces":
        library = load_narrative_library(library_path(DRIVING_FORCES_LIBRARY_PATH))
        for force, score in persona["driving_forces"]["scores"].items():
            add(force, score, classify_driving_force_score, library["forces"][force])
    elif domain == "eq":
        library = load_narrative_library(library_path(EQ_LIBRARY_PATH))
        for dimension, score in persona["eq"]["scores"].items():
            add(dimension, score, classify_eq_score, library["dimensions"][dimension])
        for field, key in (("self_composite", "self"), ("others_composite", "others"), ("total_eq", "total")):
            add(field, persona["eq"][field], classify_eq_score, library["composite_ranges"][key])
    return result
