"""Pure validation and normalization for MHDB merged records."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class NormalizationError(ValueError):
    """Raised when MHDB source data cannot be normalized safely."""


def _record(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise NormalizationError(f"{context}: expected an object")
    return value


def _integer(record: Mapping[str, Any], key: str, context: str) -> int:
    value = record.get(key)
    if type(value) is not int:
        raise NormalizationError(f"{context}.{key}: expected an integer")
    return value


def _positive_integer(record: Mapping[str, Any], key: str, context: str) -> int:
    value = _integer(record, key, context)
    if value <= 0:
        raise NormalizationError(f"{context}.{key}: expected a positive integer")
    return value


def _names(record: Mapping[str, Any], context: str) -> dict[str, str]:
    names = _record(record.get("names"), f"{context}.names")
    result: dict[str, str] = {}
    for language in ("ja", "en"):
        value = names.get(language)
        if not isinstance(value, str) or not value.strip():
            raise NormalizationError(f"{context}.names.{language}: expected a name")
        result[language] = value
    return result


def skill_id(source_id: int) -> str:
    return f"skill:{source_id}"


def normalize_skills(records: list[object]) -> list[dict[str, object]]:
    """Normalize MHDB skills into stable, minimal records."""
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(records):
        initial_context = f"skills[{index}]"
        record = _record(value, initial_context)
        source_id = _integer(record, "game_id", initial_context)
        context = f"skill {source_id}"
        normalized_id = skill_id(source_id)
        if normalized_id in seen_ids:
            raise NormalizationError(f"{context}: duplicate game_id")
        seen_ids.add(normalized_id)
        kind = record.get("kind")
        if kind not in {"armor", "weapon", "set", "group"}:
            raise NormalizationError(f"{context}.kind: unsupported value {kind!r}")
        source_ranks = record.get("ranks")
        if not isinstance(source_ranks, list) or not source_ranks:
            raise NormalizationError(f"{context}.ranks: expected a non-empty list")
        ranks: list[dict[str, int]] = []
        seen_levels: set[int] = set()
        for rank_index, rank_value in enumerate(source_ranks):
            rank_context = f"{context}.ranks[{rank_index}]"
            rank = _record(rank_value, rank_context)
            level = _positive_integer(rank, "level", rank_context)
            if level in seen_levels:
                raise NormalizationError(f"{rank_context}.level: duplicate {level}")
            seen_levels.add(level)
            normalized_rank = {"level": level}
            if "set_pieces_required" in rank:
                normalized_rank["set_pieces_required"] = _positive_integer(
                    rank, "set_pieces_required", rank_context
                )
            ranks.append(normalized_rank)
        ranks.sort(key=lambda item: item["level"])
        normalized.append(
            {
                "id": normalized_id,
                "source_id": source_id,
                "names": _names(record, context),
                "kind": kind,
                "max_level": max(seen_levels),
                "ranks": ranks,
            }
        )
    return sorted(normalized, key=lambda item: str(item["id"]))
