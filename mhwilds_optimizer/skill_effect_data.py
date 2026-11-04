"""Load and validate versioned declarative combat skill effects."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType
from typing import Any

from mhwilds_optimizer.combo_data import SourceReference, VerificationStatus
from mhwilds_optimizer.equipment_models import EquipmentCatalog, SkillKind
from mhwilds_optimizer.skill_effect_models import (
    CONDITION_KEYS,
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


class SkillEffectDataError(ValueError):
    """Raised when a skill effect table violates its versioned schema."""


_TOP_LEVEL_FIELDS = {
    "schema_version",
    "game_version",
    "verification_status",
    "sources",
    "skills",
    "unsupported",
    "non_damage",
}
_SKILL_ID = re.compile(r"skill:-?\d+\Z")


def _default_path() -> Path:
    return Path(__file__).with_name("data") / "skill_effects" / "1.042.00.03.json"


def _record(value: object, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SkillEffectDataError(f"{field} must be an object")
    return value


def _require_exact_fields(
    record: Mapping[str, object], expected: set[str], field: str
) -> None:
    missing = expected - set(record)
    extra = set(record) - expected
    if missing:
        raise SkillEffectDataError(f"{field} missing field {min(missing)}")
    if extra:
        raise SkillEffectDataError(f"{field} has unexpected field {min(extra)}")


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise SkillEffectDataError(f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SkillEffectDataError(f"{field} must be a non-empty string")
    return value


def _positive_integer(value: object, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise SkillEffectDataError(f"{field} must be a positive integer")
    return value


def _skill_id(value: object, field: str) -> str:
    identifier = _text(value, field)
    if _SKILL_ID.fullmatch(identifier) is None:
        raise SkillEffectDataError(f"{field} must be a stable skill ID")
    return identifier


def _enum(enum_type: type[Any], value: object, field: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise SkillEffectDataError(f"{field} has an unsupported value {value!r}") from error


def _decimal(value: object, field: str) -> Decimal:
    if not isinstance(value, str) or not value.strip():
        raise SkillEffectDataError(f"{field} must be a decimal string")
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise SkillEffectDataError(f"{field} must be a decimal string") from error
    if not number.is_finite():
        raise SkillEffectDataError(f"{field} must be finite")
    return number


def _source(value: object, index: int) -> SourceReference:
    context = f"sources[{index}]"
    record = _record(value, context)
    checked_at = _text(record.get("checked_at"), f"{context}.checked_at")
    try:
        checked_date = date.fromisoformat(checked_at)
    except ValueError as error:
        raise SkillEffectDataError(f"{context}.checked_at must be an ISO date") from error
    supports = tuple(
        _text(item, f"{context}.supports[{item_index}]")
        for item_index, item in enumerate(
            _array(record.get("supports"), f"{context}.supports")
        )
    )
    return SourceReference(
        name=_text(record.get("name"), f"{context}.name"),
        url=_text(record.get("url"), f"{context}.url"),
        checked_at=checked_date,
        supports=supports,
    )


def _condition(value: object, context: str) -> EffectCondition:
    record = _record(value, context)
    key = _text(record.get("key"), f"{context}.key")
    if key not in CONDITION_KEYS:
        raise SkillEffectDataError(f"{context}.key has an unsupported value {key!r}")
    condition_value = record.get("value")
    if not isinstance(condition_value, (bool, str)):
        raise SkillEffectDataError(f"{context}.value must be bool or string")
    return EffectCondition(
        key=key,
        operator=_enum(
            ConditionOperator,
            record.get("operator"),
            f"{context}.operator",
        ),
        value=condition_value,
    )


def _modifier(value: object, context: str) -> EffectModifier:
    record = _record(value, context)
    return EffectModifier(
        kind=_enum(ModifierKind, record.get("kind"), f"{context}.kind"),
        value=_decimal(record.get("value"), f"{context}.value"),
    )


def _clause(value: object, context: str) -> EffectClause:
    record = _record(value, context)
    conditions = tuple(
        _condition(item, f"{context}.conditions[{index}]")
        for index, item in enumerate(
            _array(record.get("conditions"), f"{context}.conditions")
        )
    )
    modifiers = tuple(
        _modifier(item, f"{context}.modifiers[{index}]")
        for index, item in enumerate(
            _array(record.get("modifiers"), f"{context}.modifiers")
        )
    )
    if not modifiers:
        raise SkillEffectDataError(f"{context}.modifiers must not be empty")
    return EffectClause(
        conditions=conditions,
        modifiers=modifiers,
    )


def _supported(value: object, index: int) -> SkillEffectDefinition:
    context = f"skills[{index}]"
    record = _record(value, context)
    identifier = _skill_id(record.get("id"), f"{context}.id")
    ranks: dict[int, SkillRankEffect] = {}
    for rank_index, rank_value in enumerate(
        _array(record.get("ranks"), f"{context}.ranks")
    ):
        rank_context = f"{context}.ranks[{rank_index}]"
        rank_record = _record(rank_value, rank_context)
        level = _positive_integer(rank_record.get("level"), f"{rank_context}.level")
        if level in ranks:
            raise SkillEffectDataError(f"{context} contains duplicate rank {level}")
        clauses = tuple(
            _clause(item, f"{rank_context}.clauses[{clause_index}]")
            for clause_index, item in enumerate(
                _array(rank_record.get("clauses"), f"{rank_context}.clauses")
            )
        )
        if not clauses:
            raise SkillEffectDataError(f"{rank_context}.clauses must not be empty")
        ranks[level] = SkillRankEffect(
            level=level,
            clauses=clauses,
        )
    max_level = _positive_integer(record.get("max_level"), f"{context}.max_level")
    if set(ranks) != set(range(1, max_level + 1)):
        raise SkillEffectDataError(
            f"{context}.ranks must contain every level from 1 through {max_level}"
        )
    return SkillEffectDefinition(
        id=identifier,
        kind=_enum(SkillKind, record.get("kind"), f"{context}.kind"),
        max_level=max_level,
        ranks=MappingProxyType(dict(sorted(ranks.items()))),
    )


def _classified(
    value: object,
    index: int,
    category: str,
    model_type: type[UnsupportedSkill] | type[NonDamageSkill],
) -> UnsupportedSkill | NonDamageSkill:
    context = f"{category}[{index}]"
    record = _record(value, context)
    return model_type(
        id=_skill_id(record.get("id"), f"{context}.id"),
        kind=_enum(SkillKind, record.get("kind"), f"{context}.kind"),
        max_level=_positive_integer(record.get("max_level"), f"{context}.max_level"),
        reason=_text(record.get("reason"), f"{context}.reason"),
    )


def _mapping(values: list[Any], field: str) -> Mapping[str, Any]:
    result: dict[str, Any] = {}
    for value in values:
        if value.id in result:
            raise SkillEffectDataError(f"{field} contains duplicate ID {value.id}")
        result[value.id] = value
    return MappingProxyType(dict(sorted(result.items())))


def _validate_categories(
    skills: Mapping[str, SkillEffectDefinition],
    unsupported: Mapping[str, UnsupportedSkill],
    non_damage: Mapping[str, NonDamageSkill],
) -> None:
    categories = (set(skills), set(unsupported), set(non_damage))
    if any(first & second for index, first in enumerate(categories) for second in categories[index + 1 :]):
        raise SkillEffectDataError("skill ID appears in more than one category")


def _validate_catalog(
    catalog: EquipmentCatalog,
    skills: Mapping[str, SkillEffectDefinition],
    unsupported: Mapping[str, UnsupportedSkill],
    non_damage: Mapping[str, NonDamageSkill],
) -> None:
    if not isinstance(catalog, EquipmentCatalog):
        raise SkillEffectDataError("catalog must be an EquipmentCatalog")
    definitions = {definition.id: definition for definition in catalog.skills}
    for entry in (*skills.values(), *unsupported.values(), *non_damage.values()):
        definition = definitions.get(entry.id)
        if definition is None:
            raise SkillEffectDataError(f"unknown {entry.id} in catalog")
        if definition.kind is not entry.kind:
            raise SkillEffectDataError(f"{entry.id} kind mismatch")
        if definition.max_level != entry.max_level:
            raise SkillEffectDataError(f"{entry.id} max_level mismatch")


def load_skill_effect_table(
    catalog: EquipmentCatalog | None = None,
    path: Path | None = None,
    *,
    expected_game_version: str = "1.042.00.03",
) -> SkillEffectTable:
    """Load one immutable skill effect table from JSON."""
    source_path = path if path is not None else _default_path()
    try:
        payload = _record(
            json.loads(source_path.read_text(encoding="utf-8")),
            "root",
        )
        _require_exact_fields(payload, _TOP_LEVEL_FIELDS, "root")
        if payload.get("schema_version") != 1:
            raise SkillEffectDataError("schema_version must be 1")
        game_version = _text(payload.get("game_version"), "game_version")
        if game_version != expected_game_version:
            raise SkillEffectDataError(
                f"game_version must be {expected_game_version}; got {game_version}"
            )
        skills = _mapping(
            [
                _supported(item, index)
                for index, item in enumerate(_array(payload.get("skills"), "skills"))
            ],
            "skills",
        )
        unsupported = _mapping(
            [
                _classified(item, index, "unsupported", UnsupportedSkill)
                for index, item in enumerate(
                    _array(payload.get("unsupported"), "unsupported")
                )
            ],
            "unsupported",
        )
        non_damage = _mapping(
            [
                _classified(item, index, "non_damage", NonDamageSkill)
                for index, item in enumerate(
                    _array(payload.get("non_damage"), "non_damage")
                )
            ],
            "non_damage",
        )
        _validate_categories(skills, unsupported, non_damage)
        if catalog is not None:
            _validate_catalog(catalog, skills, unsupported, non_damage)
        return SkillEffectTable(
            schema_version=_positive_integer(
                payload.get("schema_version"), "schema_version"
            ),
            game_version=game_version,
            verification_status=_enum(
                VerificationStatus,
                payload.get("verification_status"),
                "verification_status",
            ),
            sources=tuple(
                _source(item, index)
                for index, item in enumerate(
                    _array(payload.get("sources"), "sources")
                )
            ),
            skills=skills,
            unsupported=unsupported,
            non_damage=non_damage,
        )
    except SkillEffectDataError as error:
        raise SkillEffectDataError(f"{source_path}: {error}") from error
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise SkillEffectDataError(f"{source_path}: {error}") from error
