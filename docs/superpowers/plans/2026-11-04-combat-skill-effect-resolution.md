# Combat Skill Effect Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 装備構成の有効スキルレベルと手入力武器から、Ver.1.042.00.03の直接コンボ火力に必要な能力値を条件付き効果も含めて解決する。

**Architecture:** バージョン付きJSONを検証済みの不変効果モデルへ読み込み、共通リゾルバが自動条件と明示条件を評価して補正を集約する。解決結果は拡張した既存 `CombatStats` に接続し、適用・不発・無視・未対応を監査情報として同時に返す。

**Tech Stack:** Python 3.11、標準ライブラリ `dataclasses` / `decimal` / `enum` / `json` / `unittest`

**Spec:** `docs/superpowers/specs/2026-11-04-combat-skill-effect-resolution-design.md`

## Global Constraints

- 対象ゲームバージョンは `1.042.00.03` とする。
- 効果値はJSON文字列から `Decimal` へ変換し、`float` を経由しない。
- MHDB固定コミット `c50a1eb892f4a1ad9bb35c147801658804be2cc2` の安定IDを使い、ゲーム由来の名称・説明全文は組み込みデータへ複製しない。
- 常時効果と条件付き効果は同じ宣言的効果節で扱い、条件未指定を暗黙の `false` にしない。
- 直接コンボ火力以外、状態異常、斬れ味消費、追加ヒット、双剣以外の固有効果は扱わない。
- 数値または現行モデルでの評価方法が確定しない火力スキルは推測せず `unsupported` に分類する。
- 解決とダメージ計算は `continuous_approx` に限定し、`game_exact` の保証を追加しない。
- non-strict結果は `ranking_eligible=False` とし、候補ランキングには使用できない。

## Review Focus

- 手作りまたは古い `FeasibleBuild` に未知・上限超過のスキルレベルがある場合、表引き前に文脈付き `SkillResolutionError` にする（Task 3）。
- `FeasibleBuild.weapon_id` とコンテキストの武器IDが食い違う場合、別武器の能力値を使わず拒否する（Task 3）。
- 自動条件と明示条件が同じキーへ異なる値を与えた場合、どちらかを優先せず拒否する（Task 3）。
- 無属性武器に属性攻撃強化または属性会心がある場合、架空の属性値を生成せず不発として監査する（Task 4）。
- strict失敗をnon-strictへ切り替えた場合も、警告と `ranking_eligible=False` を必ず残す（Task 3）。

---

### Task 1: Damage Model Modifier Hooks

**Files:**
- Modify: `mhwilds_optimizer/damage_models.py`
- Modify: `mhwilds_optimizer/damage.py`
- Modify: `tests/test_damage.py`
- Modify: `tests/test_weapon_models.py`

**Interfaces:**
- Consumes: existing `CombatStats`, `calculate_hit_damage(...)`, and `combat_stats_from_weapon(...)`
- Produces: `CombatStats.raw_damage_modifier`, `element_damage_modifier`, and `positive_element_critical_modifier`, each defaulting to `Decimal("1")`

- [ ] **Step 1: Write failing model-validation and compatibility tests**

Append tests proving existing seven-argument `CombatStats` construction and `combat_stats_from_weapon` still produce three default-one fields. Add table-driven cases requiring each new field to be a finite positive `Decimal`, rejecting `int`, `float`, zero, negative, and infinity with `DamageInputError`.

- [ ] **Step 2: Run focused tests and confirm the missing-field failure**

Run: `uv run python -m unittest tests.test_damage tests.test_weapon_models -v`

Expected: FAIL because `CombatStats` does not expose the new modifier fields.

- [ ] **Step 3: Extend `CombatStats` compatibly**

Add the three fields at the end of the frozen dataclass with default `Decimal("1")` values and validate them with `_require_positive` in `__post_init__`.

- [ ] **Step 4: Write failing physical, elemental, and elemental-critical tests**

Using the current one-hit fixture, assert:

- `raw_damage_modifier=Decimal("1.2")` multiplies only `physical` once.
- `element_damage_modifier=Decimal("1.3")` multiplies only `elemental` once.
- 40% positive affinity and `positive_element_critical_modifier=Decimal("1.25")` multiply elemental damage by `1.10`.
- negative affinity leaves elemental damage unchanged while preserving the existing negative physical critical calculation.
- the three new modifiers compose independently with `demon_dodge_buff`.

- [ ] **Step 5: Implement the damage-formula hooks**

Add `_expected_element_critical_modifier(stats: CombatStats) -> Decimal`; return `1 + affinity / 100 * (positive_element_critical_modifier - 1)` only for positive affinity, otherwise `1`. Apply `raw_damage_modifier` once to the physical component and both elemental modifiers once to the elemental component.

