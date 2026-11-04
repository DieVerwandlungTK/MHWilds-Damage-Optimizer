import unittest
from dataclasses import FrozenInstanceError
from decimal import Decimal
from types import MappingProxyType

from mhwilds_optimizer.combo_data import VerificationStatus
from mhwilds_optimizer.damage_models import CombatStats, Sharpness, TargetHitzones
from mhwilds_optimizer.equipment_models import (
    EquipmentCatalog,
    FeasibleBuild,
    SkillDefinition,
    SkillKind,
)
from mhwilds_optimizer.skill_effect_models import (
    ConditionOperator,
    EffectClause,
    EffectCondition,
    EffectModifier,
    ModifierKind,
    NonDamageSkill,
    SkillEffectDefinition,
    SkillEffectTable,
    SkillRankEffect,
    UnsupportedSkill,
)
from mhwilds_optimizer.skill_effects import (
    MissingSkillConditionError,
    SkillConditionState,
    SkillEffectAudit,
    SkillResolutionContext,
    SkillResolutionError,
    SkillResolutionResult,
    resolve_combat_stats,
)
from mhwilds_optimizer.weapon_models import ElementType, Weapon


def test_weapon() -> Weapon:
    return Weapon(
        id="weapon:test",
        name="Test Blades",
        raw=Decimal("100"),
        element_type=ElementType.FIRE,
        element=Decimal("20"),
        affinity_percent=Decimal("10"),
        sharpness=Sharpness.GREEN,
        slots=(),
        skills={},
    )


def test_target(*, sever: str = "45") -> TargetHitzones:
    return TargetHitzones(
        sever=Decimal(sever),
        element=Decimal("20"),
        monster_damage_modifier=Decimal("1"),
    )


def empty_catalog() -> EquipmentCatalog:
    return EquipmentCatalog(skills=(), armor=(), decorations=(), charms=())


def empty_build() -> FeasibleBuild:
    return FeasibleBuild(
        armor_ids={},
        charm_id="charm:none",
        decorations=(),
        granted_skill_levels={},
        effective_skill_levels={},
        weapon_id="weapon:test",
    )


def empty_table() -> SkillEffectTable:
    empty = MappingProxyType({})
    return SkillEffectTable(
        schema_version=1,
        game_version="1.042.00.03",
        verification_status=VerificationStatus.CROSS_CHECKED,
        sources=(),
        skills=empty,
        unsupported=empty,
        non_damage=empty,
    )


def effect_clause(
    *,
    conditions: tuple[EffectCondition, ...] = (),
    modifiers: tuple[EffectModifier, ...] = (
        EffectModifier(ModifierKind.RAW_FLAT, Decimal("1")),
    ),
) -> EffectClause:
    return EffectClause(conditions=conditions, modifiers=modifiers)


def condition(key: str, value: bool | str, *, at_most: bool = False) -> EffectCondition:
    return EffectCondition(
        key=key,
        operator=(
            ConditionOperator.AT_MOST if at_most else ConditionOperator.EQUALS
        ),
        value=value,
    )


def one_skill_fixture(
    clauses: tuple[EffectClause, ...],
    *,
    skill_id: str = "skill:1",
    kind: SkillKind = SkillKind.ARMOR,
) -> tuple[FeasibleBuild, EquipmentCatalog, SkillEffectTable]:
    definition = SkillDefinition(skill_id, kind, 1)
    catalog = EquipmentCatalog(
        skills=(definition,),
        armor=(),
        decorations=(),
        charms=(),
    )
    build = FeasibleBuild(
        armor_ids={},
        charm_id="charm:none",
        decorations=(),
        granted_skill_levels={skill_id: 1},
        effective_skill_levels={skill_id: 1},
        weapon_id="weapon:test",
    )
    effect = SkillEffectDefinition(
        id=skill_id,
        kind=kind,
        max_level=1,
        ranks=MappingProxyType(
            {1: SkillRankEffect(level=1, clauses=clauses)}
        ),
    )
    empty = MappingProxyType({})
    table = SkillEffectTable(
        schema_version=1,
        game_version="1.042.00.03",
        verification_status=VerificationStatus.CROSS_CHECKED,
        sources=(),
        skills=MappingProxyType({skill_id: effect}),
        unsupported=empty,
        non_damage=empty,
    )
    return build, catalog, table


