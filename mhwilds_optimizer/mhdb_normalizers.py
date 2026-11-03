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


def _skill_levels(
    value: object, known_skills: Mapping[str, int], context: str
) -> dict[str, int]:
    source = _record(value, context)
    result: dict[str, int] = {}
    for source_key, level_value in source.items():
        try:
            normalized_id = skill_id(int(source_key))
        except (TypeError, ValueError) as error:
            raise NormalizationError(f"{context}: invalid skill ID {source_key!r}") from error
        if normalized_id not in known_skills:
            raise NormalizationError(f"{context}: unknown {normalized_id}")
        if type(level_value) is not int or not 0 < level_value <= known_skills[normalized_id]:
            raise NormalizationError(f"{context}.{normalized_id}: invalid level {level_value!r}")
        result[normalized_id] = level_value
    return dict(sorted(result.items()))


def _bonus(
    value: object, known_skills: Mapping[str, int], context: str
) -> dict[str, object] | None:
    if value is None:
        return None
    source = _record(value, context)
    source_skill = _integer(source, "skill_id", context)
    normalized_skill = skill_id(source_skill)
    if normalized_skill not in known_skills:
        raise NormalizationError(f"{context}: unknown {normalized_skill}")
    source_ranks = source.get("ranks")
    if not isinstance(source_ranks, list) or not source_ranks:
        raise NormalizationError(f"{context}.ranks: expected a non-empty list")
    ranks: list[dict[str, int]] = []
    for index, rank_value in enumerate(source_ranks):
        rank_context = f"{context}.ranks[{index}]"
        rank = _record(rank_value, rank_context)
        pieces = _positive_integer(rank, "pieces", rank_context)
        level = _positive_integer(rank, "skill_level", rank_context)
        if level > known_skills[normalized_skill]:
            raise NormalizationError(f"{rank_context}.skill_level: exceeds {normalized_skill}")
        ranks.append({"pieces": pieces, "skill_level": level})
    ranks.sort(key=lambda item: (item["pieces"], item["skill_level"]))
    return {"skill_id": normalized_skill, "ranks": ranks}


def _slots(value: object, context: str) -> list[int]:
    if not isinstance(value, list):
        raise NormalizationError(f"{context}: expected a list")
    if any(type(level) is not int or level not in {1, 2, 3} for level in value):
        raise NormalizationError(f"{context}: slot levels must be 1 through 3")
    return list(value)


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


def normalize_armor(
    records: list[object], known_skills: Mapping[str, int]
) -> list[dict[str, object]]:
    """Flatten armor sets into stable armor-piece records."""
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    valid_parts = {"head", "chest", "arms", "waist", "legs"}
    for set_index, set_value in enumerate(records):
        set_record = _record(set_value, f"armor sets[{set_index}]")
        source_set_id = _integer(set_record, "game_id", f"armor sets[{set_index}]")
        context = f"armor set {source_set_id}"
        set_names = _names(set_record, context)
        rarity = _positive_integer(set_record, "rarity", context)
        set_bonus = _bonus(set_record.get("set_bonus"), known_skills, f"{context}.set_bonus")
        group_bonus = _bonus(
            set_record.get("group_bonus"), known_skills, f"{context}.group_bonus"
        )
        pieces = set_record.get("pieces")
        if not isinstance(pieces, list):
            raise NormalizationError(f"{context}.pieces: expected a list")
        seen_parts: set[str] = set()
        for piece_index, piece_value in enumerate(pieces):
            piece_context = f"{context}.pieces[{piece_index}]"
            piece = _record(piece_value, piece_context)
            part = piece.get("kind")
            if part not in valid_parts:
                raise NormalizationError(f"{piece_context}.kind: unsupported {part!r}")
            if part in seen_parts:
                raise NormalizationError(f"{context}: duplicate armor part {part}")
            seen_parts.add(part)
            normalized_id = f"armor:{source_set_id}:{part}"
            if normalized_id in seen_ids:
                raise NormalizationError(f"{piece_context}: duplicate ID {normalized_id}")
            seen_ids.add(normalized_id)
            normalized.append(
                {
                    "id": normalized_id,
                    "source_set_id": source_set_id,
                    "set_names": set_names,
                    "names": _names(piece, piece_context),
                    "part": part,
                    "rarity": rarity,
                    "slots": _slots(piece.get("slots"), f"{piece_context}.slots"),
                    "skills": _skill_levels(
                        piece.get("skills"), known_skills, f"{piece_context}.skills"
                    ),
                    "set_bonus": set_bonus,
                    "group_bonus": group_bonus,
                }
            )
    return sorted(normalized, key=lambda item: str(item["id"]))


