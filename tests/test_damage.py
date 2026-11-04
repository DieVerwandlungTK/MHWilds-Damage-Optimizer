import unittest
from dataclasses import replace
from decimal import Decimal

from mhwilds_optimizer.combo_data import Hit, VerificationStatus, load_combo
from mhwilds_optimizer.damage import (
    UnverifiedDamageError,
    calculate_combo_damage,
    calculate_hit_damage,
)
from mhwilds_optimizer.damage_models import (
    DEFAULT_DAMAGE_RULES,
    CalculationMode,
    CombatStats,
    DamageInputError,
    Sharpness,
    TargetHitzones,
)


def valid_stats() -> CombatStats:
    return CombatStats(
        raw=Decimal("100"),
        element=Decimal("20"),
        affinity_percent=Decimal("25"),
        positive_critical_modifier=Decimal("1.25"),
        negative_critical_modifier=Decimal("0.75"),
        sharpness=Sharpness.WHITE,
        demon_dodge_buff=False,
    )


def valid_target() -> TargetHitzones:
    return TargetHitzones(
        sever=Decimal("60"),
        element=Decimal("20"),
        monster_damage_modifier=Decimal("1"),
    )


class DamageModelTests(unittest.TestCase):
    def test_accepts_valid_combat_stats_and_target(self) -> None:
        stats = valid_stats()
        target = valid_target()

        self.assertEqual(stats.raw, Decimal("100"))
        self.assertEqual(stats.sharpness, Sharpness.WHITE)
        self.assertEqual(stats.raw_damage_modifier, Decimal("1"))
        self.assertEqual(stats.element_damage_modifier, Decimal("1"))
        self.assertEqual(stats.positive_element_critical_modifier, Decimal("1"))
        self.assertEqual(target.sever, Decimal("60"))

    def test_default_rules_use_sourced_sharpness_modifiers(self) -> None:
        expected = {
            Sharpness.RED: ("0.5", "0.25"),
            Sharpness.ORANGE: ("0.75", "0.5"),
            Sharpness.YELLOW: ("1", "0.75"),
            Sharpness.GREEN: ("1.05", "1"),
            Sharpness.BLUE: ("1.2", "1.0625"),
            Sharpness.WHITE: ("1.32", "1.15"),
        }

        self.assertEqual(set(DEFAULT_DAMAGE_RULES.sharpness), set(expected))
        for color, (raw, element) in expected.items():
            with self.subTest(color=color):
                modifiers = DEFAULT_DAMAGE_RULES.sharpness[color]
                self.assertEqual(modifiers.raw, Decimal(raw))
                self.assertEqual(modifiers.element, Decimal(element))

    def test_rejects_invalid_combat_stats(self) -> None:
        cases = {
            "raw": Decimal("-1"),
            "element": Decimal("-1"),
            "affinity_percent": Decimal("100.1"),
            "positive_critical_modifier": Decimal("0"),
            "negative_critical_modifier": Decimal("-0.1"),
            "sharpness": "white",
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(DamageInputError, field):
                    replace(valid_stats(), **{field: value})

        with self.assertRaisesRegex(DamageInputError, "affinity_percent"):
            replace(valid_stats(), affinity_percent=Decimal("-100.1"))
        with self.assertRaisesRegex(DamageInputError, "raw"):
            replace(valid_stats(), raw=100)  # type: ignore[arg-type]

    def test_rejects_invalid_skill_damage_modifiers(self) -> None:
        fields = (
            "raw_damage_modifier",
            "element_damage_modifier",
            "positive_element_critical_modifier",
        )
        invalid_values = (
            1,
            1.0,
            Decimal("0"),
            Decimal("-0.1"),
            Decimal("Infinity"),
        )
        for field in fields:
            for value in invalid_values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(DamageInputError, field):
                        replace(valid_stats(), **{field: value})

    def test_rejects_invalid_target_hitzones_and_multiplier(self) -> None:
        cases = {
            "sever": Decimal("100.1"),
            "element": Decimal("-0.1"),
            "monster_damage_modifier": Decimal("0"),
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(DamageInputError, field):
                    replace(valid_target(), **{field: value})

    def test_rejects_non_finite_decimal_inputs(self) -> None:
        cases = (
            ("raw", lambda: replace(valid_stats(), raw=Decimal("Infinity"))),
            (
                "affinity_percent",
                lambda: replace(valid_stats(), affinity_percent=Decimal("NaN")),
            ),
            (
                "monster_damage_modifier",
                lambda: replace(
                    valid_target(), monster_damage_modifier=Decimal("Infinity")
                ),
            ),
        )
        for field, construct in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(DamageInputError, field):
                    construct()


class ContinuousHitDamageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hit = Hit(
            index=1,
            move_id="test_move",
            move_hit_index=1,
            motion_value=Decimal("10"),
            element_modifier=Decimal("0.6"),
            damage_type="sever",
        )
        self.stats = replace(
            valid_stats(),
            affinity_percent=Decimal("0"),
            sharpness=Sharpness.GREEN,
        )
        self.target = replace(valid_target(), element=Decimal("25"))

    def calculate(self, **stats_changes: object):
        stats = replace(self.stats, **stats_changes)
        return calculate_hit_damage(stats, self.hit, self.target)

    def test_calculates_unrounded_physical_elemental_and_total(self) -> None:
        result = self.calculate()

        self.assertEqual(result.physical, Decimal("6.3000"))
        self.assertEqual(result.elemental, Decimal("3.000"))
        self.assertEqual(result.total, Decimal("9.3000"))
        self.assertEqual(result.expected_critical_modifier, Decimal("1"))
        self.assertEqual(result.mode, CalculationMode.CONTINUOUS_APPROX)
        self.assertEqual(result.verification_status, VerificationStatus.CROSS_CHECKED)
        self.assertTrue(any("cross_checked" in warning for warning in result.warnings))

    def test_positive_affinity_uses_positive_critical_modifier(self) -> None:
        result = self.calculate(affinity_percent=Decimal("40"))

        self.assertEqual(result.expected_critical_modifier, Decimal("1.10"))
        self.assertEqual(result.physical, Decimal("6.930000"))

    def test_negative_affinity_uses_negative_critical_modifier(self) -> None:
        result = self.calculate(affinity_percent=Decimal("-40"))

        self.assertEqual(result.expected_critical_modifier, Decimal("0.90"))
        self.assertEqual(result.physical, Decimal("5.670000"))

    def test_raw_damage_modifier_affects_only_physical_once(self) -> None:
        result = self.calculate(raw_damage_modifier=Decimal("1.2"))

        self.assertEqual(result.physical, Decimal("7.56000"))
        self.assertEqual(result.elemental, Decimal("3.000"))

    def test_element_damage_modifier_affects_only_elemental_once(self) -> None:
        result = self.calculate(element_damage_modifier=Decimal("1.3"))

        self.assertEqual(result.physical, Decimal("6.3000"))
        self.assertEqual(result.elemental, Decimal("3.9000"))

    def test_positive_affinity_applies_element_critical_modifier(self) -> None:
        result = self.calculate(
            affinity_percent=Decimal("40"),
            positive_element_critical_modifier=Decimal("1.25"),
        )

        self.assertEqual(result.physical, Decimal("6.930000"))
        self.assertEqual(result.elemental, Decimal("3.30000"))

    def test_negative_affinity_does_not_reduce_elemental_damage(self) -> None:
        result = self.calculate(
            affinity_percent=Decimal("-40"),
            positive_element_critical_modifier=Decimal("1.25"),
        )

        self.assertEqual(result.physical, Decimal("5.670000"))
        self.assertEqual(result.elemental, Decimal("3.000"))

    def test_skill_modifiers_compose_with_demon_dodge_once(self) -> None:
        result = self.calculate(
            affinity_percent=Decimal("40"),
            demon_dodge_buff=True,
            raw_damage_modifier=Decimal("1.2"),
            element_damage_modifier=Decimal("1.3"),
            positive_element_critical_modifier=Decimal("1.25"),
        )

        self.assertEqual(result.physical, Decimal("9.56340000"))
        self.assertEqual(result.elemental, Decimal("5.5770000"))

    def test_demon_dodge_uses_separate_raw_and_element_modifiers(self) -> None:
        result = self.calculate(demon_dodge_buff=True)

        self.assertEqual(result.physical, Decimal("7.24500"))
        self.assertEqual(result.elemental, Decimal("3.9000"))

    def test_monster_modifier_affects_both_components_once(self) -> None:
        target = replace(self.target, monster_damage_modifier=Decimal("1.2"))

        result = calculate_hit_damage(self.stats, self.hit, target)

        self.assertEqual(result.physical, Decimal("7.56000"))
        self.assertEqual(result.elemental, Decimal("3.6000"))

    def test_zero_stats_and_hitzones_produce_zero_components(self) -> None:
        stats = replace(self.stats, raw=Decimal("0"), element=Decimal("0"))
        target = replace(self.target, sever=Decimal("0"), element=Decimal("0"))

        result = calculate_hit_damage(stats, self.hit, target)

        self.assertEqual(result.physical, Decimal("0"))
        self.assertEqual(result.elemental, Decimal("0"))
        self.assertEqual(result.total, Decimal("0"))

    def test_rejects_invalid_manually_constructed_hit(self) -> None:
        cases = (
            ("motion_value", replace(self.hit, motion_value=Decimal("-1"))),
            ("element_modifier", replace(self.hit, element_modifier=Decimal("0"))),
            ("motion_value", replace(self.hit, motion_value=0.5)),
            ("damage_type", replace(self.hit, damage_type="blunt")),
        )
        for field, hit in cases:
            with self.subTest(field=field, value=getattr(hit, field)):
                with self.assertRaisesRegex(DamageInputError, field):
                    calculate_hit_damage(self.stats, hit, self.target)


class ContinuousComboDamageTests(unittest.TestCase):
    def test_aggregates_ordered_hits_and_propagates_weakest_status(self) -> None:
        combo = load_combo()
        stats = replace(
            valid_stats(),
            affinity_percent=Decimal("0"),
            sharpness=Sharpness.GREEN,
        )
        target = replace(valid_target(), element=Decimal("25"))
        verified_rules = replace(
            DEFAULT_DAMAGE_RULES,
            verification_status=VerificationStatus.VERIFIED,
        )

        result = calculate_combo_damage(
            combo,
            stats,
            target,
            rules=verified_rules,
            mode=CalculationMode.CONTINUOUS_APPROX,
        )

        self.assertEqual(result.combo_id, "dual_blades:demon_dance_1_3")
        self.assertEqual([item.hit.index for item in result.hits], list(range(1, 28)))
        self.assertEqual(result.physical, Decimal("247.59"))
        self.assertEqual(result.elemental, Decimal("100"))
        self.assertEqual(result.total, Decimal("347.59"))
        self.assertEqual(result.verification_status, VerificationStatus.CROSS_CHECKED)
        self.assertTrue(any("cross_checked" in warning for warning in result.warnings))


class GameExactDamageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.combo = load_combo()
        self.hit = Hit(
            index=1,
            move_id="rounding_test",
            move_hit_index=1,
            motion_value=Decimal("8"),
            element_modifier=Decimal("0.6"),
            damage_type="sever",
        )
        self.stats = CombatStats(
            raw=Decimal("117"),
            element=Decimal("19"),
            affinity_percent=Decimal("0"),
            positive_critical_modifier=Decimal("1.25"),
            negative_critical_modifier=Decimal("0.75"),
            sharpness=Sharpness.GREEN,
            demon_dodge_buff=False,
        )
        self.target = TargetHitzones(
            sever=Decimal("60"),
            element=Decimal("25"),
            monster_damage_modifier=Decimal("1"),
        )
        self.verified_rules = replace(
            DEFAULT_DAMAGE_RULES,
            verification_status=VerificationStatus.VERIFIED,
        )

    def test_rejects_cross_checked_combo_data_in_exact_mode(self) -> None:
        with self.assertRaisesRegex(UnverifiedDamageError, "data"):
            calculate_combo_damage(
                self.combo,
                self.stats,
                self.target,
                rules=self.verified_rules,
                mode=CalculationMode.GAME_EXACT,
            )

    def test_empty_combo_cannot_bypass_exact_mode_data_gate(self) -> None:
        empty_combo = replace(self.combo, hits=())

        with self.assertRaisesRegex(UnverifiedDamageError, "data"):
            calculate_combo_damage(
                empty_combo,
                self.stats,
                self.target,
                rules=self.verified_rules,
                mode=CalculationMode.GAME_EXACT,
            )

    def test_rejects_cross_checked_rules_in_exact_mode(self) -> None:
        verified_combo = replace(
            self.combo,
            verification_status=VerificationStatus.VERIFIED,
        )

        with self.assertRaisesRegex(UnverifiedDamageError, "rules"):
            calculate_combo_damage(
                verified_combo,
                self.stats,
                self.target,
                mode=CalculationMode.GAME_EXACT,
            )

    def test_rounds_each_verified_hit_component_half_up(self) -> None:
        result = calculate_hit_damage(
            self.stats,
            self.hit,
            self.target,
            rules=self.verified_rules,
            data_status=VerificationStatus.VERIFIED,
            mode=CalculationMode.GAME_EXACT,
        )

        self.assertEqual(result.physical, Decimal("5.9"))
        self.assertEqual(result.elemental, Decimal("2.9"))
        self.assertEqual(result.total, Decimal("8.8"))
        self.assertEqual(result.warnings, ())

    def test_sums_rounded_hits_without_rerounding_combo_totals(self) -> None:
        verified_combo = replace(
            self.combo,
            verification_status=VerificationStatus.VERIFIED,
            hits=(self.hit, replace(self.hit, index=2, move_hit_index=2)),
        )

        result = calculate_combo_damage(
            verified_combo,
            self.stats,
            self.target,
            rules=self.verified_rules,
            mode=CalculationMode.GAME_EXACT,
        )

        self.assertEqual(result.physical, Decimal("11.8"))
        self.assertEqual(result.elemental, Decimal("5.8"))
        self.assertEqual(result.total, Decimal("17.6"))
        self.assertEqual([hit.total for hit in result.hits], [Decimal("8.8")] * 2)

    def test_continuous_mode_remains_unrounded_for_cross_checked_inputs(self) -> None:
        result = calculate_hit_damage(
            self.stats,
            self.hit,
            self.target,
            mode=CalculationMode.CONTINUOUS_APPROX,
        )

        self.assertEqual(result.physical, Decimal("5.8968"))
        self.assertEqual(result.elemental, Decimal("2.850"))
        self.assertEqual(result.verification_status, VerificationStatus.CROSS_CHECKED)


if __name__ == "__main__":
    unittest.main()
