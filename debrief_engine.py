from score_formatting import format_score
import json
from pathlib import Path
from typing import Any
from ai_reasoner import AIReasoner
from guardrails import check_question_guardrails
from response_validator import validate_ai_response
from context_router import ContextDomain
from narratives.narrative_renderer import (
    render_disc_narrative,
    render_driving_forces_narrative,
    render_eq_narrative,
    render_integrated_narrative,
)

from schemas import validate_persona
from debrief_state import (
    DebriefState,
    InteractionMode,
    DEBRIEF_SEQUENCE
)


class DebriefEngine:
    """
    Core deterministic engine for the XQ Family Debrief system.

    The engine loads and validates an external persona JSON file.
    Because persona data is separate from application logic,
    different people can be loaded without changing the engine.
    """

    def __init__(self, persona_path: str | Path, ai_reasoner=None, experience='family') -> None:
        from workspace_experience import Experience
        self.experience = Experience(experience)
        self.persona_path = Path(persona_path)
        self.data = self._load_persona()

        # This will eventually become part of our state machine.
        self.current_state = DebriefState.INTRODUCTION
        self.interaction_mode = InteractionMode.DEBRIEF
        self.paused_state = None
        self.ai_reasoner = (
            ai_reasoner
            if ai_reasoner is not None
            else (AIReasoner(experience='business') if self.experience.business else AIReasoner())
        )

    def _load_persona(self) -> dict[str, Any]:
        """
        Load and validate persona data from a JSON file.
        """

        if not self.persona_path.exists():
            raise FileNotFoundError(
                f"Persona file not found: {self.persona_path}"
            )

        with self.persona_path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        validate_persona(data)
        if self.experience.business and data.get('experience') != 'business':
            raise ValueError('Select a business-scoped profile for this workspace.')

        if self.experience.business:
            from narrative_perspective import legacy_participant_text
            # Adapt older generated prose only in memory. Scores, identity and
            # the saved source profile remain untouched.
            fields = {
                'disc': ('behavioral_characteristics', 'value_to_family'),
                'driving_forces': ('motivational_strengths', 'energizers', 'stressors'),
                'integrated': tuple(data['integrated']),
            }
            for section, keys in fields.items():
                for key in keys:
                    value = data[section][key]
                    data[section][key] = ([legacy_participant_text(item, data['person']) for item in value]
                                          if isinstance(value, list)
                                          else legacy_participant_text(value, data['person']))

        return data

    @property
    def person(self) -> dict[str, Any]:
        """
        Convenience access to the active person's identity data.
        """

        return self.data["person"]

    @property
    def display_name(self) -> str:
        """
        Return the active person's preferred display name.
        """

        return self.person["display_name"]

    def get_introduction(self) -> str:
        """
        Produce the deterministic introduction.
        """

        name = self.display_name
        role = self.person["family_role"]

        return (
            f"Welcome, {name}. "
            f"This debrief will review your assessment results "
            f"in the context of your role as {role}."
        )

    def get_disc_scores(self) -> str:
        """
        Return exact Natural and Adapted DISC scores.
        """

        name = self.display_name

        natural = self.data["disc"]["natural"]
        adapted = self.data["disc"]["adapted"]

        return (
            f"Your Natural DISC scores are "
            f"D {format_score(natural['D'])}, "
            f"I {format_score(natural['I'])}, "
            f"S {format_score(natural['S'])}, "
            f"and C {format_score(natural['C'])}.\n\n"
            f"Your Adapted DISC scores are "
            f"D {format_score(adapted['D'])}, "
            f"I {format_score(adapted['I'])}, "
            f"S {format_score(adapted['S'])}, "
            f"and C {format_score(adapted['C'])}."
        )

    def get_primary_disc_style(self) -> str:
        """
        Return the exact stored DISC style name.
        """

        style = self.data["disc"]["primary_style"]

        return (
            f"Your primary behavioral style "
            f"is {style}."
        )

    def get_behavioral_characteristics(self) -> str:
        """
        Return approved behavioral characteristics exactly
        as stored in the canonical persona.
        """

        characteristics = self.data[
            "disc"
        ]["behavioral_characteristics"]

        lines = [
            f"Your behavioral characteristics include:"
        ]

        for characteristic in characteristics:
            lines.append(
                f"- {characteristic}"
            )

        return "\n".join(lines)

    def get_value_to_family(self) -> str:
        """
        Return approved Value to the Family statements.
        """

        values = self.data[
            "disc"
        ]["value_to_family"]

        lines = [
            f"Your potential contributions to the team include:" if self.experience.business
            else f"Your potential value to the family includes:"
        ]

        for value in values:
            lines.append(
                f"- {value}"
            )

        return "\n".join(lines)

    def get_driving_force_scores(self) -> str:
        """
        Return exact Driving Forces names and scores.
        """

        scores = self.data[
            "driving_forces"
        ]["scores"]

        lines = [
            f"Your Driving Forces scores are:"
        ]

        for force, score in scores.items():
            lines.append(
                f"- {force}: {format_score(score)}"
            )

        return "\n".join(lines)

    def get_driving_force_clusters(self) -> str:
        """
        Return exact Driving Forces cluster assignments.
        """

        driving_forces = self.data[
            "driving_forces"
        ]

        primary = ", ".join(
            driving_forces["primary_cluster"]
        )

        situational = ", ".join(
            driving_forces["situational_cluster"]
        )

        indifferent = ", ".join(
            driving_forces["indifferent_cluster"]
        )

        return (
            f"Primary Driving Forces: {primary}.\n"
            f"Situational Driving Forces: {situational}.\n"
            f"Indifferent Driving Forces: {indifferent}."
        )

    def get_eq_scores(self) -> str:
        """
        Return exact Emotional Intelligence scores.
        """

        eq = self.data["eq"]
        scores = eq["scores"]

        return (
            f"Your Emotional Intelligence scores are:\n"
            f"- Self-Awareness: {format_score(scores['self_awareness'])}\n"
            f"- Self-Regulation: {format_score(scores['self_regulation'])}\n"
            f"- Motivation: {format_score(scores['motivation'])}\n"
            f"- Social Awareness: {format_score(scores['social_awareness'])}\n"
            f"- Social Regulation: {format_score(scores['social_regulation'])}\n"
            f"- SELF Composite: {format_score(eq['self_composite'])}\n"
            f"- OTHERS Composite: {format_score(eq['others_composite'])}\n"
            f"- TOTAL EQ: {format_score(eq['total_eq'])}"
        )

    def get_integrated_analysis(self) -> str:
        """
        Return the approved deterministic integrated analysis.
        """

        integrated = self.data["integrated"]

        lines = [
            f"Your Integrated Analysis",
            "",
            integrated["overview"],
            "",
            "Combined Strengths:",
        ]

        for strength in integrated["strengths"]:
            lines.append(
                f"- {strength}"
            )

        lines.append("")
        lines.append(
            "Potential Development Areas:"
        )

        for area in integrated["development_areas"]:
            lines.append(
                f"- {area}"
            )

        lines.append("")
        lines.append(
            "Workplace Applications:" if self.experience.business else "Family Applications:"
        )

        for application in integrated[
            "family_applications"
        ]:
            lines.append(
                f"- {application}"
            )

        lines.append("")
        lines.append(
            integrated["closing_summary"]
        )

        return "\n".join(lines)

    def get_current_state(self) -> DebriefState:
        """
        Return the current debrief state.
        """

        return self.current_state


    def get_current_content(self) -> str:
        """
        Return the deterministic content associated with
        the current debrief state.
        """

        state_handlers = {
            # New States
            DebriefState.DISC_NARRATIVE:
                self.get_disc_narrative,

            DebriefState.DRIVING_FORCES_NARRATIVE:
                self.get_driving_forces_narrative,

            DebriefState.EQ_NARRATIVE:
                self.get_eq_narrative,

            DebriefState.INTEGRATED_NARRATIVE:
                self.get_integrated_narrative,
                
            # OLD - FOR DEV TESTING - DON'T TOUCH!
            DebriefState.INTRODUCTION:
                self.get_introduction,

            DebriefState.DISC_SCORES:
                self.get_disc_scores,

            DebriefState.DISC_STYLE:
                self.get_primary_disc_style,

            DebriefState.BEHAVIORAL_CHARACTERISTICS:
                self.get_behavioral_characteristics,

            DebriefState.VALUE_TO_FAMILY:
                self.get_value_to_family,

            DebriefState.DRIVING_FORCES_SCORES:
                self.get_driving_force_scores,

            DebriefState.DRIVING_FORCES_CLUSTERS:
                self.get_driving_force_clusters,

            DebriefState.EQ_SCORES:
                self.get_eq_scores,

            DebriefState.INTEGRATED_ANALYSIS:
                self.get_integrated_analysis,
        }

        if self.current_state == DebriefState.COMPLETE:
            return self.get_conclusion()

        handler = state_handlers.get(
            self.current_state
        )

        if handler is None:
            raise RuntimeError(
                f"No content handler exists for state: "
                f"{self.current_state}"
            )

        return handler()


    def advance(self) -> DebriefState:
        """
        Advance the debrief to the next approved state.

        Returns:
            The new current state.
        """

        current_index = DEBRIEF_SEQUENCE.index(
            self.current_state
        )

        if self.interaction_mode == InteractionMode.QUESTION:
                raise RuntimeError(
                    "Cannot advance the debrief while in question mode."
                )
            
        if (
            self.current_state
            == DebriefState.COMPLETE
        ):
            return self.current_state

        self.current_state = DEBRIEF_SEQUENCE[
            current_index + 1
        ]

        return self.current_state


    def reset(self) -> None:
        """
        Reset the current person's debrief to the beginning.
        """

        self.current_state = DebriefState.INTRODUCTION
        self.interaction_mode = InteractionMode.DEBRIEF
        self.paused_state = None

    def switch_persona(
        self,
        persona_path: str | Path,
    ) -> None:
        """
        Hot-swap the active person.

        The same engine instance can load another valid XQ persona
        without restarting the application.
        """

        new_path = Path(persona_path)

        # Preserve the current persona if the new file fails validation.
        old_path = self.persona_path
        old_data = self.data

        try:
            self.persona_path = new_path
            self.data = self._load_persona()

        except Exception:
            self.persona_path = old_path
            self.data = old_data
            raise

        # Reset debrief progress for the newly loaded person.
        self.current_state = DebriefState.INTRODUCTION
        self.interaction_mode = InteractionMode.DEBRIEF
        self.paused_state = None
        
    def get_interaction_mode(self) -> InteractionMode:
        """
        Return the current interaction mode.
        """

        return self.interaction_mode


    def get_conclusion(self) -> str:
        context = "workplace" if self.experience.business else "family"
        return (
            f"Thank you, {self.display_name}, for taking time to explore your {context} insights. "
            "Your debrief is complete. Take a moment to consider one insight you would like to put into practice. "
            "If you have questions, type one in the question box and select Ask your guide. "
            "To ask aloud, select Enter Question Mode, then use Record a question if it is available. "
            "To start again, open Conversation options and select Restart the debrief. "
            "Thank you for joining us."
        )

    def enter_question_mode(self) -> None:
        """
        Pause the debrief at the current state
        and enter question mode.
        """

        if self.interaction_mode == InteractionMode.QUESTION:
            return

        self.paused_state = self.current_state

        self.interaction_mode = InteractionMode.QUESTION


    def exit_question_mode(self) -> None:
        """
        Exit question mode and return to the
        state where the interruption occurred.
        """

        if self.interaction_mode != InteractionMode.QUESTION:
            return

        if self.paused_state is not None:
            self.current_state = self.paused_state

        self.paused_state = None

        self.interaction_mode = InteractionMode.DEBRIEF


    def answer_question(
        self,
        question: str,
    ) -> str:

        cleaned_question = question.strip()

        if not cleaned_question:
            return "No question was provided."

        # -----------------------------------
        # PRE-GENERATION GUARDRAIL
        # -----------------------------------

        guardrail_result = check_question_guardrails(
            cleaned_question
        )

        if not guardrail_result.allowed:
            return (
                guardrail_result.response
                or
                "This question cannot be answered "
                "within the scope of the assessment."
            )

        # -----------------------------------
        # GPT REASONING
        # -----------------------------------

        reasoning_result = self.ai_reasoner.answer_question(
            question=cleaned_question,
            state=self.current_state,
            persona_data=self.data,
        )

        # -----------------------------------
        # POST-GENERATION VALIDATION
        # -----------------------------------

        validation = validate_ai_response(
            response=reasoning_result.response,
            resolved_domain=ContextDomain(
                    reasoning_result.resolved_domain
            ),
            persona_data=self.data,
        )

        if not validation.valid:

            print()
            print("[RESPONSE BLOCKED BY VALIDATOR]")

            for issue in validation.issues:
                print(f"- {issue}")

            return (
                "I can't provide that response because it did "
                "not pass the XQ response validation rules. "
                "Let's keep the answer limited to the verified "
                "assessment information available in this section."
            )

        return reasoning_result.response
#--------------------------------------------------------------------
# !!!! DO NOT REMOVE ANYTHING BEFORE THIS POINT, ONLY EDIT BELOW !!!!
#--------------------------------------------------------------------
    #DISC
    def get_disc_narrative(self) -> str:
        return render_disc_narrative(
            self.data, experience=self.experience.name
        )

    #12DF
    def get_driving_forces_narrative(
            self,
    ) -> str:
        return render_driving_forces_narrative(
            self.data, experience=self.experience.name
        )

    #EQ
    def get_eq_narrative(
            self,
    ) -> str:
        return render_eq_narrative(
            self.data, experience=self.experience.name
        )

    #Integrated
    def get_integrated_narrative(
            self,
    ) -> str:
        return render_integrated_narrative(
            self.data, experience=self.experience.name
        )
