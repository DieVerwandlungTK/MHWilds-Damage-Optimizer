"""Generate and verify local normalized optimizer data from pinned MHDB JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path

from mhwilds_optimizer.data_download import (
    MHDB_COMMIT,
    MHDB_REPOSITORY_URL,
    verify_mhdb_download,
)
from mhwilds_optimizer.mhdb_normalizers import (
    normalize_armor,
    normalize_decorations,
    normalize_regular_charms,
    normalize_skills,
)

OUTPUT_FILES = (
    "skills.json",
    "armor.json",
    "decorations.json",
    "regular_charms.json",
    "validation_report.json",
)
Now = Callable[[], datetime]


class NormalizationVerificationError(ValueError):
    """Raised when a normalized dataset fails provenance or integrity checks."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("normalization timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def verify_normalized_data(
    normalized_dir: Path, *, raw_manifest_sha256: str
) -> None:
    """Verify normalized file set, provenance, hashes, and JSON shape."""
    expected_names = {*OUTPUT_FILES, "manifest.json"}
    try:
        actual_names = {path.name for path in normalized_dir.iterdir()}
    except OSError as error:
        raise NormalizationVerificationError(
            f"cannot read normalized directory {normalized_dir}: {error}"
        ) from error
    if actual_names != expected_names:
        raise NormalizationVerificationError(
            f"unexpected normalized files: expected {sorted(expected_names)}, "
            f"found {sorted(actual_names)}"
        )
    try:
        manifest = json.loads((normalized_dir / "manifest.json").read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise NormalizationVerificationError(f"invalid manifest.json: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise NormalizationVerificationError("manifest.json has an unsupported schema")
    source = manifest.get("source")
    if not isinstance(source, dict) or source.get("commit") != MHDB_COMMIT:
        raise NormalizationVerificationError("manifest.json has an unexpected source commit")
    if source.get("raw_manifest_sha256") != raw_manifest_sha256:
        raise NormalizationVerificationError("raw manifest SHA-256 does not match")
    entries = manifest.get("files")
    if (
        not isinstance(entries, list)
        or any(not isinstance(entry, dict) for entry in entries)
        or [entry.get("name") for entry in entries] != list(OUTPUT_FILES)
    ):
        raise NormalizationVerificationError("manifest.json output file list does not match")
    parsed_outputs: dict[str, object] = {}
    for entry in entries:
        name = entry["name"]
        try:
            payload = (normalized_dir / name).read_bytes()
            parsed_outputs[name] = json.loads(payload)
        except (OSError, json.JSONDecodeError) as error:
            raise NormalizationVerificationError(f"invalid {name}: {error}") from error
        if entry.get("size") != len(payload):
            raise NormalizationVerificationError(f"{name} size does not match manifest")
        if entry.get("sha256") != hashlib.sha256(payload).hexdigest():
            raise NormalizationVerificationError(f"{name} SHA-256 does not match manifest")
    counts = manifest.get("counts")
    expected_counts = {
        "skills": len(parsed_outputs["skills.json"]),
        "armor": len(parsed_outputs["armor.json"]),
        "decorations": len(parsed_outputs["decorations.json"]),
        "regular_charms": len(parsed_outputs["regular_charms.json"]),
    }
    if counts != expected_counts:
        raise NormalizationVerificationError("manifest.json counts do not match outputs")


def normalize_mhdb_data(
    raw_root: Path,
    normalized_root: Path,
    *,
    now: Now = utc_now,
) -> Path:
    """Transform verified raw MHDB files into a normalized local dataset."""
    raw_dir = raw_root / "mhdb" / MHDB_COMMIT
    verify_mhdb_download(raw_dir)
    raw_manifest_hash = hashlib.sha256((raw_dir / "manifest.json").read_bytes()).hexdigest()
    source_root = normalized_root / "mhdb"
    target = source_root / MHDB_COMMIT
    if target.exists():
        verify_normalized_data(target, raw_manifest_sha256=raw_manifest_hash)
        return target
    raw = {
        name: json.loads((raw_dir / name).read_bytes())
        for name in ("Skill.json", "Armor.json", "Accessory.json", "Amulet.json")
    }
    skills = normalize_skills(raw["Skill.json"])
    known_skills = {str(item["id"]): int(item["max_level"]) for item in skills}
    armor = normalize_armor(raw["Armor.json"], known_skills)
    decorations = normalize_decorations(raw["Accessory.json"], known_skills)
    regular_charms, excluded_random = normalize_regular_charms(
        raw["Amulet.json"], known_skills
    )
    counts = {
        "skills": len(skills),
        "armor": len(armor),
        "decorations": len(decorations),
        "regular_charms": len(regular_charms),
    }
    outputs: dict[str, object] = {
        "skills.json": skills,
        "armor.json": armor,
        "decorations.json": decorations,
        "regular_charms.json": regular_charms,
        "validation_report.json": {
            "counts": counts,
            "excluded_random_charm_records": excluded_random,
            "warnings": [
                f"excluded {excluded_random} random amulet record(s) from regular charms"
            ],
            "errors": [],
        },
    }
    source_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{MHDB_COMMIT}-", dir=source_root
    ) as staging_name:
        staging = Path(staging_name)
        manifest_files: list[dict[str, object]] = []
        for name in OUTPUT_FILES:
            payload = _json_bytes(outputs[name])
            (staging / name).write_bytes(payload)
            manifest_files.append(
                {
                    "name": name,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        manifest = {
            "schema_version": 1,
            "source": {
                "repository": MHDB_REPOSITORY_URL,
                "commit": MHDB_COMMIT,
                "raw_manifest_sha256": raw_manifest_hash,
            },
            "generated_at": _timestamp(now()),
            "counts": counts,
            "files": manifest_files,
        }
        (staging / "manifest.json").write_bytes(_json_bytes(manifest))
        staging.rename(target)
    verify_normalized_data(target, raw_manifest_sha256=raw_manifest_hash)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    """Run the MHDB normalization command."""
    parser = argparse.ArgumentParser(description="Normalize pinned MHDB source data")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/raw"),
        help="raw data root (default: data/raw)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/normalized"),
        help="normalized data root (default: data/normalized)",
    )
    arguments = parser.parse_args(argv)
    output_dir = normalize_mhdb_data(arguments.input, arguments.output)
    print(output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
