import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from mhwilds_optimizer.data_download import (
    MHDB_COMMIT,
    MHDB_FILES,
    MHDB_LICENSE,
    MHDB_REPOSITORY_URL,
    download_mhdb_data,
)


class DownloadDataTests(unittest.TestCase):
    def test_downloads_pinned_files_and_writes_manifest(self) -> None:
        payloads = {
            "Armor.json": b'[{"game_id":1}]',
            "Accessory.json": b'[{"game_id":2}]',
            "Amulet.json": b'[{"game_id":3}]',
            "Skill.json": b'[{"game_id":4}]',
        }
        expected_hashes = {
            "Armor.json": "b1970985d1b0a6edfa1443ddb0aac77d8d581bb520a173f8e2f6640d3ceed367",
            "Accessory.json": "484f7c729cbd6104b247009eeaa19c74b5b73b4278ec8281b104c0ff349c7b0f",
            "Amulet.json": "becf4bdd2a58cafc2737facfe1ed06d63868e0ccbf571714a0da82e3df812c93",
            "Skill.json": "034fe042d7d8f993debdf003f1d2645cb5432f984e6770b3fb40350a46a77579",
        }
        fetched_urls: list[str] = []

        def fetch(url: str) -> bytes:
            fetched_urls.append(url)
            return payloads[url.rsplit("/", 1)[-1]]

        fixed_time = datetime(2026, 11, 3, 10, 20, 30, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_root = Path(temporary_directory)
            download_dir = download_mhdb_data(
                raw_root,
                fetch=fetch,
                now=lambda: fixed_time,
            )

            self.assertEqual(
                download_dir,
                raw_root / "mhdb" / "c50a1eb892f4a1ad9bb35c147801658804be2cc2",
            )
            self.assertEqual(MHDB_COMMIT, "c50a1eb892f4a1ad9bb35c147801658804be2cc2")
            self.assertEqual(
                fetched_urls,
                [
                    f"https://raw.githubusercontent.com/LartTyler/mhdb-wilds-data/{MHDB_COMMIT}/output/merged/{name}"
                    for name in ("Armor.json", "Accessory.json", "Amulet.json", "Skill.json")
                ],
            )
            self.assertEqual(MHDB_FILES, tuple(payloads))
            for name, payload in payloads.items():
                self.assertEqual((download_dir / name).read_bytes(), payload)

            manifest = json.loads((download_dir / "manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["source"]["repository"], MHDB_REPOSITORY_URL)
            self.assertEqual(manifest["source"]["commit"], MHDB_COMMIT)
            self.assertEqual(manifest["source"]["license"], MHDB_LICENSE)
            self.assertEqual(manifest["fetched_at"], "2026-11-03T10:20:30Z")
            self.assertEqual([item["name"] for item in manifest["files"]], list(payloads))
            for item in manifest["files"]:
                name = item["name"]
                self.assertEqual(item["url"], fetched_urls[list(payloads).index(name)])
                self.assertEqual(item["size"], len(payloads[name]))
                self.assertEqual(item["sha256"], expected_hashes[name])


if __name__ == "__main__":
    unittest.main()