def skill_effect(
    skill_id: str,
    clauses: tuple[EffectClause, ...],
    *,
    kind: SkillKind = SkillKind.ARMOR,
) -> SkillEffectDefinition:
    return SkillEffectDefinition(
        id=skill_id,
        kind=kind,
        max_level=1,
        ranks=MappingProxyType(
            {1: SkillRankEffect(level=1, clauses=clauses)}
        ),
    )


def resolution_fixture(
    *,
    definitions: tuple[SkillDefinition, ...],
    levels: dict[str, int],
    effects: tuple[SkillEffectDefinition, ...] = (),
    unsupported: tuple[UnsupportedSkill, ...] = (),
    non_damage: tuple[NonDamageSkill, ...] = (),
    weapon_id: str = "weapon:test",
    game_version: str = "1.042.00.03",
) -> tuple[FeasibleBuild, EquipmentCatalog, SkillEffectTable]:
    catalog = EquipmentCatalog(
        skills=definitions,
        armor=(),
        decorations=(),
        charms=(),
    )
    build = FeasibleBuild(
        armor_ids={},
        charm_id="charm:none",
        decorations=(),
        granted_skill_levels=levels,
        effective_skill_levels=levels,
        weapon_id=weapon_id,
    )
    table = SkillEffectTable(
        schema_version=1,
        game_version=game_version,
        verification_status=VerificationStatus.CROSS_CHECKED,
        sources=(),
        skills=MappingProxyType({effect.id: effect for effect in effects}),
        unsupported=MappingProxyType({entry.id: entry for entry in unsupported}),
        non_damage=MappingProxyType({entry.id: entry for entry in non_damage}),
    )
    return build, catalog, table


def test_context(*, conditions: SkillConditionState | None = None) -> SkillResolutionContext:
    return SkillResolutionContext(
        weapon=test_weapon(),
        target=test_target(),
        monster_enraged=False,
        target_wounded=False,
        conditions=conditions or SkillConditionState(),
        demon_dodge_buff=False,
    )


