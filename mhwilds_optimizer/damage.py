"""Pure hit and combo damage calculations."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from mhwilds_optimizer.combo_data import Combo, Hit, VerificationStatus
from mhwilds_optimizer.damage_models import (
    DEFAULT_DAMAGE_RULES,
    CalculationMode,
    ComboDamage,
    CombatStats,
    DamageInputError,
    DamageRules,
    HitDamage,
    TargetHitzones,
)

_HUNDRED = Decimal("100")
_STATUS_ORDER = {
    VerificationStatus.UNVERIFIED: 0,
    VerificationStatus.CROSS_CHECKED: 1,
    VerificationStatus.VERIFIED: 2,
}
_DISPLAY_QUANTUM = Decimal("0.1")


class UnverifiedDamageError(ValueError):
    """Raised when exact calculation is requested with unverified inputs."""


def _weaker_status(
    first: VerificationStatus, second: VerificationStatus
) -> VerificationStatus:
    return min((first, second), key=_STATUS_ORDER.__getitem__)


def _expected_critical_modifier(stats: CombatStats) -> Decimal:
    affinity = stats.affinity_percent / _HUNDRED
    if affinity >= 0:
        return Decimal("1") + affinity * (
            stats.positive_critical_modifier - Decimal("1")
        )
    return Decimal("1") - abs(affinity) * (
        Decimal("1") - stats.negative_critical_modifier
    )


def _expected_element_critical_modifier(stats: CombatStats) -> Decimal:
    affinity = stats.affinity_percent / _HUNDRED
    if affinity <= 0:
        return Decimal("1")
    return Decimal("1") + affinity * (
        stats.positive_element_critical_modifier - Decimal("1")
    )


def _warnings(status: VerificationStatus) -> tuple[str, ...]:
    if status is VerificationStatus.VERIFIED:
        return ()
    return (
        f"damage result uses {status.value} inputs and is not game-verified",
    )


def _require_exact_verified(
    mode: CalculationMode,
    data_status: VerificationStatus,
    rules_status: VerificationStatus,
) -> None:
    if mode is not CalculationMode.GAME_EXACT:
        return
    if data_status is not VerificationStatus.VERIFIED:
        raise UnverifiedDamageError(
            f"game_exact requires verified data; got {data_status.value}"
        )
    if rules_status is not VerificationStatus.VERIFIED:
        raise UnverifiedDamageError(
            f"game_exact requires verified rules; got {rules_status.value}"
        )


def _validate_hit(hit: Hit) -> None:
    if not isinstance(hit, Hit):
        raise DamageInputError("hit must be a Hit value")
    for field in ("motion_value", "element_modifier"):
        value = getattr(hit, field)
        if not isinstance(value, Decimal):
            raise DamageInputError(f"{field} must be Decimal")
        if not value.is_finite() or value <= 0:
            raise DamageInputError(f"{field} must be finite and positive")
    if hit.damage_type != "sever":
        raise DamageInputError("damage_type must be sever")


def calculate_hit_damage(
    stats: CombatStats,
    hit: Hit,
    target: TargetHitzones,
    *,
    rules: DamageRules = DEFAULT_DAMAGE_RULES,
    data_status: VerificationStatus = VerificationStatus.CROSS_CHECKED,
    mode: CalculationMode = CalculationMode.CONTINUOUS_APPROX,
) -> HitDamage:
    """Calculate expected physical and elemental damage for one hit."""
    if not isinstance(data_status, VerificationStatus):
        raise DamageInputError("data_status must be a VerificationStatus value")
    if not isinstance(mode, CalculationMode):
        raise DamageInputError("mode must be a CalculationMode value")
    _require_exact_verified(mode, data_status, rules.verification_status)
    _validate_hit(hit)

    sharpness = rules.sharpness[stats.sharpness]
    raw_dodge = (
        rules.demon_dodge_raw_modifier
        if stats.demon_dodge_buff
        else Decimal("1")
    )
    element_dodge = (
        rules.demon_dodge_element_modifier
        if stats.demon_dodge_buff
        else Decimal("1")
    )
    critical = _expected_critical_modifier(stats)
    element_critical = _expected_element_critical_modifier(stats)
    physical = (
        stats.raw
        * raw_dodge
        * hit.motion_value
        / _HUNDRED
        * sharpness.raw
        * target.sever
        / _HUNDRED
        * target.monster_damage_modifier
        * critical
        * stats.raw_damage_modifier
    )
    elemental = (
        stats.element
        * element_dodge
        * hit.element_modifier
        * sharpness.element
        * target.element
        / _HUNDRED
        * target.monster_damage_modifier
        * element_critical
        * stats.element_damage_modifier
    )
    if mode is CalculationMode.GAME_EXACT:
        physical = physical.quantize(_DISPLAY_QUANTUM, rounding=ROUND_HALF_UP)
        elemental = elemental.quantize(_DISPLAY_QUANTUM, rounding=ROUND_HALF_UP)
    status = _weaker_status(data_status, rules.verification_status)
    return HitDamage(
        hit=hit,
        physical=physical,
        elemental=elemental,
        total=physical + elemental,
        expected_critical_modifier=critical,
        mode=mode,
        verification_status=status,
        warnings=_warnings(status),
    )


def calculate_combo_damage(
    combo: Combo,
    stats: CombatStats,
    target: TargetHitzones,
    *,
    rules: DamageRules = DEFAULT_DAMAGE_RULES,
    mode: CalculationMode = CalculationMode.CONTINUOUS_APPROX,
) -> ComboDamage:
    """Calculate and aggregate every ordered hit in a combo."""
    if not isinstance(mode, CalculationMode):
        raise DamageInputError("mode must be a CalculationMode value")
    _require_exact_verified(
        mode, combo.verification_status, rules.verification_status
    )
    hits = tuple(
        calculate_hit_damage(
            stats,
            hit,
            target,
            rules=rules,
            data_status=combo.verification_status,
            mode=mode,
        )
        for hit in combo.hits
    )
    physical = sum((hit.physical for hit in hits), start=Decimal("0"))
    elemental = sum((hit.elemental for hit in hits), start=Decimal("0"))
    status = _weaker_status(combo.verification_status, rules.verification_status)
    return ComboDamage(
        combo_id=combo.id,
        hits=hits,
        physical=physical,
        elemental=elemental,
        total=physical + elemental,
        mode=mode,
        verification_status=status,
        warnings=_warnings(status),
    )
