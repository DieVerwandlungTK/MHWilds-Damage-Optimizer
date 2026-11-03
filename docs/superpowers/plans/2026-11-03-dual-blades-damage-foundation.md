# Dual Blades Damage Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source-traceable 27-hit Dual Blades Demon Dance I–III dataset and a pure Python calculator that returns physical, elemental, and total expected damage without claiming unverified exactness.

**Architecture:** Store the small, redistributable numeric combo definition as package JSON and validate it into frozen domain models at load time. Keep damage inputs and results in a separate model module, with pure calculation functions using `Decimal`; propagate the weakest verification status from combo data and rules into every combo result.

**Tech Stack:** Python 3.12 standard library (`dataclasses`, `decimal`, `enum`, `json`, `pathlib`, `unittest`); no new runtime dependency.

**Spec:** `docs/superpowers/specs/2026-11-03-dual-blades-damage-foundation-design.md`

## Global Constraints

- Support Python `>=3.12` and add no dependency.
- Do not copy game descriptions or images; commit only numeric hit data and source metadata.
- Use `Decimal`, never binary `float`, for damage arithmetic and JSON numeric conversion.
- Treat affinity and hitzones as percentages in `[-100, 100]` and `[0, 100]` respectively; all multipliers must be positive.
- The committed data starts at `cross_checked`, not `verified`.
- `continuous_approx` may run with warnings; `game_exact` must reject any input below `verified`.
- Do not implement skills, buff stacking, sharpness depletion, status buildup, MIP integration, or Demon Flurry I–II.

## Review Focus

- JSON numeric values decoded through binary `float`: Task 1 tests exact `Decimal("0.6")` values.
- Silent acceptance of malformed or incomplete 27-hit data: Task 1 tests count, contiguous indexes, move boundaries, and invalid fixtures.
- Percentage/multiplier boundary confusion: Task 2 tests invalid affinity, hitzone, and non-positive multiplier inputs.
- Negative-affinity expected damage accidentally using the positive critical modifier: Task 2 tests both signs independently.
- Exact mode producing a number from `cross_checked` data or rules: Task 3 tests both failure paths and only permits all-`verified` inputs.

---

### Task 1: Source-traceable combo data and loader

**Files:**
- Create: `mhwilds_optimizer/data/combos/dual_blades.json`
- Create: `mhwilds_optimizer/combo_data.py`
- Create: `tests/test_combo_data.py`

**Interfaces:**
- Consumes: package-local JSON and no earlier task API.
- Produces: `VerificationStatus`, `SourceReference`, `Hit`, `Combo`, `ComboDataError`, and `load_combo(combo_id: str = "dual_blades:demon_dance_1_3", path: Path | None = None) -> Combo` from `mhwilds_optimizer.combo_data`.

- [ ] **Step 1: Write the failing happy-path source-data tests**

Add `ComboDataTests.test_loads_demon_dance_hit_sequences_as_decimal` asserting:

```python
combo = load_combo()
self.assertEqual(combo.id, "dual_blades:demon_dance_1_3")
self.assertEqual(combo.weapon_type, "dual_blades")
self.assertEqual(combo.verification_status, VerificationStatus.CROSS_CHECKED)
self.assertEqual(len(combo.hits), 27)
self.assertEqual(
    [hit.motion_value for hit in combo.hits],
    list(map(Decimal, map(str, [18, 18, 6, 6, 10, 10, 4, 4, 20, 20, 11, 11,
                                16, 16, 6, 25,
                                22, 8, 5, 22, 5, 14, 18, 8, 18, 36, 36]))),
)
self.assertEqual(
    [hit.element_modifier for hit in combo.hits],
    list(map(Decimal, map(str, [1, 1, 0.6, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8,
                                0.6, 0.6, 0.8, 0.8,
                                0.6, 0.6, 0.6, 0.6, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8]))),
)
```

Also assert move counts `{"demon_dance_1": 12, "demon_dance_2": 4, "demon_dance_3": 11}`, global indexes `1..27`, per-move indexes restarting at 1, every damage type equal to `"sever"`, and the five approved source URLs from the spec are present with non-empty `supports` fields.

- [ ] **Step 2: Run the happy-path test to verify it fails**

Run: `python -m unittest tests.test_combo_data.ComboDataTests.test_loads_demon_dance_hit_sequences_as_decimal -v`

Expected: `ERROR` because `mhwilds_optimizer.combo_data` does not exist.

- [ ] **Step 3: Add the JSON and minimal frozen loader models**

Create:

```python
class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    CROSS_CHECKED = "cross_checked"
    VERIFIED = "verified"

@dataclass(frozen=True)
class SourceReference:
    name: str
    url: str
    checked_at: date
    supports: tuple[str, ...]

@dataclass(frozen=True)
class Hit:
    index: int
    move_id: str
    move_hit_index: int
    motion_value: Decimal
    element_modifier: Decimal
    damage_type: str

@dataclass(frozen=True)
class Combo:
    id: str
    weapon_type: str
    game_version: str
    checked_through_version: str
    verification_status: VerificationStatus
    sources: tuple[SourceReference, ...]
    hits: tuple[Hit, ...]

class ComboDataError(ValueError): ...
```

