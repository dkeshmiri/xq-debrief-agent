import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from context_builder import ContextBuilder
from context_router import (
    resolve_domain_with_state,
    route_question,
)
from routing_policy import evaluate_routing_policy
from debrief_state import DebriefState
from dataclasses import dataclass


load_dotenv()

@dataclass
class AIReasoningResult:
    response: str
    resolved_domain: str
    is_cross_domain: bool
class AIReasoner:
    """
    Controlled reasoning layer for XQ debrief questions.

    The reasoner receives only a narrow context packet assembled
    from validated persona data and approved XQ knowledge.
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

        self.context_builder = ContextBuilder(
            knowledge_dir=knowledge_dir
        )

    def build_context(
        self,
        question: str,
        state: DebriefState,
        persona_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Evaluate routing policy and assemble an approved context packet.
        """
        decision = evaluate_routing_policy(
            question=question,
            state=state,
        )

        context = self.context_builder.build_context(
            route=decision.route,
            resolved_domain=decision.resolved_domain,
            persona_data=persona_data,
        )

        context["debrief_state"] = state.value

        context["routing_policy"] = {
            "resolved_domain": decision.resolved_domain.value,
            "current_domain": decision.current_domain.value,
            "is_cross_domain": decision.is_cross_domain,
            "allowed": decision.allowed,
            "reason": decision.reason,
        }


        return context

    def answer_question(
        self,
        question: str,
        state: DebriefState,
        persona_data: dict[str, Any],
    ) -> AIReasoningResult:
        """
        Ask GPT a tightly scoped question using approved context.
        """

        context = self.build_context(
            question=question,
            state=state,
            persona_data=persona_data,
        )

        system_prompt = """
You are the reasoning component inside the XQ Family Debrief system.

PROFILE-GROUNDED APPLICATION IS ALLOWED.

THE VALIDATED XQ CONTEXT PACKET IS THE AUTHORITATIVE SOURCE OF TRUTH.

For direct factual questions about DISC scores, Driving Forces scores or clusters,
EQ scores or composites, primary styles, or other values explicitly present in
the context packet:

- Answer directly from the exact value in the context packet.
- Do not claim information is missing if it is present anywhere in the packet.
- Do not infer, estimate, recalculate, or substitute a value.
- Preserve exact numbers, labels, categories, and capitalization.
- If the requested fact truly is not present in the context packet, say that it
  cannot be verified from the provided context.

For application questions, you may then make cautious, profile-grounded
interpretations using the rules below:

When score_range_wording is supplied, use its matching band language as the
starting point for interpretation. Preserve its meaning and qualifications.
General knowledge about a dimension must not override the person's score-specific
wording. Follow score_range_policy; these wording bands are not population norms.

You may use verified DISC, Driving Forces, EQ, integrated analysis,
approved narrative content, and known family context to provide
practical communication, parenting, relationship, conflict-management,
and family-dynamics suggestions.

You may make cautious, reasonable inferences from verified profile data
when answering application questions.

Use language such as:
- may
- can
- might
- could
- one possibility is
- one useful approach may be
- based on this profile
- this may show up as

Do not present an inference as a verified fact.

You may explain how the user's own verified traits could affect:
- communication with a spouse or partner
- parenting and interactions with children
- conflict
- decision-making
- emotional pacing
- family roles
- collaboration
- stress responses
- relationship dynamics

Do not diagnose medical, psychiatric, developmental, or personality
disorders.

Do not claim that DISC, Driving Forces, or EQ proves:
- causation
- pathology
- intent
- another person's internal state
- a clinical condition

Practical behavioral coaching is allowed.
Clinical or diagnostic interpretation is not.
"""

        user_prompt = f"""
CURRENT DEBRIEF STATE:
{state.value}

VALIDATED XQ CONTEXT PACKET:
{json.dumps(context, indent=2)}

USER QUESTION:
Answer this question usingthe validated context packet above.
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

        routing_policy = context["routing_policy"]

        if not output_text:
            return (
                "The reasoning component did not return an answer. "
                "Please restate the question."
            )

        return AIReasoningResult(
            response=output_text,
            resolved_domain=routing_policy["resolved_domain"],
            is_cross_domain=routing_policy["is_cross_domain"],
        )
