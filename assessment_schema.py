"""Typed contracts for report extraction and family-oriented persona writing."""
from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model

FORCES = (
    "Intellectual", "Instinctive", "Resourceful", "Selfless", "Harmonious",
    "Objective", "Altruistic", "Intentional", "Commanding", "Collaborative",
    "Structured", "Receptive",
)
EQ_DIMENSIONS = (
    "self_awareness", "self_regulation", "motivation", "social_awareness",
    "social_regulation",
)
COMPOSITES = ("self_composite", "others_composite", "total_eq")
Score = Annotated[float, Field(strict=True, ge=0, le=100)]
Text = Annotated[str, Field(min_length=1, max_length=12000)]
Force = Literal[*FORCES]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Explicit named score properties give the model and the review form the same keys.
DiscScores = create_model("DiscScores", __base__=Contract, **{k: (Score | None, ...) for k in "DISC"})
ForceScores = create_model("ForceScores", __base__=Contract, **{k: (Score | None, ...) for k in FORCES})
EqScores = create_model("EqScores", __base__=Contract, **{k: (Score | None, ...) for k in EQ_DIMENSIONS})


class PersonFacts(Contract):
    first_name: Text | None
    display_name: Text | None
    age: Annotated[int, Field(strict=True, ge=0, le=120)] | None


class AssessmentFacts(Contract):
    assessment_date: str | None
    source: Text | None


class DiscFacts(Contract):
    natural: DiscScores
    adapted: DiscScores
    primary_style: Text | None


class ForceFacts(Contract):
    scores: ForceScores
    primary_cluster: list[Force]
    situational_cluster: list[Force]
    indifferent_cluster: list[Force]


class EqFacts(Contract):
    scores: EqScores
    self_composite: Score | None
    others_composite: Score | None
    total_eq: Score | None


class Facts(Contract):
    person: PersonFacts
    assessment: AssessmentFacts
    disc: DiscFacts
    driving_forces: ForceFacts
    eq: EqFacts


class Evidence(Contract):
    field: Text
    document: Text
    page: Annotated[int, Field(strict=True, ge=1)]
    observation: Text


class ReportSection(Contract):
    title: Text
    document: Text
    pages: list[Annotated[int, Field(strict=True, ge=1)]]
    findings: list[Text]


class Extraction(Contract):
    facts: Facts
    evidence: list[Evidence]
    sections: list[ReportSection]
    warnings: list[Text]


class DiscLanguage(Contract):
    behavioral_characteristics: Annotated[list[Text], Field(min_length=1)]
    value_to_family: Annotated[list[Text], Field(min_length=1)]
    communication_do: Annotated[list[Text], Field(min_length=1)]
    communication_dont: Annotated[list[Text], Field(min_length=1)]


class ForceLanguage(Contract):
    motivational_strengths: Annotated[list[Text], Field(min_length=1)]
    energizers: Annotated[list[Text], Field(min_length=1)]
    stressors: Annotated[list[Text], Field(min_length=1)]


class IntegratedLanguage(Contract):
    overview: Text
    strengths: Annotated[list[Text], Field(min_length=1)]
    development_areas: Annotated[list[Text], Field(min_length=1)]
    family_applications: Annotated[list[Text], Field(min_length=1)]
    closing_summary: Text


class FamilyLanguage(Contract):
    disc: DiscLanguage
    driving_forces: ForceLanguage
    integrated: IntegratedLanguage


class GenerateRequest(Contract):
    draft_id: str
    revision: Annotated[int, Field(strict=True, ge=1)]
    reviewed: Literal[True]


class OverrideRequest(Contract):
    revision: Annotated[int, Field(strict=True, ge=1)]
    facts: Facts
    family_role: Annotated[str, Field(min_length=1, max_length=100)]
    pin: str


def missing_fields(facts: Facts) -> list[str]:
    """Age is optional in the existing persona schema; other facts are required."""
    missing = []

    def visit(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                visit(child, f"{path}.{key}".lstrip("."))
        elif path != "person.age" and (value is None or value == [] or value == ""):
            missing.append(path)

    visit(facts.model_dump())
    return missing


def validate_review(facts: Facts) -> None:
    value = facts.assessment.assessment_date
    if value is not None:
        try:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except ValueError:
            raise ValueError("Assessment date must be YYYY-MM-DD, or blank if unknown.") from None
    clusters = facts.driving_forces
    names = clusters.primary_cluster + clusters.situational_cluster + clusters.indifferent_cluster
    if len(set(names)) != len(names):
        raise ValueError("A Driving Force cannot appear more than once across clusters.")
    for path, value in (
        ("First name", facts.person.first_name),
        ("Display name", facts.person.display_name),
        ("Assessment source", facts.assessment.source),
        ("Primary style", facts.disc.primary_style),
    ):
        if value is not None and not value.strip():
            raise ValueError(f"{path} cannot contain only whitespace.")