`load_combo` must read numeric JSON tokens with `json.load(..., parse_float=Decimal, parse_int=Decimal)`, convert indexes to `int` only after checking integrality, and return the requested combo.

- [ ] **Step 4: Run the happy-path test to verify it passes**

Run: `python -m unittest tests.test_combo_data.ComboDataTests.test_loads_demon_dance_hit_sequences_as_decimal -v`

Expected: `OK` with 1 test run.

- [ ] **Step 5: Write malformed-data tests**

Add table-driven temporary-file tests proving `ComboDataError` for an unknown combo ID, 26 hits, duplicate/non-contiguous indexes, wrong move counts, non-positive motion value, non-positive element modifier, a damage type other than `sever`, missing source support, and malformed verification status. Assert error messages include the failing field or combo ID.

- [ ] **Step 6: Run malformed-data tests to verify they fail**

Run: `python -m unittest tests.test_combo_data -v`

Expected: `FAIL` for malformed fixtures that the minimal loader still accepts.

- [ ] **Step 7: Add complete boundary validation in `load_combo`**

Validate schema version `1`, required top-level fields, exactly one uniquely identified requested combo, the fixed `12/4/11` move sequence, contiguous indexes, positive numeric values, `sever`, non-empty source metadata, and valid ISO dates. Wrap JSON/I/O/type failures in `ComboDataError` while retaining the failing path in the message.

- [ ] **Step 8: Run Task 1 tests**

Run: `python -m unittest tests.test_combo_data -v`

Expected: all Task 1 tests pass.

- [ ] **Step 9: Commit Task 1**

```bash
git add mhwilds_optimizer/data/combos/dual_blades.json mhwilds_optimizer/combo_data.py tests/test_combo_data.py
git commit -m "feat: add sourced dual blades combo data"
```

### Task 2: Typed continuous damage calculation

**Files:**
- Create: `mhwilds_optimizer/damage_models.py`
- Create: `mhwilds_optimizer/damage.py`
- Create: `tests/test_damage.py`

**Interfaces:**
- Consumes: `Hit`, `Combo`, and `VerificationStatus` from Task 1.
- Produces: `CalculationMode`, `Sharpness`, `SharpnessModifiers`, `CombatStats`, `TargetHitzones`, `DamageRules`, `HitDamage`, `ComboDamage`, `DamageInputError`, `DEFAULT_DAMAGE_RULES`, `calculate_hit_damage(...) -> HitDamage`, and `calculate_combo_damage(...) -> ComboDamage`.

- [ ] **Step 1: Write failing model-boundary tests**

Create tests for these constructors and exact fields:

```python
CombatStats(
    raw=Decimal("100"),
    element=Decimal("20"),
    affinity_percent=Decimal("25"),
    positive_critical_modifier=Decimal("1.25"),
    negative_critical_modifier=Decimal("0.75"),
    sharpness=Sharpness.WHITE,
    demon_dodge_buff=False,
)
TargetHitzones(
    sever=Decimal("60"),
    element=Decimal("20"),
    monster_damage_modifier=Decimal("1"),
)
```

Assert `DamageInputError` for raw/element below zero, affinity outside `[-100, 100]`, either hitzone outside `[0, 100]`, non-positive critical or monster multipliers, and an unknown sharpness string. Include exact red/green/blue/white modifier assertions from the spec, especially white raw `1.32` and element `1.15`.

- [ ] **Step 2: Run model-boundary tests to verify they fail**

Run: `python -m unittest tests.test_damage.DamageModelTests -v`

Expected: `ERROR` because the modules do not exist.

- [ ] **Step 3: Implement frozen input/result models and default cross-checked rules**

Define the enums and dataclasses named in Interfaces. `DamageRules` contains all six sharpness entries from the spec, Demon Dodge raw `1.15`, Demon Dodge element `1.3`, and `VerificationStatus.CROSS_CHECKED`. Validate in `__post_init__`; accept `Decimal` only so callers cannot introduce float artifacts.

- [ ] **Step 4: Run model-boundary tests to verify they pass**

Run: `python -m unittest tests.test_damage.DamageModelTests -v`

Expected: `OK`.

- [ ] **Step 5: Write failing continuous hit-calculation tests**

Use one `Hit` with motion value `10`, element modifier `0.6`, green sharpness, raw `100`, element `20`, sever hitzone `60`, element hitzone `25`, and neutral affinity. Assert physical `Decimal("6.3000")`, elemental `Decimal("3.000")`, total `Decimal("9.3000")`, and no intermediate rounding.

Add independent tests asserting:

- positive affinity 40 with modifier 1.25 yields expected critical multiplier `1.10`;
- negative affinity -40 uses 0.75 and yields `0.90`;
- Demon Dodge multiplies physical by `1.15` and elemental by `1.3` separately;
- monster multiplier affects both components once;
- zero raw, zero element, and zero hitzones produce valid zero components.

- [ ] **Step 6: Run hit-calculation tests to verify they fail**

Run: `python -m unittest tests.test_damage.ContinuousHitDamageTests -v`

Expected: `FAIL` or `ERROR` because calculation functions are absent.