- [ ] **Step 6: Verify and commit Task 1**

Run: `uv run python -m unittest tests.test_damage tests.test_weapon_models -v`

Expected: PASS.

```bash
git add mhwilds_optimizer/damage_models.py mhwilds_optimizer/damage.py tests/test_damage.py tests/test_weapon_models.py
git commit -m "feat: support skill damage modifiers"
```

### Task 2: Versioned Skill Effect Data Loader

**Files:**
- Create: `mhwilds_optimizer/skill_effect_models.py`
- Create: `mhwilds_optimizer/skill_effect_data.py`
- Create: `tests/test_skill_effect_data.py`

**Interfaces:**
- Consumes: `EquipmentCatalog`, `SkillDefinition`, `SkillKind`, `VerificationStatus`, and `SourceReference`
- Produces: `SkillEffectDataError`, `ModifierKind`, `ConditionOperator`, `EffectCondition`, `EffectModifier`, `EffectClause`, `SkillRankEffect`, `SkillEffectDefinition`, `UnsupportedSkill`, `NonDamageSkill`, `SkillEffectTable`, and `load_skill_effect_table(catalog: EquipmentCatalog | None = None, path: Path | None = None, *, expected_game_version: str = "1.042.00.03") -> SkillEffectTable`

- [ ] **Step 1: Write failing minimal-schema and immutability tests**

Create a temporary JSON fixture containing one supported skill, one unsupported skill, one non-damage skill, one source, and two rank effects. Assert strings such as `"1.04"` become exact `Decimal` values; all sequences are tuples; all ID/rank/category mappings are immutable; and the returned table records schema version `1`, game version, verification status, and sources.

- [ ] **Step 2: Run the loader test and confirm the missing-module failure**

Run: `uv run python -m unittest tests.test_skill_effect_data -v`

Expected: FAIL because `mhwilds_optimizer.skill_effect_data` and its models do not exist.

- [ ] **Step 3: Define the effect-table value model and JSON contract**

Use these exact enums:

- `ModifierKind`: `raw_flat`, `raw_multiplier`, `affinity_points`, `element_flat`, `element_multiplier`, `positive_critical_modifier`, `raw_damage_multiplier`, `element_damage_multiplier`, `positive_element_critical_modifier`.
- `ConditionOperator`: `equals`, `at_most`.

Every category entry records `kind` and `max_level`. Each supported rank contains ordered clauses; each clause contains zero or more `EffectCondition(key: str, operator: ConditionOperator, value: bool | str)` values and one or more `EffectModifier(kind: ModifierKind, value: Decimal)` values. `positive_critical_modifier` and `positive_element_critical_modifier` are replacement candidates; flat values add and multiplier values multiply.

- [ ] **Step 4: Implement strict parsing for a valid fixture**

Parse JSON integers normally and require every modifier value to be a non-empty decimal string before constructing `Decimal`. Copy collections into tuple or `MappingProxyType`, and wrap file, JSON, and model failures as path-aware `SkillEffectDataError`.

- [ ] **Step 5: Write failing schema, catalog, and version validation tests**

Add table-driven cases for missing/extra top-level fields, schema version other than `1`, target-version mismatch, invalid verification/source data, unknown modifier/operator/condition key, non-string/non-finite modifier values, empty clauses/modifiers, duplicate IDs/ranks, rank gaps, rank beyond `max_level`, catalog kind mismatch, unknown skill ID, and the same ID appearing in more than one of `skills` / `unsupported` / `non_damage`.

Condition keys accepted by schema version 1 are: `monster_enraged`, `target_weak`, `target_wounded`, `sharpness`, `weapon_element`, `full_health`, `health_at_most_35_percent`, `red_health`, `maximum_stamina`, `virus_overcome`, `target_poisoned_or_paralyzed`, `hunter_statused`, `after_dodge`, `after_damage`, `after_bind_recovery`, `after_power_clash_or_offset`, `after_perfect_guard`, `after_eating`, `wet`, `bubbled`, `latent_power_active`, `burst_stage`, and `burst_active`. The combined target-status key prevents Foray from being applied twice when both statuses are represented; separate wet/bubbled keys preserve Slicked Blade stacking.

- [ ] **Step 6: Implement cross-validation and verify Task 2**

Validate stable ID syntax, declared kinds/max levels, complete supported rank sequences from 1 through `max_level`, and category disjointness without a catalog. When a catalog is supplied, additionally reject unknown IDs and kind/max-level mismatches. Allow a catalog skill to remain unclassified at load time so the resolver can report it only when a build actually uses it.

Run: `uv run python -m unittest tests.test_skill_effect_data -v`

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```bash
git add mhwilds_optimizer/skill_effect_models.py mhwilds_optimizer/skill_effect_data.py tests/test_skill_effect_data.py
git commit -m "feat: load versioned skill effect data"
```

