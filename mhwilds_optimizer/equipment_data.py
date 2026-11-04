"""Load a verified normalized MHDB directory into equipment models."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from mhwilds_optimizer.equipment_models import (
    ArmorBonus,
    ArmorPart,
    ArmorPiece,
    BonusRank,
    Decoration,
    EquipmentCatalog,
    EquipmentInputError,
    RegularCharm,
    SkillDefinition,
    SkillKind,
    SlotType,
)

CONSUMED_FILES = {
    "skills.json": "skills",
    "armor.json": "armor",
    "decorations.json": "decorations",
    "regular_charms.json": "regular_charms",
}


class EquipmentDataError(ValueError):
    """Raised when normalized equipment data fails integrity or shape checks."""


def _read_json(path: Path, context: str) -> tuple[bytes, object]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise EquipmentDataError(f"{context}: cannot read file: {error}") from error
    try:
        return payload, json.loads(payload)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise EquipmentDataError(f"{context}: invalid JSON: {error}") from error


def _record(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EquipmentDataError(f"{context}: expected an object")
    return value


def _records(value: object, context: str) -> list[object]:
    if not isinstance(value, list):
        raise EquipmentDataError(f"{context}: expected a list")
    return value


def _identifier(record: Mapping[str, Any], context: str) -> str:
    value = record.get("id")
    if not isinstance(value, str) or not value.strip():
        raise EquipmentDataError(f"{context}.id: expected a non-empty string")
    return value


def _mapping(record: Mapping[str, Any], field: str, context: str) -> Mapping[str, int]:
    value = record.get(field)
    if not isinstance(value, Mapping):
        raise EquipmentDataError(f"{context}.{field}: expected an object")
    return value  # type: ignore[return-value]


def _slots(record: Mapping[str, Any], context: str) -> tuple[int, ...]:
    value = record.get("slots")
    if not isinstance(value, list):
        raise EquipmentDataError(f"{context}.slots: expected a list")
    return tuple(value)


def _bonus(
    record: Mapping[str, Any], field: str, context: str
) -> ArmorBonus | None:
    value = record.get(field)
    if value is None:
        return None
    bonus_record = _record(value, f"{context}.{field}")
    skill_id = bonus_record.get("skill_id")
    if not isinstance(skill_id, str) or not skill_id.strip():
        raise EquipmentDataError(
            f"{context}.{field}.skill_id: expected a non-empty string"
        )
    rank_values = bonus_record.get("ranks")
    if not isinstance(rank_values, list):
        raise EquipmentDataError(f"{context}.{field}.ranks: expected a list")
    try:
        ranks: list[BonusRank] = []
        for index, rank_value in enumerate(rank_values):
            rank = _record(rank_value, f"{context}.{field}.ranks[{index}]")
            ranks.append(
                BonusRank(
                    rank.get("pieces"),  # type: ignore[arg-type]
                    rank.get("skill_level"),  # type: ignore[arg-type]
                )
            )
        return ArmorBonus(skill_id, tuple(ranks))
    except EquipmentInputError as error:
        raise EquipmentDataError(f"{context}.{field}: {error}") from error


def _enum(enum_type, value: object, context: str):
    try:
        return enum_type(value)
    except (TypeError, ValueError) as error:
        raise EquipmentDataError(f"{context}: unsupported value {value!r}") from error


def _manifest_entries(manifest: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    value = manifest.get("files")
    if not isinstance(value, list):
        raise EquipmentDataError("manifest.json.files: expected a list")
    entries: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(value):
        entry = _record(item, f"manifest.json.files[{index}]")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise EquipmentDataError(
                f"manifest.json.files[{index}].name: expected a file name"
            )
        if name in entries:
            raise EquipmentDataError(f"manifest.json.files: duplicate entry {name}")
        entries[name] = entry
    return entries


def _verified_payloads(
    normalized_dir: Path, manifest: Mapping[str, Any]
) -> dict[str, list[object]]:
    entries = _manifest_entries(manifest)
    counts = _record(manifest.get("counts"), "manifest.json.counts")
    result: dict[str, list[object]] = {}
    for name, count_key in CONSUMED_FILES.items():
        entry = entries.get(name)
        if entry is None:
            raise EquipmentDataError(f"{name}: missing manifest entry")
        payload, parsed = _read_json(normalized_dir / name, name)
        expected_size = entry.get("size")
        if type(expected_size) is not int or expected_size != len(payload):
            raise EquipmentDataError(f"{name}: size does not match manifest")
        expected_hash = entry.get("sha256")
        if (
            not isinstance(expected_hash, str)
            or hashlib.sha256(payload).hexdigest() != expected_hash
        ):
            raise EquipmentDataError(f"{name}: SHA-256 does not match manifest")
        records = _records(parsed, name)
        expected_count = counts.get(count_key)
        if type(expected_count) is not int or expected_count != len(records):
            raise EquipmentDataError(f"{name}: count does not match manifest")
        result[name] = records
    return result


def _skills(records: list[object]) -> tuple[SkillDefinition, ...]:
    result: list[SkillDefinition] = []
    for index, value in enumerate(records):
        initial_context = f"skills.json[{index}]"
        record = _record(value, initial_context)
        identifier = _identifier(record, initial_context)
        context = f"{initial_context} ({identifier})"
        result.append(
            SkillDefinition(
                identifier,
                _enum(SkillKind, record.get("kind"), f"{context}.kind"),
                record.get("max_level"),  # type: ignore[arg-type]
            )
        )
    return tuple(result)


def _armor(records: list[object]) -> tuple[ArmorPiece, ...]:
    result: list[ArmorPiece] = []
    for index, value in enumerate(records):
        initial_context = f"armor.json[{index}]"
        record = _record(value, initial_context)
        identifier = _identifier(record, initial_context)
        context = f"{initial_context} ({identifier})"
        result.append(
            ArmorPiece(
                identifier,
                _enum(ArmorPart, record.get("part"), f"{context}.part"),
                _mapping(record, "skills", context),
                _slots(record, context),
                _bonus(record, "set_bonus", context),
                _bonus(record, "group_bonus", context),
            )
        )
    return tuple(result)


def _decorations(records: list[object]) -> tuple[Decoration, ...]:
    result: list[Decoration] = []
    for index, value in enumerate(records):
        initial_context = f"decorations.json[{index}]"
        record = _record(value, initial_context)
        identifier = _identifier(record, initial_context)
        context = f"{initial_context} ({identifier})"
        result.append(
            Decoration(
                identifier,
                _enum(SlotType, record.get("slot_type"), f"{context}.slot_type"),
                record.get("required_slot_level"),  # type: ignore[arg-type]
                _mapping(record, "skills", context),
            )
        )
    return tuple(result)


def _charms(records: list[object]) -> tuple[RegularCharm, ...]:
    result: list[RegularCharm] = []
    for index, value in enumerate(records):
        initial_context = f"regular_charms.json[{index}]"
        record = _record(value, initial_context)
        identifier = _identifier(record, initial_context)
        context = f"{initial_context} ({identifier})"
        result.append(
            RegularCharm(
                identifier,
                _mapping(record, "skills", context),
                _slots(record, context),
            )
        )
    return tuple(result)


def load_equipment_catalog(normalized_dir: Path) -> EquipmentCatalog:
    """Verify normalized files and return their solver-facing representation."""
    if not isinstance(normalized_dir, Path):
        raise EquipmentDataError("normalized_dir must be a Path")
    _, manifest_value = _read_json(normalized_dir / "manifest.json", "manifest.json")
    manifest = _record(manifest_value, "manifest.json")
    if type(manifest.get("schema_version")) is not int or manifest.get(
        "schema_version"
    ) != 1:
        raise EquipmentDataError("manifest.json has an unsupported schema_version")
    payloads = _verified_payloads(normalized_dir, manifest)
    try:
        return EquipmentCatalog(
            skills=_skills(payloads["skills.json"]),
            armor=_armor(payloads["armor.json"]),
            decorations=_decorations(payloads["decorations.json"]),
            charms=_charms(payloads["regular_charms.json"]),
        )
    except EquipmentDataError:
        raise
    except (EquipmentInputError, TypeError, ValueError) as error:
        raise EquipmentDataError(f"normalized equipment: {error}") from error