class SkillResolutionModelTests(unittest.TestCase):
    def test_condition_state_copies_and_freezes_valid_values(self) -> None:
        source: dict[str, bool | str] = {
            "full_health": True,
            "sharpness": "green",
            "weapon_element": "fire",
            "burst_stage": "maximum",
        }

        state = SkillConditionState(source)
        source["full_health"] = False

        self.assertEqual(tuple(state.values), tuple(sorted(source)))
        self.assertIs(state.values["full_health"], True)
        with self.assertRaises(TypeError):
            state.values["full_health"] = False  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            state.values = {}  # type: ignore[misc]

    def test_condition_state_rejects_unknown_keys_and_wrong_value_types(self) -> None:
        cases = (
            ({"unknown": True}, "unknown"),
            ({"full_health": "yes"}, "full_health"),
            ({"sharpness": "purple"}, "sharpness"),
            ({"weapon_element": "blast"}, "weapon_element"),
            ({"burst_stage": ""}, "burst_stage"),
        )
        for values, pattern in cases:
            with self.subTest(values=values):
                with self.assertRaisesRegex(SkillResolutionError, pattern):
                    SkillConditionState(values)

    def test_context_rejects_invalid_types(self) -> None:
        valid = {
            "weapon": test_weapon(),
            "target": test_target(),
            "monster_enraged": False,
            "target_wounded": False,
            "conditions": SkillConditionState(),
            "demon_dodge_buff": False,
        }
        cases = (
            ("weapon", object()),
            ("target", object()),
            ("monster_enraged", 0),
            ("target_wounded", 0),
            ("conditions", {}),
            ("demon_dodge_buff", 0),
        )
        for field, value in cases:
            with self.subTest(field=field):
                arguments = dict(valid)
                arguments[field] = value
                with self.assertRaisesRegex(SkillResolutionError, field):
                    SkillResolutionContext(**arguments)  # type: ignore[arg-type]

    def test_result_and_audit_are_frozen_and_copy_evidence(self) -> None:
        evidence = {"full_health": True}
        audit = SkillEffectAudit("skill:1", 1, 0, "applied", evidence)
        evidence["full_health"] = False
        stats = CombatStats(
            raw=Decimal("100"),
            element=Decimal("20"),
            affinity_percent=Decimal("10"),
            positive_critical_modifier=Decimal("1.25"),
            negative_critical_modifier=Decimal("0.75"),
            sharpness=Sharpness.GREEN,
            demon_dodge_buff=False,
        )
        result = SkillResolutionResult(
            stats=stats,
            audit=(audit,),
            ignored_skill_ids=("skill:2",),
            warnings=(),
            verification_status=VerificationStatus.CROSS_CHECKED,
            ranking_eligible=True,
        )

        self.assertIs(audit.condition_evidence["full_health"], True)
        self.assertIs(result.stats, stats)
        with self.assertRaises(TypeError):
            audit.condition_evidence["full_health"] = False  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            result.ranking_eligible = False  # type: ignore[misc]

    def test_resolver_rejects_invalid_base_critical_modifiers(self) -> None:
        cases = (
            ("base_positive_critical_modifier", 1.25),
            ("base_positive_critical_modifier", Decimal("0")),
            ("base_negative_critical_modifier", Decimal("Infinity")),
            ("base_negative_critical_modifier", Decimal("-1")),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                arguments = {
                    "base_positive_critical_modifier": Decimal("1.25"),
                    "base_negative_critical_modifier": Decimal("0.75"),
                }
                arguments[field] = value
                with self.assertRaisesRegex(SkillResolutionError, field):
                    resolve_combat_stats(
                        empty_build(),
                        empty_catalog(),
                        test_context(),
                        table=empty_table(),
                        **arguments,  # type: ignore[arg-type]
                    )


class SkillConditionResolutionTests(unittest.TestCase):
    def resolve(
        self,
        clauses: tuple[EffectClause, ...],
        *,
        target: TargetHitzones | None = None,
        enraged: bool = False,
        wounded: bool = False,
        conditions: SkillConditionState | None = None,
    ) -> SkillResolutionResult:
        build, catalog, table = one_skill_fixture(clauses)
        context = SkillResolutionContext(
            weapon=test_weapon(),
            target=target or test_target(),
            monster_enraged=enraged,
            target_wounded=wounded,
            conditions=conditions or SkillConditionState(),
            demon_dodge_buff=False,
        )
        return resolve_combat_stats(build, catalog, context, table=table)

    def test_derives_automatic_conditions_at_boundaries(self) -> None:
        clauses = (
            effect_clause(conditions=(condition("target_weak", True),)),
            effect_clause(
                conditions=(condition("monster_enraged", True),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("2")),),
            ),
            effect_clause(
                conditions=(condition("target_wounded", True),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("4")),),
            ),
            effect_clause(
                conditions=(condition("weapon_element", "fire"),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("8")),),
            ),
            effect_clause(
                conditions=(condition("sharpness", "green", at_most=True),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("16")),),
            ),
        )

        active = self.resolve(clauses, enraged=True, wounded=True)
        below_boundary = self.resolve(clauses, target=test_target(sever="44.9"))

        self.assertEqual(active.stats.raw, Decimal("131"))
        self.assertEqual(
            tuple(item.outcome for item in active.audit),
            ("applied",) * 5,
        )
        self.assertEqual(below_boundary.stats.raw, Decimal("124"))
        self.assertEqual(
            tuple(item.outcome for item in below_boundary.audit),
            ("inactive", "inactive", "inactive", "applied", "applied"),
        )

    def test_explicit_condition_distinguishes_true_false_and_missing(self) -> None:
        clauses = (
            effect_clause(
                conditions=(condition("full_health", True),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("5")),),
            ),
        )

        active = self.resolve(
            clauses,
            conditions=SkillConditionState({"full_health": True}),
        )
        inactive = self.resolve(
            clauses,
            conditions=SkillConditionState({"full_health": False}),
        )

        self.assertEqual(active.stats.raw, Decimal("105"))
        self.assertEqual(active.audit[0].outcome, "applied")
        self.assertEqual(inactive.stats.raw, Decimal("100"))
        self.assertEqual(inactive.audit[0].outcome, "inactive")
        with self.assertRaisesRegex(MissingSkillConditionError, "full_health"):
            self.resolve(clauses)

    def test_explicit_automatic_condition_must_match_derived_value(self) -> None:
        clauses = (
            effect_clause(conditions=(condition("target_weak", True),)),
        )

        matching = self.resolve(
            clauses,
            conditions=SkillConditionState({"target_weak": True}),
        )

        self.assertEqual(matching.stats.raw, Decimal("101"))
        with self.assertRaisesRegex(SkillResolutionError, "target_weak"):
            self.resolve(
                clauses,
                conditions=SkillConditionState({"target_weak": False}),
            )

    def test_conditions_within_clause_are_and_and_clauses_are_independent(self) -> None:
        clauses = (
            effect_clause(
                conditions=(
                    condition("target_weak", True),
                    condition("monster_enraged", True),
                ),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("3")),),
            ),
            effect_clause(
                conditions=(condition("target_wounded", True),),
                modifiers=(EffectModifier(ModifierKind.RAW_FLAT, Decimal("4")),),
            ),
        )

        one_active = self.resolve(clauses, wounded=True)
        both_active = self.resolve(clauses, enraged=True, wounded=True)

        self.assertEqual(one_active.stats.raw, Decimal("104"))
        self.assertEqual(
            tuple(item.outcome for item in one_active.audit),
            ("inactive", "applied"),
        )
        self.assertEqual(both_active.stats.raw, Decimal("107"))


