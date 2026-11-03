# MHDB Data Download Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download the four MHDB merged JSON inputs needed for Phase 1 from a pinned upstream commit, record their provenance and integrity, and keep all downloaded data out of Git.

**Architecture:** A standard-library Python module owns the pinned source definition, staged download, JSON validation, SHA-256 manifest, and verification of an existing download. Its module CLI writes under `data/raw/` by default; unit tests inject an in-memory fetch function so the suite never depends on the network.

**Tech Stack:** Python 3.12 standard library, `unittest`, Git

**Spec:** `docs/superpowers/specs/2026-11-03-mhdb-data-download-design.md`

## Global Constraints

- Fetch only `Armor.json`, `Accessory.json`, `Amulet.json`, and `Skill.json` from MHDB Wilds Data commit `c50a1eb892f4a1ad9bb35c147801658804be2cc2`.
- Store downloads under `data/raw/mhdb/<commit>/`; do not commit raw JSON or its generated manifest.
- Record repository URL, commit, retrieval timestamp, file URL, byte size, SHA-256, and GPL-3.0 license metadata.
- Use no guessed game fields or constants and perform no normalization in this phase.
- Use Python 3.12 and standard-library runtime dependencies only.

## Review Focus

- A truncated or syntactically invalid response must fail before any final download directory appears; covered by Task 2's invalid-JSON test.
- A network failure after earlier files were fetched must leave no partial final directory or success manifest; covered by Task 2's interrupted-fetch test.
- A previously downloaded file changed locally must be reported rather than silently trusted; covered by Task 2's tamper test.
- Re-running against an intact pinned download must not contact the network; covered by Task 2's reuse test.
- Running the documented command from the repository root must use `data/raw` and keep generated files invisible to Git; covered by Task 3's CLI and live verification steps.

---

### Task 1: Pinned source and manifest-producing downloader

**Files:**
- Create: `mhwilds_optimizer/__init__.py`
- Create: `mhwilds_optimizer/data_download.py`
- Create: `tests/__init__.py`
- Create: `tests/test_data_download.py`

**Interfaces:**
- Consumes: A destination root `pathlib.Path`; an injectable `fetch(url: str) -> bytes`; an injectable timezone-aware `now() -> datetime`.
- Produces: `download_mhdb_data(raw_root: Path, *, fetch: FetchBytes = fetch_url, now: Now = utc_now) -> Path`, returning `data/raw/mhdb/<commit>` after all four files and `manifest.json` are durable.
- Produces: constants `MHDB_REPOSITORY_URL`, `MHDB_COMMIT`, `MHDB_LICENSE`, and `MHDB_FILES`.

- [ ] **Step 1: Write the failing happy-path test**

Add `DownloadDataTests.test_downloads_pinned_files_and_writes_manifest` using deterministic JSON byte payloads and a fixed UTC timestamp. Assert the fetch URLs contain the full pinned commit and the exact four names; the returned directory contains those bytes; and `manifest.json` contains schema version 1, repository, commit, timestamp ending in `Z`, GPL-3.0 metadata, URL, size, and the exact SHA-256 for every file.

- [ ] **Step 2: Run the test and verify RED**

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_downloads_pinned_files_and_writes_manifest -v`

Expected: ERROR because `mhwilds_optimizer.data_download` does not exist.

- [ ] **Step 3: Implement the minimal pinned downloader**

In `mhwilds_optimizer/data_download.py`, define the constants and the `FetchBytes`/`Now` callable aliases. Implement `fetch_url(url: str) -> bytes` with `urllib.request.urlopen` and a finite timeout, `utc_now() -> datetime`, and `download_mhdb_data(...) -> Path`. Fetch into a temporary sibling directory, parse each payload with `json.loads`, require a top-level JSON list, calculate SHA-256 from the exact stored bytes, write a UTF-8 indented manifest with sorted keys, then rename the staging directory to the final commit directory only after all writes succeed.

- [ ] **Step 4: Run the focused test and full suite to verify GREEN**

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_downloads_pinned_files_and_writes_manifest -v`

Expected: PASS.

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 1 test passes with no errors or failures.

- [ ] **Step 5: Commit Task 1**

```bash
git add mhwilds_optimizer tests
git commit -m "feat: add pinned MHDB data downloader"
```

### Task 2: Failure atomicity and existing-download verification

**Files:**
- Modify: `mhwilds_optimizer/data_download.py`
- Modify: `tests/test_data_download.py`

**Interfaces:**
- Consumes: Task 1's final directory and manifest format.
- Produces: `verify_mhdb_download(download_dir: Path) -> None`, raising `DownloadVerificationError` for missing, malformed, unexpected, or hash-mismatched content.
- Changes: `download_mhdb_data(...)` verifies and reuses a complete existing target without fetching; errors always remove only the temporary staging directory and preserve any prior complete target.

