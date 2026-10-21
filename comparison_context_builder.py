import json
from pathlib import Path
from typing import Any

from context_router import ContextDomain
from knowledge_schema import validate_all_knowledge


class ComparisonContextBuilder:
    """
    Combines deterministic comparison facts with approved XQ knowledge.

    This component does not generate relationship conclusions.
    """

    def __init__(
        self,
        knowledge_dir: str | Path = "knowledge",
    ) -> None:
        self.knowledge_dir = Path(knowledge_dir)

        validate_all_knowledge(
            self.knowledge_dir
        )

        self.disc_knowledge = self._load_json(
            self.knowledge_dir / "disc_knowledge.json"
        )

        self.driving_forces_knowledge = self._load_json(
            self.knowledge_dir
            / "driving_forces_knowledge.json"
        )

        self.eq_knowledge = self._load_json(
            self.knowledge_dir / "eq_knowledge.json"
        )

    def _load_json(
        self,
        path: Path,
    ) -> dict[str, Any]:
        with path.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                f"Knowledge file must contain an object: {path}"
            )

        return data

    def build_context(
        self,
        comparison: dict[str, Any],
        domain: ContextDomain,
        included_domains: (
            list[ContextDomain] | None
        ) = None,
    ) -> dict[str, Any]:

        resolved_included_domains = (
            included_domains
            if included_domains is not None
            else [domain]
        )
        
        context: dict[str, Any] = {
            "people": comparison["people"],
            "domain": domain.value,
            "included_domains": [
                included_domain.value
                for included_domain
                in resolved_included_domains
            ],
            "interpretation_boundary": (
                "Score differences are verified comparison facts. "
                "They do not independently prove compatibility, "
                "conflict, intent, superiority, or relationship outcomes."
            ),
        }

        if domain == ContextDomain.DISC:
            context["disc"] = self._build_disc_context(
                comparison["disc"]
            )

        elif domain == ContextDomain.DRIVING_FORCES:
            context["driving_forces"] = (
                self._build_driving_forces_context(
                    comparison["driving_forces"]
                )
            )

        elif domain == ContextDomain.EQ:
            context["eq"] = self._build_eq_context(
                comparison["eq"]
            )

        elif domain == ContextDomain.INTEGRATED:
            context["integrated"] = (
                self._build_integrated_context(
                    comparison=comparison,
                    included_domains=(
                        resolved_included_domains
                    ),
                )
            )

        else:
            context["general"] = (
                "No comparison domain was selected."
            )

        return context

    def _build_disc_context(
        self,
        disc_comparison: dict[str, Any],
    ) -> dict[str, Any]:
        styles = disc_comparison["primary_styles"]

        style_a = styles["person_a"]
        style_b = styles["person_b"]

        approved_styles = self.disc_knowledge["styles"]

        dimensions: dict[str, Any] = {}

        for code in ("D", "I", "S", "C"):
            dimensions[code] = {
                "approved_knowledge": (
                    self.disc_knowledge[
                        "dimensions"
                    ][code]
                ),
                "natural_comparison": (
                    disc_comparison[
                        "natural"
                    ][code]
                ),
                "adapted_comparison": (
                    disc_comparison[
                        "adapted"
                    ][code]
                ),
            }

        return {
            "primary_styles": {
                "person_a": {
                    "name": style_a,
                    "approved_knowledge": approved_styles[
                        style_a
                    ],
                },
                "person_b": {
                    "name": style_b,
                    "approved_knowledge": approved_styles[
                        style_b
                    ],
                },
                "same_style": styles["same_style"],
            },
            "dimensions": dimensions,
            "interpretation_rules": [
                (
                    "A higher DISC score does not mean a person "
                    "is better, healthier, or more capable."
                ),
                (
                    "Differences may reflect different behavioral "
                    "preferences, pace, communication, or responses "
                    "to the environment."
                ),
                (
                    "Do not infer motive, diagnosis, or relationship "
                    "quality from DISC differences alone."
                ),
            ],
        }

    def _build_driving_forces_context(
        self,
        forces_comparison: dict[str, Any],
    ) -> dict[str, Any]:
        approved_forces = self.driving_forces_knowledge[
            "forces"
        ]

        scores: dict[str, Any] = {}

        for force_name, comparison in (
            forces_comparison["scores"].items()
        ):
            scores[force_name] = {
                "comparison": comparison,
                "approved_knowledge": approved_forces[
                    force_name
                ],
            }

        primary_clusters = forces_comparison[
            "primary_clusters"
        ]

        relevant_force_names = sorted(
            set(primary_clusters["person_a"])
            | set(primary_clusters["person_b"])
        )

        primary_knowledge = {
            force_name: approved_forces[force_name]
            for force_name in relevant_force_names
        }

        return {
            "scores": scores,
            "primary_clusters": primary_clusters,
            "primary_force_knowledge": primary_knowledge,
            "cluster_definitions": (
                self.driving_forces_knowledge[
                    "cluster_definitions"
                ]
            ),
            "interpretation_rules": [
                (
                    "Different Driving Forces reflect different "
                    "sources of motivation, not greater or lesser worth."
                ),
                (
                    "A score gap does not independently prove "
                    "conflict or incompatibility."
                ),
                (
                    "Shared primary forces may indicate similar "
                    "motivational priorities, but not identical behavior."
                ),
            ],
        }

    def _build_eq_context(
        self,
        eq_comparison: dict[str, Any],
    ) -> dict[str, Any]:
        approved_dimensions = self.eq_knowledge[
            "dimensions"
        ]

        dimensions: dict[str, Any] = {}

        for dimension_name, comparison in (
            eq_comparison["dimensions"].items()
        ):
            dimensions[dimension_name] = {
                "comparison": comparison,
                "approved_knowledge": (
                    approved_dimensions[
                        dimension_name
                    ]
                ),
            }

        composites: dict[str, Any] = {}

        for composite_name, comparison in (
            eq_comparison["composites"].items()
        ):
            composites[composite_name] = {
                "comparison": comparison,
                "approved_knowledge": (
                    self.eq_knowledge[
                        "composites"
                    ][composite_name]
                ),
            }

        return {
            "dimensions": dimensions,
            "composites": composites,
            "interpretation_rules": (
                self.eq_knowledge[
                    "interpretation_rules"
                ]
            ),
            "comparison_boundaries": [
                (
                    "A higher EQ score does not prove that one "
                    "person is emotionally healthier or more mature."
                ),
                (
                    "EQ results must not be used to diagnose "
                    "psychological, psychiatric, medical, or "
                    "developmental conditions."
                ),
                (
                    "Differences may identify areas for discussion, "
                    "adaptation, or development, but do not determine "
                    "relationship outcomes."
                ),
            ],
        }

    def _build_integrated_context(
        self,
        comparison: dict[str, Any],
        included_domains: list[ContextDomain],
    ) -> dict[str, Any]:
        """
        Build a controlled multi-domain comparison packet.
        """

        integrated: dict[str, Any] = {
            "included_domains": [
                domain.value
                for domain in included_domains
            ],
            "interpretation_rules": [
                (
                    "Use only the assessment domains included "
                    "in this packet."
                ),
                (
                    "Describe possible interactions without "
                    "claiming certainty, compatibility, conflict, "
                    "intent, or relationship outcomes."
                ),
                (
                    "Keep verified score differences separate "
                    "from cautious interpretation."
                ),
            ],
        }

        if ContextDomain.DISC in included_domains:
            integrated["disc"] = (
                self._build_disc_context(
                    comparison["disc"]
                )
            )

        if (
            ContextDomain.DRIVING_FORCES
            in included_domains
        ):
            integrated["driving_forces"] = (
                self._build_driving_forces_context(
                    comparison[
                        "driving_forces"
                    ]
                )
            )

        if ContextDomain.EQ in included_domains:
            integrated["eq"] = (
                self._build_eq_context(
                    comparison["eq"]
                )
            )

        return integrated