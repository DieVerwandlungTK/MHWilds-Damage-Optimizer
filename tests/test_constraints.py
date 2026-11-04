import unittest
from dataclasses import replace
from decimal import Decimal
from itertools import product
from unittest.mock import patch

from mip import Model

from mhwilds_optimizer.constraints import (
    EnumerationResult,
    SolveStatus,
    enumerate_feasible_builds,
    solve_feasible_build,
)
from mhwilds_optimizer.equipment_models import (
    ArmorBonus,
    ArmorPart,
    BonusRank,
    Decoration,
    EquipmentCatalog,
    EquipmentInputError,
    FeasibleBuild,
    RequirementKind,
    SkillDefinition,
    SkillKind,
    SkillRequirement,
    SlotType,
)
from mhwilds_optimizer.damage_models import Sharpness
from mhwilds_optimizer.weapon_models import ElementType, Weapon
from tests.equipment_fixtures import make_tiny_catalog


BuildSignature = tuple[
    tuple[tuple[str, str], ...],
    str,
    tuple[tuple[str, int, str], ...],
]


def manual_weapon(
    *,
    identifier: str = "weapon:test",
    skills: dict[str, int] | None = None,
    slots: tuple[int, ...] = (),
) -> Weapon:
    return Weapon(
        id=identifier,
        name="Test Blades",
        raw=Decimal("200"),
        element_type=ElementType.NONE,
        element=Decimal("0"),
        affinity_percent=Decimal("0"),
        sharpness=Sharpness.WHITE,
        slots=slots,
        skills=skills or {},
    )


def with_bonus_tags(
    catalog: EquipmentCatalog,
    *,
    set_ids: set[str] | None = None,
    group_ids: set[str] | None = None,
) -> EquipmentCatalog:
    set_bonus = ArmorBonus(
        "skill:set", (BonusRank(2, 1), BonusRank(4, 2))
    )
    group_bonus = ArmorBonus("skill:group", (BonusRank(3, 1),))
    return replace(
        catalog,
        armor=tuple(
            replace(
                piece,
                set_bonus=set_bonus if piece.id in (set_ids or ()) else None,
                group_bonus=group_bonus if piece.id in (group_ids or ()) else None,
            )
            for piece in catalog.armor
        ),
    )


def build_signature(build: FeasibleBuild) -> BuildSignature:
    return (
        tuple(sorted((part.value, identifier) for part, identifier in build.armor_ids.items())),
        build.charm_id,
        tuple(
            sorted(
                (item.owner_id, item.slot_index, item.decoration_id)
                for item in build.decorations
            )
        ),
    )


def requirements_satisfied(
    levels: dict[str, int],
    requirements: tuple[SkillRequirement, ...],
    maximums: dict[str, int],
) -> bool:
    for requirement in requirements:
        granted = levels.get(requirement.skill_id, 0)
        if requirement.kind is RequirementKind.FORBIDDEN:
            if granted != 0:
                return False
        elif requirement.kind is RequirementKind.MINIMUM:
            if granted < (requirement.level or 0):
                return False
        elif requirement.level == maximums[requirement.skill_id]:
            if granted < (requirement.level or 0):
                return False
        elif granted != requirement.level:
            return False
    return True


