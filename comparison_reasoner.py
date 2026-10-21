import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from comparison_context_builder import ComparisonContextBuilder
from comparison_engine import ComparisonEngine
from context_router import (
    ContextDomain,
    DISC_TERMS,
    DRIVING_FORCE_TERMS,
    EQ_TERMS,
    route_question,
)

from comparison_response_validator import (
    ValidationStatus,
    validate_comparison_response,
)

ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=ENV_PATH)


@dataclass
class ComparisonReasoningResult:
    response: str
    resolved_domain: ContextDomain
    validation_issues: list[str] | None = None

def detect_requested_comparison_domains(
            question: str,
    ) -> list[ContextDomain]:
        """
        Determine which assessment domains the comparison
        questions explicitly requests.
        """

        normalized = question.lower().strip()

        requested: list[ContextDomain] = []

        if any(
            term in normalized
            for term in DISC_TERMS
        ):
            requested.append(
                ContextDomain.DISC
            )

        if any(
            term in normalized
            for term in DRIVING_FORCE_TERMS
        ):
            requested.append(
                ContextDomain.DRIVING_FORCES
            )

        if any(
            term in normalized
            for term in EQ_TERMS
        ):
            requested.append(
                ContextDomain.EQ
            )

        return requested

class ComparisonReasoner:
    """
    Controlled reasoning layer for two-person assessment comparisons.
    """


    def __init__(
        self,
        client: Any | None = None,
        knowledge_dir: str | Path = "knowledge",
    ) -> None:
        if client is not None:
            self.client = client
        else:
            api_key = os.getenv("OPENAI_API_KEY")

            if not api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY was not found in the environment."
                )

            self.client = OpenAI(api_key=api_key)

        self.comparison_engine = ComparisonEngine()

        self.context_builder = ComparisonContextBuilder(
            knowledge_dir=knowledge_dir
        )

    def resolve_comparison_domain(
        self,
        question: str,
    ) -> ContextDomain:
        """
        Comparison questions must identify a supported domain.

        Unlike individual debrief questions, there is no current
        debrief state to use as a fallback.
        """

        route = route_question(question)

        if route.domain == ContextDomain.GENERAL:
            raise ValueError(
                "The comparison question must identify DISC, "
                "Driving Forces, or EQ."
            )

        return route.domain

    def build_context(
        self,
        question: str,
        persona_a: dict[str, Any],
        persona_b: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a domain-specific comparison packet.
        """

        resolved_domain = self.resolve_comparison_domain(
            question
        )

        included_domains = (
            detect_requested_comparison_domains(
                question
            )
        )

        if (
            resolved_domain == ContextDomain.INTEGRATED
            and not included_domains
        ):
            included_domains = [
                ContextDomain.DISC,
                ContextDomain.DRIVING_FORCES,
                ContextDomain.EQ,
            ]

        comparison = self.comparison_engine.compare_personas(
            persona_a=persona_a,
            persona_b=persona_b,
        )

        context = self.context_builder.build_context(
            comparison=comparison,
            domain=resolved_domain,
            included_domains=included_domains,
        )

        context["question_domain"] = resolved_domain.value

        context["included_domains"] = [
            domain.value
            for domain in included_domains
        ]

        return context

    def answer_question(
        self,
        question: str,
        persona_a: dict[str, Any],
        persona_b: dict[str, Any],
    ) -> ComparisonReasoningResult:
        """
        Answer a two-person comparison question from a narrow,
        approved context packet.
        """

        context = self.build_context(
            question=question,
            persona_a=persona_a,
            persona_b=persona_b,
        )

        resolved_domain = ContextDomain(
            context["question_domain"]
        )

        system_prompt = """
You are the controlled comparison-reasoning component inside
the XQ Family Debrief system.

Follow these rules:

1. Use only the supplied validated comparison context.
2. Keep person_a and person_b facts separate.
3. Never assign one person's scores, style, role, or traits to the other.
4. Preserve exact XQ terminology.
5. Never invent scores, labels, definitions, motives, history, or family facts.
6. A higher score does not mean better, healthier, smarter, more mature, or more capable.
7. A score difference does not prove compatibility, incompatibility, conflict, intent, dominance, submission, or a relationship outcome.
8. Describe only possible interaction patterns supported by the supplied facts and approved knowledge.
9. Use cautious language such as "may," "could," or "may contribute."
10. Distinguish verified comparison facts from possible interpretation.
11. Do not diagnose medical, psychological, psychiatric, or developmental conditions.
12. If the question cannot be supported by the supplied context, say that the available comparison data is insufficient.
13. When the comparison domain is integrated, use each assessment domain listed in included_domains.
14. Do not reduce an integrated comparison to only one of the included domains.
15. Do not introduce assessment domains that are absent from included_domains.
16. Explain how the verified differences may interact, while avoiding claims about fixed views, intent, compatibility, or outcomes.
17. When verified differences across two profiles are supplied, explain how
those differences may interact in practical family situations.
18. You may identify likely areas of complementarity, friction, pacing
differences, communication mismatches, and decision-making tension when
those interpretations are supported by the supplied comparison data.
19. Do not stop at describing score differences. Translate the verified
differences into practical interaction patterns while preserving cautious
language and avoiding guaranteed outcomes.
"""

        user_prompt = f"""
VALIDATED XQ COMPARISON CONTEXT:
{json.dumps(context, indent=2)}

USER QUESTION:
{question}
"""

        response = self.client.responses.create(
            model="gpt-5.6",
            input=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
        )

        output_text = response.output_text.strip()

        if not output_text:
            output_text = (
                "The comparison reasoning component did not "
                "return an answer. Please restate the question."
            )

        validation = validate_comparison_response(
            response=output_text,
            context=context,
            resolved_domain=resolved_domain,
        )

        if validation.status == ValidationStatus.BLOCK:
            return ComparisonReasoningResult(
                response=(
                    "The comparison could not be completed "
                    "reliably. Please try the question again."
                ),
                resolved_domain=resolved_domain,
                validation_issues=validation.issues,
            )

        if validation.status == ValidationStatus.RETRY:
            return ComparisonReasoningResult(
                response=(
                    "The comparison response was incomplete. "
                    "Please try the question again."
                ),
                resolved_domain=resolved_domain,
                validation_issues=validation.issues,
            )

        return ComparisonReasoningResult(
            response=output_text,
            resolved_domain=resolved_domain,
            validation_issues=None,
        )