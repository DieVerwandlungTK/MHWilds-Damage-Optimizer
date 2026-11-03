# MHDB Data Normalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the four pinned MHDB raw JSON inputs into locally generated, validated, provenance-tracked optimizer inputs without committing derived game data.

**Architecture:** Pure functions in `mhdb_normalizers.py` validate and transform source records into deterministic lists with namespaced IDs. `data_normalization.py` verifies the raw download, orchestrates all transforms, writes every output through a staging directory, verifies an existing normalized dataset, and exposes the CLI.

**Tech Stack:** Python 3.12 standard library, `unittest`, Git

**Spec:** `docs/superpowers/specs/2026-11-03-mhdb-normalization-design.md`

## Global Constraints

- Read only the verified MHDB commit `c50a1eb892f4a1ad9bb35c147801658804be2cc2` downloaded by `mhwilds_optimizer.data_download`.
- Generate `skills.json`, `armor.json`, `decorations.json`, `regular_charms.json`, `validation_report.json`, and `manifest.json` under `data/normalized/mhdb/<commit>/`.
- Keep `data/normalized/` out of Git; commit only code, tests, schema documentation, and usage instructions.
- Preserve only Japanese and English names; do not copy descriptions or other translations.
- Do not infer missing game values. Random/appraised charm source records are excluded from regular charms and reported, not converted into legal appraised charm rolls.
- Use Python 3.12 and standard-library runtime dependencies only.

## Review Focus

- A missing or wrongly typed required source field must raise `NormalizationError` with record context and leave no final output; covered by Tasks 1 and 3.
- An armor, decoration, charm, or bonus reference to an unknown skill must fail rather than produce a dangling ID; covered by Task 2.
- Armor sets with fewer than five pieces must remain valid while a duplicate part within one set must fail; covered by Task 2.
- `is_random=true` amulets must be excluded from regular charms and counted in the report; covered by Task 2.
- An existing normalized file or manifest that was modified must be rejected, while an intact dataset must be reused without rewriting; covered by Task 3.

---

### Task 1: Shared validation and skill normalization

**Files:**
- Create: `mhwilds_optimizer/mhdb_normalizers.py`
- Create: `tests/test_data_normalization.py`

**Interfaces:**
- Produces: `NormalizationError(ValueError)`.
- Produces: `normalize_skills(records: list[object]) -> list[dict[str, object]]`.
- Produces: stable helpers for namespaced IDs, required fields, `{ja, en}` names, and skill-level maps consumed by Task 2.

- [ ] **Step 1: Write the failing skill-normalization tests**

Add `SkillNormalizationTests.test_normalizes_skill_identity_names_kind_and_ranks` with two literal source skills, including one rank with `set_pieces_required`. Assert exact namespaced IDs, source IDs, `{ja, en}` names, kinds, rank levels, optional piece threshold, sorted output, and `max_level` derived from the highest rank level.

Add `test_rejects_missing_english_skill_name_with_context`, asserting `NormalizationError` includes the source `game_id` and `names.en`.

- [ ] **Step 2: Run the tests and verify RED**

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_normalization.SkillNormalizationTests -v`

Expected: ERROR because `mhwilds_optimizer.mhdb_normalizers` does not exist.

- [ ] **Step 3: Implement minimal shared validation and `normalize_skills`**

Validate record/object types, integer `game_id`, non-empty `ja` and `en`, supported skill kinds (`armor`, `weapon`, `set`, `group`), non-empty rank lists, unique positive integer rank levels, and optional positive integer `set_pieces_required`. Generate `skill:<game_id>` IDs and sort by ID.

- [ ] **Step 4: Run focused tests and the full suite**

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_normalization.SkillNormalizationTests -v`

Expected: 2 tests pass.

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 9 tests pass with no errors or failures.

- [ ] **Step 5: Commit Task 1**

```bash
git add mhwilds_optimizer/mhdb_normalizers.py tests/test_data_normalization.py
git commit -m "feat: normalize MHDB skills"
```

### Task 2: Armor, decoration, and regular charm normalization