def exhaustive_signatures(
    catalog: EquipmentCatalog,
    requirements: tuple[SkillRequirement, ...],
) -> set[BuildSignature]:
    armor_by_part = [
        tuple(piece for piece in catalog.armor if piece.part is part)
        for part in ArmorPart
    ]
    armor_decorations = tuple(
        item for item in catalog.decorations if item.slot_type is SlotType.ARMOR
    )
    maximums = {skill.id: skill.max_level for skill in catalog.skills}
    result: set[BuildSignature] = set()
    for armor_choice in product(*armor_by_part):
        for charm in catalog.charms:
            owners = (*armor_choice, charm)
            slots = [
                (owner.id, index, level)
                for owner in owners
                for index, level in enumerate(owner.slots)
            ]
            slot_options = [
                (None,)
                + tuple(
                    decoration
                    for decoration in armor_decorations
                    if decoration.required_slot_level <= level
                )
                for _, _, level in slots
            ]
            for chosen_decorations in product(*slot_options):
                levels: dict[str, int] = {}
                for item in owners:
                    for skill_id, level in item.skills.items():
                        levels[skill_id] = levels.get(skill_id, 0) + level
                bonus_counts: dict[
                    tuple[str, str], tuple[tuple[BonusRank, ...], int]
                ] = {}
                for piece in armor_choice:
                    for kind, bonus in (
                        ("set", piece.set_bonus),
                        ("group", piece.group_bonus),
                    ):
                        if bonus is None:
                            continue
                        key = (kind, bonus.skill_id)
                        ranks, count = bonus_counts.get(key, (bonus.ranks, 0))
                        bonus_counts[key] = (ranks, count + 1)
                for (_, skill_id), (ranks, count) in bonus_counts.items():
                    reached = [
                        rank.skill_level for rank in ranks if count >= rank.pieces
                    ]
                    if reached:
                        levels[skill_id] = levels.get(skill_id, 0) + max(reached)
                placements: list[tuple[str, int, str]] = []
                for (owner_id, index, _), decoration in zip(
                    slots, chosen_decorations, strict=True
                ):
                    if decoration is None:
                        continue
                    placements.append((owner_id, index, decoration.id))
                    for skill_id, level in decoration.skills.items():
                        levels[skill_id] = levels.get(skill_id, 0) + level
                if not requirements_satisfied(levels, requirements, maximums):
                    continue
                result.add(
                    (
                        tuple(
                            sorted(
                                (piece.part.value, piece.id) for piece in armor_choice
                            )
                        ),
                        charm.id,
                        tuple(sorted(placements)),
                    )
                )
    return result