- [ ] **Step 1: Write and run the failure-atomicity RED tests**

Add `test_invalid_json_leaves_no_final_directory`, with one payload truncated, and `test_fetch_failure_after_first_file_leaves_no_partial_download`, whose fetch raises `OSError` on its second call. In both cases assert the original exception is raised and neither `<raw>/mhdb/<commit>` nor a staging directory remains.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_invalid_json_leaves_no_final_directory tests.test_data_download.DownloadDataTests.test_fetch_failure_after_first_file_leaves_no_partial_download -v`

Expected: at least one test FAILS because Task 1 does not yet guarantee complete staging cleanup.

- [ ] **Step 2: Implement cleanup and verify GREEN**

Use `tempfile.TemporaryDirectory` under `<raw>/mhdb` so every exception removes staging automatically; keep the final rename as the last operation.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_invalid_json_leaves_no_final_directory tests.test_data_download.DownloadDataTests.test_fetch_failure_after_first_file_leaves_no_partial_download -v`

Expected: both tests PASS.

- [ ] **Step 3: Write and run existing-download verification RED tests**

Add `test_reuses_verified_download_without_fetching` and `test_rejects_tampered_existing_file`. The first performs a second call with a fetch function that raises if invoked; the second changes one downloaded byte and expects `DownloadVerificationError` naming the file.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_reuses_verified_download_without_fetching tests.test_data_download.DownloadDataTests.test_rejects_tampered_existing_file -v`

Expected: FAIL because existing targets are not verified and reused.

- [ ] **Step 4: Implement verification and verify GREEN**

Implement `DownloadVerificationError` and `verify_mhdb_download(...)`. Require exactly the declared four JSON files plus `manifest.json`, validate manifest source identity and file entries, recompute byte sizes and hashes, and parse each JSON file as a top-level list. Call it before returning an existing target and after finalizing a new target.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests -v`

Expected: 5 tests pass.

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 5 tests pass with no errors or failures.

- [ ] **Step 5: Commit Task 2**

```bash
git add mhwilds_optimizer/data_download.py tests/test_data_download.py
git commit -m "feat: verify MHDB download integrity"
```

### Task 3: CLI, ignore rules, documentation, and live download

**Files:**
- Modify: `mhwilds_optimizer/data_download.py`
- Create: `.gitignore` if absent; otherwise modify it without removing existing entries.
- Modify: `README.md` while preserving any existing project content.
- Modify: `tests/test_data_download.py`
- Local-only output: `data/raw/mhdb/c50a1eb892f4a1ad9bb35c147801658804be2cc2/`

**Interfaces:**
- Consumes: Task 2's `download_mhdb_data` and verification behavior.
- Produces: `main(argv: Sequence[str] | None = None) -> int` and the command `uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_download --source mhdb --output data/raw`.

- [ ] **Step 1: Write and run the CLI RED test**

Add `test_cli_help_documents_source_and_output`, calling `main(["--help"])` while capturing stdout. Assert exit code 0 through `SystemExit`, and help text containing `--source`, `mhdb`, `--output`, and `data/raw`.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_cli_help_documents_source_and_output -v`

Expected: ERROR because `main` is absent.

- [ ] **Step 2: Implement the CLI and verify GREEN**

Use `argparse`; accept only `--source mhdb`; default `--output` to `data/raw`; print the completed directory and return 0. Add the `if __name__ == "__main__"` entry point.

Run: `uv run --no-project --python 3.12 python -m unittest tests.test_data_download.DownloadDataTests.test_cli_help_documents_source_and_output -v`

Expected: PASS.

- [ ] **Step 3: Add ignore and provenance documentation**

Add `data/raw/` to `.gitignore`. Document the exact command, generated location, pinned commit, local manifest, GPL-3.0 source license, and the reason raw game-derived JSON is not committed in `README.md`.

- [ ] **Step 4: Run the complete offline suite**

Run: `uv run --no-project --python 3.12 python -m unittest discover -s tests -v`

Expected: 6 tests pass with no errors or failures.

- [ ] **Step 5: Perform and inspect the live download**

Run: `uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_download --source mhdb --output data/raw`

Expected: prints `data/raw/mhdb/c50a1eb892f4a1ad9bb35c147801658804be2cc2` and exits 0.

Run a read-only Python inspection that parses all four files and reports list counts.

Expected at the pinned commit: `Armor.json=194`, `Accessory.json=361`, `Amulet.json=64`, `Skill.json=179`.

Run: `git status --short`

Expected: no paths beneath `data/raw/` appear.

- [ ] **Step 6: Commit Task 3**

```bash
git add .gitignore README.md mhwilds_optimizer/data_download.py tests/test_data_download.py
git commit -m "feat: expose MHDB download CLI"
```
