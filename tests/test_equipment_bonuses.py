import unittest
from dataclasses import replace

from mhwilds_optimizer.equipment_bonuses import (
    activated_bonus_levels,
    collect_bonus_families,
)
from mhwilds_optimizer.equipment_models import (
    ArmorBonus,
    BonusRank,
    EquipmentInputError,
    SkillKind,
)
from tests.equipment_fixtures import make_tiny_catalog


def make_bonus_catalog():
    catalog = make_tiny_catalog()
    set_bonus = ArmorBonus(
        "skill:set", (BonusRank(2, 1), BonusRank(4, 2))
    )
    group_bonus = ArmorBonus("skill:group", (BonusRank(3, 1),))
    group_ids = {
        "armor:offense:head",
        "armor:base:chest",
        "armor:base:arms",
    }
    armor = tuple(
        replace(
            piece,
            set_bonus=set_bonus,
            group_bonus=group_bonus if piece.id in group_ids else None,
        )
        for piece in catalog.armor
    )
    return replace(catalog, armor=armor)


class BonusFamilyTests(unittest.TestCase):
    def test_collects_one_deterministic_family_per_kind_and_skill(self) -> None:
        catalog = make_bonus_catalog()

        result = collect_bonus_families(catalog)

        self.assertEqual(
            [(family.kind, family.skill_id) for family in result],
            [
                (SkillKind.GROUP, "skill:group"),
                (SkillKind.SET, "skill:set"),
            ],
        )
        self.assertEqual(
            result[0].armor_ids,
            (
                "armor:base:arms",
                "armor:base:chest",
                "armor:offense:head",
            ),
        )
        self.assertEqual(
            result[1].armor_ids,
            tuple(sorted(piece.id for piece in catalog.armor)),
        )
        self.assertEqual(
            result[1].ranks,
            (BonusRank(2, 1), BonusRank(4, 2)),
        )

    def test_rejects_an_unknown_selected_armor_id(self) -> None:
        with self.assertRaisesRegex(EquipmentInputError, "unknown selected armor"):
            activated_bonus_levels(make_bonus_catalog(), {"armor:missing:head"})


class ActivatedBonusLevelTests(unittest.TestCase):
    def test_activates_the_highest_reached_rank_at_every_boundary(self) -> None:
        catalog = make_bonus_catalog()
        ordered_ids = (
            "armor:critical:head",
            "armor:base:chest",
            "armor:base:arms",
            "armor:base:waist",
            "armor:base:legs",
        )
        expected_set_levels = (None, None, 1, 1, 2, 2)

        for count, expected_level in enumerate(expected_set_levels):
            with self.subTest(count=count):
                levels = activated_bonus_levels(catalog, ordered_ids[:count])
                self.assertEqual(levels.get("skill:set"), expected_level)

    def test_counts_shared_set_and_group_tags_independently(self) -> None:
        catalog = make_bonus_catalog()
        selected = {
            "armor:offense:head",
            "armor:base:chest",
            "armor:base:arms",
            "armor:base:waist",
        }

        levels = activated_bonus_levels(catalog, selected)

        self.assertEqual(levels, {"skill:group": 1, "skill:set": 2})
        with self.assertRaises(TypeError):
            levels["skill:set"] = 1  # type: ignore[index]

    def test_duplicate_selected_ids_do_not_inflate_piece_counts(self) -> None:
        catalog = make_bonus_catalog()

        levels = activated_bonus_levels(
            catalog,
            ["armor:critical:head", "armor:critical:head"],
        )

        self.assertEqual(levels, {})


if __name__ == "__main__":
    unittest.main()
