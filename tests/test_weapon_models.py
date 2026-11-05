import unittest
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal

from mhwilds_optimizer.damage_models import DamageInputError, Sharpness
from mhwilds_optimizer.weapon_models import (
    ElementType,
    Weapon,
    WeaponInputError,
    combat_stats_from_weapon,
)


def valid_weapon() -> Weapon:
    return Weapon(
        id="weapon:test",
        name="Test Blades",
        raw=Decimal("210"),
        element_type=ElementType.FIRE,
        element=Decimal("24"),
        affinity_percent=Decimal("15"),
        sharpness=Sharpness.WHITE,
        slots=(3, 2, 1),
        skills={"skill:z": 1, "skill:a": 2},
    )


class WeaponModelTests(unittest.TestCase):
    def test_accepts_and_freezes_a_complete_weapon(self) -> None:
        weapon = valid_weapon()

        self.assertEqual(weapon.id, "weapon:test")
        self.assertEqual(weapon.name, "Test Blades")
        self.assertEqual(weapon.raw, Decimal("210"))
        self.assertEqual(weapon.element_type, ElementType.FIRE)
        self.assertEqual(weapon.element, Decimal("24"))
        self.assertEqual(weapon.affinity_percent, Decimal("15"))
        self.assertEqual(weapon.sharpness, Sharpness.WHITE)
        self.assertEqual(weapon.slots, (3, 2, 1))
        self.assertEqual(tuple(weapon.skills), ("skill:a", "skill:z"))
        with self.assertRaises(TypeError):
            weapon.skills["skill:new"] = 1  # type: ignore[index]
        with self.assertRaises(FrozenInstanceError):
            weapon.raw = Decimal("220")  # type: ignore[misc]

    def test_rejects_empty_identity_fields(self) -> None:
        for field in ("id", "name"):
            with self.subTest(field=field):
                with self.assertRaisesRegex(WeaponInputError, field):
                    replace(valid_weapon(), **{field: " "})

    def test_rejects_invalid_numeric_values(self) -> None:
        cases = (
            ("raw", 210),
            ("raw", Decimal("NaN")),
            ("raw", Decimal("-1")),
            ("element", 24.0),
            ("element", Decimal("Infinity")),
            ("element", Decimal("-1")),
            ("affinity_percent", 15),
            ("affinity_percent", Decimal("-100.1")),
            ("affinity_percent", Decimal("100.1")),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with self.assertRaisesRegex(WeaponInputError, field):
                    replace(valid_weapon(), **{field: value})

    def test_rejects_inconsistent_element_type_and_value(self) -> None:
        with self.assertRaisesRegex(WeaponInputError, "element"):
            replace(
                valid_weapon(),
                element_type=ElementType.NONE,
                element=Decimal("1"),
            )
        with self.assertRaisesRegex(WeaponInputError, "element"):
            replace(valid_weapon(), element=Decimal("0"))
        with self.assertRaisesRegex(WeaponInputError, "element_type"):
            replace(valid_weapon(), element_type="fire")  # type: ignore[arg-type]

    def test_rejects_invalid_sharpness_and_slots(self) -> None:
        with self.assertRaisesRegex(WeaponInputError, "sharpness"):
            replace(valid_weapon(), sharpness="white")  # type: ignore[arg-type]

        for slots in ([3, 2, 1], (0,), (4,), (True,)):
            with self.subTest(slots=slots):
                with self.assertRaisesRegex(WeaponInputError, "slots"):
                    replace(valid_weapon(), slots=slots)  # type: ignore[arg-type]

    def test_rejects_invalid_skill_mappings(self) -> None:
        cases = (
            (("skill:a", 1),),
            {" ": 1},
            {"skill:a": 0},
            {"skill:a": True},
        )
        for skills in cases:
            with self.subTest(skills=skills):
                with self.assertRaisesRegex(WeaponInputError, "skills"):
                    replace(valid_weapon(), skills=skills)  # type: ignore[arg-type]


class WeaponDamageAdapterTests(unittest.TestCase):
    def test_builds_combat_stats_from_weapon_and_combat_state(self) -> None:
        stats = combat_stats_from_weapon(
            valid_weapon(),
            positive_critical_modifier=Decimal("1.25"),
            negative_critical_modifier=Decimal("0.75"),
            demon_dodge_buff=True,
        )

        self.assertEqual(stats.raw, Decimal("210"))
        self.assertEqual(stats.element, Decimal("24"))
        self.assertEqual(stats.affinity_percent, Decimal("15"))
        self.assertEqual(stats.sharpness, Sharpness.WHITE)
        self.assertEqual(stats.positive_critical_modifier, Decimal("1.25"))
        self.assertEqual(stats.negative_critical_modifier, Decimal("0.75"))
        self.assertEqual(stats.raw_damage_modifier, Decimal("1"))
        self.assertEqual(stats.element_damage_modifier, Decimal("1"))
        self.assertEqual(stats.positive_element_critical_modifier, Decimal("1"))
        self.assertIs(stats.demon_dodge_buff, True)

    def test_preserves_combat_stats_validation(self) -> None:
        cases = (
            ("positive_critical_modifier", Decimal("0")),
            ("negative_critical_modifier", Decimal("-1")),
            ("demon_dodge_buff", 1),
        )
        for field, value in cases:
            with self.subTest(field=field):
                arguments = {
                    "positive_critical_modifier": Decimal("1.25"),
                    "negative_critical_modifier": Decimal("0.75"),
                    "demon_dodge_buff": False,
                }
                arguments[field] = value
                with self.assertRaisesRegex(DamageInputError, field):
                    combat_stats_from_weapon(valid_weapon(), **arguments)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