def normalize_decorations(
    records: list[object], known_skills: Mapping[str, int]
) -> list[dict[str, object]]:
    """Normalize weapon and armor decorations without mixing their slot types."""
    normalized: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, value in enumerate(records):
        record = _record(value, f"decorations[{index}]")
        source_id = _integer(record, "game_id", f"decorations[{index}]")
        context = f"decoration {source_id}"
        normalized_id = f"decoration:{source_id}"
        if normalized_id in seen_ids:
            raise NormalizationError(f"{context}: duplicate game_id")
        seen_ids.add(normalized_id)
        slot_type = record.get("allowed_on")
        if slot_type not in {"weapon", "armor"}:
            raise NormalizationError(f"{context}.allowed_on: unsupported {slot_type!r}")
        slot_level = _positive_integer(record, "level", context)
        if slot_level > 3:
            raise NormalizationError(f"{context}.level: slot level must be 1 through 3")
        normalized.append(
            {
                "id": normalized_id,
                "source_id": source_id,
                "names": _names(record, context),
                "slot_type": slot_type,
                "required_slot_level": slot_level,
                "rarity": _positive_integer(record, "rarity", context),
                "skills": _skill_levels(
                    record.get("skills"), known_skills, f"{context}.skills"
                ),
            }
        )
    return sorted(normalized, key=lambda item: str(item["id"]))


def normalize_regular_charms(
    records: list[object], known_skills: Mapping[str, int]
) -> tuple[list[dict[str, object]], int]:
    """Flatten regular amulet ranks and report excluded random parents."""
    normalized: list[dict[str, object]] = []
    excluded_random = 0
    seen_ids: set[str] = set()
    for index, value in enumerate(records):
        record = _record(value, f"amulets[{index}]")
        source_id = _integer(record, "game_id", f"amulets[{index}]")
        context = f"amulet {source_id}"
        is_random = record.get("is_random")
        if type(is_random) is not bool:
            raise NormalizationError(f"{context}.is_random: expected a boolean")
        if is_random:
            excluded_random += 1
            continue
        ranks = record.get("ranks")
        if not isinstance(ranks, list) or not ranks:
            raise NormalizationError(f"{context}.ranks: expected a non-empty list")
        seen_ranks: set[int] = set()
        for rank_index, rank_value in enumerate(ranks):
            rank_context = f"{context}.ranks[{rank_index}]"
            rank = _record(rank_value, rank_context)
            level = _positive_integer(rank, "level", rank_context)
            if level in seen_ranks:
                raise NormalizationError(f"{rank_context}.level: duplicate {level}")
            seen_ranks.add(level)
            normalized_id = f"regular_charm:{source_id}:{level}"
            if normalized_id in seen_ids:
                raise NormalizationError(f"{rank_context}: duplicate ID {normalized_id}")
            seen_ids.add(normalized_id)
            normalized.append(
                {
                    "id": normalized_id,
                    "source_id": source_id,
                    "rank": level,
                    "names": _names(rank, rank_context),
                    "rarity": _positive_integer(rank, "rarity", rank_context),
                    "skills": _skill_levels(
                        rank.get("skills"), known_skills, f"{rank_context}.skills"
                    ),
                    "slots": [],
                }
            )
    return sorted(normalized, key=lambda item: str(item["id"])), excluded_random
