# Equipment Feasibility Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load normalized MHDB equipment into validated immutable models and use Python-MIP/HiGHS to find and enumerate legal armor, regular charm, and armor-decoration builds satisfying skill requirements.

**Architecture:** Keep schema parsing and domain validation independent from the solver. Model each physical armor/charm slot explicitly with binary decoration-placement variables, then reconstruct typed build results from the same variables; validate the solver against an independent exhaustive-search oracle on a tiny fixture.

**Tech Stack:** Python 3.11, standard-library `dataclasses`/`unittest`, Python-MIP pinned at `50f00c92b3b093d7bd554a61e5e672e5c5e43aec`, HiGHS, uv

**Spec:** `docs/superpowers/specs/2026-11-04-equipment-feasibility-model-design.md`

## Global Constraints

- Set `.python-version` to `3.11` and `requires-python = ">=3.11,<3.12"`; pin `mip[highs]` to official commit `50f00c92b3b093d7bd554a61e5e672e5c5e43aec`; commit the generated `uv.lock`.
- Use normalized stable IDs, never display names, for joins and solver output.
- Select exactly one armor piece for each of `head`, `chest`, `arms`, `waist`, `legs`, and exactly one regular charm.
- Only armor decorations may occupy armor/charm slots; one slot accepts at most one decoration whose required level does not exceed the slot level.
- Do not implement weapon slots, set/group bonuses, damage objectives, Artian weapons, or appraised charms in this plan.
- Keep tests independent of downloaded `data/raw/` and `data/normalized/` content.

## Review Focus

- A catalog missing every candidate for one armor part must return `infeasible`, not crash or silently skip that part; pin in Task 3.
- An empty regular-charm catalog must return `infeasible`, not create a charm-free build; pin in Task 3.
- A manifest hash/count mismatch or malformed JSON must raise `EquipmentDataError` before model construction; pin in Task 2.
- Duplicate or unknown skill requirements and zero/out-of-range levels must raise `EquipmentInputError`; pin in Task 1.
- HiGHS initialization/optimization failure must return `error` with a diagnostic and never masquerade as `infeasible`; pin in Task 3.

---

### Task 1: Python 3.11 dependency and immutable equipment models

**Files:**
- Modify: `.python-version`
- Modify: `pyproject.toml`
- Create: `uv.lock`
- Create: `mhwilds_optimizer/equipment_models.py`
- Create: `tests/equipment_fixtures.py`
- Create: `tests/test_equipment_models.py`

**Interfaces:**
- Consumes: normalized IDs and level conventions documented in `docs/data-schema.md`.
- Produces: `ArmorPart`, `SlotType`, `SkillKind`, `RequirementKind`, `SkillDefinition`, `ArmorPiece`, `Decoration`, `RegularCharm`, `EquipmentCatalog`, `SkillRequirement`, `DecorationPlacement`, `FeasibleBuild`, `EquipmentInputError`, and `validate_requirements(catalog, requirements) -> tuple[SkillRequirement, ...]`.

- [ ] **Step 1: Pin the supported runtime and solver dependency**

Change `.python-version` to `3.11` and `requires-python` in `pyproject.toml` to `>=3.11,<3.12`, then run `uv add --python 3.11 'mip[highs] @ git+https://github.com/coin-or/python-mip.git@50f00c92b3b093d7bd554a61e5e672e5c5e43aec'`. Verify `uv.lock` resolves that exact commit and `highspy` without widening the Python constraint.

- [ ] **Step 2: Write failing model validation tests**

Add unittest cases asserting that a valid tiny catalog is constructed with immutable skill mappings, while duplicate IDs, unknown referenced skills, invalid armor parts, slot levels outside 1–3, and non-positive skill grants raise `EquipmentInputError`. Add `make_tiny_catalog()` in `tests/equipment_fixtures.py` with two head candidates, one candidate for every other part, two charms, one armor decoration, and one weapon decoration.

