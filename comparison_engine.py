from copy import deepcopy
from typing import Any

from schemas import validate_persona


class ComparisonEngine:
    """
    Creates deterministic, factual comparison packets
    from two validated persona records.
    """

    def compare_personas(
        self,
        persona_a: dict[str, Any],
        persona_b: dict[str, Any],
    ) -> dict[str, Any]:

        validate_persona(persona_a)
        validate_persona(persona_b)

        person_a = persona_a["person"]
        person_b = persona_b["person"]

        if person_a["person_id"] == person_b["person_id"]:
            raise ValueError(
                "A comparison requires two different people."
            )

        return {
            "people": {
                "person_a": {
                    "person_id": person_a["person_id"],
                    "display_name": person_a["display_name"],
                    "family_role": person_a["family_role"],
                },
                "person_b": {
                    "person_id": person_b["person_id"],
                    "display_name": person_b["display_name"],
                    "family_role": person_b["family_role"],
                },
            },
            "disc": self._compare_disc(
                persona_a["disc"],
                persona_b["disc"],
            ),
            "driving_forces": self._compare_driving_forces(
                persona_a["driving_forces"],
                persona_b["driving_forces"],
            ),
            "eq": self._compare_eq(
                persona_a["eq"],
                persona_b["eq"],
            ),
        }

    def _compare_score_sets(
        self,
        scores_a: dict[str, int | float],
        scores_b: dict[str, int | float],
    ) -> dict[str, dict[str, int | float | str]]:

        if set(scores_a.keys()) != set(scores_b.keys()):
            raise ValueError(
                "Comparison score sets must contain identical keys."
            )

        comparison: dict[
            str,
            dict[str, int | float | str],
        ] = {}

        for score_name in scores_a:
            value_a = scores_a[score_name]
            value_b = scores_b[score_name]
            difference = value_a - value_b

            if difference > 0:
                higher = "person_a"
            elif difference < 0:
                higher = "person_b"
            else:
                higher = "equal"

            comparison[score_name] = {
                "person_a": value_a,
                "person_b": value_b,
                "difference_a_minus_b": difference,
                "higher": higher,
            }

        return comparison

    def _compare_disc(
        self,
        disc_a: dict[str, Any],
        disc_b: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            "primary_styles": {
                "person_a": disc_a["primary_style"],
                "person_b": disc_b["primary_style"],
                "same_style": (
                    disc_a["primary_style"]
                    == disc_b["primary_style"]
                ),
            },
            "natural": self._compare_score_sets(
                disc_a["natural"],
                disc_b["natural"],
            ),
            "adapted": self._compare_score_sets(
                disc_a["adapted"],
                disc_b["adapted"],
            ),
        }

    def _compare_driving_forces(
        self,
        forces_a: dict[str, Any],
        forces_b: dict[str, Any],
    ) -> dict[str, Any]:

        return {
            "scores": self._compare_score_sets(
                forces_a["scores"],
                forces_b["scores"],
            ),
            "primary_clusters": {
                "person_a": list(
                    forces_a.get("primary_cluster", [])
                ),
                "person_b": list(
                    forces_b.get("primary_cluster", [])
                ),
                "shared": sorted(
                    set(
                        forces_a.get(
                            "primary_cluster",
                            [],
                        )
                    )
                    & set(
                        forces_b.get(
                            "primary_cluster",
                            [],
                        )
                    )
                ),
            },
        }

    def _compare_eq(
        self,
        eq_a: dict[str, Any],
        eq_b: dict[str, Any],
    ) -> dict[str, Any]:

        composites_a = {
            "SELF": eq_a["self_composite"],
            "OTHERS": eq_a["others_composite"],
            "TOTAL_EQ": eq_a["total_eq"],
        }

        composites_b = {
            "SELF": eq_b["self_composite"],
            "OTHERS": eq_b["others_composite"],
            "TOTAL_EQ": eq_b["total_eq"],
        }

        return {
            "dimensions": self._compare_score_sets(
                eq_a["scores"],
                eq_b["scores"],
            ),
            "composites": self._compare_score_sets(
                composites_a,
                composites_b,
            ),
        }

    def create_detached_packet(
        self,
        persona_a: dict[str, Any],
        persona_b: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Return a fully detached comparison packet.
        """

        return deepcopy(
            self.compare_personas(
                persona_a,
                persona_b,
            )
        )