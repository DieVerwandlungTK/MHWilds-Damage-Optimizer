"""Resolve declarative combat skill effects into damage-model statistics."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from types import MappingProxyType

from mhwilds_optimizer.combo_data import VerificationStatus
from mhwilds_optimizer.damage_models import CombatStats, Sharpness, TargetHitzones
from mhwilds_optimizer.equipment_models import EquipmentCatalog, FeasibleBuild
from mhwilds_optimizer.skill_effect_data import load_skill_effect_table
from mhwilds_optimizer.skill_effect_models import (
    CONDITION_KEYS,
    ConditionOperator,
    EffectCondition,
    ModifierKind,
    SkillEffectTable,
)
from mhwilds_optimizer.weapon_models import (
    ElementType,
    Weapon,
    combat_stats_from_weapon,
)


class SkillResolutionError(ValueError):
    """Raised when skill effects cannot be resolved without guessing."""


class MissingSkillConditionError(SkillResolutionError):
    """Raised when an active skill needs an unspecified combat condition."""


_STRING_CONDITIONS = {"sharpness", "weapon_element", "burst_stage"}
_SHARPNESS_ORDER = {sharpness.value: index for index, sharpness in enumerate(Sharpness)}
_AUTOMATIC_CONDITIONS = {
    "monster_enraged",
    "target_weak",
    "target_wounded",
    "sharpness",
    "weapon_element",
}


@dataclass(frozen=True)
class SkillConditionState:
    values: Mapping[str, bool | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping):
            raise SkillResolutionError("condition values must be a mapping")
        copied: dict[str, bool | str] = {}
        for key, value in self.values.items():
            if key not in CONDITION_KEYS:
                raise SkillResolutionError(f"unknown condition {key}")
            if key not in _STRING_CONDITIONS:
                if type(value) is not bool:
                    raise SkillResolutionError(f"{key} must be bool")
            elif key == "sharpness":
                if value not in {member.value for member in Sharpness}:
                    raise SkillResolutionError(f"sharpness has invalid value {value!r}")
            elif key == "weapon_element":
                if value not in {member.value for member in ElementType}:
                    raise SkillResolutionError(
                        f"weapon_element has invalid value {value!r}"
                    )
            elif not isinstance(value, str) or not value:
                raise SkillResolutionError("burst_stage must be a non-empty string")
            copied[key] = value
        object.__setattr__(
            self,
            "values",
            MappingProxyType(dict(sorted(copied.items()))),
        )


@dataclass(frozen=True)
class SkillResolutionContext:
    weapon: Weapon
    target: TargetHitzones
    monster_enraged: bool
    target_wounded: bool
    conditions: SkillConditionState = field(default_factory=SkillConditionState)
    demon_dodge_buff: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.weapon, Weapon):
            raise SkillResolutionError("weapon must be a Weapon")
        if not isinstance(self.target, TargetHitzones):
            raise SkillResolutionError("target must be TargetHitzones")
        for name in ("monster_enraged", "target_wounded", "demon_dodge_buff"):
            if type(getattr(self, name)) is not bool:
                raise SkillResolutionError(f"{name} must be bool")
        if not isinstance(self.conditions, SkillConditionState):
            raise SkillResolutionError("conditions must be SkillConditionState")


@dataclass(frozen=True)
class SkillEffectAudit:
    skill_id: str
    level: int
    clause_index: int
    outcome: str
    condition_evidence: Mapping[str, bool | str]

    def __post_init__(self) -> None:
        if self.outcome not in {"applied", "inactive"}:
            raise SkillResolutionError("audit outcome must be applied or inactive")
        object.__setattr__(
            self,
            "condition_evidence",
            MappingProxyType(dict(sorted(self.condition_evidence.items()))),
        )


@dataclass(frozen=True)
class SkillResolutionResult:
    stats: CombatStats
    audit: tuple[SkillEffectAudit, ...]
    ignored_skill_ids: tuple[str, ...]
    warnings: tuple[str, ...]
    verification_status: VerificationStatus
    ranking_eligible: bool


def _require_positive_decimal(value: object, field_name: str) -> Decimal:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value <= 0
    ):
        raise SkillResolutionError(f"{field_name} must be a finite positive Decimal")
    return value


def _automatic_values(context: SkillResolutionContext) -> dict[str, bool | str]:
    return {
        "monster_enraged": context.monster_enraged,
        "target_weak": context.target.sever >= Decimal("45"),
        "target_wounded": context.target_wounded,
        "sharpness": context.weapon.sharpness.value,
        "weapon_element": context.weapon.element_type.value,
    }


def _actual_condition_value(
    condition: EffectCondition,
    context: SkillResolutionContext,
    automatic: Mapping[str, bool | str],
) -> bool | str:
    explicit = context.conditions.values
    if condition.key in _AUTOMATIC_CONDITIONS:
        actual = automatic[condition.key]
        if condition.key in explicit and explicit[condition.key] != actual:
            raise SkillResolutionError(
                f"explicit {condition.key} conflicts with derived value"
            )
        return actual
    if condition.key not in explicit:
        raise MissingSkillConditionError(
            f"missing required condition {condition.key}"
        )
    return explicit[condition.key]


def _condition_matches(condition: EffectCondition, actual: bool | str) -> bool:
    if condition.operator is ConditionOperator.EQUALS:
        return actual == condition.value
    if condition.operator is ConditionOperator.AT_MOST:
        if condition.key != "sharpness" or not isinstance(condition.value, str):
            raise SkillResolutionError("at_most is only valid for sharpness")
        if not isinstance(actual, str):
            raise SkillResolutionError("sharpness condition value must be a string")
        return _SHARPNESS_ORDER[actual] <= _SHARPNESS_ORDER[condition.value]
    raise SkillResolutionError(f"unsupported condition operator {condition.operator}")


def resolve_combat_stats(
    build: FeasibleBuild,
    catalog: EquipmentCatalog,
    context: SkillResolutionContext,
    *,
    table: SkillEffectTable | None = None,
    expected_game_version: str = "1.042.00.03",
    strict: bool = True,
    base_positive_critical_modifier: Decimal = Decimal("1.25"),
    base_negative_critical_modifier: Decimal = Decimal("0.75"),
) -> SkillResolutionResult:
    """Resolve one feasible build into continuous damage inputs."""
    if not isinstance(build, FeasibleBuild):
        raise SkillResolutionError("build must be a FeasibleBuild")
    if not isinstance(catalog, EquipmentCatalog):
        raise SkillResolutionError("catalog must be an EquipmentCatalog")
    if not isinstance(context, SkillResolutionContext):
        raise SkillResolutionError("context must be a SkillResolutionContext")
    if type(strict) is not bool:
        raise SkillResolutionError("strict must be bool")
    positive_critical = _require_positive_decimal(
        base_positive_critical_modifier,
        "base_positive_critical_modifier",
    )
    negative_critical = _require_positive_decimal(
        base_negative_critical_modifier,
        "base_negative_critical_modifier",
    )
    resolved_table = table or load_skill_effect_table(
        catalog,
        expected_game_version=expected_game_version,
    )
    if not isinstance(resolved_table, SkillEffectTable):
        raise SkillResolutionError("table must be a SkillEffectTable")
    if resolved_table.game_version != expected_game_version:
        raise SkillResolutionError(
            f"effect table version {resolved_table.game_version} does not match "
            f"{expected_game_version}"
        )
    if build.weapon_id is not None and build.weapon_id != context.weapon.id:
        raise SkillResolutionError("build weapon_id does not match context weapon")

    catalog_skills = {definition.id: definition for definition in catalog.skills}
    warnings: list[str] = []
    ignored: list[str] = []
    skipped_incomplete = False
    supported_ids: list[str] = []
    for skill_id in sorted(build.effective_skill_levels):
        level = build.effective_skill_levels[skill_id]
        definition = catalog_skills.get(skill_id)
        if definition is None:
            raise SkillResolutionError(f"unknown {skill_id} in effective skill levels")
        if level > definition.max_level:
            raise SkillResolutionError(
                f"{skill_id} level {level} exceeds max_level {definition.max_level}"
            )
        if skill_id in resolved_table.non_damage:
            ignored.append(skill_id)
            continue
        unsupported = resolved_table.unsupported.get(skill_id)
        if unsupported is not None:
            message = f"unsupported {skill_id}: {unsupported.reason}"
            if strict:
                raise SkillResolutionError(message)
            warnings.append(message)
            skipped_incomplete = True
            continue
        if skill_id not in resolved_table.skills:
            message = f"unclassified {skill_id}"
            if strict:
                raise SkillResolutionError(message)
            warnings.append(message)
            skipped_incomplete = True
            continue
        supported_ids.append(skill_id)

    stats = combat_stats_from_weapon(
        context.weapon,
        positive_critical_modifier=positive_critical,
        negative_critical_modifier=negative_critical,
        demon_dodge_buff=context.demon_dodge_buff,
    )
    automatic = _automatic_values(context)
    raw_flat = Decimal("0")
    raw_multiplier = Decimal("1")
    element_flat = Decimal("0")
    element_multiplier = Decimal("1")
    affinity_points = Decimal("0")
    raw_damage_multiplier = Decimal("1")
    element_damage_multiplier = Decimal("1")
    positive_critical_replacements: set[Decimal] = set()
    positive_element_critical_replacements: set[Decimal] = set()
    audit: list[SkillEffectAudit] = []
    for skill_id in supported_ids:
        effect = resolved_table.skills[skill_id]
        level = build.effective_skill_levels[skill_id]
        rank = effect.ranks[level]
        for clause_index, clause in enumerate(rank.clauses):
            evidence: dict[str, bool | str] = {}
            matches = True
            for clause_condition in clause.conditions:
                actual = _actual_condition_value(
                    clause_condition,
                    context,
                    automatic,
                )
                evidence[clause_condition.key] = actual
                if not _condition_matches(clause_condition, actual):
                    matches = False
            audit.append(
                SkillEffectAudit(
                    skill_id=skill_id,
                    level=level,
                    clause_index=clause_index,
                    outcome="applied" if matches else "inactive",
                    condition_evidence=evidence,
                )
            )
            if not matches:
                continue
            for modifier in clause.modifiers:
                if modifier.kind is ModifierKind.RAW_FLAT:
                    raw_flat += modifier.value
                elif modifier.kind is ModifierKind.RAW_MULTIPLIER:
                    raw_multiplier *= modifier.value
                elif modifier.kind is ModifierKind.ELEMENT_FLAT:
                    element_flat += modifier.value
                elif modifier.kind is ModifierKind.ELEMENT_MULTIPLIER:
                    element_multiplier *= modifier.value
                elif modifier.kind is ModifierKind.AFFINITY_POINTS:
                    affinity_points += modifier.value
                elif modifier.kind is ModifierKind.RAW_DAMAGE_MULTIPLIER:
                    raw_damage_multiplier *= modifier.value
                elif modifier.kind is ModifierKind.ELEMENT_DAMAGE_MULTIPLIER:
                    element_damage_multiplier *= modifier.value
                elif modifier.kind is ModifierKind.POSITIVE_CRITICAL_MODIFIER:
                    positive_critical_replacements.add(modifier.value)
                elif (
                    modifier.kind
                    is ModifierKind.POSITIVE_ELEMENT_CRITICAL_MODIFIER
                ):
                    positive_element_critical_replacements.add(modifier.value)
                else:
                    raise SkillResolutionError(
                        f"unsupported modifier kind {modifier.kind}"
                    )
    if len(positive_critical_replacements) > 1:
        raise SkillResolutionError("conflicting positive critical modifiers")
    if len(positive_element_critical_replacements) > 1:
        raise SkillResolutionError("conflicting positive element critical modifiers")
    resolved_positive_critical = next(
        iter(positive_critical_replacements),
        positive_critical,
    )
    resolved_positive_element_critical = next(
        iter(positive_element_critical_replacements),
        Decimal("1"),
    )
    affinity = max(
        Decimal("-100"),
        min(Decimal("100"), stats.affinity_percent + affinity_points),
    )
    stats = replace(
        stats,
        raw=stats.raw * raw_multiplier + raw_flat,
        element=stats.element * element_multiplier + element_flat,
        affinity_percent=affinity,
        positive_critical_modifier=resolved_positive_critical,
        raw_damage_modifier=raw_damage_multiplier,
        element_damage_modifier=element_damage_multiplier,
        positive_element_critical_modifier=resolved_positive_element_critical,
    )
    return SkillResolutionResult(
        stats=stats,
        audit=tuple(audit),
        ignored_skill_ids=tuple(ignored),
        warnings=tuple(warnings),
        verification_status=resolved_table.verification_status,
        ranking_eligible=not skipped_incomplete,
    )