class SkillAggregationTests(unittest.TestCase):
    def resolve_fixture(
        self,
        fixture: tuple[FeasibleBuild, EquipmentCatalog, SkillEffectTable],
        *,
        context: SkillResolutionContext | None = None,
        strict: bool = True,
    ) -> SkillResolutionResult:
        build, catalog, table = fixture
        return resolve_combat_stats(
            build,
            catalog,
            context or test_context(),
            table=table,
            strict=strict,
        )

    def test_aggregates_every_modifier_in_defined_order_and_clamps_affinity(self) -> None:
        first = skill_effect(
            "skill:1",
            (
                effect_clause(
                    modifiers=(
                        EffectModifier(ModifierKind.RAW_MULTIPLIER, Decimal("1.1")),
                        EffectModifier(ModifierKind.RAW_FLAT, Decimal("5")),
                        EffectModifier(
                            ModifierKind.ELEMENT_MULTIPLIER, Decimal("1.2")
                        ),
                        EffectModifier(ModifierKind.ELEMENT_FLAT, Decimal("4")),
                        EffectModifier(ModifierKind.AFFINITY_POINTS, Decimal("95")),
                        EffectModifier(
                            ModifierKind.POSITIVE_CRITICAL_MODIFIER,
                            Decimal("1.30"),
                        ),
                        EffectModifier(
                            ModifierKind.RAW_DAMAGE_MULTIPLIER, Decimal("1.05")
                        ),
                        EffectModifier(
                            ModifierKind.ELEMENT_DAMAGE_MULTIPLIER,
                            Decimal("1.10"),
                        ),
                        EffectModifier(
                            ModifierKind.POSITIVE_ELEMENT_CRITICAL_MODIFIER,
                            Decimal("1.15"),
                        ),
                    )
                ),
            ),
        )
        second = skill_effect(
            "skill:2",
            (
                effect_clause(
                    modifiers=(
                        EffectModifier(ModifierKind.RAW_MULTIPLIER, Decimal("1.2")),
                        EffectModifier(ModifierKind.RAW_FLAT, Decimal("3")),
                        EffectModifier(
                            ModifierKind.ELEMENT_MULTIPLIER, Decimal("1.1")
                        ),
                        EffectModifier(ModifierKind.ELEMENT_FLAT, Decimal("2")),
                        EffectModifier(ModifierKind.AFFINITY_POINTS, Decimal("10")),
                        EffectModifier(
                            ModifierKind.RAW_DAMAGE_MULTIPLIER, Decimal("1.2")
                        ),
                        EffectModifier(
                            ModifierKind.ELEMENT_DAMAGE_MULTIPLIER, Decimal("1.3")
                        ),
                    )
                ),
            ),
        )
        fixture = resolution_fixture(
            definitions=(
                SkillDefinition("skill:1", SkillKind.ARMOR, 1),
                SkillDefinition("skill:2", SkillKind.WEAPON, 1),
            ),
            levels={"skill:2": 1, "skill:1": 1},
            effects=(second, first),
        )
        context = SkillResolutionContext(
            weapon=test_weapon(),
            target=test_target(),
            monster_enraged=False,
            target_wounded=False,
            demon_dodge_buff=True,
        )

        result = self.resolve_fixture(fixture, context=context)

        self.assertEqual(result.stats.raw, Decimal("140.00"))
        self.assertEqual(result.stats.element, Decimal("32.40"))
        self.assertEqual(result.stats.affinity_percent, Decimal("100"))
        self.assertEqual(result.stats.positive_critical_modifier, Decimal("1.30"))
        self.assertEqual(result.stats.negative_critical_modifier, Decimal("0.75"))
        self.assertEqual(result.stats.raw_damage_modifier, Decimal("1.260"))
        self.assertEqual(result.stats.element_damage_modifier, Decimal("1.430"))
        self.assertEqual(
            result.stats.positive_element_critical_modifier,
            Decimal("1.15"),
        )
        self.assertIs(result.stats.sharpness, Sharpness.GREEN)
        self.assertIs(result.stats.demon_dodge_buff, True)
        self.assertEqual(tuple(item.skill_id for item in result.audit), ("skill:1", "skill:2"))

    def test_clamps_negative_affinity_and_records_element_mismatch_inactive(self) -> None:
        effect = skill_effect(
            "skill:1",
            (
                effect_clause(
                    conditions=(condition("weapon_element", "water"),),
                    modifiers=(
                        EffectModifier(ModifierKind.ELEMENT_FLAT, Decimal("50")),
                    ),
                ),
                effect_clause(
                    modifiers=(
                        EffectModifier(ModifierKind.AFFINITY_POINTS, Decimal("-150")),
                    )
                ),
            ),
        )
        fixture = resolution_fixture(
            definitions=(SkillDefinition("skill:1", SkillKind.ARMOR, 1),),
            levels={"skill:1": 1},
            effects=(effect,),
        )

        result = self.resolve_fixture(fixture)

        self.assertEqual(result.stats.element, Decimal("20"))
        self.assertEqual(result.stats.affinity_percent, Decimal("-100"))
        self.assertEqual(
            tuple(item.outcome for item in result.audit),
            ("inactive", "applied"),
        )

    def test_rejects_conflicting_active_critical_replacements(self) -> None:
        for kind in (
            ModifierKind.POSITIVE_CRITICAL_MODIFIER,
            ModifierKind.POSITIVE_ELEMENT_CRITICAL_MODIFIER,
        ):
            with self.subTest(kind=kind):
                effects = tuple(
                    skill_effect(
                        f"skill:{index}",
                        (
                            effect_clause(
                                modifiers=(
                                    EffectModifier(kind, Decimal(value)),
                                )
                            ),
                        ),
                    )
                    for index, value in ((1, "1.2"), (2, "1.3"))
                )
                fixture = resolution_fixture(
                    definitions=(
                        SkillDefinition("skill:1", SkillKind.ARMOR, 1),
                        SkillDefinition("skill:2", SkillKind.ARMOR, 1),
                    ),
                    levels={"skill:1": 1, "skill:2": 1},
                    effects=effects,
                )
                with self.assertRaisesRegex(SkillResolutionError, "conflicting"):
                    self.resolve_fixture(fixture)


