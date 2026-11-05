"""Immutable models for declarative combat skill effects."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from mhwilds_optimizer.combo_data import SourceReference, VerificationStatus
from mhwilds_optimizer.equipment_models import SkillKind


CONDITION_KEYS = frozenset(
    {
        "monster_enraged",
        "target_weak",
        "target_wounded",
        "sharpness",
        "weapon_element",
        "full_health",
        "health_at_most_35_percent",
        "red_health",
        "maximum_stamina",
        "virus_overcome",
        "target_poisoned_or_paralyzed",
        "hunter_statused",
        "after_dodge",
        "after_damage",
        "after_bind_recovery",
        "after_power_clash_or_offset",
        "after_perfect_guard",
        "after_eating",
        "wet",
        "bubbled",
        "latent_power_active",
        "burst_stage",
        "burst_active",
    }
)


class ModifierKind(StrEnum):
    RAW_FLAT = "raw_flat"
    RAW_MULTIPLIER = "raw_multiplier"
    AFFINITY_POINTS = "affinity_points"
    ELEMENT_FLAT = "element_flat"
    ELEMENT_MULTIPLIER = "element_multiplier"
    POSITIVE_CRITICAL_MODIFIER = "positive_critical_modifier"
    RAW_DAMAGE_MULTIPLIER = "raw_damage_multiplier"
    ELEMENT_DAMAGE_MULTIPLIER = "element_damage_multiplier"
    POSITIVE_ELEMENT_CRITICAL_MODIFIER = "positive_element_critical_modifier"


class ConditionOperator(StrEnum):
    EQUALS = "equals"
    AT_MOST = "at_most"


@dataclass(frozen=True)
class EffectCondition:
    key: str
    operator: ConditionOperator
    value: bool | str


@dataclass(frozen=True)
class EffectModifier:
    kind: ModifierKind
    value: Decimal


@dataclass(frozen=True)
class EffectClause:
    conditions: tuple[EffectCondition, ...]
    modifiers: tuple[EffectModifier, ...]


@dataclass(frozen=True)
class SkillRankEffect:
    level: int
    clauses: tuple[EffectClause, ...]


@dataclass(frozen=True)
class SkillEffectDefinition:
    id: str
    kind: SkillKind
    max_level: int
    ranks: Mapping[int, SkillRankEffect]


@dataclass(frozen=True)
class UnsupportedSkill:
    id: str
    kind: SkillKind
    max_level: int
    reason: str


@dataclass(frozen=True)
class NonDamageSkill:
    id: str
    kind: SkillKind
    max_level: int
    reason: str


@dataclass(frozen=True)
class SkillEffectTable:
    schema_version: int
    game_version: str
    verification_status: VerificationStatus
    sources: tuple[SourceReference, ...]
    skills: Mapping[str, SkillEffectDefinition]
    unsupported: Mapping[str, UnsupportedSkill]
    non_damage: Mapping[str, NonDamageSkill]
