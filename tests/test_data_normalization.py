import unittest

from mhwilds_optimizer.mhdb_normalizers import NormalizationError, normalize_skills


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


if __name__ == "__main__":
    unittest.main()
