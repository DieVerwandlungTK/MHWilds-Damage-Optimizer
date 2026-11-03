import unittest

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


if __name__ == "__main__":
    unittest.main()
