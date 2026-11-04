# Manual Weapon Input Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 手入力した完成済み双剣の基礎性能をダメージ計算へ渡し、武器固有スキルと武器装飾品を装備実現可能性判定へ含める。

**Architecture:** 新しい不変 `Weapon` モデルは武器単体の値を検証し、変換関数が既存の `CombatStats` と接続する。可否判定では武器を候補変数にせず固定入力として受け取り、固有スキルを定数項、武器装飾品を既存と同型の配置変数として加える。

**Tech Stack:** Python 3.11、標準ライブラリ `dataclasses` / `decimal` / `unittest`、Python-MIP + HiGHS

**Spec:** `docs/superpowers/specs/2026-11-04-manual-weapon-input-design.md`

## Global Constraints

- 武器は1回の探索につき1本の固定入力とし、選択変数を作らない。
- MHDBの武器ファイルを取得・正規化しない。
- 対応属性は `none`、`fire`、`water`、`thunder`、`ice`、`dragon` とし、状態異常を扱わない。
- 武器用と防具用の装飾品およびスロットを混在させない。
- 武器省略時の既存APIと既存結果を維持する。
- スキル効果による能力値補正と、武器によるシリーズ／グループ発動部位数への寄与は実装しない。

## Review Focus

- `int`、`float`、非有限 `Decimal` を武器数値に渡した場合、暗黙変換せず `WeaponInputError` にする（Task 1）。
- `element_type` と0／正の `element` が矛盾する場合、構築時に拒否する（Task 1）。
- 未知、上限超過、または `SkillKind.WEAPON` でない固有スキルはソルバー実行前に `EquipmentInputError` にする（Task 2）。
- 武器IDが防具または護石IDと衝突する場合、装飾品所有者を曖昧にせず `EquipmentInputError` にする（Task 2）。
- スロットレベル不足とスロット種別不一致では、違法な装飾品配置を作らない（Task 3）。

---

### Task 1: Manual Weapon Model and Damage Adapter

**Files:**
- Create: `mhwilds_optimizer/weapon_models.py`
- Create: `tests/test_weapon_models.py`

**Interfaces:**
- Consumes: `mhwilds_optimizer.damage_models.CombatStats`, `Sharpness`
- Produces: `ElementType`, `WeaponInputError`, `Weapon`, `combat_stats_from_weapon(weapon: Weapon, *, positive_critical_modifier: Decimal, negative_critical_modifier: Decimal, demon_dodge_buff: bool) -> CombatStats`

- [ ] **Step 1: Write failing construction and immutability tests**

Add `valid_weapon() -> Weapon` and tests asserting the exact stored values, tuple slots, immutable/sorted skills, and `FrozenInstanceError` on assignment. Add table-driven failures for empty IDs/names, non-`Decimal` and non-finite numbers, negative raw/element, affinity outside `[-100, 100]`, invalid sharpness, non-tuple or levels outside 1–3 slots, non-mapping/empty skill IDs/non-positive skill levels, and invalid `ElementType`.

- [ ] **Step 2: Run the model tests and confirm the missing module failure**

Run: `uv run python -m unittest tests.test_weapon_models -v`

Expected: FAIL because `mhwilds_optimizer.weapon_models` does not exist.

- [ ] **Step 3: Implement the weapon value model**

Create `WeaponInputError`, the six-value `ElementType`, and frozen `Weapon(id: str, name: str, raw: Decimal, element_type: ElementType, element: Decimal, affinity_percent: Decimal, sharpness: Sharpness, slots: tuple[int, ...], skills: Mapping[str, int])`. Copy skills into a sorted `MappingProxyType`; require `element == Decimal("0")` for `NONE` and `element > 0` otherwise.

- [ ] **Step 4: Write and run failing damage-adapter tests**

Assert that `combat_stats_from_weapon` copies raw, element, affinity, and sharpness and uses the three keyword-only combat arguments. Assert invalid critical modifiers and non-boolean dodge state retain `DamageInputError` behavior from `CombatStats`.

Run: `uv run python -m unittest tests.test_weapon_models -v`

Expected: FAIL because `combat_stats_from_weapon` is absent.

- [ ] **Step 5: Implement the adapter and verify Task 1**

Implement the exact interface above by constructing `CombatStats` without applying skill effects.

Run: `uv run python -m unittest tests.test_weapon_models tests.test_damage -v`

Expected: PASS.

- [ ] **Step 6: Commit Task 1**

```bash
git add mhwilds_optimizer/weapon_models.py tests/test_weapon_models.py
git commit -m "feat: add manual weapon input model"
```

### Task 2: Fixed Weapon Skills in Feasibility Solving

**Files:**
- Modify: `mhwilds_optimizer/equipment_models.py`
- Modify: `mhwilds_optimizer/constraints.py`
- Modify: `tests/test_equipment_models.py`
- Modify: `tests/test_constraints.py`

