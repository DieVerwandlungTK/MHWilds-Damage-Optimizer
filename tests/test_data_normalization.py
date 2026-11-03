import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

from mhwilds_optimizer.data_download import MHDB_COMMIT, download_mhdb_data
import mhwilds_optimizer.data_normalization as data_normalization
from mhwilds_optimizer.data_normalization import (
    NormalizationVerificationError,
    normalize_mhdb_data,
    verify_normalized_data,
)

from mhwilds_optimizer.mhdb_normalizers import (
    NormalizationError,
    normalize_armor,
    normalize_decorations,
    normalize_regular_charms,
    normalize_skills,
)


class SkillNormalizationTests(unittest.TestCase):
    def test_normalizes_skill_identity_names_kind_and_ranks(self) -> None:
        records = [
            {
                "game_id": 2,
                "names": {"ja": "防具技", "en": "Armor Skill", "fr": "ignore"},
                "kind": "armor",
                "ranks": [{"level": 1}, {"level": 3}],
            },
            {
                "game_id": -1,
                "names": {"ja": "シリーズ技", "en": "Set Skill"},
                "kind": "set",
                "ranks": [
                    {"level": 1, "set_pieces_required": 2},
                    {"level": 2, "set_pieces_required": 4},
                ],
            },
        ]

        result = normalize_skills(records)

        self.assertEqual(
            result,
            [
                {
                    "id": "skill:-1",
                    "source_id": -1,
                    "names": {"ja": "シリーズ技", "en": "Set Skill"},
                    "kind": "set",
                    "max_level": 2,
                    "ranks": [
                        {"level": 1, "set_pieces_required": 2},
                        {"level": 2, "set_pieces_required": 4},
                    ],
                },
                {
                    "id": "skill:2",
                    "source_id": 2,
                    "names": {"ja": "防具技", "en": "Armor Skill"},
                    "kind": "armor",
                    "max_level": 3,
                    "ranks": [{"level": 1}, {"level": 3}],
                },
            ],
        )

    def test_rejects_missing_english_skill_name_with_context(self) -> None:
        records = [
            {
                "game_id": 42,
                "names": {"ja": "日本語のみ"},
                "kind": "armor",
                "ranks": [{"level": 1}],
            }
        ]

        with self.assertRaisesRegex(NormalizationError, r"42.*names\.en"):
            normalize_skills(records)


