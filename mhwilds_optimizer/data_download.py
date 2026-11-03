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
    staging = Path(tempfile.mkdtemp(prefix=f".{MHDB_COMMIT}-", dir=source_root))
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
    return target