**Interfaces:**
- Consumes: Task 1 `Weapon`
- Produces: `FeasibleBuild.weapon_id: str | None`, `solve_feasible_build(..., *, weapon: Weapon | None = None)`, `enumerate_feasible_builds(..., *, limit: int | None = None, weapon: Weapon | None = None)`

- [ ] **Step 1: Write failing result-model and compatibility tests**

Assert `FeasibleBuild` accepts omitted `weapon_id` as `None`, accepts a non-empty explicit ID, and rejects an empty explicit ID. Call both public solver functions without `weapon` and assert the existing tiny-catalog signatures and status are unchanged.

- [ ] **Step 2: Run focused tests and confirm the interface failures**

Run: `uv run python -m unittest tests.test_equipment_models tests.test_constraints -v`

Expected: FAIL on the absent `weapon_id` and `weapon` parameters.

- [ ] **Step 3: Add the optional weapon result and solver interfaces**

Append `weapon_id: str | None = None` to `FeasibleBuild`. Thread the keyword-only optional `Weapon` through `_build_model` and `_ModelState`, returning its ID during reconstruction while keeping `None` behavior unchanged.

- [ ] **Step 4: Write failing fixed-skill and cross-model validation tests**

Using a `SkillKind.WEAPON` definition, assert a fixed weapon skill can satisfy `MINIMUM`, affects `EXACT`, and violates `FORBIDDEN`. Assert pre-solver `EquipmentInputError` for an unknown skill, level above `max_level`, armor/set/group kind skill, and weapon ID equal to an armor or charm ID.

- [ ] **Step 5: Implement validation and fixed skill terms**

Before precheck/solver exception handling, validate the optional value is `Weapon`, its ID is not an armor/charm owner ID, and every skill is a known `SkillKind.WEAPON` skill within its maximum. Add fixed skill levels as constants to the corresponding MIP expressions.

- [ ] **Step 6: Verify and commit Task 2**

Run: `uv run python -m unittest tests.test_equipment_models tests.test_constraints -v`

Expected: PASS.

```bash
git add mhwilds_optimizer/equipment_models.py mhwilds_optimizer/constraints.py tests/test_equipment_models.py tests/test_constraints.py
git commit -m "feat: include fixed weapon skills in feasibility"
```

### Task 3: Weapon Decoration Slots and User Documentation

**Files:**
- Modify: `mhwilds_optimizer/constraints.py`
- Modify: `tests/test_constraints.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 2 optional fixed weapon solver input and existing `DecorationPlacement`
- Produces: weapon-owned `DecorationPlacement` values and enumeration cuts covering weapon decoration choices

- [ ] **Step 1: Write failing weapon-slot feasibility tests**

Add a weapon with level-2 and level-1 slots and weapon decorations requiring levels 1, 2, and 3. Assert a requirement satisfiable only by legal weapon decorations is feasible; the level-3 decoration cannot use either slot; armor decorations never use weapon slots; weapon decorations never use armor/charm slots; and returned placements use the weapon ID and correct slot index.

- [ ] **Step 2: Run focused tests and confirm infeasibility**

Run: `uv run python -m unittest tests.test_constraints.FeasibilitySolverTests -v`

Expected: FAIL because weapon slots have no placement variables.

- [ ] **Step 3: Add weapon placement variables and reconstruction**

Create placement variables for compatible `SlotType.WEAPON` decorations on each fixed weapon slot, constrain each slot to at most one decoration, add their skill terms, and reuse the existing placement reconstruction. Ensure these variables remain in `_ModelState.binary_variables`.

- [ ] **Step 4: Write failing enumeration tests**

For a tiny catalog with one optional weapon decoration placement, compare enumerated build signatures including `weapon_id` and all decoration placements against a small exhaustive expected set. Assert `limit` still truncates deterministically without duplicate complete assignments.

- [ ] **Step 5: Verify weapon-aware enumeration**

Run: `uv run python -m unittest tests.test_constraints -v`

Expected: PASS with distinct empty/occupied weapon-slot assignments where each satisfies the requirements.

- [ ] **Step 6: Document manual weapon input**

Update the feasibility example in `README.md` to construct a `Weapon`, pass it by keyword, describe weapon-owned placements, and replace the statement that weapon slots are unsupported. State that the values are manual and that skill effects, weapon selection, state ailments, and series/group contribution remain unsupported.

- [ ] **Step 7: Run full verification and commit Task 3**

Run: `uv run python -m unittest discover -s tests -v`

Expected: all tests PASS with 0 failures and 0 errors.

```bash
git add mhwilds_optimizer/constraints.py tests/test_constraints.py README.md
git commit -m "feat: support weapon decoration slots"
```