class EquipmentNormalizationTests(unittest.TestCase):
    def test_normalizes_partial_armor_set_with_bonuses(self) -> None:
        records = [
            {
                "game_id": 100,
                "names": {"ja": "試作一式", "en": "Prototype Set"},
                "rarity": 8,
                "set_bonus": {
                    "skill_id": 20,
                    "ranks": [{"pieces": 2, "skill_level": 1}],
                },
                "group_bonus": {
                    "skill_id": 30,
                    "ranks": [{"pieces": 3, "skill_level": 1}],
                },
                "pieces": [
                    {
                        "kind": "head",
                        "names": {"ja": "試作頭", "en": "Prototype Helm"},
                        "slots": [3, 1],
                        "skills": {"10": 2},
                    }
                ],
            }
        ]

        result = normalize_armor(
            records,
            {"skill:10": 3, "skill:20": 2, "skill:30": 1},
        )

        self.assertEqual(
            result,
            [
                {
                    "id": "armor:100:head",
                    "source_set_id": 100,
                    "set_names": {"ja": "試作一式", "en": "Prototype Set"},
                    "names": {"ja": "試作頭", "en": "Prototype Helm"},
                    "part": "head",
                    "rarity": 8,
                    "slots": [3, 1],
                    "skills": {"skill:10": 2},
                    "set_bonus": {
                        "skill_id": "skill:20",
                        "ranks": [{"pieces": 2, "skill_level": 1}],
                    },
                    "group_bonus": {
                        "skill_id": "skill:30",
                        "ranks": [{"pieces": 3, "skill_level": 1}],
                    },
                }
            ],
        )

    def test_rejects_duplicate_armor_part_and_unknown_skill(self) -> None:
        base_piece = {
            "kind": "head",
            "names": {"ja": "頭", "en": "Head"},
            "slots": [],
            "skills": {"10": 1},
        }
        with self.subTest("duplicate part"):
            records = [
                {
                    "game_id": 1,
                    "names": {"ja": "一式", "en": "Set"},
                    "rarity": 1,
                    "set_bonus": None,
                    "group_bonus": None,
                    "pieces": [base_piece, dict(base_piece)],
                }
            ]
            with self.assertRaisesRegex(NormalizationError, "duplicate.*head"):
                normalize_armor(records, {"skill:10": 1})

        with self.subTest("unknown skill"):
            records = [
                {
                    "game_id": 2,
                    "names": {"ja": "一式", "en": "Set"},
                    "rarity": 1,
                    "set_bonus": None,
                    "group_bonus": None,
                    "pieces": [{**base_piece, "skills": {"999": 1}}],
                }
            ]
            with self.assertRaisesRegex(NormalizationError, "skill:999"):
                normalize_armor(records, {"skill:10": 1})

    def test_normalizes_weapon_and_armor_decorations(self) -> None:
        records = [
            {
                "game_id": 6,
                "names": {"ja": "防具珠", "en": "Armor Jewel"},
                "allowed_on": "armor",
                "level": 2,
                "rarity": 5,
                "skills": {"10": 1},
            },
            {
                "game_id": -5,
                "names": {"ja": "武器珠", "en": "Weapon Jewel"},
                "allowed_on": "weapon",
                "level": 3,
                "rarity": 7,
                "skills": {"11": 2},
            },
        ]

        result = normalize_decorations(records, {"skill:10": 1, "skill:11": 2})

        self.assertEqual(
            result,
            [
                {
                    "id": "decoration:-5",
                    "source_id": -5,
                    "names": {"ja": "武器珠", "en": "Weapon Jewel"},
                    "slot_type": "weapon",
                    "required_slot_level": 3,
                    "rarity": 7,
                    "skills": {"skill:11": 2},
                },
                {
                    "id": "decoration:6",
                    "source_id": 6,
                    "names": {"ja": "防具珠", "en": "Armor Jewel"},
                    "slot_type": "armor",
                    "required_slot_level": 2,
                    "rarity": 5,
                    "skills": {"skill:10": 1},
                },
            ],
        )

    def test_flattens_regular_charm_ranks_and_reports_random_records(self) -> None:
        records = [
            {
                "game_id": 50,
                "is_random": False,
                "ranks": [
                    {
                        "level": 1,
                        "names": {"ja": "護石Ⅰ", "en": "Charm I"},
                        "rarity": 3,
                        "skills": {"10": 1},
                    },
                    {
                        "level": 2,
                        "names": {"ja": "護石Ⅱ", "en": "Charm II"},
                        "rarity": 5,
                        "skills": {"10": 2},
                    },
                ],
            },
            {"game_id": 60, "is_random": True, "ranks": []},
        ]

        charms, excluded = normalize_regular_charms(records, {"skill:10": 2})

        self.assertEqual(excluded, 1)
        self.assertEqual(
            charms,
            [
                {
                    "id": "regular_charm:50:1",
                    "source_id": 50,
                    "rank": 1,
                    "names": {"ja": "護石Ⅰ", "en": "Charm I"},
                    "rarity": 3,
                    "skills": {"skill:10": 1},
                    "slots": [],
                },
                {
                    "id": "regular_charm:50:2",
                    "source_id": 50,
                    "rank": 2,
                    "names": {"ja": "護石Ⅱ", "en": "Charm II"},
                    "rarity": 5,
                    "skills": {"skill:10": 2},
                    "slots": [],
                },
            ],
        )

    def test_rejects_unknown_equipment_skill_reference(self) -> None:
        decoration = {
            "game_id": 1,
            "names": {"ja": "珠", "en": "Jewel"},
            "allowed_on": "armor",
            "level": 1,
            "rarity": 1,
            "skills": {"999": 1},
        }
        with self.subTest("decoration"):
            with self.assertRaisesRegex(NormalizationError, "skill:999"):
                normalize_decorations([decoration], {"skill:10": 1})

        amulet = {
            "game_id": 2,
            "is_random": False,
            "ranks": [
                {
                    "level": 1,
                    "names": {"ja": "護石", "en": "Charm"},
                    "rarity": 1,
                    "skills": {"999": 1},
                }
            ],
        }
        with self.subTest("charm"):
            with self.assertRaisesRegex(NormalizationError, "skill:999"):
                normalize_regular_charms([amulet], {"skill:10": 1})


