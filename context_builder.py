import json
from pathlib import Path
from typing import Any

from context_router import (
    ContextDomain,
    ContextRoute,
    ContextTopic,
)


from narratives.score_wording import RANGE_POLICY, score_wording


class ContextBuilder:

    def __init__(
        self,
        knowledge_dir: str | Path = "knowledge",
    ) -> None:

        self.knowledge_dir = Path(knowledge_dir)

        self.disc_knowledge = self._load_json(
            self.knowledge_dir
            / "disc_knowledge.json"
        )

        self.driving_forces_knowledge = self._load_json(
            self.knowledge_dir
            / "driving_forces_knowledge.json"
        )

        self.eq_knowledge = self._load_json(
            self.knowledge_dir
            / "eq_knowledge.json"
        )

    def _load_json(
        self,
        path: Path,
    ) -> dict[str, Any]:

        with path.open(
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    def build_context(
        self,
        route: ContextRoute,
        resolved_domain: ContextDomain,
        persona_data: dict[str, Any],
    ) -> dict[str, Any]:

        person = persona_data["person"]

        context: dict[str, Any] = {
            "person": {
                "display_name": person[
                    "display_name"
                ],
                "family_role": person[
                    "family_role"
                ],
            },
            "route": {
                "domain": resolved_domain.value,
                "topic": route.topic.value,
                "matched_terms": route.matched_terms,
            },
        }

        if resolved_domain == ContextDomain.DISC:

            context["disc"] = (
                self._build_disc_context(
                    route=route,
                    persona_data=persona_data,
                )
            )

        elif (
            resolved_domain
            == ContextDomain.DRIVING_FORCES
        ):

            context["driving_forces"] = (
                self._build_driving_forces_context(
                    route=route,
                    persona_data=persona_data,
                )
            )

        elif resolved_domain == ContextDomain.EQ:

            context["eq"] = (
                self._build_eq_context(
                    route=route,
                    persona_data=persona_data,
                )
            )

        elif resolved_domain == ContextDomain.INTEGRATED:

            context["integrated"] = (
                self._build_integrated_context(
                    persona_data=persona_data,
                )
            )

        else:

            context["general"] = (
                "No assessment domain could be "
                "confidently resolved."
            )

        wording = score_wording(persona_data, resolved_domain.value)
        if wording:
            context["score_range_wording"] = wording
            context["score_range_policy"] = RANGE_POLICY
        return context

    def _build_disc_context(
        self,
        route: ContextRoute,
        persona_data: dict[str, Any],
    ) -> dict[str, Any]:

        disc = persona_data["disc"]

        primary_style = disc["primary_style"]

        style_knowledge = (
            self.disc_knowledge[
                "styles"
            ].get(
                primary_style,
                {},
            )
        )

        context: dict[str, Any] = {
            "primary_style": primary_style,
        }

        if route.topic == ContextTopic.SCORES:

            context["natural"] = disc["natural"]
            context["adapted"] = disc["adapted"]

        elif route.topic == ContextTopic.COMMUNICATION:

            context["communication_do"] = (
                disc.get(
                    "communication_do",
                    [],
                )
            )

            context["communication_dont"] = (
                disc.get(
                    "communication_dont",
                    [],
                )
            )

            context[
                "approved_style_definition"
            ] = style_knowledge.get(
                "definition"
            )

            context[
                "approved_communication_guidance"
            ] = style_knowledge.get(
                "communication_guidance",
                {},
            )

        elif route.topic == ContextTopic.STRENGTHS:

            context[
                "behavioral_characteristics"
            ] = disc.get(
                "behavioral_characteristics",
                [],
            )

            context[
                "value_to_family"
            ] = disc.get(
                "value_to_family",
                [],
            )

            context[
                "approved_potential_strengths"
            ] = style_knowledge.get(
                "potential_strengths",
                [],
            )

        elif route.topic == ContextTopic.DEVELOPMENT:

            context[
                "approved_potential_challenges"
            ] = style_knowledge.get(
                "potential_challenges",
                [],
            )

        else:

            context["natural"] = disc["natural"]
            context["adapted"] = disc["adapted"]

            context[
                "approved_style_definition"
            ] = style_knowledge.get(
                "definition"
            )

            context[
                "behavioral_characteristics"
            ] = disc.get(
                "behavioral_characteristics",
                [],
            )

        return context

    def _build_driving_forces_context(
        self,
        route: ContextRoute,
        persona_data: dict[str, Any],
    ) -> dict[str, Any]:

        forces = persona_data[
            "driving_forces"
        ]

        context: dict[str, Any] = {}

        matched_force_names: list[str] = []

        approved_forces = (
            self.driving_forces_knowledge[
                "forces"
            ]
        )

        for force_name in approved_forces:

            if any(
                force_name.lower()
                == matched.lower()
                for matched in route.matched_terms
            ):
                matched_force_names.append(
                    force_name
                )

        if matched_force_names:

            context[
                "matched_forces"
            ] = {}

            for force_name in matched_force_names:

                context[
                    "matched_forces"
                ][
                    force_name
                ] = {
                    "score": forces[
                        "scores"
                    ].get(
                        force_name
                    ),
                    "approved_knowledge": (
                        approved_forces[
                            force_name
                        ]
                    ),
                }

        if route.topic == ContextTopic.SCORES:

            context[
                "scores"
            ] = forces["scores"]

        elif route.topic == ContextTopic.ENERGIZERS:

            context[
                "person_energizers"
            ] = forces.get(
                "energizers",
                [],
            )

        elif route.topic == ContextTopic.STRESSORS:

            context[
                "person_stressors"
            ] = forces.get(
                "stressors",
                [],
            )

        elif route.topic == ContextTopic.STRENGTHS:

            context[
                "motivational_strengths"
            ] = forces.get(
                "motivational_strengths",
                [],
            )

        elif route.topic == ContextTopic.CONFLICTS:

            context[
                "primary_cluster"
            ] = forces.get(
                "primary_cluster",
                [],
            )

            context[
                "situational_cluster"
            ] = forces.get(
                "situational_cluster",
                [],
            )

        else:

            context[
                "primary_cluster"
            ] = forces.get(
                "primary_cluster",
                [],
            )

            context[
                "situational_cluster"
            ] = forces.get(
                "situational_cluster",
                [],
            )

            context[
                "indifferent_cluster"
            ] = forces.get(
                "indifferent_cluster",
                [],
            )

        return context

    def _build_eq_context(
        self,
        route: ContextRoute,
        persona_data: dict[str, Any],
    ) -> dict[str, Any]:

        eq = persona_data["eq"]

        context: dict[str, Any] = {}

        approved_dimensions = (
            self.eq_knowledge[
                "dimensions"
            ]
        )

        matched_dimensions: list[str] = []

        normalized_matches = {
            match.lower().replace(
                "-",
                " ",
            )
            for match in route.matched_terms
        }

        for (
            dimension_key,
            dimension_data,
        ) in approved_dimensions.items():

            display_name = (
                dimension_data[
                    "display_name"
                ]
                .lower()
                .replace(
                    "-",
                    " ",
                )
            )

            if display_name in normalized_matches:

                matched_dimensions.append(
                    dimension_key
                )

        if matched_dimensions:

            context[
                "matched_dimensions"
            ] = {}

            for dimension_key in matched_dimensions:

                context[
                    "matched_dimensions"
                ][
                    dimension_key
                ] = {
                    "score": eq[
                        "scores"
                    ].get(
                        dimension_key
                    ),
                    "approved_knowledge": (
                        approved_dimensions[
                            dimension_key
                        ]
                    ),
                }

        if route.topic == ContextTopic.SCORES:

            context["scores"] = eq["scores"]

            context[
                "self_composite"
            ] = eq["self_composite"]

            context[
                "others_composite"
            ] = eq["others_composite"]

            context[
                "total_eq"
            ] = eq["total_eq"]

        else:

            context[
                "scores"
            ] = eq["scores"]

        context[
            "interpretation_rules"
        ] = self.eq_knowledge.get(
            "interpretation_rules",
            {},
        )

        return context

    def _build_integrated_context(
            self,
            persona_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Build a controlled multi-domain context packet using
        verified persona data and the approved stored synthesis.
        """

        disc = persona_data["disc"]

        driving_forces = persona_data["driving_forces"]

        eq = persona_data["eq"]

        integrated = persona_data["integrated"]

        primary_style = disc["primary_style"]

        style_knowledge = (
            self.disc_knowledge[
                "styles"
            ].get(
                primary_style,
                {},
            )
        )

        primary_force_knowledge: dict[
            str,
            Any,
        ] = {}

        approved_forces = (
            self.driving_forces_knowledge[
                "forces"
            ]
        )

        for force_name in driving_forces[
            "primary_cluster"
        ]:
            if force_name in approved_forces:
                primary_force_knowledge[
                    force_name
                ] = approved_forces[
                    force_name
                ]

        return {
            "disc": {
                "natural": disc["natural"],
                "adapted": disc["adapted"],
                "primary_style": primary_style,
                "behavioral_characteristics": (
                    disc.get(
                        "behavioral_characteristics",
                        [],
                    )
                ),
                "value_to_family": disc.get(
                    "value_to_family",
                    [],
                ),
                "communication_do": disc.get(
                    "communication_do",
                    [],
                ),
                "communication_dont": disc.get(
                    "communication_dont",
                    [],
                ),
                "approved_style_definition": (
                    style_knowledge.get(
                        "definition"
                    )
                ),
            },
            "driving_forces": {
                "scores": driving_forces[
                    "scores"
                ],
                "primary_cluster": (
                    driving_forces[
                        "primary_cluster"
                    ]
                ),
                "situational_cluster": (
                    driving_forces[
                        "situational_cluster"
                    ]
                ),
                "motivational_strengths": (
                    driving_forces.get(
                        "motivational_strengths",
                        [],
                    )
                ),
                "energizers": (
                    driving_forces.get(
                        "energizers",
                        [],
                    )
                ),
                "stressors": (
                    driving_forces.get(
                        "stressors",
                        [],
                    )
                ),
                "approved_primary_force_knowledge": (
                    primary_force_knowledge
                ),
            },
            "eq": {
                "scores": eq["scores"],
                "self_composite": (
                    eq["self_composite"]
                ),
                "others_composite": (
                    eq["others_composite"]
                ),
                "total_eq": eq["total_eq"],
                "interpretation_rules": (
                    self.eq_knowledge.get(
                        "interpretation_rules",
                        {},
                    )
                ),
            },
            "approved_integrated_analysis": (
                integrated
            ),
            "interpretation_boundary": (
                "The stored integrated analysis is the approved "
                "anchor. Use exact assessment facts and cautious "
                "interpretation only. Do not invent new traits, "
                "motives, diagnoses, or relationship outcomes."
            ),
        }
