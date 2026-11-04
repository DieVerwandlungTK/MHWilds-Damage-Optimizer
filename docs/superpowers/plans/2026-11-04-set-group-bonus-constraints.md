# Set and Group Bonus Constraints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve normalized armor bonus metadata and make set/group skill activation participate in feasibility requirements, enumeration, and reconstructed build skill levels.

**Architecture:** Extend the immutable equipment boundary with validated bonus ranks, then collect per-skill bonus families in a solver-independent module. Add exact threshold activation variables to the existing HiGHS model while independently recomputing activated levels during result reconstruction and exhaustive-oracle tests.

**Tech Stack:** Python 3.11, standard-library `dataclasses`/`unittest`, Python-MIP pinned at `50f00c92b3b093d7bd554a61e5e672e5c5e43aec`, HiGHS, uv

**Spec:** `docs/superpowers/specs/2026-11-04-set-group-bonus-constraints-design.md`

## Global Constraints

- Count bonus membership by `(SkillKind.SET | SkillKind.GROUP, skill_id)`, not by `source_set_id`; this permits α/β and other source sets carrying the same normalized bonus tag to mix.
- Treat each bonus rank's `skill_level` as the cumulative level at its `pieces` threshold; add rank-to-rank increments to the MILP expression.
- Canonicalize exact duplicate `(pieces, skill_level)` ranks, but reject conflicting or non-increasing ranks and inconsistent definitions for the same bonus family.
- Bonus activation must affect `minimum`, `exact`, and `forbidden` requirements and both granted/effective result skill maps.
- Do not add weapon candidates, weapon slots, weapon bonus counts, skill-effect values, or a damage objective.
- Keep tests independent of downloaded data; real-data loading/solving is an optional local verification, not a suite requirement.

## Review Focus

- An unavoidable threshold must make `forbidden` infeasible; an activation variable must not be allowed to stay zero after its threshold is met. Pin in Task 3.
- A threshold not reached must not satisfy `minimum`; an activation variable must not be allowed to turn on early. Pin in Task 3.
- Distinct source armor sets carrying the same series `skill_id` must count together. Pin in Tasks 2 and 3.
- Exact duplicate source ranks must load, while same-threshold/different-level and non-increasing definitions must raise a contextual input/data error. Pin in Task 1.
- Enumeration no-good cuts must still identify physical equipment/decorations rather than producing duplicate builds through deterministic helper variables. Pin in Task 3.

---

### Task 1: Immutable bonus models and verified loading

**Files:**
- Modify: `mhwilds_optimizer/equipment_models.py`
- Modify: `mhwilds_optimizer/equipment_data.py`
- Modify: `tests/equipment_fixtures.py`
- Modify: `tests/test_equipment_models.py`
- Modify: `tests/test_equipment_data.py`

**Interfaces:**
- Consumes: normalized `armor.json` records with `set_bonus` / `group_bonus` objects from schema version 1.
- Produces: `BonusRank(pieces: int, skill_level: int)`, `ArmorBonus(skill_id: str, ranks: tuple[BonusRank, ...])`, and optional `set_bonus` / `group_bonus` fields on `ArmorPiece`.

- [ ] **Step 1: Write failing immutable-model tests**

Add tests that construct a two-rank `ArmorBonus`, assert its ranks are immutable and sorted, and assert exact duplicate ranks collapse to one. Add rejection cases for empty ranks, non-positive values, the same threshold with different levels, and a higher threshold with a non-increasing skill level.

- [ ] **Step 2: Run the focused model tests and confirm failure**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_models -v`

Expected: FAIL because `BonusRank` and `ArmorBonus` do not exist.

- [ ] **Step 3: Implement bonus value objects and extend `ArmorPiece`**

Add the exact interfaces above. Keep existing callers compatible by appending
`set_bonus: ArmorBonus | None = None` and `group_bonus: ArmorBonus | None = None`
after `slots`. Canonicalize exact duplicate ranks and store the result as a tuple;
validate strict increases in both `pieces` and `skill_level`.

- [ ] **Step 4: Test catalog foreign keys, kinds, and family consistency**

Add cases asserting rejection when a set bonus references an unknown or non-`SET`
skill, a group bonus references a non-`GROUP` skill, or two armor pieces attach
different ranks to the same `(kind, skill_id)`. Include a valid catalog where
different armor candidates share one series definition.

- [ ] **Step 5: Implement catalog-level bonus validation**

In `EquipmentCatalog.__post_init__`, verify referenced skill existence/kind and
one consistent `ArmorBonus` value per `(SkillKind.SET | SkillKind.GROUP, skill_id)`.
Do not require all armor pieces from the same display/source set to be present.

- [ ] **Step 6: Write failing loader tests for both bonus kinds**

Extend the fixture JSON with a set skill and group skill, load one armor record
containing both bonuses, and assert typed IDs/ranks. Add a payload with exact
duplicate ranks and assert canonicalization succeeds; add conflicting ranks and
assert `EquipmentDataError` identifies the armor record.

- [ ] **Step 7: Parse normalized bonuses with record context**

Add a private parser returning `ArmorBonus | None`, convert each rank to
`BonusRank`, and pass both fields to `ArmorPiece`. Wrap model validation at the
record boundary so rank failures name `armor.json[index]` and the armor ID.

- [ ] **Step 8: Run focused and full tests**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_models tests.test_equipment_data -v`

Expected: all focused tests PASS.

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 9: Commit the model and loader layer**

```bash
git add mhwilds_optimizer/equipment_models.py mhwilds_optimizer/equipment_data.py tests/equipment_fixtures.py tests/test_equipment_models.py tests/test_equipment_data.py
git commit -m "feat: load armor bonus definitions"
```