- [ ] **Step 3: Run the focused tests and confirm the expected import failure**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_models -v`

Expected: FAIL because `mhwilds_optimizer.equipment_models` does not exist.

- [ ] **Step 4: Implement the enums and frozen dataclasses**

Use these field contracts:

```python
SkillDefinition(id: str, kind: SkillKind, max_level: int)
ArmorPiece(id: str, part: ArmorPart, skills: Mapping[str, int], slots: tuple[int, ...])
Decoration(id: str, slot_type: SlotType, required_slot_level: int, skills: Mapping[str, int])
RegularCharm(id: str, skills: Mapping[str, int], slots: tuple[int, ...])
EquipmentCatalog(skills: tuple[SkillDefinition, ...], armor: tuple[ArmorPiece, ...], decorations: tuple[Decoration, ...], charms: tuple[RegularCharm, ...])
SkillRequirement(skill_id: str, kind: RequirementKind, level: int | None = None)
DecorationPlacement(owner_id: str, slot_index: int, decoration_id: str)
FeasibleBuild(armor_ids: Mapping[ArmorPart, str], charm_id: str, decorations: tuple[DecorationPlacement, ...], granted_skill_levels: Mapping[str, int], effective_skill_levels: Mapping[str, int])
```

Copy input mappings into `MappingProxyType`, validate all catalog foreign keys and duplicate IDs in `EquipmentCatalog.__post_init__`, and sort validated requirements by `skill_id` for deterministic model construction.

- [ ] **Step 5: Test requirement validation boundaries**

Add cases for one valid request of each kind and assert rejection of duplicate skill IDs, unknown skill IDs, a level on `forbidden`, a missing level on `minimum`/`exact`, level 0, and a level above `SkillDefinition.max_level`.

- [ ] **Step 6: Run the model tests and the existing suite**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_models -v`

Expected: all focused tests PASS.

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS under Python 3.11.

- [ ] **Step 7: Commit the dependency and model layer**

```bash
git add .python-version pyproject.toml uv.lock mhwilds_optimizer/equipment_models.py tests/equipment_fixtures.py tests/test_equipment_models.py
git commit -m "feat: define equipment optimization models"
```

### Task 2: Verified normalized equipment loader

**Files:**
- Create: `mhwilds_optimizer/equipment_data.py`
- Create: `tests/test_equipment_data.py`

**Interfaces:**
- Consumes: Task 1 model constructors and a `Path` containing `manifest.json`, `skills.json`, `armor.json`, `decorations.json`, and `regular_charms.json`.
- Produces: `EquipmentDataError` and `load_equipment_catalog(normalized_dir: Path) -> EquipmentCatalog`.

- [ ] **Step 1: Write a failing successful-load test**

Create a temporary normalized directory using records shaped exactly like `docs/data-schema.md`. Write a manifest with byte sizes, SHA-256 values, and counts, then assert that `load_equipment_catalog()` returns the expected IDs, enums, slots, and skill levels while ignoring display-name and bonus fields that are outside this phase.

- [ ] **Step 2: Run the loader test and verify failure**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_data -v`

Expected: FAIL because `mhwilds_optimizer.equipment_data` does not exist.

- [ ] **Step 3: Implement strict JSON and manifest loading**

Implement `load_equipment_catalog(normalized_dir: Path) -> EquipmentCatalog`. Require manifest schema version 1; verify each consumed file's listed size and SHA-256; require manifest counts to match array lengths; convert `part`, `kind`, and `slot_type` strings to Task 1 enums; wrap filesystem, Unicode, JSON, shape, and model-validation failures in contextual `EquipmentDataError`.

- [ ] **Step 4: Add corruption and schema-boundary tests**

Assert `EquipmentDataError` for malformed JSON, a changed file after hashing, a mismatched manifest count, a missing consumed file entry, a non-list top-level payload, and an unknown skill reference. Check each message names the responsible file or record.

- [ ] **Step 5: Run focused and full tests**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_data -v`

Expected: all focused tests PASS.

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit the loader**

```bash
git add mhwilds_optimizer/equipment_data.py tests/test_equipment_data.py
git commit -m "feat: load normalized equipment catalogs"
```

### Task 3: HiGHS feasibility solver and result reconstruction

**Files:**
- Create: `mhwilds_optimizer/constraints.py`
- Create: `tests/test_constraints.py`

**Interfaces:**
- Consumes: `EquipmentCatalog`, validated `Sequence[SkillRequirement]`, and Task 1 result models.
- Produces: `SolveStatus`, `SolveResult(status: SolveStatus, build: FeasibleBuild | None, message: str | None)`, and `solve_feasible_build(catalog, requirements) -> SolveResult`.

- [ ] **Step 1: Write failing end-to-end feasibility tests**