**Files:**
- Modify: `mhwilds_optimizer/mhdb_normalizers.py`
- Modify: `tests/test_data_normalization.py`

**Interfaces:**
- Consumes: `known_skills: Mapping[str, int]`, mapping normalized skill ID to maximum level.
- Produces: `normalize_armor(records, known_skills) -> list[dict[str, object]]`.
- Produces: `normalize_decorations(records, known_skills) -> list[dict[str, object]]`.
- Produces: `normalize_regular_charms(records, known_skills) -> tuple[list[dict[str, object]], int]`, where the integer is the number of excluded random source records.

- [ ] **Step 1: Write and run armor RED tests**

Add `EquipmentNormalizationTests.test_normalizes_partial_armor_set_with_bonuses` using a one-piece set. Assert composite armor ID, source set ID, part, slots, normalized skill map, rarity, set names, piece names, and normalized set/group bonus thresholds. This proves a partial set is valid.

Add `test_rejects_duplicate_armor_part_and_unknown_skill`, with subtests proving both conditions raise contextual `NormalizationError`.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_normalization.EquipmentNormalizationTests.test_normalizes_partial_armor_set_with_bonuses tests.test_data_normalization.EquipmentNormalizationTests.test_rejects_duplicate_armor_part_and_unknown_skill -v`

Expected: ERROR because `normalize_armor` is absent.

- [ ] **Step 2: Implement armor normalization and verify GREEN**

Accept only parts `head`, `chest`, `arms`, `waist`, `legs`; slot levels 1 through 3; positive skill levels not exceeding `known_skills`; and unique parts per source set. Normalize bonus `skill_id` references and positive `pieces`/`skill_level` thresholds. Sort armor by ID.

Run the two armor tests from Step 1.

Expected: both pass.

- [ ] **Step 3: Write and run decoration/charm RED tests**

Add `test_normalizes_weapon_and_armor_decorations` asserting `slot_type`, `required_slot_level`, normalized IDs and skills for one record of each type.

Add `test_flattens_regular_charm_ranks_and_reports_random_records` with one two-rank regular amulet and one random amulet. Assert two composite IDs, empty `slots`, rank values, skills, and excluded count 1.

Add `test_rejects_unknown_equipment_skill_reference`, covering decoration and charm references.

Run these three tests.

Expected: ERROR because the two normalizers are absent.

- [ ] **Step 4: Implement decoration/charm normalization and verify GREEN**

Validate decoration `allowed_on` as `weapon` or `armor`, required slot level 1 through 3, names, rarity, and referenced skill levels. Flatten only `is_random=false` amulet ranks; require unique positive rank levels and use empty slots without inferring source data. Count each skipped random parent record. Sort both outputs by ID.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_normalization.EquipmentNormalizationTests -v`

Expected: 5 tests pass.

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 14 tests pass with no errors or failures.

- [ ] **Step 5: Commit Task 2**

```bash
git add mhwilds_optimizer/mhdb_normalizers.py tests/test_data_normalization.py
git commit -m "feat: normalize MHDB equipment data"
```

### Task 3: Atomic dataset generation and integrity verification

**Files:**
- Create: `mhwilds_optimizer/data_normalization.py`
- Modify: `tests/test_data_normalization.py`

**Interfaces:**
- Consumes: Task 1/2 normalizers and `verify_mhdb_download(download_dir: Path) -> None`.
- Produces: `normalize_mhdb_data(raw_root: Path, normalized_root: Path, *, now: Now = utc_now) -> Path`.
- Produces: `verify_normalized_data(normalized_dir: Path, *, raw_manifest_sha256: str) -> None`, raising `NormalizationVerificationError`.

- [ ] **Step 1: Write and run the dataset-generation RED test**

Add `DatasetNormalizationTests.test_writes_all_outputs_manifest_and_report` using a complete tiny raw directory created through `download_mhdb_data` with injected payloads. Assert the exact six output filenames, normalized counts, excluded random count, raw commit and raw manifest SHA-256, schema version 1, output sizes and literal SHA-256 values, fixed UTC `generated_at`, and successful verification.