class FeasibilitySolverTests(unittest.TestCase):
    def test_explicit_absent_weapon_preserves_existing_solver_behavior(self) -> None:
        result = solve_feasible_build(make_tiny_catalog(), (), weapon=None)
        enumerated = enumerate_feasible_builds(
            make_tiny_catalog(), (), limit=1, weapon=None
        )

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        assert result.build is not None
        self.assertIsNone(result.build.weapon_id)
        self.assertEqual(enumerated.status, SolveStatus.FEASIBLE)
        self.assertEqual(len(enumerated.builds), 1)
        self.assertIsNone(enumerated.builds[0].weapon_id)

    def test_fixed_weapon_skill_participates_in_all_requirement_modes(self) -> None:
        catalog = make_tiny_catalog()
        weapon = manual_weapon(skills={"skill:weapon": 1})

        minimum = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:weapon", RequirementKind.MINIMUM, 1),),
            weapon=weapon,
        )
        exact = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:weapon", RequirementKind.EXACT, 1),),
            weapon=weapon,
        )
        forbidden = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:weapon", RequirementKind.FORBIDDEN),),
            weapon=weapon,
        )

        self.assertEqual(minimum.status, SolveStatus.FEASIBLE)
        self.assertEqual(exact.status, SolveStatus.FEASIBLE)
        self.assertEqual(forbidden.status, SolveStatus.INFEASIBLE)
        assert minimum.build is not None
        self.assertEqual(minimum.build.weapon_id, "weapon:test")
        self.assertEqual(minimum.build.granted_skill_levels["skill:weapon"], 1)
        self.assertEqual(minimum.build.effective_skill_levels["skill:weapon"], 1)

    def test_fixed_weapon_skill_changes_exact_below_the_maximum(self) -> None:
        catalog = make_tiny_catalog()
        catalog = replace(
            catalog,
            skills=tuple(
                SkillDefinition(skill.id, skill.kind, 2)
                if skill.id == "skill:weapon"
                else skill
                for skill in catalog.skills
            ),
        )

        exact = SkillRequirement("skill:weapon", RequirementKind.EXACT, 1)
        matching = solve_feasible_build(
            catalog,
            (exact,),
            weapon=manual_weapon(skills={"skill:weapon": 1}),
        )
        exceeded = solve_feasible_build(
            catalog,
            (exact,),
            weapon=manual_weapon(skills={"skill:weapon": 2}),
        )

        self.assertEqual(matching.status, SolveStatus.FEASIBLE)
        self.assertEqual(exceeded.status, SolveStatus.INFEASIBLE)

    def test_rejects_weapon_skills_inconsistent_with_the_catalog(self) -> None:
        catalog = make_tiny_catalog()
        cases = (
            ("unknown", manual_weapon(skills={"skill:missing": 1})),
            ("max_level", manual_weapon(skills={"skill:weapon": 2})),
            ("SkillKind.WEAPON", manual_weapon(skills={"skill:attack": 1})),
            ("SkillKind.WEAPON", manual_weapon(skills={"skill:set": 1})),
            ("SkillKind.WEAPON", manual_weapon(skills={"skill:group": 1})),
        )
        for message, weapon in cases:
            with self.subTest(message=message, skills=weapon.skills):
                with self.assertRaisesRegex(EquipmentInputError, message):
                    solve_feasible_build(catalog, (), weapon=weapon)

    def test_rejects_a_weapon_owner_id_collision(self) -> None:
        catalog = make_tiny_catalog()
        for identifier in (catalog.armor[0].id, catalog.charms[0].id):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(EquipmentInputError, "owner id"):
                    solve_feasible_build(
                        catalog, (), weapon=manual_weapon(identifier=identifier)
                    )

    def test_rejects_a_non_weapon_before_enumeration(self) -> None:
        with self.assertRaisesRegex(EquipmentInputError, "weapon"):
            enumerate_feasible_builds(
                make_tiny_catalog(), (), weapon="weapon:test"  # type: ignore[arg-type]
            )

    def test_set_bonus_minimum_selects_two_tagged_pieces(self) -> None:
        catalog = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={"armor:offense:head", "armor:base:chest"},
        )

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:set", RequirementKind.MINIMUM, 1),),
        )

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        assert result.build is not None
        self.assertEqual(
            result.build.armor_ids[ArmorPart.HEAD], "armor:offense:head"
        )
        self.assertEqual(result.build.granted_skill_levels["skill:set"], 1)

    def test_set_bonus_does_not_activate_below_its_threshold(self) -> None:
        catalog = with_bonus_tags(
            make_tiny_catalog(), set_ids={"armor:base:chest"}
        )

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:set", RequirementKind.MINIMUM, 1),),
        )

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)

    def test_unavoidable_set_bonus_makes_forbidden_infeasible(self) -> None:
        catalog = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={
                "armor:offense:head",
                "armor:critical:head",
                "armor:base:chest",
            },
        )

        result = solve_feasible_build(
            catalog,
            (SkillRequirement("skill:set", RequirementKind.FORBIDDEN),),
        )

        self.assertEqual(result.status, SolveStatus.INFEASIBLE)

    def test_exact_set_bonus_distinguishes_first_and_second_rank(self) -> None:
        two_tagged = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={
                "armor:offense:head",
                "armor:critical:head",
                "armor:base:chest",
            },
        )
        all_tagged = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={piece.id for piece in make_tiny_catalog().armor},
        )

        first_rank = solve_feasible_build(
            two_tagged,
            (SkillRequirement("skill:set", RequirementKind.EXACT, 1),),
        )
        missing_second_rank = solve_feasible_build(
            two_tagged,
            (SkillRequirement("skill:set", RequirementKind.EXACT, 2),),
        )
        exceeded_first_rank = solve_feasible_build(
            all_tagged,
            (SkillRequirement("skill:set", RequirementKind.EXACT, 1),),
        )
        second_rank = solve_feasible_build(
            all_tagged,
            (SkillRequirement("skill:set", RequirementKind.EXACT, 2),),
        )

        self.assertEqual(first_rank.status, SolveStatus.FEASIBLE)
        self.assertEqual(missing_second_rank.status, SolveStatus.INFEASIBLE)
        self.assertEqual(exceeded_first_rank.status, SolveStatus.INFEASIBLE)
        self.assertEqual(second_rank.status, SolveStatus.FEASIBLE)
        assert second_rank.build is not None
        self.assertEqual(second_rank.build.granted_skill_levels["skill:set"], 2)

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


