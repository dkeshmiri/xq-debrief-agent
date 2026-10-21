from dataclasses import dataclass

from context_router import (
    ContextDomain,
    ContextRoute,
    resolve_domain_with_state,
    route_question,
)
from debrief_state import DebriefState


@dataclass
class RoutingDecision:
    route: ContextRoute
    resolved_domain: ContextDomain
    current_domain: ContextDomain
    is_cross_domain: bool
    allowed: bool
    reason: str


def domain_for_state(
    state: DebriefState,
) -> ContextDomain:
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


    if state in (
        DebriefState.INTEGRATED_ANALYSIS,
        DebriefState.INTEGRATED_NARRATIVE,
    ):
        return ContextDomain.INTEGRATED

    return ContextDomain.GENERAL


def evaluate_routing_policy(
    question: str,
    state: DebriefState,
) -> RoutingDecision:
    route = route_question(question)

    resolved_domain = resolve_domain_with_state(
        route=route,
        state=state,
    )

    current_domain = domain_for_state(state)

    is_cross_domain = (
        current_domain != ContextDomain.GENERAL
        and resolved_domain != ContextDomain.GENERAL
        and resolved_domain != current_domain
    )

    return RoutingDecision(
        route=route,
        resolved_domain=resolved_domain,
        current_domain=current_domain,
        is_cross_domain=is_cross_domain,
        allowed=True,
        reason=(
            "Integrated question detected. Multiple assessment "
            "may be used while the debrief state remains "
            "unchanged."
            if resolved_domain == ContextDomain.INTEGRATED
            else (
                "Explicit cross-domain questions are allowed, "
                "but the debrief state must remain unchanged."
                if is_cross_domain
                else "Question is within the current debrief domain."
            )
        ),
    )