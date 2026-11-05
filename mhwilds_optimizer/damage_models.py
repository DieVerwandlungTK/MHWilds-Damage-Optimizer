"""Typed inputs, rules, and results for pure damage calculations."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from mhwilds_optimizer.combo_data import Hit, VerificationStatus


class DamageInputError(ValueError):
    """Raised when damage inputs mix units or exceed supported bounds."""


class CalculationMode(StrEnum):
    CONTINUOUS_APPROX = "continuous_approx"
    GAME_EXACT = "game_exact"


class Sharpness(StrEnum):
    RED = "red"
    ORANGE = "orange"
    YELLOW = "yellow"
    GREEN = "green"
    BLUE = "blue"
    WHITE = "white"


def _require_decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise DamageInputError(f"{field} must be Decimal")
    if not value.is_finite():
        raise DamageInputError(f"{field} must be finite")
    return value


def _require_positive(value: object, field: str) -> Decimal:
    number = _require_decimal(value, field)
    if number <= 0:
        raise DamageInputError(f"{field} must be positive")
    return number


def _require_range(
    value: object, field: str, minimum: Decimal, maximum: Decimal
) -> Decimal:
    number = _require_decimal(value, field)
    if not minimum <= number <= maximum:
        raise DamageInputError(f"{field} must be between {minimum} and {maximum}")
    return number


@dataclass(frozen=True)
class SharpnessModifiers:
    raw: Decimal
    element: Decimal

    def __post_init__(self) -> None:
        _require_positive(self.raw, "sharpness.raw")
        _require_positive(self.element, "sharpness.element")


@dataclass(frozen=True)
class CombatStats:
    raw: Decimal
    element: Decimal
    affinity_percent: Decimal
    positive_critical_modifier: Decimal
    negative_critical_modifier: Decimal
    sharpness: Sharpness
    demon_dodge_buff: bool
    raw_damage_modifier: Decimal = Decimal("1")
    element_damage_modifier: Decimal = Decimal("1")
    positive_element_critical_modifier: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        raw = _require_decimal(self.raw, "raw")
        element = _require_decimal(self.element, "element")
        if raw < 0:
            raise DamageInputError("raw must not be negative")
        if element < 0:
            raise DamageInputError("element must not be negative")
        _require_range(
            self.affinity_percent,
            "affinity_percent",
            Decimal("-100"),
            Decimal("100"),
        )
        _require_positive(
            self.positive_critical_modifier, "positive_critical_modifier"
        )
        _require_positive(
            self.negative_critical_modifier, "negative_critical_modifier"
        )
        _require_positive(self.raw_damage_modifier, "raw_damage_modifier")
        _require_positive(self.element_damage_modifier, "element_damage_modifier")
        _require_positive(
            self.positive_element_critical_modifier,
            "positive_element_critical_modifier",
        )
        if not isinstance(self.sharpness, Sharpness):
            raise DamageInputError("sharpness must be a Sharpness value")
        if not isinstance(self.demon_dodge_buff, bool):
            raise DamageInputError("demon_dodge_buff must be bool")


@dataclass(frozen=True)
class TargetHitzones:
    sever: Decimal
    element: Decimal
    monster_damage_modifier: Decimal

    def __post_init__(self) -> None:
        _require_range(self.sever, "sever", Decimal("0"), Decimal("100"))
        _require_range(self.element, "element", Decimal("0"), Decimal("100"))
        _require_positive(
            self.monster_damage_modifier, "monster_damage_modifier"
        )


@dataclass(frozen=True)
class DamageRules:
    sharpness: Mapping[Sharpness, SharpnessModifiers]
    demon_dodge_raw_modifier: Decimal
    demon_dodge_element_modifier: Decimal
    verification_status: VerificationStatus

    def __post_init__(self) -> None:
        expected = set(Sharpness)
        if set(self.sharpness) != expected:
            raise DamageInputError("sharpness rules must contain every Sharpness value")
        for color, modifiers in self.sharpness.items():
            if not isinstance(color, Sharpness) or not isinstance(
                modifiers, SharpnessModifiers
            ):
                raise DamageInputError("sharpness rules contain an invalid value")
        object.__setattr__(self, "sharpness", MappingProxyType(dict(self.sharpness)))
        _require_positive(
            self.demon_dodge_raw_modifier, "demon_dodge_raw_modifier"
        )
        _require_positive(
            self.demon_dodge_element_modifier, "demon_dodge_element_modifier"
        )
        if not isinstance(self.verification_status, VerificationStatus):
            raise DamageInputError(
                "verification_status must be a VerificationStatus value"
            )


@dataclass(frozen=True)
class HitDamage:
    hit: Hit
    physical: Decimal
    elemental: Decimal
    total: Decimal
    expected_critical_modifier: Decimal
    mode: CalculationMode
    verification_status: VerificationStatus
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ComboDamage:
    combo_id: str
    hits: tuple[HitDamage, ...]
    physical: Decimal
    elemental: Decimal
    total: Decimal
    mode: CalculationMode
    verification_status: VerificationStatus
    warnings: tuple[str, ...]


DEFAULT_DAMAGE_RULES = DamageRules(
    sharpness={
        Sharpness.RED: SharpnessModifiers(Decimal("0.5"), Decimal("0.25")),
        Sharpness.ORANGE: SharpnessModifiers(Decimal("0.75"), Decimal("0.5")),
        Sharpness.YELLOW: SharpnessModifiers(Decimal("1"), Decimal("0.75")),
        Sharpness.GREEN: SharpnessModifiers(Decimal("1.05"), Decimal("1")),
        Sharpness.BLUE: SharpnessModifiers(Decimal("1.2"), Decimal("1.0625")),
        Sharpness.WHITE: SharpnessModifiers(Decimal("1.32"), Decimal("1.15")),
    },
    demon_dodge_raw_modifier=Decimal("1.15"),
    demon_dodge_element_modifier=Decimal("1.3"),
    verification_status=VerificationStatus.CROSS_CHECKED,
)