class SkillResolutionPolicyTests(unittest.TestCase):
    def test_rejects_unknown_and_out_of_range_build_skill_levels(self) -> None:
        definition = SkillDefinition("skill:1", SkillKind.ARMOR, 1)
        effect = skill_effect("skill:1", (effect_clause(),))
        cases = (
            ({"skill:999": 1}, "unknown skill:999"),
            ({"skill:1": 2}, "skill:1.*max_level"),
        )
        for levels, pattern in cases:
            with self.subTest(levels=levels):
                fixture = resolution_fixture(
                    definitions=(definition,),
                    levels=levels,
                    effects=(effect,),
                )
                with self.assertRaisesRegex(SkillResolutionError, pattern):
                    SkillAggregationTests().resolve_fixture(fixture)

    def test_rejects_weapon_and_version_mismatches(self) -> None:
        weapon_fixture = resolution_fixture(
            definitions=(),
            levels={},
            weapon_id="weapon:other",
        )
        version_fixture = resolution_fixture(
            definitions=(),
            levels={},
            game_version="1.043.00.00",
        )

        with self.assertRaisesRegex(SkillResolutionError, "weapon_id"):
            SkillAggregationTests().resolve_fixture(weapon_fixture)
        with self.assertRaisesRegex(SkillResolutionError, "version"):
            SkillAggregationTests().resolve_fixture(version_fixture)

    def test_strict_and_non_strict_unsupported_and_unclassified_policy(self) -> None:
        unsupported = UnsupportedSkill(
            "skill:1", SkillKind.ARMOR, 1, "value_unverified"
        )
        fixtures = (
            resolution_fixture(
                definitions=(SkillDefinition("skill:1", SkillKind.ARMOR, 1),),
                levels={"skill:1": 1},
                unsupported=(unsupported,),
            ),
            resolution_fixture(
                definitions=(SkillDefinition("skill:2", SkillKind.ARMOR, 1),),
                levels={"skill:2": 1},
            ),
        )
        for fixture in fixtures:
            with self.subTest(skill_id=next(iter(fixture[0].effective_skill_levels))):
                with self.assertRaisesRegex(SkillResolutionError, "unsupported|unclassified"):
                    SkillAggregationTests().resolve_fixture(fixture)

                result = SkillAggregationTests().resolve_fixture(
                    fixture,
                    strict=False,
                )
                self.assertEqual(result.stats.raw, Decimal("100"))
                self.assertTrue(result.warnings)
                self.assertIs(result.ranking_eligible, False)

    def test_non_damage_skills_are_audited_as_ignored(self) -> None:
        fixture = resolution_fixture(
            definitions=(SkillDefinition("skill:1", SkillKind.ARMOR, 1),),
            levels={"skill:1": 1},
            non_damage=(
                NonDamageSkill("skill:1", SkillKind.ARMOR, 1, "defense_only"),
            ),
        )

        result = SkillAggregationTests().resolve_fixture(fixture)

        self.assertEqual(result.stats.raw, Decimal("100"))
        self.assertEqual(result.ignored_skill_ids, ("skill:1",))
        self.assertEqual(result.warnings, ())
        self.assertIs(result.ranking_eligible, True)

    def test_missing_conditions_remain_errors_in_non_strict_mode(self) -> None:
        fixture = one_skill_fixture(
            (
                effect_clause(
                    conditions=(condition("full_health", True),),
                ),
            )
        )

        with self.assertRaisesRegex(MissingSkillConditionError, "full_health"):
            SkillAggregationTests().resolve_fixture(fixture, strict=False)


if __name__ == "__main__":
    unittest.main()
