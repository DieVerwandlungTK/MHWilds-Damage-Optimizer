"""Python-MIP feasibility model for fixed weapons and other equipment."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from mip import BINARY, HIGHS, Model, OptimizationStatus, Var, xsum

from mhwilds_optimizer.equipment_bonuses import (
    activated_bonus_levels,
    collect_bonus_families,
)
from mhwilds_optimizer.equipment_models import (
    ArmorPart,
    DecorationPlacement,
    EquipmentCatalog,
    EquipmentInputError,
    FeasibleBuild,
    RequirementKind,
    SkillKind,
    SkillRequirement,
    SlotType,
    validate_requirements,
)
from mhwilds_optimizer.weapon_models import Weapon


class SolveStatus(StrEnum):
    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    ERROR = "error"


@dataclass(frozen=True)
class SolveResult:
    status: SolveStatus
    build: FeasibleBuild | None
    message: str | None = None


@dataclass(frozen=True)
class EnumerationResult:
    status: SolveStatus
    builds: tuple[FeasibleBuild, ...]
    message: str | None = None


PlacementKey = tuple[str, int, str]
BonusActivationKey = tuple[str, str, int]


@dataclass
class _ModelState:
    model: Model
    catalog: EquipmentCatalog
    weapon: Weapon | None
    armor_variables: Mapping[str, Var]
    charm_variables: Mapping[str, Var]
    placement_variables: Mapping[PlacementKey, Var]
    bonus_activation_variables: Mapping[BonusActivationKey, Var]

    @property
    def binary_variables(self) -> tuple[Var, ...]:
        return (
            *self.armor_variables.values(),
            *self.charm_variables.values(),
            *self.placement_variables.values(),
        )


def _candidate_precheck(catalog: EquipmentCatalog) -> str | None:
    for part in ArmorPart:
        if not any(piece.part is part for piece in catalog.armor):
            return f"no armor candidate for {part.value}"
    if not catalog.charms:
        return "no regular charm candidate"
    return None


def _validate_weapon(catalog: EquipmentCatalog, weapon: Weapon | None) -> None:
    if weapon is None:
        return
    if not isinstance(weapon, Weapon):
        raise EquipmentInputError("weapon must be a Weapon or None")
    owner_ids = {piece.id for piece in catalog.armor} | {
        charm.id for charm in catalog.charms
    }
    if weapon.id in owner_ids:
        raise EquipmentInputError(f"weapon owner id conflicts with equipment: {weapon.id}")
    definitions = {skill.id: skill for skill in catalog.skills}
    for skill_id, level in weapon.skills.items():
        definition = definitions.get(skill_id)
        if definition is None:
            raise EquipmentInputError(f"weapon references unknown skill {skill_id}")
        if definition.kind is not SkillKind.WEAPON:
            raise EquipmentInputError(
                f"weapon skill {skill_id} must reference SkillKind.WEAPON"
            )
        if level > definition.max_level:
            raise EquipmentInputError(f"weapon.{skill_id} exceeds max_level")


def _build_model(
    catalog: EquipmentCatalog,
    requirements: Sequence[SkillRequirement],
    weapon: Weapon | None,
) -> _ModelState:
    model = Model(solver_name=HIGHS)
    model.verbose = 0

    armor_variables = {
        piece.id: model.add_var(name=f"armor:{index}", var_type=BINARY)
        for index, piece in enumerate(catalog.armor)
    }
    charm_variables = {
        charm.id: model.add_var(name=f"charm:{index}", var_type=BINARY)
        for index, charm in enumerate(catalog.charms)
    }
    for part in ArmorPart:
        model += (
            xsum(
                armor_variables[piece.id]
                for piece in catalog.armor
                if piece.part is part
            )
            == 1
        )
    model += xsum(charm_variables.values()) == 1

    bonus_activation_variables: dict[BonusActivationKey, Var] = {}
    bonus_skill_terms: dict[str, list] = {}
    for family in collect_bonus_families(catalog):
        selected_count = xsum(
            armor_variables[identifier] for identifier in family.armor_ids
        )
        previous_level = 0
        for rank in family.ranks:
            key = (family.kind.value, family.skill_id, rank.pieces)
            active = model.add_var(
                name=f"bonus:{len(bonus_activation_variables)}",
                var_type=BINARY,
            )
            bonus_activation_variables[key] = active
            model += selected_count >= rank.pieces * active
            model += selected_count <= rank.pieces - 1 + len(ArmorPart) * active
            increment = rank.skill_level - previous_level
            bonus_skill_terms.setdefault(family.skill_id, []).append(
                increment * active
            )
            previous_level = rank.skill_level

    armor_decorations = tuple(
        decoration
        for decoration in catalog.decorations
        if decoration.slot_type is SlotType.ARMOR
    )
    weapon_decorations = tuple(
        decoration
        for decoration in catalog.decorations
        if decoration.slot_type is SlotType.WEAPON
    )
    placement_variables: dict[PlacementKey, Var] = {}
    owners = (
        *((piece, armor_variables[piece.id]) for piece in catalog.armor),
        *((charm, charm_variables[charm.id]) for charm in catalog.charms),
    )
    for owner, selected in owners:
        for slot_index, slot_level in enumerate(owner.slots):
            variables: list[Var] = []
            for decoration in armor_decorations:
                if decoration.required_slot_level > slot_level:
                    continue
                key = (owner.id, slot_index, decoration.id)
                variable = model.add_var(
                    name=f"decoration:{len(placement_variables)}",
                    var_type=BINARY,
                )
                placement_variables[key] = variable
                variables.append(variable)
            if variables:
                model += xsum(variables) <= selected
    if weapon is not None:
        for slot_index, slot_level in enumerate(weapon.slots):
            variables = []
            for decoration in weapon_decorations:
                if decoration.required_slot_level > slot_level:
                    continue
                key = (weapon.id, slot_index, decoration.id)
                variable = model.add_var(
                    name=f"decoration:{len(placement_variables)}",
                    var_type=BINARY,
                )
                placement_variables[key] = variable
                variables.append(variable)
            if variables:
                model += xsum(variables) <= 1

    skill_expressions = {}
    for skill in catalog.skills:
        terms = []
        if weapon is not None:
            fixed_level = weapon.skills.get(skill.id, 0)
            if fixed_level:
                terms.append(fixed_level)
        for piece in catalog.armor:
            level = piece.skills.get(skill.id, 0)
            if level:
                terms.append(level * armor_variables[piece.id])
        for charm in catalog.charms:
            level = charm.skills.get(skill.id, 0)
            if level:
                terms.append(level * charm_variables[charm.id])
        decorations = {
            item.id: item for item in (*armor_decorations, *weapon_decorations)
        }
        for key, variable in placement_variables.items():
            level = decorations[key[2]].skills.get(skill.id, 0)
            if level:
                terms.append(level * variable)
        terms.extend(bonus_skill_terms.get(skill.id, ()))
        skill_expressions[skill.id] = xsum(terms)

    maximums = {skill.id: skill.max_level for skill in catalog.skills}
    for requirement in requirements:
        expression = skill_expressions[requirement.skill_id]
        if requirement.kind is RequirementKind.FORBIDDEN:
            model += expression == 0
        elif requirement.kind is RequirementKind.MINIMUM:
            assert requirement.level is not None
            model += expression >= requirement.level
        else:
            assert requirement.level is not None
            if requirement.level == maximums[requirement.skill_id]:
                model += expression >= requirement.level
            else:
                model += expression == requirement.level

    return _ModelState(
        model=model,
        catalog=catalog,
        weapon=weapon,
        armor_variables=armor_variables,
        charm_variables=charm_variables,
        placement_variables=placement_variables,
        bonus_activation_variables=bonus_activation_variables,
    )


def _selected(variable: Var) -> bool:
    return variable.x is not None and variable.x > 0.5


def _reconstruct_build(state: _ModelState) -> FeasibleBuild:
    selected_armor = {
        piece.part: piece
        for piece in state.catalog.armor
        if _selected(state.armor_variables[piece.id])
    }
    selected_charm = next(
        charm
        for charm in state.catalog.charms
        if _selected(state.charm_variables[charm.id])
    )
    placements = tuple(
        DecorationPlacement(owner_id, slot_index, decoration_id)
        for (owner_id, slot_index, decoration_id), variable in sorted(
            state.placement_variables.items()
        )
        if _selected(variable)
    )

    granted: dict[str, int] = dict(state.weapon.skills) if state.weapon else {}
    for item in (*selected_armor.values(), selected_charm):
        for skill_id, level in item.skills.items():
            granted[skill_id] = granted.get(skill_id, 0) + level
    decorations = {item.id: item for item in state.catalog.decorations}
    for placement in placements:
        for skill_id, level in decorations[placement.decoration_id].skills.items():
            granted[skill_id] = granted.get(skill_id, 0) + level
    bonus_levels = activated_bonus_levels(
        state.catalog, {piece.id for piece in selected_armor.values()}
    )
    for skill_id, level in bonus_levels.items():
        granted[skill_id] = granted.get(skill_id, 0) + level
    maximums = {skill.id: skill.max_level for skill in state.catalog.skills}
    effective = {
        skill_id: min(level, maximums[skill_id])
        for skill_id, level in granted.items()
    }
    return FeasibleBuild(
        armor_ids={part: piece.id for part, piece in selected_armor.items()},
        charm_id=selected_charm.id,
        decorations=placements,
        granted_skill_levels=granted,
        effective_skill_levels=effective,
        weapon_id=state.weapon.id if state.weapon is not None else None,
    )


def solve_feasible_build(
    catalog: EquipmentCatalog,
    requirements: Sequence[SkillRequirement],
    *,
    weapon: Weapon | None = None,
) -> SolveResult:
    """Return one legal build satisfying the requirements, if one exists."""
    validated_requirements = validate_requirements(catalog, requirements)
    _validate_weapon(catalog, weapon)
    precheck_message = _candidate_precheck(catalog)
    if precheck_message is not None:
        return SolveResult(SolveStatus.INFEASIBLE, None, precheck_message)
    try:
        state = _build_model(catalog, validated_requirements, weapon)
        optimization_status = state.model.optimize()
    except Exception as error:
        return SolveResult(SolveStatus.ERROR, None, f"solver error: {error}")
    if optimization_status in {
        OptimizationStatus.OPTIMAL,
        OptimizationStatus.FEASIBLE,
    }:
        try:
            return SolveResult(SolveStatus.FEASIBLE, _reconstruct_build(state))
        except Exception as error:
            return SolveResult(
                SolveStatus.ERROR,
                None,
                f"cannot reconstruct solver result: {error}",
            )
    if optimization_status is OptimizationStatus.INFEASIBLE:
        return SolveResult(SolveStatus.INFEASIBLE, None)
    return SolveResult(
        SolveStatus.ERROR,
        None,
        f"unexpected solver status: {optimization_status}",
    )


def enumerate_feasible_builds(
    catalog: EquipmentCatalog,
    requirements: Sequence[SkillRequirement],
    *,
    limit: int | None = None,
    weapon: Weapon | None = None,
) -> EnumerationResult:
    """Enumerate distinct complete binary assignments for a small catalog."""
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise EquipmentInputError("limit must be a positive integer or None")
    validated_requirements = validate_requirements(catalog, requirements)
    _validate_weapon(catalog, weapon)
    precheck_message = _candidate_precheck(catalog)
    if precheck_message is not None:
        return EnumerationResult(SolveStatus.INFEASIBLE, (), precheck_message)
    try:
        state = _build_model(catalog, validated_requirements, weapon)
    except Exception as error:
        return EnumerationResult(SolveStatus.ERROR, (), f"solver error: {error}")

    builds: list[FeasibleBuild] = []
    while True:
        try:
            optimization_status = state.model.optimize()
        except Exception as error:
            return EnumerationResult(
                SolveStatus.ERROR,
                tuple(builds),
                f"solver error: {error}",
            )
        if optimization_status in {
            OptimizationStatus.OPTIMAL,
            OptimizationStatus.FEASIBLE,
        }:
            try:
                builds.append(_reconstruct_build(state))
            except Exception as error:
                return EnumerationResult(
                    SolveStatus.ERROR,
                    tuple(builds),
                    f"cannot reconstruct solver result: {error}",
                )
            if limit is not None and len(builds) >= limit:
                return EnumerationResult(SolveStatus.FEASIBLE, tuple(builds))
            selected = [
                variable for variable in state.binary_variables if _selected(variable)
            ]
            unselected = [
                variable for variable in state.binary_variables if not _selected(variable)
            ]
            state.model += (
                xsum(selected) - xsum(unselected) <= len(selected) - 1
            )
            continue
        if optimization_status is OptimizationStatus.INFEASIBLE:
            if builds:
                return EnumerationResult(SolveStatus.FEASIBLE, tuple(builds))
            return EnumerationResult(SolveStatus.INFEASIBLE, ())
        return EnumerationResult(
            SolveStatus.ERROR,
            tuple(builds),
            f"unexpected solver status: {optimization_status}",
        )
