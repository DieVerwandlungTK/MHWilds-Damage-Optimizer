import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

import mhwilds_optimizer.data_download as data_download
from mhwilds_optimizer.data_download import (
    MHDB_COMMIT,
    MHDB_FILES,
    MHDB_LICENSE,
    MHDB_REPOSITORY_URL,
    download_mhdb_data,
)


class DownloadDataTests(unittest.TestCase):
    def assert_no_download_artifacts(self, raw_root: Path) -> None:
        source_root = raw_root / "mhdb"
        self.assertFalse((source_root / MHDB_COMMIT).exists())
        self.assertEqual(list(source_root.iterdir()), [])

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

    def test_invalid_json_leaves_no_final_directory(self) -> None:
        payloads = {
            "Armor.json": b"[]",
            "Accessory.json": b"[]",
            "Amulet.json": b"[]",
            "Skill.json": b"[",
        }

        def fetch(url: str) -> bytes:
            return payloads[url.rsplit("/", 1)[-1]]

        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_root = Path(temporary_directory)

            with self.assertRaises(json.JSONDecodeError):
                download_mhdb_data(raw_root, fetch=fetch)

            self.assert_no_download_artifacts(raw_root)

    def test_fetch_failure_after_first_file_leaves_no_partial_download(self) -> None:
        calls = 0

        def fetch(_url: str) -> bytes:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("connection interrupted")
            return b"[]"

        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_root = Path(temporary_directory)

            with self.assertRaisesRegex(OSError, "connection interrupted"):
                download_mhdb_data(raw_root, fetch=fetch)

            self.assert_no_download_artifacts(raw_root)

    def test_reuses_verified_download_without_fetching(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_root = Path(temporary_directory)
            first_result = download_mhdb_data(raw_root, fetch=lambda _url: b"[]")

            def unexpected_fetch(_url: str) -> bytes:
                self.fail("verified downloads must not contact the network")

            second_result = download_mhdb_data(raw_root, fetch=unexpected_fetch)

            self.assertEqual(second_result, first_result)

    def test_rejects_tampered_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            raw_root = Path(temporary_directory)
            download_dir = download_mhdb_data(raw_root, fetch=lambda _url: b"[]")
            (download_dir / "Armor.json").write_bytes(b"[{}]")

            with self.assertRaisesRegex(
                data_download.DownloadVerificationError, "Armor.json"
            ):
                download_mhdb_data(raw_root, fetch=lambda _url: b"[]")

    def test_cli_help_documents_source_and_output(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_context:
            data_download.main(["--help"])

        self.assertEqual(exit_context.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("--source", help_text)
        self.assertIn("mhdb", help_text)
        self.assertIn("--output", help_text)
        self.assertIn("data/raw", help_text)


if __name__ == "__main__":
    unittest.main()
