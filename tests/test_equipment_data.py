import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from mhwilds_optimizer.equipment_data import (
    EquipmentDataError,
    load_equipment_catalog,
)
from mhwilds_optimizer.equipment_models import ArmorPart, BonusRank, SkillKind, SlotType


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def dataset_payloads() -> dict[str, object]:
    skills = [
        {
            "id": "skill:attack",
            "source_id": 1,
            "names": {"ja": "攻撃", "en": "Attack"},
            "kind": "armor",
            "max_level": 3,
            "ranks": [{"level": 1}, {"level": 2}, {"level": 3}],
        },
        {
            "id": "skill:weapon",
            "source_id": 2,
            "names": {"ja": "武器技", "en": "Weapon Skill"},
            "kind": "weapon",
            "max_level": 1,
            "ranks": [{"level": 1}],
        },
        {
            "id": "skill:set",
            "source_id": 3,
            "names": {"ja": "シリーズ", "en": "Set Bonus"},
            "kind": "set",
            "max_level": 2,
            "ranks": [
                {"level": 1, "set_pieces_required": 2},
                {"level": 2, "set_pieces_required": 4},
            ],
        },
        {
            "id": "skill:group",
            "source_id": 4,
            "names": {"ja": "グループ", "en": "Group Bonus"},
            "kind": "group",
            "max_level": 1,
            "ranks": [{"level": 1, "set_pieces_required": 3}],
        },
    ]
    armor = [
        {
            "id": "armor:10:head",
            "source_set_id": 10,
            "set_names": {"ja": "試作", "en": "Prototype"},
            "names": {"ja": "試作頭", "en": "Prototype Helm"},
            "part": "head",
            "rarity": 8,
            "slots": [3, 1],
            "skills": {"skill:attack": 1},
            "set_bonus": {
                "skill_id": "skill:set",
                "ranks": [
                    {"pieces": 2, "skill_level": 1},
                    {"pieces": 2, "skill_level": 1},
                    {"pieces": 4, "skill_level": 2},
                ],
            },
            "group_bonus": {
                "skill_id": "skill:group",
                "ranks": [{"pieces": 3, "skill_level": 1}],
            },
        }
    ]
    decorations = [
        {
            "id": "decoration:20",
            "source_id": 20,
            "names": {"ja": "攻撃珠", "en": "Attack Jewel"},
            "slot_type": "armor",
            "required_slot_level": 2,
            "rarity": 6,
            "skills": {"skill:attack": 1},
        },
        {
            "id": "decoration:21",
            "source_id": 21,
            "names": {"ja": "武器珠", "en": "Weapon Jewel"},
            "slot_type": "weapon",
            "required_slot_level": 1,
            "rarity": 6,
            "skills": {"skill:weapon": 1},
        },
    ]
    charms = [
        {
            "id": "regular_charm:30:1",
            "source_id": 30,
            "rank": 1,
            "names": {"ja": "攻撃の護石", "en": "Attack Charm"},
            "rarity": 5,
            "skills": {"skill:attack": 1},
            "slots": [],
        }
    ]
    return {
        "skills.json": skills,
        "armor.json": armor,
        "decorations.json": decorations,
        "regular_charms.json": charms,
        "validation_report.json": {
            "counts": {
                "skills": len(skills),
                "armor": len(armor),
                "decorations": len(decorations),
                "regular_charms": len(charms),
            },
            "warnings": [],
            "errors": [],
        },
    }


