"""Typed manual weapon inputs and damage-model conversion."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

from mhwilds_optimizer.damage_models import CombatStats, Sharpness


class WeaponInputError(ValueError):
    """Raised when a manually entered weapon is inconsistent."""


class ElementType(StrEnum):
    NONE = "none"
    FIRE = "fire"
    WATER = "water"
    THUNDER = "thunder"
    ICE = "ice"
    DRAGON = "dragon"


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WeaponInputError(f"{field} must be a non-empty string")
    return value


def _require_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise WeaponInputError(f"{field} must be a finite Decimal")
    return value


def _freeze_skills(value: Mapping[str, int]) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise WeaponInputError("skills must be a mapping")
    result: dict[str, int] = {}
    for skill_id, level in value.items():
        normalized_id = _require_text(skill_id, "skills skill ID")
        if type(level) is not int or level <= 0:
            raise WeaponInputError(f"skills.{normalized_id} must be a positive integer")
        result[normalized_id] = level
    return MappingProxyType(dict(sorted(result.items())))


@dataclass(frozen=True)
class Weapon:
    id: str
    name: str
    raw: Decimal
    element_type: ElementType
    element: Decimal
    affinity_percent: Decimal
    sharpness: Sharpness
    slots: tuple[int, ...]
    skills: Mapping[str, int]

    def __post_init__(self) -> None:
        _require_text(self.id, "id")
        _require_text(self.name, "name")
        raw = _require_decimal(self.raw, "raw")
        element = _require_decimal(self.element, "element")
        affinity = _require_decimal(self.affinity_percent, "affinity_percent")
        if raw < 0:
            raise WeaponInputError("raw must not be negative")
        if element < 0:
            raise WeaponInputError("element must not be negative")
        if not Decimal("-100") <= affinity <= Decimal("100"):
            raise WeaponInputError("affinity_percent must be between -100 and 100")
        if not isinstance(self.element_type, ElementType):
            raise WeaponInputError("element_type must be an ElementType")
        if self.element_type is ElementType.NONE and element != 0:
            raise WeaponInputError("element must be zero when element_type is none")
        if self.element_type is not ElementType.NONE and element <= 0:
            raise WeaponInputError("element must be positive for an elemental weapon")
        if not isinstance(self.sharpness, Sharpness):
            raise WeaponInputError("sharpness must be a Sharpness value")
        if not isinstance(self.slots, tuple) or any(
            type(level) is not int or level not in {1, 2, 3}
            for level in self.slots
        ):
            raise WeaponInputError("slots must be a tuple of levels 1 through 3")
        object.__setattr__(self, "skills", _freeze_skills(self.skills))


def combat_stats_from_weapon(
    weapon: Weapon,
    *,
    positive_critical_modifier: Decimal,
    negative_critical_modifier: Decimal,
    demon_dodge_buff: bool,
) -> CombatStats:
    """Create damage inputs from a completed weapon and combat-only state."""
    return CombatStats(
        raw=weapon.raw,
        element=weapon.element,
        affinity_percent=weapon.affinity_percent,
        positive_critical_modifier=positive_critical_modifier,
        negative_critical_modifier=negative_critical_modifier,
        sharpness=weapon.sharpness,
        demon_dodge_buff=demon_dodge_buff,
    )