- [ ] **Step 7: Implement the pure hit calculator**

Use this exact public signature:

```python
def calculate_hit_damage(
    stats: CombatStats,
    hit: Hit,
    target: TargetHitzones,
    *,
    rules: DamageRules = DEFAULT_DAMAGE_RULES,
    data_status: VerificationStatus = VerificationStatus.CROSS_CHECKED,
    mode: CalculationMode = CalculationMode.CONTINUOUS_APPROX,
) -> HitDamage:
```

Implement the two formulas and sign-specific expected-critical multiplier from the spec. Return component values, total, mode, the weaker of `data_status` and `rules.verification_status`, and deterministic warnings.

- [ ] **Step 8: Run continuous hit-calculation tests**

Run: `python -m unittest tests.test_damage.ContinuousHitDamageTests -v`

Expected: all tests pass.

- [ ] **Step 9: Write and implement the continuous combo aggregation test**

Test that `calculate_combo_damage(combo, stats, target, rules=..., mode=...)` returns 27 ordered hit results, sums their physical and elemental values independently, and uses the weaker combo/rules status. Implement it by calling `calculate_hit_damage` for every hit; do not duplicate formulas.

- [ ] **Step 10: Run Task 2 tests**

Run: `python -m unittest tests.test_damage -v`

Expected: all Task 2 tests pass.

- [ ] **Step 11: Commit Task 2**

```bash
git add mhwilds_optimizer/damage_models.py mhwilds_optimizer/damage.py tests/test_damage.py
git commit -m "feat: calculate continuous combo damage"
```

### Task 3: Exact-mode safety gate, rounding, and user documentation

**Files:**
- Modify: `mhwilds_optimizer/damage.py`
- Modify: `tests/test_damage.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: all Task 1 and Task 2 interfaces.
- Produces: `UnverifiedDamageError`, stable exact-mode rejection behavior, and documented public usage.

- [ ] **Step 1: Write failing exact-mode safety tests**

Add `GameExactDamageTests` proving:

- `cross_checked` combo data with verified rules raises `UnverifiedDamageError` naming `data`;
- verified combo data with cross-checked rules raises `UnverifiedDamageError` naming `rules`;
- when both are verified, each physical and elemental component is rounded independently to one decimal with `Decimal.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)`, then added;
- combo totals equal the sum of already-rounded hit components;
- continuous mode remains unrounded and available for `cross_checked` inputs.

- [ ] **Step 2: Run exact-mode tests to verify they fail**

Run: `python -m unittest tests.test_damage.GameExactDamageTests -v`

Expected: `FAIL` because the strict gate and exact rounding are not implemented.

- [ ] **Step 3: Implement `UnverifiedDamageError` and exact mode**

Before calculating, reject each below-verified input with a contextual message. For permitted exact mode, calculate the same unrounded physical and elemental expressions as continuous mode, quantize components independently, and derive the hit total from those components. Never round combo totals again.

- [ ] **Step 4: Run exact-mode and full damage tests**

Run: `python -m unittest tests.test_damage -v`

Expected: all damage tests pass.

- [ ] **Step 5: Add README usage and limitation documentation**

Document the package API with a minimal example using `load_combo`, `CombatStats`, `TargetHitzones`, and `calculate_combo_damage`. State that the committed Ver.1.020.00 values were checked through Ver.1.042.00.03, remain `cross_checked`, permit only `continuous_approx`, and that `game_exact` intentionally stops until game-measured regression evidence promotes both data and rules to `verified`.

- [ ] **Step 6: Run the complete repository verification**

Run: `python -m unittest discover -s tests -v`

Expected: all existing download/normalization tests and all new combo/damage tests pass with zero failures and zero errors.

Run: `git diff --check`

Expected: no output and exit code 0.

- [ ] **Step 7: Commit Task 3**

```bash
git add mhwilds_optimizer/damage.py tests/test_damage.py README.md
git commit -m "feat: gate exact damage on verified inputs"
```

### Task 4: Final source and requirements audit

**Files:**
- Modify only if the audit finds a defect in files created by Tasks 1–3.

**Interfaces:**
- Consumes: the completed feature.
- Produces: verification evidence; no new API.

- [ ] **Step 1: Compare committed JSON against both source sequences**

Manually compare all 27 motion values and element modifiers, move boundaries `12/4/11`, source URLs, `game_version`, and `checked_through_version` with the approved design and source notes. Record any discrepancy as a failing test before correcting it.

- [ ] **Step 2: Audit the design requirement checklist**

Confirm every goal and non-goal in the design: sourced data, separate physical/element totals, sharpness, signed affinity, Demon Dodge, monster modifier, Decimal arithmetic, status propagation, strict exact gate, and no out-of-scope skill/MIP behavior.

- [ ] **Step 3: Run final verification from a clean process**

Run: `python -m unittest discover -s tests -v`

Expected: zero failures and zero errors.

Run: `git status --short`

Expected: no uncommitted files.

- [ ] **Step 4: If the audit required fixes, commit them**

```bash
git add <only-audited-feature-files>
git commit -m "fix: align damage foundation with verified design"
```
