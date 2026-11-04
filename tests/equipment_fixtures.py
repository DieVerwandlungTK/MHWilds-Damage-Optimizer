from mhwilds_optimizer.equipment_models import (
    ArmorPart,
    ArmorPiece,
    Decoration,
    EquipmentCatalog,
    RegularCharm,
    SkillDefinition,
    SkillKind,
    SlotType,
)


def make_tiny_catalog() -> EquipmentCatalog:
    return EquipmentCatalog(
        skills=(
            SkillDefinition("skill:attack", SkillKind.ARMOR, 3),
            SkillDefinition("skill:critical", SkillKind.ARMOR, 2),
            SkillDefinition("skill:weapon", SkillKind.WEAPON, 1),
            SkillDefinition("skill:set", SkillKind.SET, 2),
            SkillDefinition("skill:group", SkillKind.GROUP, 1),
        ),
        armor=(
            ArmorPiece(
                "armor:offense:head",
                ArmorPart.HEAD,
                {"skill:attack": 1},
                (3,),
            ),
            ArmorPiece(
                "armor:critical:head",
                ArmorPart.HEAD,
                {"skill:critical": 1},
                (1,),
            ),
            ArmorPiece("armor:base:chest", ArmorPart.CHEST, {}, ()),
            ArmorPiece("armor:base:arms", ArmorPart.ARMS, {}, ()),
            ArmorPiece("armor:base:waist", ArmorPart.WAIST, {}, ()),
            ArmorPiece("armor:base:legs", ArmorPart.LEGS, {}, ()),
        ),
        decorations=(
            Decoration(
                "decoration:attack",
                SlotType.ARMOR,
                1,
                {"skill:attack": 1},
            ),
            Decoration(
                "decoration:weapon",
                SlotType.WEAPON,
                1,
                {"skill:weapon": 1},
            ),
        ),
        charms=(
            RegularCharm("regular_charm:attack", {"skill:attack": 1}, ()),
            RegularCharm("regular_charm:slot", {}, (1,)),
        ),
    )
