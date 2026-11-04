import unittest
from dataclasses import replace
from unittest.mock import patch

from mhwilds_optimizer.constraints import (
    SolveStatus,
    solve_feasible_build,
)
from mhwilds_optimizer.equipment_models import (
    ArmorPart,
    Decoration,
    RequirementKind,
    SkillRequirement,
    SlotType,
)
from tests.equipment_fixtures import make_tiny_catalog


class FeasibilitySolverTests(unittest.TestCase):
    def test_reconstructs_the_unique_legal_build_and_capped_skill_levels(self) -> None:
        catalog = make_tiny_catalog()
        catalog = replace(catalog, charms=(catalog.charms[0],))

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:attack", RequirementKind.EXACT, 3),),
        )

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        self.assertIsNone(result.message)
        self.assertIsNotNone(result.build)
        build = result.build
        assert build is not None
        self.assertEqual(set(build.armor_ids), set(ArmorPart))
        self.assertEqual(build.armor_ids[ArmorPart.HEAD], "armor:offense:head")
        self.assertEqual(build.charm_id, "regular_charm:attack")
        self.assertEqual(
            [
                (item.owner_id, item.slot_index, item.decoration_id)
                for item in build.decorations
            ],
            [("armor:offense:head", 0, "decoration:attack")],
        )
        self.assertEqual(build.granted_skill_levels, {"skill:attack": 3})
        self.assertEqual(build.effective_skill_levels, {"skill:attack": 3})
        self.assertNotIn("skill:weapon", build.effective_skill_levels)

    def test_caps_effective_levels_but_preserves_granted_levels(self) -> None:
        catalog = make_tiny_catalog()
        forced_armor = (catalog.armor[1],) + tuple(
            replace(piece, skills={"skill:attack": 1}) for piece in catalog.armor[2:]
        )
        catalog = replace(
            catalog,
            armor=forced_armor,
            decorations=(),
            charms=(replace(catalog.charms[1], slots=()),),
        )
        requirement = SkillRequirement("skill:attack", RequirementKind.EXACT, 3)

        result = solve_feasible_build(catalog, (requirement,))

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        assert result.build is not None
        self.assertEqual(result.build.granted_skill_levels["skill:attack"], 4)
        self.assertEqual(result.build.effective_skill_levels["skill:attack"], 3)

    def test_returns_infeasible_when_an_armor_part_has_no_candidate(self) -> None:
        catalog = make_tiny_catalog()
        catalog = replace(
            catalog,
            armor=tuple(piece for piece in catalog.armor if piece.part is not ArmorPart.LEGS),
        )

        result = solve_feasible_build(catalog, ())

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)
        self.assertIsNone(result.build)

    def test_returns_infeasible_when_no_regular_charm_exists(self) -> None:
        catalog = replace(make_tiny_catalog(), charms=())

        result = solve_feasible_build(catalog, ())

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)
        self.assertIsNone(result.build)

    def test_returns_infeasible_for_an_impossible_minimum(self) -> None:
        catalog = make_tiny_catalog()

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:critical", RequirementKind.MINIMUM, 2),),
        )

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)

    def test_does_not_place_a_large_decoration_in_a_small_slot(self) -> None:
        catalog = make_tiny_catalog()
        critical_head = catalog.armor[1]
        catalog = replace(
            catalog,
            armor=(critical_head,) + catalog.armor[2:],
            decorations=(
                Decoration(
                    "decoration:critical",
                    SlotType.ARMOR,
                    2,
                    {"skill:critical": 1},
                ),
            ),
            charms=(catalog.charms[0],),
        )

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:critical", RequirementKind.MINIMUM, 2),),
        )

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)

    def test_returns_infeasible_when_a_forbidden_skill_is_unavoidable(self) -> None:
        catalog = make_tiny_catalog()
        chest = replace(catalog.armor[2], skills={"skill:attack": 1})
        catalog = replace(catalog, armor=catalog.armor[:2] + (chest,) + catalog.armor[3:])

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:attack", RequirementKind.FORBIDDEN),),
        )

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)

    def test_reports_model_initialization_failure_as_error(self) -> None:
        with patch(
            "mhwilds_optimizer.constraints.Model",
            side_effect=RuntimeError("initialization failed"),
        ):
            result = solve_feasible_build(make_tiny_catalog(), ())

        self.assertEqual(result.status, SolveStatus.ERROR)
        self.assertIsNone(result.build)
        self.assertIn("initialization failed", result.message or "")

    def test_reports_optimization_failure_as_error(self) -> None:
        with patch(
            "mhwilds_optimizer.constraints.Model.optimize",
            side_effect=RuntimeError("optimization failed"),
        ):
            result = solve_feasible_build(make_tiny_catalog(), ())

        self.assertEqual(result.status, SolveStatus.ERROR)
        self.assertIsNone(result.build)
        self.assertIn("optimization failed", result.message or "")


if __name__ == "__main__":
    unittest.main()