Run the focused test.

Expected: ERROR because `mhwilds_optimizer.data_normalization` does not exist.

- [ ] **Step 2: Implement generation and verify GREEN**

Read and transform the four verified raw files. Build `known_skills` from normalized skills. Write deterministic UTF-8 JSON for the four arrays and report into a `TemporaryDirectory` below `<normalized_root>/mhdb`; then write a manifest containing source identity, raw manifest hash, schema version, timestamp, counts, sizes, and SHA-256 values. Rename only after all transforms and writes succeed, then verify the result.

Run the focused test.

Expected: PASS.

- [ ] **Step 3: Write and run RED tests for failure atomicity and reuse**

Add `test_source_validation_failure_leaves_no_final_or_staging_directory`, supplying an unknown skill reference and asserting `NormalizationError` plus no artifacts.

Add `test_reuses_verified_dataset_without_rewriting` by recording manifest bytes and modification times, invoking normalization again, and asserting they remain unchanged.

Add `test_rejects_tampered_normalized_output`, changing one output byte and expecting `NormalizationVerificationError` naming the file.

Run the three tests.

Expected: at least the reuse and tamper tests fail because existing output verification is absent.

- [ ] **Step 4: Implement existing-output verification and verify GREEN**

Require exactly the six declared files; validate manifest schema, source commit, raw manifest hash, output names/counts/sizes/hashes; parse the five non-manifest JSON outputs; and return an intact existing directory before doing any transformation or writes. Use automatic staging cleanup for every failure.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_normalization.DatasetNormalizationTests -v`

Expected: 4 tests pass.

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 18 tests pass with no errors or failures.

- [ ] **Step 5: Commit Task 3**

```bash
git add mhwilds_optimizer/data_normalization.py tests/test_data_normalization.py
git commit -m "feat: generate verified normalized dataset"
```

### Task 4: CLI, documentation, and live normalization

**Files:**
- Modify: `mhwilds_optimizer/data_normalization.py`
- Modify: `.gitignore`
- Modify: `README.md`
- Create: `docs/data-schema.md`
- Modify: `tests/test_data_normalization.py`
- Local-only output: `data/normalized/mhdb/c50a1eb892f4a1ad9bb35c147801658804be2cc2/`

**Interfaces:**
- Consumes: Task 3 orchestration.
- Produces: `main(argv: Sequence[str] | None = None) -> int` and `uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_normalization --input data/raw --output data/normalized`.

- [ ] **Step 1: Write and run the CLI RED test**

Add `test_cli_help_documents_input_and_output`, asserting `main(["--help"])` exits 0 and documents `--input`, `data/raw`, `--output`, and `data/normalized`.

Run the focused test.

Expected: ERROR because `main` is absent.

- [ ] **Step 2: Implement CLI and verify GREEN**

Use `argparse`, print the completed normalized directory, and return 0. Add the module entry point.

Run the focused test.

Expected: PASS.

- [ ] **Step 3: Add ignore rules and documentation**

Add `data/normalized/` without removing current ignore entries. Extend README with the exact normalization command, output path, expected fixed-commit counts, regeneration behavior, and local-only licensing rationale. Document every normalized field and ID format in `docs/data-schema.md`.

- [ ] **Step 4: Run the complete offline suite**

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 19 tests pass with no errors or failures.

- [ ] **Step 5: Perform and inspect live normalization**

Run: `uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_normalization --input data/raw --output data/normalized`

Expected: prints the fixed-commit normalized directory and exits 0.

Inspect and verify the generated dataset.

Expected: `skills=179`, `armor=714`, `decorations=361`, `regular_charms=183`, `excluded_random_charm_records=4`, all hashes valid, and no `data/normalized/` path in `git status --short`.

- [ ] **Step 6: Commit Task 4**

```bash
git add .gitignore README.md docs/data-schema.md mhwilds_optimizer/data_normalization.py tests/test_data_normalization.py
git commit -m "feat: expose MHDB normalization CLI"
```