class FeasibleBuildEnumerationTests(unittest.TestCase):
    def test_bonus_requirements_match_independent_exhaustive_search(self) -> None:
        ranked_catalog = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={
                "armor:offense:head",
                "armor:base:chest",
                "armor:base:arms",
                "armor:base:waist",
            },
            group_ids={
                "armor:offense:head",
                "armor:base:chest",
                "armor:base:legs",
            },
        )
        optional_catalog = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={"armor:offense:head", "armor:base:chest"},
        )
        scenarios = (
            (
                "set minimum",
                ranked_catalog,
                (SkillRequirement("skill:set", RequirementKind.MINIMUM, 1),),
            ),
            (
                "set exact first rank",
                ranked_catalog,
                (SkillRequirement("skill:set", RequirementKind.EXACT, 1),),
            ),
            (
                "set exact second rank",
                ranked_catalog,
                (SkillRequirement("skill:set", RequirementKind.EXACT, 2),),
            ),
            (
                "group across series",
                ranked_catalog,
                (SkillRequirement("skill:group", RequirementKind.MINIMUM, 1),),
            ),
            (
                "set forbidden",
                optional_catalog,
                (SkillRequirement("skill:set", RequirementKind.FORBIDDEN),),
            ),
        )

        for name, catalog, requirements in scenarios:
            with self.subTest(name=name):
                expected = exhaustive_signatures(catalog, requirements)
                result = enumerate_feasible_builds(catalog, requirements)

                self.assertEqual(
                    result.status,
                    SolveStatus.FEASIBLE if expected else SolveStatus.INFEASIBLE,
                )
                self.assertEqual(
                    {build_signature(build) for build in result.builds}, expected
                )

    def test_bonus_helpers_do_not_create_duplicate_physical_builds(self) -> None:
        catalog = with_bonus_tags(
            make_tiny_catalog(),
            set_ids={piece.id for piece in make_tiny_catalog().armor},
            group_ids={
                "armor:offense:head",
                "armor:base:chest",
                "armor:base:arms",
            },
        )
        requirements = (
            SkillRequirement("skill:set", RequirementKind.MINIMUM, 1),
        )

        result = enumerate_feasible_builds(catalog, requirements)
        signatures = [build_signature(build) for build in result.builds]

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        self.assertEqual(len(signatures), len(set(signatures)))
        self.assertEqual(set(signatures), exhaustive_signatures(catalog, requirements))

    def test_matches_independent_exhaustive_search_for_requirement_modes(self) -> None:
        catalog = make_tiny_catalog()
        scenarios = {
            "minimum": (
                SkillRequirement("skill:attack", RequirementKind.MINIMUM, 2),
            ),
            "exact below cap": (
                SkillRequirement("skill:critical", RequirementKind.EXACT, 1),
            ),
            "exact at cap": (
                SkillRequirement("skill:attack", RequirementKind.EXACT, 3),
            ),
            "forbidden": (
                SkillRequirement("skill:attack", RequirementKind.FORBIDDEN),
            ),
        }

        for name, requirements in scenarios.items():
            with self.subTest(name=name):
                result = enumerate_feasible_builds(catalog, requirements)

                self.assertEqual(result.status, SolveStatus.FEASIBLE)
                self.assertEqual(
                    {build_signature(build) for build in result.builds},
                    exhaustive_signatures(catalog, requirements),
                )

    def test_limit_stops_after_requested_number_of_builds(self) -> None:
        result = enumerate_feasible_builds(make_tiny_catalog(), (), limit=1)

        self.assertEqual(result.status, SolveStatus.FEASIBLE)
        self.assertEqual(len(result.builds), 1)

    def test_rejects_non_positive_limit(self) -> None:
        with self.assertRaisesRegex(EquipmentInputError, "limit"):
            enumerate_feasible_builds(make_tiny_catalog(), (), limit=0)

    def test_infeasible_catalog_returns_no_builds(self) -> None:
        catalog = replace(make_tiny_catalog(), charms=())

        result = enumerate_feasible_builds(catalog, ())

        self.assertEqual(
            result,
            EnumerationResult(SolveStatus.INFEASIBLE, (), "no regular charm candidate"),
        )

    def test_repeated_enumeration_returns_the_same_signature_set(self) -> None:
        catalog = make_tiny_catalog()
        requirements = (
            SkillRequirement("skill:attack", RequirementKind.MINIMUM, 2),
        )

        first = enumerate_feasible_builds(catalog, requirements)
        second = enumerate_feasible_builds(catalog, requirements)

        self.assertEqual(
            {build_signature(build) for build in first.builds},
            {build_signature(build) for build in second.builds},
        )

    def test_optimization_error_preserves_builds_found_before_failure(self) -> None:
        original_optimize = Model.optimize
        calls = 0

        def optimize_once_then_fail(model: Model):
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_optimize(model)
            raise RuntimeError("later optimization failed")

        with patch.object(Model, "optimize", new=optimize_once_then_fail):
            result = enumerate_feasible_builds(make_tiny_catalog(), ())

        self.assertEqual(result.status, SolveStatus.ERROR)
        self.assertEqual(len(result.builds), 1)
        self.assertIn("later optimization failed", result.message or "")


if __name__ == "__main__":
    unittest.main()
