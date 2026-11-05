import copy
import json
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from mhwilds_optimizer.combo_data import VerificationStatus
from mhwilds_optimizer.equipment_models import (
    EquipmentCatalog,
    SkillDefinition,
    SkillKind,
)
from mhwilds_optimizer.skill_effect_data import (
    SkillEffectDataError,
    load_skill_effect_table,
)
from mhwilds_optimizer.skill_effect_models import (
    ConditionOperator,
    ModifierKind,
)


def valid_payload() -> dict[str, object]:
    return {
        "schema_version": 1,
        "game_version": "1.042.00.03",
        "verification_status": "cross_checked",
        "sources": [
            {
                "name": "fixture source",
                "url": "https://example.com/skills",
                "checked_at": "2026-11-04",
                "supports": ["skill identity", "rank values"],
            }
        ],
        "skills": [
            {
                "id": "skill:1",
                "kind": "weapon",
                "max_level": 2,
                "ranks": [
                    {
                        "level": 1,
                        "clauses": [
                            {
                                "conditions": [],
                                "modifiers": [
                                    {"kind": "raw_flat", "value": "3"}
                                ],
                            }
                        ],
                    },
                    {
                        "level": 2,
                        "clauses": [
                            {
                                "conditions": [
                                    {
                                        "key": "monster_enraged",
                                        "operator": "equals",
                                        "value": True,
                                    }
                                ],
                                "modifiers": [
                                    {"kind": "raw_multiplier", "value": "1.04"}
                                ],
                            }
                        ],
                    },
                ],
            }
        ],
        "unsupported": [
            {
                "id": "skill:2",
                "kind": "armor",
                "max_level": 1,
                "reason": "value_unverified",
            }
        ],
        "non_damage": [
            {
                "id": "skill:3",
                "kind": "group",
                "max_level": 1,
                "reason": "defense_only",
            }
        ],
    }


