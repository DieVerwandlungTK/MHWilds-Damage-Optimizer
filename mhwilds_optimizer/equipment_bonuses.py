"""Solver-independent armor set and group bonus activation."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from mhwilds_optimizer.equipment_models import (
    BonusRank,
    EquipmentCatalog,
    EquipmentInputError,
    SkillKind,
)


@dataclass(frozen=True)
class BonusFamily:
    kind: SkillKind
    skill_id: str
    ranks: tuple[BonusRank, ...]
    armor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.kind not in {SkillKind.SET, SkillKind.GROUP}:
            raise EquipmentInputError("bonus family kind must be set or group")
        if not isinstance(self.skill_id, str) or not self.skill_id.strip():
            raise EquipmentInputError("bonus family skill_id must be non-empty")
        if not self.ranks or any(
            not isinstance(rank, BonusRank) for rank in self.ranks
        ):
            raise EquipmentInputError("bonus family ranks must contain BonusRank values")
        if not self.armor_ids or any(
            not isinstance(identifier, str) or not identifier.strip()
            for identifier in self.armor_ids
        ):
            raise EquipmentInputError("bonus family armor_ids must be non-empty IDs")


def collect_bonus_families(catalog: EquipmentCatalog) -> tuple[BonusFamily, ...]:
    """Collect armor carrying each validated set/group skill tag."""
    if not isinstance(catalog, EquipmentCatalog):
        raise EquipmentInputError("catalog must be an EquipmentCatalog")
    groups: dict[tuple[SkillKind, str], tuple[tuple[BonusRank, ...], list[str]]] = {}
    for piece in catalog.armor:
        for kind, bonus in (
            (SkillKind.SET, piece.set_bonus),
            (SkillKind.GROUP, piece.group_bonus),
        ):
            if bonus is None:
                continue
            key = (kind, bonus.skill_id)
            if key not in groups:
                groups[key] = (bonus.ranks, [])
            groups[key][1].append(piece.id)
    return tuple(
        BonusFamily(kind, skill_id, ranks, tuple(sorted(armor_ids)))
        for (kind, skill_id), (ranks, armor_ids) in sorted(
            groups.items(), key=lambda item: (item[0][0].value, item[0][1])
        )
    )


def activated_bonus_levels(
    catalog: EquipmentCatalog,
    selected_armor_ids: Collection[str],
) -> Mapping[str, int]:
    """Return the cumulative bonus level reached by selected armor tags."""
    if not isinstance(selected_armor_ids, Collection):
        raise EquipmentInputError("selected_armor_ids must be a collection")
    selected = set(selected_armor_ids)
    known_ids = {piece.id for piece in catalog.armor}
    unknown = selected - known_ids
    if unknown:
        raise EquipmentInputError(f"unknown selected armor: {min(unknown)!r}")

    levels: dict[str, int] = {}
    for family in collect_bonus_families(catalog):
        count = len(selected.intersection(family.armor_ids))
        reached = [rank.skill_level for rank in family.ranks if count >= rank.pieces]
        if reached:
            levels[family.skill_id] = max(reached)
    return MappingProxyType(dict(sorted(levels.items())))
