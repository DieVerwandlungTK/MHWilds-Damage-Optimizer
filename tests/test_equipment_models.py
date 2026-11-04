import unittest
from dataclasses import replace

from mhwilds_optimizer.equipment_models import (
    ArmorPart,
    ArmorPiece,
    Decoration,
    EquipmentCatalog,
    EquipmentInputError,
    RegularCharm,
    RequirementKind,
    SkillDefinition,
    SkillKind,
    SkillRequirement,
    SlotType,
    validate_requirements,
)
from tests.equipment_fixtures import make_tiny_catalog


class EquipmentCatalogTests(unittest.TestCase):
    def test_copies_skill_mappings_into_immutable_values(self) -> None:
        source_skills = {"skill:attack": 1}
        piece = ArmorPiece("armor:test:head", ArmorPart.HEAD, source_skills, (3,))
        source_skills["skill:attack"] = 2

        self.assertEqual(piece.skills, {"skill:attack": 1})
        with self.assertRaises(TypeError):
            piece.skills["skill:attack"] = 2  # type: ignore[index]

    def test_accepts_a_valid_catalog(self) -> None:
        catalog = make_tiny_catalog()

        self.assertEqual(len(catalog.armor), 6)
        self.assertEqual(catalog.armor[0].part, ArmorPart.HEAD)
        self.assertEqual(catalog.decorations[0].slot_type, SlotType.ARMOR)

    def test_rejects_duplicate_ids_across_each_candidate_kind(self) -> None:
        catalog = make_tiny_catalog()
        cases = {
            "skill": lambda: replace(
                catalog, skills=catalog.skills + (catalog.skills[0],)
            ),
            "armor": lambda: replace(
                catalog, armor=catalog.armor + (catalog.armor[0],)
            ),
            "decoration": lambda: replace(
                catalog,
                decorations=catalog.decorations + (catalog.decorations[0],),
            ),
            "charm": lambda: replace(
                catalog, charms=catalog.charms + (catalog.charms[0],)
            ),
        }

        for kind, construct in cases.items():
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(EquipmentInputError, rf"duplicate.*{kind}"):
                    construct()

    def test_rejects_an_owner_id_shared_by_armor_and_charm(self) -> None:
        catalog = make_tiny_catalog()
        conflicting_charm = RegularCharm(catalog.armor[0].id, {}, ())

        with self.assertRaisesRegex(EquipmentInputError, "armor and charm"):
            replace(catalog, charms=(conflicting_charm, *catalog.charms[1:]))

    def test_rejects_unknown_skill_references(self) -> None:
        catalog = make_tiny_catalog()
        bad_piece = ArmorPiece(
            "armor:unknown:head",
            ArmorPart.HEAD,
            {"skill:missing": 1},
            (),
        )

        with self.assertRaisesRegex(EquipmentInputError, "skill:missing"):
            replace(catalog, armor=(bad_piece,) + catalog.armor[2:])

    def test_rejects_invalid_part_slot_and_granted_level(self) -> None:
        cases = (
            (
                "part",
                lambda: ArmorPiece("armor:bad:head", "helmet", {}, ()),  # type: ignore[arg-type]
            ),
            (
                "slots",
                lambda: RegularCharm("regular_charm:bad", {}, (0,)),
            ),
            (
                "required_slot_level",
                lambda: Decoration("decoration:bad", SlotType.ARMOR, 4, {}),
            ),
            (
                "skill:attack",
                lambda: ArmorPiece(
                    "armor:bad:head",
                    ArmorPart.HEAD,
                    {"skill:attack": 0},
                    (),
                ),
            ),
        )

        for field, construct in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(EquipmentInputError, field):
                    construct()


class SkillRequirementTests(unittest.TestCase):
    def test_validates_and_sorts_one_requirement_of_each_kind(self) -> None:
        catalog = make_tiny_catalog()
        requirements = (
            SkillRequirement("skill:weapon", RequirementKind.FORBIDDEN),
            SkillRequirement("skill:critical", RequirementKind.EXACT, 1),
            SkillRequirement("skill:attack", RequirementKind.MINIMUM, 2),
        )

        result = validate_requirements(catalog, requirements)

        self.assertEqual(
            [requirement.skill_id for requirement in result],
            ["skill:attack", "skill:critical", "skill:weapon"],
        )

    def test_rejects_invalid_requirement_boundaries(self) -> None:
        catalog = make_tiny_catalog()
        cases = (
            (
                "duplicate",
                (
                    SkillRequirement("skill:attack", RequirementKind.MINIMUM, 1),
                    SkillRequirement("skill:attack", RequirementKind.EXACT, 1),
                ),
            ),
            (
                "unknown",
                (SkillRequirement("skill:missing", RequirementKind.MINIMUM, 1),),
            ),
            (
                "forbidden",
                (SkillRequirement("skill:attack", RequirementKind.FORBIDDEN, 1),),
            ),
            (
                "level",
                (SkillRequirement("skill:attack", RequirementKind.MINIMUM),),
            ),
            (
                "level",
                (SkillRequirement("skill:attack", RequirementKind.EXACT, 0),),
            ),
            (
                "max_level",
                (SkillRequirement("skill:attack", RequirementKind.MINIMUM, 4),),
            ),
        )

        for message, requirements in cases:
            with self.subTest(message=message, requirements=requirements):
                with self.assertRaisesRegex(EquipmentInputError, message):
                    validate_requirements(catalog, requirements)


class DefinitionBoundaryTests(unittest.TestCase):
    def test_rejects_invalid_skill_definition_and_slot_type(self) -> None:
        cases = (
            (
                "kind",
                lambda: SkillDefinition("skill:bad", "active", 1),  # type: ignore[arg-type]
            ),
            (
                "max_level",
                lambda: SkillDefinition("skill:bad", SkillKind.ARMOR, 0),
            ),
            (
                "slot_type",
                lambda: Decoration("decoration:bad", "both", 1, {}),  # type: ignore[arg-type]
            ),
        )

        for field, construct in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(EquipmentInputError, field):
                    construct()


if __name__ == "__main__":
    unittest.main()
