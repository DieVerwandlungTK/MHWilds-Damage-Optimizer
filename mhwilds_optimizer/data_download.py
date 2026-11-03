"""Download pinned MHDB source data with a reproducibility manifest."""

from __future__ import annotations

import hashlib
import json
import tempfile
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

MHDB_REPOSITORY_URL = "https://github.com/LartTyler/mhdb-wilds-data"
MHDB_COMMIT = "c50a1eb892f4a1ad9bb35c147801658804be2cc2"
MHDB_LICENSE = {
    "id": "GPL-3.0",
    "url": f"{MHDB_REPOSITORY_URL}/blob/{MHDB_COMMIT}/LICENSE",
}
MHDB_FILES = ("Armor.json", "Accessory.json", "Amulet.json", "Skill.json")
MHDB_RAW_BASE_URL = (
    "https://raw.githubusercontent.com/LartTyler/mhdb-wilds-data/"
    f"{MHDB_COMMIT}/output/merged"
)

FetchBytes = Callable[[str], bytes]
Now = Callable[[], datetime]


class DownloadVerificationError(ValueError):
    """Raised when a completed source download fails integrity checks."""


def fetch_url(url: str) -> bytes:
    """Fetch a URL with a finite timeout."""
    with urlopen(url, timeout=30) as response:
        return response.read()


def utc_now() -> datetime:
    """Return the current timezone-aware UTC time."""
    return datetime.now(timezone.utc)


def _format_timestamp(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("retrieval timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def verify_mhdb_download(download_dir: Path) -> None:
    """Verify the pinned source identity, file set, JSON shape, and hashes."""
    expected_names = {*MHDB_FILES, "manifest.json"}
    try:
        actual_names = {path.name for path in download_dir.iterdir()}
    except OSError as error:
        raise DownloadVerificationError(
            f"cannot read download directory {download_dir}: {error}"
        ) from error
    if actual_names != expected_names:
        raise DownloadVerificationError(
            f"unexpected files in {download_dir}: expected {sorted(expected_names)}, "
            f"found {sorted(actual_names)}"
        )

    try:
        manifest = json.loads((download_dir / "manifest.json").read_text("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DownloadVerificationError(f"invalid manifest.json: {error}") from error

    expected_source = {
        "repository": MHDB_REPOSITORY_URL,
        "commit": MHDB_COMMIT,
        "license": MHDB_LICENSE,
    }
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise DownloadVerificationError("manifest.json has an unsupported schema")
    if manifest.get("source") != expected_source:
        raise DownloadVerificationError("manifest.json source does not match pinned MHDB data")
    entries = manifest.get("files")
    if not isinstance(entries, list) or [entry.get("name") for entry in entries] != list(
        MHDB_FILES
    ):
        raise DownloadVerificationError("manifest.json file list does not match pinned files")

    for entry in entries:
        name = entry["name"]
        expected_url = f"{MHDB_RAW_BASE_URL}/{name}"
        if entry.get("url") != expected_url:
            raise DownloadVerificationError(f"{name} has an unexpected source URL")
        try:
            payload = (download_dir / name).read_bytes()
        except OSError as error:
            raise DownloadVerificationError(f"cannot read {name}: {error}") from error
        if entry.get("size") != len(payload):
            raise DownloadVerificationError(f"{name} size does not match manifest")
        if entry.get("sha256") != hashlib.sha256(payload).hexdigest():
            raise DownloadVerificationError(f"{name} SHA-256 does not match manifest")
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError as error:
            raise DownloadVerificationError(f"{name} is invalid JSON: {error}") from error
        if not isinstance(parsed, list):
            raise DownloadVerificationError(f"{name} must contain a top-level JSON list")


def download_mhdb_data(
    raw_root: Path,
    *,
    fetch: FetchBytes = fetch_url,
    now: Now = utc_now,
) -> Path:
    """Download the pinned MHDB files and return their completed directory."""
    source_root = raw_root / "mhdb"
    source_root.mkdir(parents=True, exist_ok=True)
    target = source_root / MHDB_COMMIT
    if target.exists():
        verify_mhdb_download(target)
        return target
    with tempfile.TemporaryDirectory(
        prefix=f".{MHDB_COMMIT}-", dir=source_root
    ) as staging_name:
        staging = Path(staging_name)
        manifest_files: list[dict[str, object]] = []

        for name in MHDB_FILES:
            url = f"{MHDB_RAW_BASE_URL}/{name}"
            payload = fetch(url)
            parsed = json.loads(payload)
            if not isinstance(parsed, list):
                raise ValueError(f"{name} must contain a top-level JSON list")
            (staging / name).write_bytes(payload)
            manifest_files.append(
                {
                    "name": name,
                    "url": url,
                    "size": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            )

        manifest = {
            "schema_version": 1,
            "source": {
                "repository": MHDB_REPOSITORY_URL,
                "commit": MHDB_COMMIT,
                "license": MHDB_LICENSE,
            },
            "fetched_at": _format_timestamp(now()),
            "files": manifest_files,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staging.rename(target)
    verify_mhdb_download(target)
    return target
