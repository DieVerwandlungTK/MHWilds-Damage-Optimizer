"""Immutable equipment inputs and solver-independent build results."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType


class EquipmentInputError(ValueError):
    """Raised when equipment candidates or requirements are inconsistent."""


class ArmorPart(StrEnum):
    HEAD = "head"
    CHEST = "chest"
    ARMS = "arms"
    WAIST = "waist"
    LEGS = "legs"


class SlotType(StrEnum):
    ARMOR = "armor"
    WEAPON = "weapon"


class SkillKind(StrEnum):
    ARMOR = "armor"
    WEAPON = "weapon"
    SET = "set"
    GROUP = "group"


class RequirementKind(StrEnum):
    MINIMUM = "minimum"
    EXACT = "exact"
    FORBIDDEN = "forbidden"


def _require_id(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EquipmentInputError(f"{field} must be a non-empty string")
    return value


def _require_positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise EquipmentInputError(f"{field} must be a positive integer")
    return value


def _freeze_skills(value: Mapping[str, int], field: str) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise EquipmentInputError(f"{field} must be a mapping")
    result: dict[str, int] = {}
    for skill_id, level in value.items():
        normalized_id = _require_id(skill_id, f"{field} skill ID")
        result[normalized_id] = _require_positive_integer(
            level, f"{field}.{normalized_id}"
        )
    return MappingProxyType(dict(sorted(result.items())))


def _validate_slots(value: tuple[int, ...], field: str) -> tuple[int, ...]:
    if not isinstance(value, tuple):
        raise EquipmentInputError(f"{field} must be a tuple")
    if any(type(level) is not int or level not in {1, 2, 3} for level in value):
        raise EquipmentInputError(f"{field} must contain slot levels 1 through 3")
    return value


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    kind: SkillKind
    max_level: int

    def __post_init__(self) -> None:
        _require_id(self.id, "skill id")
        if not isinstance(self.kind, SkillKind):
            raise EquipmentInputError("skill kind must be a SkillKind")
        _require_positive_integer(self.max_level, "max_level")


@dataclass(frozen=True)
class ArmorPiece:
    id: str
    part: ArmorPart
    skills: Mapping[str, int]
    slots: tuple[int, ...]

    def __post_init__(self) -> None:
        _require_id(self.id, "armor id")
        if not isinstance(self.part, ArmorPart):
            raise EquipmentInputError("armor part must be an ArmorPart")
        object.__setattr__(self, "skills", _freeze_skills(self.skills, "armor skills"))
        object.__setattr__(self, "slots", _validate_slots(self.slots, "armor slots"))


@dataclass(frozen=True)
class Decoration:
    id: str
    slot_type: SlotType
    required_slot_level: int
    skills: Mapping[str, int]

    def __post_init__(self) -> None:
        _require_id(self.id, "decoration id")
        if not isinstance(self.slot_type, SlotType):
            raise EquipmentInputError("slot_type must be a SlotType")
        level = _require_positive_integer(
            self.required_slot_level, "required_slot_level"
        )
        if level > 3:
            raise EquipmentInputError("required_slot_level must be 1 through 3")
        object.__setattr__(
            self,
            "skills",
            _freeze_skills(self.skills, "decoration skills"),
        )


@dataclass(frozen=True)
class RegularCharm:
    id: str
    skills: Mapping[str, int]
    slots: tuple[int, ...]

    def __post_init__(self) -> None:
        _require_id(self.id, "charm id")
        object.__setattr__(self, "skills", _freeze_skills(self.skills, "charm skills"))
        object.__setattr__(self, "slots", _validate_slots(self.slots, "charm slots"))


def _duplicate_id(values: Sequence[object], kind: str) -> None:
    seen: set[str] = set()
    for value in values:
        identifier = getattr(value, "id", None)
        if identifier in seen:
            raise EquipmentInputError(f"duplicate {kind} id: {identifier}")
        seen.add(identifier)


@dataclass(frozen=True)
class EquipmentCatalog:
    skills: tuple[SkillDefinition, ...]
    armor: tuple[ArmorPiece, ...]
    decorations: tuple[Decoration, ...]
    charms: tuple[RegularCharm, ...]

    def __post_init__(self) -> None:
        collections = (
            ("skills", self.skills, SkillDefinition),
            ("armor", self.armor, ArmorPiece),
            ("decorations", self.decorations, Decoration),
            ("charms", self.charms, RegularCharm),
        )
        for field, values, expected_type in collections:
            if not isinstance(values, tuple) or any(
                not isinstance(value, expected_type) for value in values
            ):
                raise EquipmentInputError(
                    f"{field} must be a tuple of {expected_type.__name__} values"
                )
        _duplicate_id(self.skills, "skill")
        _duplicate_id(self.armor, "armor")
        _duplicate_id(self.decorations, "decoration")
        _duplicate_id(self.charms, "charm")

        skill_levels = {skill.id: skill.max_level for skill in self.skills}
        equipment = (*self.armor, *self.decorations, *self.charms)
        for candidate in equipment:
            for skill_id, level in candidate.skills.items():
                if skill_id not in skill_levels:
                    raise EquipmentInputError(
                        f"{candidate.id} references unknown skill {skill_id}"
                    )
                if level > skill_levels[skill_id]:
                    raise EquipmentInputError(
                        f"{candidate.id}.{skill_id} exceeds max_level"
                    )


@dataclass(frozen=True)
class SkillRequirement:
    skill_id: str
    kind: RequirementKind
    level: int | None = None

    def __post_init__(self) -> None:
        _require_id(self.skill_id, "requirement skill_id")
        if not isinstance(self.kind, RequirementKind):
            raise EquipmentInputError("requirement kind must be a RequirementKind")
        if self.level is not None and type(self.level) is not int:
            raise EquipmentInputError("requirement level must be an integer")


@dataclass(frozen=True)
class DecorationPlacement:
    owner_id: str
    slot_index: int
    decoration_id: str

    def __post_init__(self) -> None:
        _require_id(self.owner_id, "placement owner_id")
        if type(self.slot_index) is not int or self.slot_index < 0:
            raise EquipmentInputError("placement slot_index must not be negative")
        _require_id(self.decoration_id, "placement decoration_id")


@dataclass(frozen=True)
class FeasibleBuild:
    armor_ids: Mapping[ArmorPart, str]
    charm_id: str
    decorations: tuple[DecorationPlacement, ...]
    granted_skill_levels: Mapping[str, int]
    effective_skill_levels: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.armor_ids, Mapping):
            raise EquipmentInputError("armor_ids must be a mapping")
        armor_ids = dict(self.armor_ids)
        if any(not isinstance(part, ArmorPart) for part in armor_ids):
            raise EquipmentInputError("armor_ids keys must be ArmorPart values")
        for identifier in armor_ids.values():
            _require_id(identifier, "armor_ids value")
        object.__setattr__(self, "armor_ids", MappingProxyType(armor_ids))
        _require_id(self.charm_id, "charm_id")
        if not isinstance(self.decorations, tuple) or any(
            not isinstance(value, DecorationPlacement) for value in self.decorations
        ):
            raise EquipmentInputError("decorations must contain DecorationPlacement values")
        object.__setattr__(
            self,
            "granted_skill_levels",
            _freeze_skills(self.granted_skill_levels, "granted_skill_levels"),
        )
        object.__setattr__(
            self,
            "effective_skill_levels",
            _freeze_skills(self.effective_skill_levels, "effective_skill_levels"),
        )


def validate_requirements(
    catalog: EquipmentCatalog,
    requirements: Sequence[SkillRequirement],
) -> tuple[SkillRequirement, ...]:
    """Validate requirement identity and bounds, returning deterministic order."""
    if not isinstance(catalog, EquipmentCatalog):
        raise EquipmentInputError("catalog must be an EquipmentCatalog")
    if not isinstance(requirements, Sequence):
        raise EquipmentInputError("requirements must be a sequence")
    skill_levels = {skill.id: skill.max_level for skill in catalog.skills}
    seen: set[str] = set()
    validated: list[SkillRequirement] = []
    for requirement in requirements:
        if not isinstance(requirement, SkillRequirement):
            raise EquipmentInputError("requirements must contain SkillRequirement values")
        if requirement.skill_id in seen:
            raise EquipmentInputError(
                f"duplicate requirement for {requirement.skill_id}"
            )
        seen.add(requirement.skill_id)
        if requirement.skill_id not in skill_levels:
            raise EquipmentInputError(
                f"unknown requirement skill {requirement.skill_id}"
            )
        if requirement.kind is RequirementKind.FORBIDDEN:
            if requirement.level is not None:
                raise EquipmentInputError("forbidden requirement must not have a level")
        else:
            if requirement.level is None or requirement.level <= 0:
                raise EquipmentInputError("requirement level must be positive")
            if requirement.level > skill_levels[requirement.skill_id]:
                raise EquipmentInputError(
                    f"requirement level exceeds max_level for {requirement.skill_id}"
                )
        validated.append(requirement)
    return tuple(sorted(validated, key=lambda item: item.skill_id))