### Task 3: Condition Resolution and Skill Effect Aggregation

**Files:**
- Create: `mhwilds_optimizer/skill_effects.py`
- Create: `tests/test_skill_effects.py`

**Interfaces:**
- Consumes: Task 1 `CombatStats` modifiers; Task 2 `SkillEffectTable`; existing `FeasibleBuild`, `EquipmentCatalog`, `Weapon`, `TargetHitzones`, and `combat_stats_from_weapon`
- Produces: `SkillResolutionError`, `MissingSkillConditionError`, `SkillConditionState`, `SkillResolutionContext`, `SkillEffectAudit`, `SkillResolutionResult`, and `resolve_combat_stats(build: FeasibleBuild, catalog: EquipmentCatalog, context: SkillResolutionContext, *, table: SkillEffectTable | None = None, expected_game_version: str = "1.042.00.03", strict: bool = True, base_positive_critical_modifier: Decimal = Decimal("1.25"), base_negative_critical_modifier: Decimal = Decimal("0.75")) -> SkillResolutionResult`

- [ ] **Step 1: Write failing state/context/result model tests**

Assert all models are frozen and copy mapping inputs. `SkillConditionState.values` accepts only the Task 2 condition keys with `bool` values except `sharpness`, `weapon_element`, and `burst_stage`, which accept their declared enum strings. Context requires `Weapon`, `TargetHitzones`, and booleans for enraged, wounded, and `demon_dodge_buff`; the public resolver rejects non-finite or non-positive base critical modifiers.

`SkillResolutionResult` exposes `stats`, ordered `audit`, `ignored_skill_ids`, `warnings`, `verification_status`, and `ranking_eligible`. Each audit entry records skill ID, level, clause index, outcome (`applied` or `inactive`), and immutable condition evidence.

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run: `uv run python -m unittest tests.test_skill_effects -v`

Expected: FAIL because `mhwilds_optimizer.skill_effects` does not exist.

- [ ] **Step 3: Write failing automatic and explicit condition tests**

Use a tiny in-memory table to assert:

- `target_weak` is true at sever hitzone 45 and false at 44.9.
- `monster_enraged`, `target_wounded`, `weapon_element`, and ordered `sharpness at_most` come from context/weapon.
- a required explicit boolean that is true applies, false creates an inactive audit, and absent raises `MissingSkillConditionError`.
- an explicitly supplied automatic value must match the derived value or raise `SkillResolutionError`.
- all conditions in one clause use AND; independent clauses may both apply.

- [ ] **Step 4: Implement tri-state condition evaluation**

Derive automatic values without mutating caller state. Order sharpness from `red` through `white`. Evaluate `equals` for boolean/string values and `at_most` only for sharpness. Resolve every condition before aggregating that clause so missing input cannot partially apply a skill.

- [ ] **Step 5: Write failing aggregation, auditing, and failure-policy tests**

Assert the exact order `(weapon.raw * product(raw_multiplier)) + sum(raw_flat)` and the equivalent element order. Assert affinity additions clamp to `[-100, 100]`; mismatched weapon elements create inactive audits; distinct simultaneous replacement values for either critical modifier raise; raw/element damage multipliers multiply; and the resulting `CombatStats` retains weapon sharpness and dodge state.

Also cover the Review Focus failures: invalid build skill level, weapon-ID mismatch, unsupported and unclassified active skills, non-damage ignored skills, version mismatch, and auto/explicit conflict. In strict mode these raise; in non-strict mode unsupported/unclassified skills produce warnings and `ranking_eligible=False` without inventing modifiers. Missing conditions and malformed inputs remain errors in both modes.

- [ ] **Step 6: Implement deterministic aggregation and policy**

Validate every non-zero effective skill against the catalog before classification. Iterate by sorted skill ID and source clause order. Start critical replacements at the supplied base positive value and `1` for elemental critical; call `combat_stats_from_weapon` with the context weapon and resolved critical values, then use `dataclasses.replace` for resolved raw, element, affinity, and Task 1 damage fields. Set `ranking_eligible` when no unsupported or unclassified skill was skipped; verification-status advisory warnings alone do not make an otherwise complete strict result ineligible.

- [ ] **Step 7: Verify and commit Task 3**

Run: `uv run python -m unittest tests.test_skill_effects tests.test_damage tests.test_weapon_models -v`

Expected: PASS.

```bash
git add mhwilds_optimizer/skill_effects.py tests/test_skill_effects.py
git commit -m "feat: resolve conditional skill effects"
```

### Task 4: Built-in Ver.1.042 Effect Catalog and End-to-End Evaluation

