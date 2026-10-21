import copy
import json
import unittest
from pathlib import Path

from comparison_context_builder import (
    ComparisonContextBuilder,
)
from comparison_engine import ComparisonEngine
from comparison_response_validator import (
    validate_comparison_response,
)
from comparison_response_validator import (
    ValidationStatus,
    validate_comparison_response,
)
from context_router import ContextDomain


class TestComparisonResponseValidator(unittest.TestCase):

    def setUp(self) -> None:
        with Path(
            "data/personas/samuel.json"
        ).open(
            "r",
            encoding="utf-8",
        ) as file:
            self.samuel = json.load(file)

        self.second_person = copy.deepcopy(
            self.samuel
        )

        self.second_person["person"].update(
            {
                "person_id": "test_person_002",
                "first_name": "Test",
                "display_name": "Test Person",
                "family_role": "Test Role",
            }
        )

        self.second_person["assessment"][
            "assessment_id"
        ] = "test_assessment_002"

        self.second_person["disc"][
            "primary_style"
        ] = "Supporter"

        self.second_person["disc"][
            "natural"
        ]["D"] = 48

        self.second_person[
            "driving_forces"
        ]["scores"]["Resourceful"] = 55

        self.second_person["eq"][
            "scores"
        ]["self_regulation"] = 80

        comparison = ComparisonEngine().compare_personas(
            self.samuel,
            self.second_person,
        )

        builder = ComparisonContextBuilder(
            "knowledge"
        )

        self.disc_context = builder.build_context(
            comparison=comparison,
            domain=ContextDomain.DISC,
        )

        self.force_context = builder.build_context(
            comparison=comparison,
            domain=ContextDomain.DRIVING_FORCES,
        )

        self.eq_context = builder.build_context(
            comparison=comparison,
            domain=ContextDomain.EQ,
        )

    def test_cautious_disc_response_passes(self) -> None:
        response = (
            "Samuel and Test Person may prefer different "
            "levels of pace and directness. This could require "
            "both people to adjust how they communicate."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(result.valid)

    def test_superiority_claim_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "Samuel is clearly the more mature person."
            ),
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertFalse(result.valid)

    def test_guaranteed_conflict_claim_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "Their score difference guarantees conflict."
            ),
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertFalse(result.valid)

    def test_legacy_term_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "Samuel's Utilitarian motivation is higher."
            ),
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertFalse(result.valid)

    def test_clinical_claim_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "This difference shows that Samuel has ADHD."
            ),
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertFalse(result.valid)

    def test_correct_resourceful_score_passes(self) -> None:
        result = validate_comparison_response(
            response=(
                "Samuel's Resourceful score is 81, while "
                "Test Person's Resourceful score is 55."
            ),
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertTrue(result.valid)

    def test_wrong_resourceful_score_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "Samuel's Resourceful score is 55."
            ),
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertFalse(result.valid)

    def test_wrong_eq_score_fails(self) -> None:
        result = validate_comparison_response(
            response=(
                "Samuel's Self-Regulation score is 80."
            ),
            context=self.eq_context,
            resolved_domain=ContextDomain.EQ,
        )

        self.assertFalse(result.valid)

    def test_normal_disc_prose_does_not_create_false_score_claims(
    self,
    ) -> None:
        response = (
            "Samuel and Test Person may communicate differently. "
            "Samuel may prefer a faster pace, while Test Person "
            "could favor steadiness and additional processing time."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )


    def test_disc_letters_inside_words_are_ignored(
        self,
    ) -> None:
        response = (
            "Different interaction styles could influence "
            "communication, consistency, and decision-making."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )


    def test_correct_explicit_natural_disc_score_passes(
        self,
    ) -> None:
        response = (
            "Samuel's natural D score is 72."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )


    def test_wrong_explicit_natural_disc_score_fails(
        self,
    ) -> None:
        response = (
            "Samuel's natural D score is 34."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertFalse(result.valid)


    def test_correct_explicit_adapted_disc_score_passes(
        self,
    ) -> None:
        response = (
            "Samuel's adapted D score is 65."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )

def test_realistic_disc_answer_passes(self) -> None:
    response = (
        "Samuel's Persuader style may lead him to communicate "
        "with greater urgency and directness. Jennifer's "
        "Supporter style may favor steadiness, patience, and "
        "time to process changes. These differences could "
        "require both people to adjust their pace and delivery."
    )

    result = validate_comparison_response(
        response=response,
        context=self.disc_context,
        resolved_domain=ContextDomain.DISC,
    )

    self.assertTrue(
        result.valid,
        msg=result.issues,
    )


def test_realistic_eq_answer_passes(self) -> None:
    response = (
        "Samuel's Self-Awareness score is 78, and Jennifer's "
        "Self-Awareness score is 74. Jennifer's Social Awareness "
        "score is 82, while Samuel's Social Awareness score is 71. "
        "These differences may affect what each person notices "
        "during emotionally demanding conversations, but they do "
        "not determine the outcome of those conversations."
    )

    result = validate_comparison_response(
        response=response,
        context=self.eq_context,
        resolved_domain=ContextDomain.EQ,
    )

    self.assertTrue(
        result.valid,
        msg=result.issues,
    )


    def test_ordinary_social_word_passes(self) -> None:
        response = (
            "Their social communication may benefit from clearer "
            "expectations and regular check-ins."
        )

        result = validate_comparison_response(
            response=response,
            context=self.eq_context,
            resolved_domain=ContextDomain.EQ,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )


    def test_disc_letters_inside_words_pass(self) -> None:
        response = (
            "Differences in communication, consistency, pace, "
            "and decision-making may require adaptation."
        )

        result = validate_comparison_response(
            response=response,
            context=self.disc_context,
            resolved_domain=ContextDomain.DISC,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )


    def test_verified_wrong_score_blocks(self) -> None:
        response = (
            "Samuel's Resourceful score is 42."
        )

        result = validate_comparison_response(
            response=response,
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertEqual(
            result.status,
            ValidationStatus.BLOCK,
        )


    def test_valid_score_in_complex_sentence_passes(
        self,
    ) -> None:
        response = (
            "Samuel's Resourceful score is 81, while Jennifer's "
            "Resourceful score is 42; this may contribute to "
            "different priorities around time, efficiency, and "
            "available resources."
        )

        result = validate_comparison_response(
            response=response,
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )

    def test_ordinary_traditional_language_passes(
        self,
    ) -> None:
        response = (
            "They may have different views about traditional "
            "family routines and expectations."
        )

        result = validate_comparison_response(
            response=response,
            context=self.force_context,
            resolved_domain=ContextDomain.DRIVING_FORCES,
        )

        self.assertTrue(
            result.valid,
            msg=result.issues,
        )