class SkillEffectDataTests(unittest.TestCase):
    def write_payload(self, payload: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "effects.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_loads_exact_immutable_effect_table(self) -> None:
        table = load_skill_effect_table(path=self.write_payload(valid_payload()))

        self.assertEqual(table.schema_version, 1)
        self.assertEqual(table.game_version, "1.042.00.03")
        self.assertIs(table.verification_status, VerificationStatus.CROSS_CHECKED)
        self.assertIsInstance(table.sources, tuple)
        self.assertEqual(table.sources[0].supports, ("skill identity", "rank values"))

        effect = table.skills["skill:1"]
        self.assertIs(effect.kind, SkillKind.WEAPON)
        self.assertEqual(tuple(effect.ranks), (1, 2))
        self.assertEqual(effect.ranks[1].clauses[0].modifiers[0].kind, ModifierKind.RAW_FLAT)
        self.assertEqual(effect.ranks[1].clauses[0].modifiers[0].value, Decimal("3"))
        condition = effect.ranks[2].clauses[0].conditions[0]
        self.assertEqual(condition.key, "monster_enraged")
        self.assertIs(condition.operator, ConditionOperator.EQUALS)
        self.assertIs(condition.value, True)
        self.assertEqual(
            effect.ranks[2].clauses[0].modifiers[0].value,
            Decimal("1.04"),
        )
        self.assertEqual(table.unsupported["skill:2"].reason, "value_unverified")
        self.assertEqual(table.non_damage["skill:3"].reason, "defense_only")

        with self.assertRaises(TypeError):
            table.skills["skill:4"] = effect  # type: ignore[index]
        with self.assertRaises(TypeError):
            effect.ranks[3] = effect.ranks[2]  # type: ignore[index]

    def assert_payload_error(
        self,
        payload: object,
        pattern: str,
        *,
        catalog: EquipmentCatalog | None = None,
        expected_game_version: str = "1.042.00.03",
    ) -> None:
        with self.assertRaisesRegex(SkillEffectDataError, pattern):
            load_skill_effect_table(
                catalog,
                self.write_payload(payload),
                expected_game_version=expected_game_version,
            )

    def test_rejects_invalid_top_level_metadata(self) -> None:
        cases: list[tuple[str, object, str]] = []

        missing = valid_payload()
        del missing["sources"]
        cases.append(("missing", missing, "sources"))

        extra = valid_payload()
        extra["unexpected"] = True
        cases.append(("extra", extra, "unexpected"))

        schema = valid_payload()
        schema["schema_version"] = 2
        cases.append(("schema", schema, "schema_version"))

        version = valid_payload()
        version["game_version"] = "1.043.00.00"
        cases.append(("version", version, "game_version"))

        verification = valid_payload()
        verification["verification_status"] = "guess"
        cases.append(("verification", verification, "verification_status"))

        source = valid_payload()
        source["sources"][0]["checked_at"] = "not-a-date"  # type: ignore[index]
        cases.append(("source", source, "checked_at"))

        for name, payload, pattern in cases:
            with self.subTest(name=name):
                self.assert_payload_error(payload, pattern)

    def test_rejects_invalid_conditions_and_modifiers(self) -> None:
        cases: list[tuple[str, object, str]] = []

        unknown_modifier = valid_payload()
        unknown_modifier["skills"][0]["ranks"][0]["clauses"][0]["modifiers"][0][
            "kind"
        ] = "raw_guess"  # type: ignore[index]
        cases.append(("modifier", unknown_modifier, "kind"))

        unknown_operator = valid_payload()
        unknown_operator["skills"][0]["ranks"][1]["clauses"][0]["conditions"][0][
            "operator"
        ] = "contains"  # type: ignore[index]
        cases.append(("operator", unknown_operator, "operator"))

        unknown_condition = valid_payload()
        unknown_condition["skills"][0]["ranks"][1]["clauses"][0]["conditions"][0][
            "key"
        ] = "unknown_state"  # type: ignore[index]
        cases.append(("condition", unknown_condition, "key"))

        string_boolean = valid_payload()
        string_boolean["skills"][0]["ranks"][1]["clauses"][0]["conditions"][0][
            "value"
        ] = "true"  # type: ignore[index]
        cases.append(("string boolean", string_boolean, "monster_enraged.*bool"))

        invalid_sharpness = valid_payload()
        sharpness_condition = invalid_sharpness["skills"][0]["ranks"][1][
            "clauses"
        ][0]["conditions"][0]  # type: ignore[index]
        sharpness_condition.update({"key": "sharpness", "value": "purple"})
        cases.append(("sharpness", invalid_sharpness, "sharpness.*value"))

        invalid_element = valid_payload()
        element_condition = invalid_element["skills"][0]["ranks"][1]["clauses"][
            0
        ]["conditions"][0]  # type: ignore[index]
        element_condition.update({"key": "weapon_element", "value": "blast"})
        cases.append(("element", invalid_element, "weapon_element.*value"))

        invalid_at_most = valid_payload()
        invalid_at_most["skills"][0]["ranks"][1]["clauses"][0]["conditions"][0][
            "operator"
        ] = "at_most"  # type: ignore[index]
        cases.append(("at most", invalid_at_most, "at_most.*sharpness"))

        numeric_value = valid_payload()
        numeric_value["skills"][0]["ranks"][0]["clauses"][0]["modifiers"][0][
            "value"
        ] = 3  # type: ignore[index]
        cases.append(("numeric", numeric_value, "decimal string"))

        infinite_value = valid_payload()
        infinite_value["skills"][0]["ranks"][0]["clauses"][0]["modifiers"][0][
            "value"
        ] = "Infinity"  # type: ignore[index]
        cases.append(("infinite", infinite_value, "finite"))

        empty_clauses = valid_payload()
        empty_clauses["skills"][0]["ranks"][0]["clauses"] = []  # type: ignore[index]
        cases.append(("clauses", empty_clauses, "clauses"))

        empty_modifiers = valid_payload()
        empty_modifiers["skills"][0]["ranks"][0]["clauses"][0]["modifiers"] = []  # type: ignore[index]
        cases.append(("modifiers", empty_modifiers, "modifiers"))

        for name, payload, pattern in cases:
            with self.subTest(name=name):
                self.assert_payload_error(payload, pattern)

    def test_rejects_invalid_skill_categories_and_ranks(self) -> None:
        cases: list[tuple[str, object, str]] = []

        duplicate_id = valid_payload()
        duplicate_id["skills"].append(copy.deepcopy(duplicate_id["skills"][0]))  # type: ignore[union-attr,index]
        cases.append(("duplicate id", duplicate_id, "duplicate ID"))

        duplicate_rank = valid_payload()
        duplicate_rank["skills"][0]["ranks"].append(  # type: ignore[index,union-attr]
            copy.deepcopy(duplicate_rank["skills"][0]["ranks"][0])  # type: ignore[index]
        )
        cases.append(("duplicate rank", duplicate_rank, "duplicate.*rank"))

        rank_gap = valid_payload()
        rank_gap["skills"][0]["ranks"][1]["level"] = 3  # type: ignore[index]
        cases.append(("rank gap", rank_gap, "ranks"))

        overlap = valid_payload()
        overlap["unsupported"][0]["id"] = "skill:1"  # type: ignore[index]
        cases.append(("overlap", overlap, "more than one category"))

        invalid_id = valid_payload()
        invalid_id["non_damage"][0]["id"] = "not-a-skill"  # type: ignore[index]
        cases.append(("invalid id", invalid_id, "skill ID"))

        for name, payload, pattern in cases:
            with self.subTest(name=name):
                self.assert_payload_error(payload, pattern)

    def test_cross_validates_against_catalog_when_supplied(self) -> None:
        valid_catalog = EquipmentCatalog(
            skills=(
                SkillDefinition("skill:1", SkillKind.WEAPON, 2),
                SkillDefinition("skill:2", SkillKind.ARMOR, 1),
                SkillDefinition("skill:3", SkillKind.GROUP, 1),
                SkillDefinition("skill:unused", SkillKind.ARMOR, 1),
            ),
            armor=(),
            decorations=(),
            charms=(),
        )
        table = load_skill_effect_table(
            valid_catalog,
            self.write_payload(valid_payload()),
        )
        self.assertEqual(tuple(table.skills), ("skill:1",))

        wrong_kind = EquipmentCatalog(
            skills=(SkillDefinition("skill:1", SkillKind.ARMOR, 2),),
            armor=(),
            decorations=(),
            charms=(),
        )
        self.assert_payload_error(valid_payload(), "kind mismatch", catalog=wrong_kind)

        unknown = EquipmentCatalog(
            skills=(SkillDefinition("skill:1", SkillKind.WEAPON, 2),),
            armor=(),
            decorations=(),
            charms=(),
        )
        self.assert_payload_error(valid_payload(), "unknown skill:2", catalog=unknown)


class BundledSkillEffectDataTests(unittest.TestCase):
    def test_bundled_table_classifies_the_fixed_skill_snapshot(self) -> None:
        table = load_skill_effect_table()

        all_ids = set(table.skills) | set(table.unsupported) | set(table.non_damage)
        self.assertEqual(table.game_version, "1.042.00.03")
        self.assertEqual(len(all_ids), 179)
        self.assertEqual(
            len(all_ids),
            len(table.skills) + len(table.unsupported) + len(table.non_damage),
        )
        self.assertIn("skill:1", table.skills)
        self.assertIn("skill:565867136", table.unsupported)
        self.assertIn("skill:1077686656", table.non_damage)

        for effect in table.skills.values():
            self.assertEqual(tuple(effect.ranks), tuple(range(1, effect.max_level + 1)))

    def test_bundled_table_cross_validates_declared_identity(self) -> None:
        table = load_skill_effect_table()
        entries = {
            entry.id: entry
            for entry in (
                *table.skills.values(),
                *table.unsupported.values(),
                *table.non_damage.values(),
            )
        }
        definitions = [
            SkillDefinition(entry.id, entry.kind, entry.max_level)
            for entry in entries.values()
        ]
        attack_index = next(
            index
            for index, definition in enumerate(definitions)
            if definition.id == "skill:1"
        )
        definitions[attack_index] = replace(
            definitions[attack_index],
            kind=SkillKind.ARMOR,
        )
        mismatched = EquipmentCatalog(
            skills=tuple(definitions),
            armor=(),
            decorations=(),
            charms=(),
        )

        with self.assertRaisesRegex(SkillEffectDataError, "skill:1 kind mismatch"):
            load_skill_effect_table(mismatched)

    def test_bundled_table_does_not_copy_localized_game_text(self) -> None:
        path = (
            Path(__file__).parents[1]
            / "mhwilds_optimizer"
            / "data"
            / "skill_effects"
            / "1.042.00.03.json"
        )
        payload = json.loads(path.read_text(encoding="utf-8"))

        for category in ("skills", "unsupported", "non_damage"):
            for entry in payload[category]:
                self.assertNotIn("names", entry)
                self.assertNotIn("descriptions", entry)


if __name__ == "__main__":
    unittest.main()