### Task 2: Solver-independent bonus family aggregation

**Files:**
- Create: `mhwilds_optimizer/equipment_bonuses.py`
- Create: `tests/test_equipment_bonuses.py`

**Interfaces:**
- Consumes: Task 1 `EquipmentCatalog`, `ArmorBonus`, `BonusRank`, and selected armor IDs.
- Produces: `BonusFamily(kind: SkillKind, skill_id: str, ranks: tuple[BonusRank, ...], armor_ids: tuple[str, ...])`, `collect_bonus_families(catalog: EquipmentCatalog) -> tuple[BonusFamily, ...]`, and `activated_bonus_levels(catalog: EquipmentCatalog, selected_armor_ids: Collection[str]) -> Mapping[str, int]`.

- [ ] **Step 1: Write failing family aggregation tests**

Build a catalog where two differently named/source-like armor candidates share a
set skill and candidates from separate series share a group skill. Assert one
family per `(kind, skill_id)`, sorted armor IDs, and deterministic family order.

- [ ] **Step 2: Run the focused tests and confirm import failure**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_bonuses -v`

Expected: FAIL because `mhwilds_optimizer.equipment_bonuses` does not exist.

- [ ] **Step 3: Implement immutable `BonusFamily` and collection**

Implement the exact interfaces above. Build membership from each armor piece's
optional bonus fields, group by kind and skill ID, and rely on Task 1 catalog
validation for consistent ranks. Reject selected armor IDs not present in the
catalog with `EquipmentInputError`.

- [ ] **Step 4: Test activated levels at every boundary**

For ranks `(2, 1), (4, 2)`, assert counts 0/1 produce no level, 2/3 produce level
1, and 4/5 produce level 2. Assert mixed armor candidates sharing the same set
skill count together, set/group families are evaluated independently, and the
returned mapping is immutable.

- [ ] **Step 5: Implement pure activated-level calculation**

Count selected member IDs per family, choose the highest rank whose threshold is
met, and combine activated levels by skill ID. Since catalog validation ties one
skill ID to one `SkillKind`, summing across different family kinds is unnecessary.

- [ ] **Step 6: Run focused and full tests**

Run: `uv run --python 3.11 python -m unittest tests.test_equipment_bonuses -v`

Expected: all focused tests PASS.

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 7: Commit the pure bonus logic**

```bash
git add mhwilds_optimizer/equipment_bonuses.py tests/test_equipment_bonuses.py
git commit -m "feat: calculate activated armor bonuses"
```

### Task 3: Exact bonus constraints, reconstruction, and oracle parity

**Files:**
- Modify: `mhwilds_optimizer/constraints.py`
- Modify: `tests/test_constraints.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 `collect_bonus_families` and `activated_bonus_levels`.
- Produces: unchanged public `solve_feasible_build(...)` and `enumerate_feasible_builds(...)` APIs whose requirements and result skill maps include activated armor bonuses.

- [ ] **Step 1: Write failing feasibility tests for exact threshold behavior**

Add a tiny catalog where only two selected tagged pieces can satisfy a set-skill
minimum. Assert one tagged piece is infeasible, two differently sourced tagged
pieces are feasible, an unavoidable threshold makes `forbidden` infeasible, and
`exact` distinguishes level 1 at two pieces from level 2 at four pieces.

- [ ] **Step 2: Run focused tests and verify the current solver fails**

Run: `uv run --python 3.11 python -m unittest tests.test_constraints -v`

Expected: FAIL because bonus skills are absent from skill expressions.

- [ ] **Step 3: Add deterministic threshold activation variables**

Extend `_ModelState` with a separate mapping of helper activation variables that
is not returned by `binary_variables`. For each family/rank, add one binary
variable and both threshold implications using the selected family armor sum and
`M = len(ArmorPart)`. Add `(skill_level - previous_skill_level) * variable` to
the referenced skill expression.

- [ ] **Step 4: Include activated bonuses during build reconstruction**

Call `activated_bonus_levels` with selected armor IDs and add those values to
`granted_skill_levels` before applying max-level caps. Keep the reconstructed
value independent from helper-variable solution values.

- [ ] **Step 5: Extend the independent exhaustive oracle**

Within `tests/test_constraints.py`, count bonus tags directly from selected armor
without importing Task 2 helpers. Add set-minimum, below/at-threshold, multi-rank,
group-across-series, exact, and forbidden cases to solver-versus-oracle signature
set comparisons.

- [ ] **Step 6: Pin enumeration uniqueness**

Use a catalog with multiple activated ranks and assert every returned physical
build signature is unique and equals the oracle set. This verifies deterministic
helper variables do not enter or weaken the physical no-good cut.

- [ ] **Step 7: Document bonus support and remaining boundary**

Update the feasibility section in `README.md` to state that series/group skill
levels activate from selected armor tags and can be required or forbidden. Keep
weapon contribution, skill-effect evaluation, and damage optimization explicit
non-goals.

- [ ] **Step 8: Run final verification**

Run: `uv run --python 3.11 python -m unittest discover -s tests -v`

Expected: all tests PASS and HiGHS output remains suppressed.

Run: `git diff --check`

Expected: no output.

Optionally, when local raw data exists, normalize it to a temporary directory,
load 714 armor records, and solve an empty-requirement smoke test.

- [ ] **Step 9: Commit the integrated constraints**

```bash
git add mhwilds_optimizer/constraints.py tests/test_constraints.py README.md
git commit -m "feat: enforce armor bonus skill thresholds"
```