def write_dataset(root: Path, payloads: dict[str, object]) -> None:
    entries = []
    for name, value in payloads.items():
        payload = json_bytes(value)
        (root / name).write_bytes(payload)
        entries.append(
            {
                "name": name,
                "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    manifest = {
        "schema_version": 1,
        "source": {"repository": "https://example.invalid", "commit": "abc"},
        "generated_at": "2026-11-04T00:00:00Z",
        "counts": {
            "skills": len(payloads["skills.json"]),  # type: ignore[arg-type]
            "armor": len(payloads["armor.json"]),  # type: ignore[arg-type]
            "decorations": len(payloads["decorations.json"]),  # type: ignore[arg-type]
            "regular_charms": len(payloads["regular_charms.json"]),  # type: ignore[arg-type]
        },
        "files": entries,
    }
    (root / "manifest.json").write_bytes(json_bytes(manifest))


class EquipmentDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.payloads = dataset_payloads()
        write_dataset(self.root, self.payloads)

    def rewrite_manifest(self, update) -> None:
        manifest_path = self.root / "manifest.json"
        manifest = json.loads(manifest_path.read_bytes())
        update(manifest)
        manifest_path.write_bytes(json_bytes(manifest))

    def test_loads_verified_normalized_records_into_typed_catalog(self) -> None:
        catalog = load_equipment_catalog(self.root)

        self.assertEqual(
            [(skill.id, skill.kind, skill.max_level) for skill in catalog.skills],
            [
                ("skill:attack", SkillKind.ARMOR, 3),
                ("skill:weapon", SkillKind.WEAPON, 1),
                ("skill:set", SkillKind.SET, 2),
                ("skill:group", SkillKind.GROUP, 1),
            ],
        )
        self.assertEqual(catalog.armor[0].id, "armor:10:head")
        self.assertEqual(catalog.armor[0].part, ArmorPart.HEAD)
        self.assertEqual(catalog.armor[0].slots, (3, 1))
        self.assertEqual(catalog.armor[0].skills, {"skill:attack": 1})
        self.assertEqual(catalog.armor[0].set_bonus.skill_id, "skill:set")
        self.assertEqual(
            catalog.armor[0].set_bonus.ranks,
            (BonusRank(2, 1), BonusRank(4, 2)),
        )
        self.assertEqual(catalog.armor[0].group_bonus.skill_id, "skill:group")
        self.assertEqual(catalog.armor[0].group_bonus.ranks, (BonusRank(3, 1),))
        self.assertEqual(
            [decoration.slot_type for decoration in catalog.decorations],
            [SlotType.ARMOR, SlotType.WEAPON],
        )
        self.assertEqual(catalog.charms[0].id, "regular_charm:30:1")

    def test_rejects_malformed_json_with_file_context(self) -> None:
        (self.root / "armor.json").write_text("{", encoding="utf-8")

        with self.assertRaisesRegex(EquipmentDataError, "armor.json"):
            load_equipment_catalog(self.root)

    def test_rejects_file_changed_after_manifest_hashing(self) -> None:
        with (self.root / "armor.json").open("ab") as stream:
            stream.write(b" ")

        with self.assertRaisesRegex(EquipmentDataError, "armor.json.*(size|SHA-256)"):
            load_equipment_catalog(self.root)

    def test_rejects_manifest_count_mismatch(self) -> None:
        self.rewrite_manifest(lambda manifest: manifest["counts"].update(armor=2))

        with self.assertRaisesRegex(EquipmentDataError, "armor.json.*count"):
            load_equipment_catalog(self.root)

    def test_rejects_missing_consumed_file_entry(self) -> None:
        self.rewrite_manifest(
            lambda manifest: manifest.update(
                files=[
                    entry
                    for entry in manifest["files"]
                    if entry["name"] != "armor.json"
                ]
            )
        )

        with self.assertRaisesRegex(EquipmentDataError, "armor.json.*manifest"):
            load_equipment_catalog(self.root)

    def test_rejects_non_list_top_level_payload(self) -> None:
        payloads = dataset_payloads()
        payloads["armor.json"] = {"not": "a list"}
        write_dataset(self.root, payloads)

        with self.assertRaisesRegex(EquipmentDataError, "armor.json.*list"):
            load_equipment_catalog(self.root)

    def test_rejects_unknown_skill_reference_with_record_context(self) -> None:
        payloads = dataset_payloads()
        armor = payloads["armor.json"]
        armor[0]["skills"] = {"skill:missing": 1}  # type: ignore[index]
        write_dataset(self.root, payloads)

        with self.assertRaisesRegex(
            EquipmentDataError, "armor:10:head.*skill:missing"
        ):
            load_equipment_catalog(self.root)

    def test_rejects_conflicting_bonus_ranks_with_record_context(self) -> None:
        payloads = dataset_payloads()
        armor = payloads["armor.json"]
        armor[0]["set_bonus"]["ranks"] = [  # type: ignore[index]
            {"pieces": 2, "skill_level": 1},
            {"pieces": 2, "skill_level": 2},
        ]
        write_dataset(self.root, payloads)

        with self.assertRaisesRegex(
            EquipmentDataError, r"armor\.json\[0\].*armor:10:head"
        ):
            load_equipment_catalog(self.root)


if __name__ == "__main__":
    unittest.main()