Using `make_tiny_catalog()`, assert that the solver selects exactly five armor IDs and one charm, places only armor decorations into compatible slots, combines equipment/charm/decoration skills, and returns effective levels capped at each skill's maximum. Use requirements that leave a single valid build so assertions do not depend on HiGHS tie-breaking.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `uv run --python 3.11 python -m unittest tests.test_constraints -v`

Expected: FAIL because `mhwilds_optimizer.constraints` does not exist.

- [ ] **Step 3: Build the HiGHS model with explicit physical slots**

Implement private model construction with `mip.Model(solver_name=mip.HIGHS)`, binary armor and charm selection variables, and binary `(owner_id, slot_index, decoration_id)` placement variables only when `SlotType.ARMOR` and `required_slot_level <= slot_level`. Constrain each part and the charm to exactly one, each slot to at most the owning selection variable, and skill totals to include every selected source.

- [ ] **Step 4: Implement requirement constraints and reconstruction**

Apply `minimum >= level`, `forbidden == 0`, `exact == level` below the maximum, and `exact >= level` at the maximum. Reconstruct `FeasibleBuild` only from variables whose solution value exceeds `0.5`; include granted and maximum-capped effective skill maps.

- [ ] **Step 5: Add infeasible-input and solver-failure tests**

Assert `SolveStatus.INFEASIBLE` with no build for a catalog missing a whole armor part, an empty charm catalog, an impossible minimum, an illegal large decoration in a small slot, and a forbidden skill present on every candidate. Mock model construction and optimization failures separately and assert `SolveStatus.ERROR`, a diagnostic message, and no build.

- [ ] **Step 6: Run focused and full tests**

Run: `uv run --python 3.11 python -m unittest tests.test_constraints -v`

Expected: all focused tests PASS and HiGHS output is suppressed.

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit the feasibility solver**

```bash
git add mhwilds_optimizer/constraints.py tests/test_constraints.py
git commit -m "feat: solve equipment feasibility with HiGHS"
```

### Task 4: Complete toy-solution enumeration and independent oracle

**Files:**
- Modify: `mhwilds_optimizer/constraints.py`
- Modify: `tests/test_constraints.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 3 model builder and reconstruction.
- Produces: `EnumerationResult(status: SolveStatus, builds: tuple[FeasibleBuild, ...], message: str | None)` and `enumerate_feasible_builds(catalog, requirements, *, limit: int | None = None) -> EnumerationResult`.

- [ ] **Step 1: Write an independent exhaustive-search oracle in the test**

In `tests/test_constraints.py`, enumerate armor/charm choices and each selected slot's `None | compatible armor decoration` choices with `itertools.product`. Compute skill totals and requirement satisfaction directly without importing private solver helpers; return canonical signatures of armor IDs, charm ID, and sorted placements.

- [ ] **Step 2: Write the failing solver-versus-oracle test**

For separate `minimum`, below-cap `exact`, at-cap `exact`, and `forbidden` scenarios, assert that the canonical signature set returned by `enumerate_feasible_builds()` exactly equals the exhaustive oracle set. Include a level-1 decoration in a level-3 slot and a weapon decoration in the catalog.

- [ ] **Step 3: Run the enumeration tests and verify failure**

Run: `uv run --python 3.11 python -m unittest tests.test_constraints -v`

Expected: FAIL because `enumerate_feasible_builds` is not defined.

- [ ] **Step 4: Implement no-good-cut enumeration**

After each feasible solve, record every binary variable's 0/1 assignment and add a cut excluding that complete assignment before optimizing again. Stop on infeasibility or after `limit` builds; require `limit` to be `None` or a positive integer. Return `error` with already-found builds and a diagnostic if a later optimization fails.

- [ ] **Step 5: Add termination and boundary tests**

Assert that `limit=1` returns one build, `limit=0` is rejected, an infeasible catalog returns an empty tuple with `infeasible`, and repeated enumeration yields the same signature set regardless of HiGHS discovery order.

- [ ] **Step 6: Document the Phase 3 foundation**

Update `README.md` with Python 3.11 setup, normalized-data loading, one `minimum` requirement example, the meaning of `feasible`/`infeasible`/`error`, and explicit non-goals: no damage objective, weapon slots, or set/group bonuses yet.

- [ ] **Step 7: Run final verification**

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS.

Run: `git diff --check`

Expected: no output.

- [ ] **Step 8: Commit the completed foundation**

```bash
git add mhwilds_optimizer/constraints.py tests/test_constraints.py README.md
git commit -m "feat: enumerate feasible equipment builds"
```
