"""Load source-traceable combo definitions bundled with the optimizer."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    CROSS_CHECKED = "cross_checked"
    VERIFIED = "verified"


@dataclass(frozen=True)
class SourceReference:
    name: str
    url: str
    checked_at: date
    supports: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    index: int
    move_id: str
    move_hit_index: int
    motion_value: Decimal
    element_modifier: Decimal
    damage_type: str


@dataclass(frozen=True)
class Combo:
    id: str
    weapon_type: str
    game_version: str
    checked_through_version: str
    verification_status: VerificationStatus
    sources: tuple[SourceReference, ...]
    hits: tuple[Hit, ...]


class ComboDataError(ValueError):
    """Raised when bundled or supplied combo data violates its schema."""


def _default_path() -> Path:
    return Path(__file__).with_name("data") / "combos" / "dual_blades.json"


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ComboDataError(f"{field} must be an object")
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        raise ComboDataError(f"{field} must be an array")
    return value


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ComboDataError(f"{field} must be a non-empty string")
    return value


def _decimal(value: object, field: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise ComboDataError(f"{field} must be a JSON number")
    if positive and value <= 0:
        raise ComboDataError(f"{field} must be positive")
    return value


def _integer(value: object, field: str) -> int:
    number = _decimal(value, field)
    if number != number.to_integral_value():
        raise ComboDataError(f"{field} must be an integer")
    return int(number)


def _field(record: dict[str, object], name: str, context: str = "") -> object:
    try:
        return record[name]
    except KeyError as error:
        prefix = f"{context}." if context else ""
        raise ComboDataError(f"missing {prefix}{name}") from error


def load_combo(
    combo_id: str = "dual_blades:demon_dance_1_3",
    path: Path | None = None,
) -> Combo:
    """Load one combo by stable ID."""
    source_path = path if path is not None else _default_path()
    try:
        with source_path.open(encoding="utf-8") as source_file:
            raw_payload = json.load(
                source_file, parse_float=Decimal, parse_int=Decimal
            )
        payload = _object(raw_payload, "root")
        if _integer(_field(payload, "schema_version"), "schema_version") != 1:
            raise ComboDataError("schema_version must be 1")
        game_version = _text(_field(payload, "game_version"), "game_version")
        checked_version = _text(
            _field(payload, "checked_through_version"), "checked_through_version"
        )
        status_value = _text(
            _field(payload, "verification_status"), "verification_status"
        )
        try:
            verification_status = VerificationStatus(status_value)
        except ValueError as error:
            raise ComboDataError(
                f"verification_status is invalid: {status_value}"
            ) from error

        sources_list = _array(_field(payload, "sources"), "sources")
        if not sources_list:
            raise ComboDataError("sources must not be empty")
        sources: list[SourceReference] = []
        for source_index, raw_source in enumerate(sources_list):
            context = f"sources[{source_index}]"
            source = _object(raw_source, context)
            checked_at_value = _text(
                _field(source, "checked_at", context), f"{context}.checked_at"
            )
            try:
                checked_at = date.fromisoformat(checked_at_value)
            except ValueError as error:
                raise ComboDataError(
                    f"{context}.checked_at is not an ISO date"
                ) from error
            raw_supports = _array(
                _field(source, "supports", context), f"{context}.supports"
            )
            if not raw_supports:
                raise ComboDataError(f"{context}.supports must not be empty")
            supports = tuple(
                _text(value, f"{context}.supports[{index}]")
                for index, value in enumerate(raw_supports)
            )
            sources.append(
                SourceReference(
                    name=_text(_field(source, "name", context), f"{context}.name"),
                    url=_text(_field(source, "url", context), f"{context}.url"),
                    checked_at=checked_at,
                    supports=supports,
                )
            )

        combo_records = _array(_field(payload, "combos"), "combos")
        combo_ids: list[str] = []
        parsed_records: list[dict[str, object]] = []
        for combo_index, raw_record in enumerate(combo_records):
            context = f"combos[{combo_index}]"
            parsed_record = _object(raw_record, context)
            combo_ids.append(
                _text(_field(parsed_record, "id", context), f"{context}.id")
            )
            parsed_records.append(parsed_record)
        if len(combo_ids) != len(set(combo_ids)):
            raise ComboDataError("combo id values must be unique")
        matching = [
            record
            for record, record_id in zip(parsed_records, combo_ids, strict=True)
            if record_id == combo_id
        ]
        if not matching:
            raise ComboDataError(f"unknown combo id: {combo_id}")
        record = matching[0]

        moves = _array(_field(record, "moves", "combo"), "combo.moves")
        expected_moves = ["demon_dance_1", "demon_dance_2", "demon_dance_3"]
        if moves != expected_moves:
            raise ComboDataError(f"move_id sequence must be {expected_moves}")
        hit_records = _array(_field(record, "hits", "combo"), "combo.hits")
        if len(hit_records) != 27:
            raise ComboDataError("hits must contain exactly 27 records")
        expected_hit_moves = (
            ["demon_dance_1"] * 12
            + ["demon_dance_2"] * 4
            + ["demon_dance_3"] * 11
        )
        per_move_indexes = (
            list(range(1, 13)) + list(range(1, 5)) + list(range(1, 12))
        )
        hits: list[Hit] = []
        for position, raw_hit in enumerate(hit_records, start=1):
            context = f"hits[{position - 1}]"
            hit = _object(raw_hit, context)
            index = _integer(_field(hit, "index", context), f"{context}.index")
            if index != position:
                raise ComboDataError(f"{context}.index must be {position}")
            move_id = _text(
                _field(hit, "move_id", context), f"{context}.move_id"
            )
            if move_id != expected_hit_moves[position - 1]:
                raise ComboDataError(
                    f"{context}.move_id must be {expected_hit_moves[position - 1]}"
                )
            move_hit_index = _integer(
                _field(hit, "move_hit_index", context),
                f"{context}.move_hit_index",
            )
            if move_hit_index != per_move_indexes[position - 1]:
                raise ComboDataError(
                    f"{context}.move_hit_index must be {per_move_indexes[position - 1]}"
                )
            damage_type = _text(
                _field(hit, "damage_type", context), f"{context}.damage_type"
            )
            if damage_type != "sever":
                raise ComboDataError(f"{context}.damage_type must be sever")
            hits.append(
                Hit(
                    index=index,
                    move_id=move_id,
                    move_hit_index=move_hit_index,
                    motion_value=_decimal(
                        _field(hit, "motion_value", context),
                        f"{context}.motion_value",
                        positive=True,
                    ),
                    element_modifier=_decimal(
                        _field(hit, "element_modifier", context),
                        f"{context}.element_modifier",
                        positive=True,
                    ),
                    damage_type=damage_type,
                )
            )
        return Combo(
            id=combo_id,
            weapon_type=_text(
                _field(record, "weapon_type", "combo"), "combo.weapon_type"
            ),
            game_version=game_version,
            checked_through_version=checked_version,
            verification_status=verification_status,
            sources=tuple(sources),
            hits=tuple(hits),
        )
    except ComboDataError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise ComboDataError(f"cannot load combo data from {source_path}: {error}") from error