class DatasetNormalizationTests(unittest.TestCase):
    def create_raw_data(self, raw_root: Path, *, unknown_skill: bool = False) -> Path:
        skill_reference = "999" if unknown_skill else "10"
        payloads = {
            "Skill.json": [
                {
                    "game_id": 10,
                    "names": {"ja": "技", "en": "Skill"},
                    "kind": "armor",
                    "ranks": [{"level": 1}],
                }
            ],
            "Armor.json": [
                {
                    "game_id": 1,
                    "names": {"ja": "一式", "en": "Set"},
                    "rarity": 1,
                    "set_bonus": None,
                    "group_bonus": None,
                    "pieces": [
                        {
                            "kind": "head",
                            "names": {"ja": "頭", "en": "Head"},
                            "slots": [1],
                            "skills": {skill_reference: 1},
                        }
                    ],
                }
            ],
            "Accessory.json": [
                {
                    "game_id": 2,
                    "names": {"ja": "珠", "en": "Jewel"},
                    "allowed_on": "armor",
                    "level": 1,
                    "rarity": 1,
                    "skills": {"10": 1},
                }
            ],
            "Amulet.json": [
                {
                    "game_id": 3,
                    "is_random": False,
                    "ranks": [
                        {
                            "level": 1,
                            "names": {"ja": "護石", "en": "Charm"},
                            "rarity": 1,
                            "skills": {"10": 1},
                        }
                    ],
                },
                {"game_id": 4, "is_random": True, "ranks": []},
            ],
        }

        def fetch(url: str) -> bytes:
            name = url.rsplit("/", 1)[-1]
            return json.dumps(payloads[name], ensure_ascii=False).encode()

        return download_mhdb_data(
            raw_root,
            fetch=fetch,
            now=lambda: datetime(2026, 11, 3, tzinfo=timezone.utc),
        )

    def test_writes_all_outputs_manifest_and_report(self) -> None:
        expected_hashes = {
            "skills.json": "f9e552fe4af0e80c1cb23a14be9475e6a35614e791a1d4a9daab533f22f0cb38",
            "armor.json": "44a070d9259290b3073ab348da31706e8ede9db8f66c9492dfff2d9a09b9491d",
            "decorations.json": "f10b4a81cbf4f39a1566ebf4873ce90ae13c1982847ce41f86b85017e57160cf",
            "regular_charms.json": "58c138e6307c6fdc951593ce58e4f769cf52e37288fa36d99dc8fcb269f172a2",
            "validation_report.json": "d374a8350cbaee796432e78f05717eab18097997e40b4c5522845cb71f3eadda",
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            raw_dir = self.create_raw_data(root / "raw")
            raw_manifest_hash = hashlib.sha256(
                (raw_dir / "manifest.json").read_bytes()
            ).hexdigest()

            output_dir = normalize_mhdb_data(
                root / "raw",
                root / "normalized",
                now=lambda: datetime(2026, 11, 3, 12, 30, tzinfo=timezone.utc),
            )

            self.assertEqual(output_dir, root / "normalized" / "mhdb" / MHDB_COMMIT)
            self.assertEqual(
                {path.name for path in output_dir.iterdir()},
                {*expected_hashes, "manifest.json"},
            )
            manifest = json.loads((output_dir / "manifest.json").read_text())
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["source"]["commit"], MHDB_COMMIT)
            self.assertEqual(manifest["source"]["raw_manifest_sha256"], raw_manifest_hash)
            self.assertEqual(manifest["generated_at"], "2026-11-03T12:30:00Z")
            self.assertEqual(manifest["counts"], {
                "skills": 1,
                "armor": 1,
                "decorations": 1,
                "regular_charms": 1,
            })
            for entry in manifest["files"]:
                self.assertEqual(entry["sha256"], expected_hashes[entry["name"]])
                self.assertEqual(entry["size"], (output_dir / entry["name"]).stat().st_size)
            report = json.loads((output_dir / "validation_report.json").read_text())
            self.assertEqual(report["excluded_random_charm_records"], 1)
            verify_normalized_data(
                output_dir, raw_manifest_sha256=raw_manifest_hash
            )

    def test_source_validation_failure_leaves_no_final_or_staging_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.create_raw_data(root / "raw", unknown_skill=True)

            with self.assertRaisesRegex(NormalizationError, "skill:999"):
                normalize_mhdb_data(root / "raw", root / "normalized")

            source_root = root / "normalized" / "mhdb"
            self.assertFalse((source_root / MHDB_COMMIT).exists())
            if source_root.exists():
                self.assertEqual(list(source_root.iterdir()), [])

    def test_reuses_verified_dataset_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.create_raw_data(root / "raw")
            output_dir = normalize_mhdb_data(root / "raw", root / "normalized")
            manifest_path = output_dir / "manifest.json"
            original_bytes = manifest_path.read_bytes()
            original_mtime = manifest_path.stat().st_mtime_ns

            second_result = normalize_mhdb_data(root / "raw", root / "normalized")

            self.assertEqual(second_result, output_dir)
            self.assertEqual(manifest_path.read_bytes(), original_bytes)
            self.assertEqual(manifest_path.stat().st_mtime_ns, original_mtime)

    def test_rejects_tampered_normalized_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            self.create_raw_data(root / "raw")
            output_dir = normalize_mhdb_data(root / "raw", root / "normalized")
            (output_dir / "armor.json").write_bytes(b"[]")

            with self.assertRaisesRegex(NormalizationVerificationError, "armor.json"):
                normalize_mhdb_data(root / "raw", root / "normalized")

    def test_cli_help_documents_input_and_output(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as exit_context:
            data_normalization.main(["--help"])

        self.assertEqual(exit_context.exception.code, 0)
        help_text = output.getvalue()
        self.assertIn("--input", help_text)
        self.assertIn("data/raw", help_text)
        self.assertIn("--output", help_text)
        self.assertIn("data/normalized", help_text)


if __name__ == "__main__":
    unittest.main()