**Files:**
- Create: `mhwilds_optimizer/data/skill_effects/1.042.00.03.json`
- Modify: `tests/test_skill_effect_data.py`
- Modify: `tests/test_skill_effects.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–3 and normalized catalogs produced from MHDB commit `c50a1eb892f4a1ad9bb35c147801658804be2cc2`
- Produces: default-path behavior for `load_skill_effect_table(...)` and `resolve_combat_stats(...)`, plus a documented build-to-combo workflow

- [ ] **Step 1: Write failing built-in catalog coverage tests**

Load the default effect table without requiring downloaded raw data. Assert game version `1.042.00.03`, exactly 179 fixed-source skill IDs, no category overlap, valid declared kinds/max levels/ranks, and representative IDs in each category. Then pass a small catalog with a deliberately mismatched kind/max level and assert optional catalog cross-validation rejects it. Assert the file contains only stable IDs, numeric/condition data, reasons, and source metadata—not localized skill names or copied game descriptions.

- [ ] **Step 2: Add the source-traceable built-in effect table**

Transcribe exact rank values from the fixed MHDB descriptions and record the individual official update URL used to check later changes. Initial supported coverage must include the five-rank Attack Boost/Critical Eye/Critical Boost/Weakness Exploit families; all five elemental attack skills; Agitator, Foray, Counterstrike, Adrenaline Rush, Resentment, Peak Performance, Heroics, Maximum Might, Latent Power, Antivirus, Slicked Blade, Offensive Guard, and Bludgeoner; plus exact direct-firepower set/group effects such as Xu Wu's Vigor (`skill:-1468066176`), Doshaguma's Might (`skill:-62248528`), and Ebony Odogaron's Power (`skill:918165056`).

At minimum classify Burst (`skill:565867136`), Coalescence (`skill:-1700743296`), Critical Element (`skill:313598432`), Elemental Absorption (`skill:1489568384`), Convert Element (`skill:2083363072`), and Flayer (`skill:-856322816`) as `unsupported` unless implementation-time primary evidence resolves their values and current-combo semantics. Classify remaining fixed-source skills explicitly as `non_damage` or `unsupported`; never infer zero effect from absence.

- [ ] **Step 3: Run catalog tests and correct data-only validation failures**

Run: `uv run python -m unittest tests.test_skill_effect_data -v`

Expected: PASS, with all fixed-source skills classified and all supported ranks validated.

- [ ] **Step 4: Write end-to-end representative build tests**

Construct a fire `Weapon` with raw `100`, element `20`, affinity `0`, and green sharpness. Use effective Attack Boost 4, Fire Attack 2, Weakness Exploit 1, Critical Boost 1, and Bludgeoner 3 in a representative `FeasibleBuild`; the fixture's granted/effective levels should represent weapon, armor, decoration, charm, and set/group contributions already merged by feasibility solving. Against sever hitzone 45 with a wound, assert resolved raw `110` (`100 * 1.02 + 8`), element `72` (`20 * 1.10 + 50`), affinity `8` (`5 + 3`), positive critical modifier `1.28`, raw damage modifier `1.10`, default-one elemental modifiers, ordered audits, and `ranking_eligible=True`. Pass those stats to the existing dual-blades combo and assert its result matches direct `calculate_combo_damage` use of the expected `CombatStats`.

Add focused built-in tests for Weakness Exploit at 44.9/45 and wounded states, Agitator enraged false/true, elemental attack type match/mismatch, Critical Boost positive/negative affinity, Bludgeoner sharpness threshold, missing explicit condition, and an unsupported skill in strict/non-strict modes. Include the Review Focus case where an elementless weapon never gains element or elemental critical damage.

- [ ] **Step 5: Verify all built-in effects through public APIs**

Run: `uv run python -m unittest tests.test_skill_effects tests.test_skill_effect_data tests.test_damage -v`

Expected: PASS.

- [ ] **Step 6: Document the resolution workflow and limitations**

Add a README example loading the normalized equipment catalog, creating a manual weapon and context, calling `resolve_combat_stats`, checking `ranking_eligible`, and passing `result.stats` to `calculate_combo_damage`. Document strict default behavior, required explicit conditions, Ver.1.042.00.03 pinning, `continuous_approx`, and the unsupported-skill audit policy.

- [ ] **Step 7: Run full verification and commit Task 4**

Run: `uv run python -m unittest discover -s tests -v`

Expected: all tests PASS with 0 failures and 0 errors.

Run: `git diff --check`

Expected: no output.

```bash
git add mhwilds_optimizer/data/skill_effects/1.042.00.03.json tests/test_skill_effect_data.py tests/test_skill_effects.py README.md
git commit -m "feat: add Ver.1.042 combat skill effects"
```
