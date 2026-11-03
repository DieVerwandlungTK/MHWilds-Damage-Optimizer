# Monster Hunter Wilds 火力最適化スクリプト — Codex 向け実装仕様

更新: 2026-11-03

## 0. 目的と開発方針

個人利用の **Python CLI スクリプト**を開発する。指定したコンボの**期待総ダメージ**を最大化する、防具・装飾品・護石・巨戟アーティアの組み合わせを探索する。さらに、理論上最適な**鑑定護石**と代替候補を出力する。

- 最適化ライブラリ: **Python-MIP**（初期ソルバー CBC）。UI / Web サーバーは不要。
- 最初の対象武器: **双剣**。対象コンボ: **乱舞 I → II → III**。後で他武器・コンボへ拡張可能にする。
- コンボの総ダメージを評価する。ヒットごとにモーション値・属性補正・ダメージ種別・ヒット部位を保持する。
- 最適化の入力: 装備候補、必須スキル、戦闘状態、肉質、バフ、巨戟アーティアの合法構成、鑑定護石の合法構成。
- 「火力上位 N 件」だけでなく、ビルド内容、理想護石、巨戟アーティアの内訳、発動スキルとダメージ内訳を表示する。
- **正確なゲーム仕様を想像で埋めない。** 出典不明・バージョン未確認のゲーム定数は `unverified` として管理し、その値が欠けている場合は厳密計算モードを停止する。
- 最終アップデート分の防具が MHDB Wilds Data に揃っているというユーザー確認を前提に、まず防具データの変換を実装する。ただし収録範囲は取得時にプログラム側でも点検する。

## 1. 対象範囲

### 必須（MVP）

1. **装備**: 頭・胴・腕・腰・脚、防具の装飾品スロット、装飾品、護石。
2. **巨戟アーティア**: 武器種・属性・パーツ/激化・復元ボーナス・武器に付与できるシリーズ/グループスキルの合法候補。実装前に各ルールと制限を確認する。
3. **鑑定護石**: ゲーム内で実現可能なスキル、レベル、スロット組み合わせを候補化。理論上の最適護石を探索。必要なら所持護石のみの探索にも対応。
4. **必須スキル**: `minimum` / `exact` / `forbidden`。武器スキルと防具スキル、上限と発動条件を適切に扱う。
5. **コンボ**: 乱舞 I～III の各ヒットを個別に定義。
6. **戦闘状態**: 鬼人化、鬼人身躱し強化 ON/OFF、モンスター怒り、怒り時のモンスター補正、傷の状態、スキル発動状態、各種バフ。
7. **肉質**: 斬・打・弾、火・水・雷・氷・龍。モンスター/部位/状態別に定義でき、ユーザーによる数値の直接指定も可能。MVP は全ヒット同一部位でよい。
8. **出力**: 最大火力 Top N、構成の内訳、実現可能性、探索時間、ソルバー状態、最適性ギャップ、各候補の正確な再評価値。

### 後続機能

- 各ヒットが別部位に当たる指定、コンボ中の斬れ味変化。
- 状態の出現確率（鬼人身躱し維持率、怒り時間割合）で重み付けした期待火力。
- 所持装備制限、鑑定護石の妥協候補、所持護石を固定して他装備を再最適化する比較。
- 別武器/別コンボ、複数目標、DPS、快適性との多目的最適化。

## 2. 入力設定（YAML 例）

**以下の数値・スキル名は設定形式の例であり、ゲーム内の確定値を意味しない。** 実際のスキルIDには正規化済みデータのIDを使用する。

```yaml
weapon_type: dual_blades
combo: demon_dance_1_3
mode: theoretical  # theoretical | owned

required_skills:
  critical_boost: {minimum: 3}
  weakness_exploit: {minimum: 3}
  # example_skill: {exact: 2}
forbidden_skills: []

target:
  monster_id: null  # null の場合、以下の手入力を使用
  part: head
  hitzones:
    sever: 60
    blunt: 55
    shot: 45
    fire: 0
    water: 20
    thunder: 25
    ice: 15
    dragon: 10
  wounded: false
  enraged: true
  enrage_damage_multiplier: 1.0  # 手入力の仮値。怒り時の肉質変更と二重適用しない

combat:
  demon_mode: true
  demon_dodge_buff: true
  sharpness_initial: white
  skill_conditions:
    agitator: auto  # auto | true | false。スキルごとに条件解釈を定義
    burst: true
  buffs:
    powercharm: true
    demondrug: false
    might_seed: false

artian:
  enabled: true
  optimize: true
  allow_only_legal_rolls: true
  optimize_weapon_skills: true

charm:
  optimize_appraised: true
  allow_regular_charms: true

objective:
  type: expected_combo_damage
  rounding: game_exact  # game_exact | continuous_approx

search:
  top_k: 20
  time_limit_seconds: 300
  mip_gap: 0.001
  require_proven_optimal: false
```

### 設定仕様上の注意

- `enraged` はスキルの発動判定とモンスター側ダメージ補正の双方に関係するが、両者を混同しない。
- `demon_dodge_buff` は物理/属性等への効果を**別々**の定数で表現。単一の一律倍率にしない。
- `weakness_exploit` など肉質で効果が変わるスキルは、評価対象ヒットの肉質から自動判定する。`skill_conditions` で必要な場合のみ明示上書きできる設計にする。
- 「必要スキルを持つ」と「戦闘中にスキル効果が発動する」は別条件。
- 手入力肉質とモンスターデータを同時に指定した場合の優先順位を明示する（推奨: 手入力を優先し、ログに表示）。
- 特定の武器に存在しないスキルや装飾品タイプの不一致を必ず検出する。

## 3. データ取得元と取り込み

| データ | 第一候補 | 注意点 |
|---|---|---|
| 防具・スロット・付与スキル | [MHDB Wilds Data](https://github.com/LartTyler/mhdb-wilds-data) | 第一採用候補。実JSON構造を調査し正規化する |
| 武器・装飾品・通常護石・スキル定義 | 同リポジトリ / [MHDB API](https://docs.wilds.mhdb.io/) | 網羅性、更新日、ID整合性を検証する |
| 鑑定護石の抽選可能範囲 | [Monster Hunter Wiki](https://monsterhunterwiki.org/wiki/Module:MHWilds) | `RngTalismans` / `TalismanSkillGroups` 相当を調査。組合せ制約も要検証 |
| 肉質・怒り状態関連 | MHDB / Monster Hunter Wiki / [Kiranico](https://mhwilds.kiranico.com/) | 状態ごとの肉質や怒り倍率は同一のソース・バージョンで照合 |
| 双剣のモーション値・属性補正 | [まかろんのゲームメモ](https://macarongamemo.com/entry/mhwilds-dual_blades-motion) | 乱舞 I～III の全ヒット・現行パッチとの整合性を要確認 |
| ダメージ計算・鬼人身躱し補正 | [黒曜のゲームメモ](https://kuroyonhon.com/mhwilds/d/dame.php) | ゲーム内実測と突き合わせる。ゲーム内処理順序/端数処理が重要 |
| 巨戟アーティアのルール | [GameWith](https://gamewith.jp/mhwilds/534657) 等の解説と抽出データ | 合法な組合せとボーナス効果を別データに保持 |

上記は**候補ソース**であり、全データの存在・完全性・最新版対応を保証するものではない。Codex は実際の URL / ファイル構造を調査し、不明項目の一覧を残すこと。サイトの利用条件、robots.txt、ライセンスを確認し、負荷を抑えた取得または手動入力を選択する。

### データ保管

```text
data/
  raw/                  # ダウンロードした原データ、ソースごと
  normalized/
    armor.json
    decorations.json
    skills.json
    regular_charms.json
    appraised_charms.json
    artian.json
    monsters.json
    combos.json
  overrides/
    corrections.yaml    # 未収録・ゲーム更新分の補正、出典付き
  manifest.json         # 出典URL、取得日、ゲームバージョン、検証状態
```

各データ項目に `source`, `game_version`, `verified`（または同等のメタ情報）を持たせ、欠損や矛盾を警告する。英日名称の差異を吸収するため、表示名ではなく安定したIDで参照する。

## 4. 正規化データの概念モデル

- `Armor`: `id`, `part`, `skills`, `slots`（**武器用/防具用の種別とレベル**）, `set_bonus_tags`, `group_tags`。
- `Decoration`: `id`, `skill_levels`, `slot_type`, `required_slot_level`, `max_count`。
- `Charm`: `id`, `kind` (`regular` / `appraised`), `skill_levels`, `slots`, `legal_roll_metadata`。
- `ArtianWeapon`: `weapon_type`, `element`, `base_stats`, `parts`, `reinforcements`, `gogmazios_skills`, `slots`。合法構成生成は個別関数にする。
- `Skill`: `id`, `max_level`, `effects_by_level`, `activation_rule`, `skill_category`。
- `MonsterPartState`: `monster_id`, `part`, `state`, `hitzones`, `monster_damage_multiplier`。
- `Combo`: `weapon_type`, `id`, `hits`。`Hit`: `motion_value`, `element_modifier`, `damage_type`, `part_override`, `special_modifiers`。

武器スロットと防具スロットを混在させない。装飾品の装着可能レベルと装備レベルを不等式で判定。シリーズ/グループスキルの**部位数・付与スキル・発動条件**は、実ゲーム仕様に合わせて定義し、勝手な加算処理をしない。

## 5. ダメージ計算エンジン

### 評価の単位

指定したコンボの各ヒット `i` の期待値を計算し、合計する。

\[
D(B,C,S,H)=\sum_{i\in C}\bigl(D_{i,\mathrm{raw}}(B,S,H_i)+D_{i,\mathrm{elem}}(B,S,H_i)\bigr)
\]

- `B`: 完成ビルド（武器、防具、装飾品、護石、スキル）。
- `C`: コンボの各ヒット列（乱舞 I～III）。
- `S`: 鬼人化、鬼人身躱し、怒り、傷、バフ、スキル発動条件。
- `H_i`: 物理/属性肉質（初期版は全ヒット同一部位）。

物理側は基礎攻撃力、攻撃スキル、モーション値、物理肉質、斬れ味、会心期待値、各種補正に依存する。属性側は属性値、属性補正、属性肉質、属性斬れ味補正、属性会心などに依存する。**倍率がどの段階に掛かるか・丸め順序・武器固有のヒット補正**を検証済みの式に沿って実装する。

### 実装上の必須ルール

1. `calculate_hit_damage(build, hit, combat_state, target)`: 各ヒットの内訳を返す。
2. `calculate_combo_damage(...)`: 全ヒット合計、物理・属性別合計、各ヒット内訳を返す。
3. 鬼人身躱しは ON/OFF と物理/属性の別係数で表現する（数値は検証後に登録）。
4. 怒り時の**モンスター側補正**、肉質変化、挑戦者の発動は独立に扱い、二重適用しない。
5. 会心率の上限・下限、負会心、会心撃【属性】等を必要に応じて考慮。
6. 計算はまず `continuous_approx` を完成させ、ゲーム内の丸め処理を再現する `game_exact` を実装する。
7. スキル効果、実際のヒット列、ゲーム内ダメージ値との対照テストを行う。未知仕様を適当な定数で代用しない。

## 6. Python-MIP での最適化

### 変数（例）

- `x_a ∈ {0,1}`: 防具 `a` の選択（各部位ちょうど1件）。
- `y_{d,s} ∈ Z_{>=0}`: スロットクラス `s` に装飾品 `d` を配置する個数。スロットごとの割当て方式でもよい。
- `z_t ∈ {0,1}`: 通常/鑑定護石候補 `t` の選択（合計1件）。
- `u_w ∈ {0,1}`: 合法な巨戟アーティア候補 `w` の選択（合計1件）、またはパーツ・ボーナス・付与スキルを直接変数化。
- `l_{s,k} ∈ {0,1}`: スキル `s` が一定レベル以上あることを示す補助変数（必要時）。

### 制約

- 防具の部位ごとに1つ、護石1つ、武器1つ。
- 武器用/防具用装飾品のスロット数とサイズの制約。
- 防具・護石・装飾品・武器付与スキルによるスキルレベルの合算と上限。
- 必須スキルの下限（`minimum`）、一致（`exact`）、禁止（`forbidden`）。
- シリーズ・グループスキルの必要部位数、武器由来の有効カウント。
- 巨戟アーティアの合法な激化/復元/付与スキル、鑑定護石の合法抽選条件。

### 非線形な火力をどう最適化するか

**注意: Python-MIP は基本的に線形目的関数を扱う。** `A * affinity` や `A * affinity * crit_multiplier`、属性会心、丸めを含む各ヒットの正確なダメージを、そのまま目的関数に書くことはできない。

実装を次のように段階化する。

1. **厳密な実現可能性モデル**をまず実装。装備/装飾品/護石/巨戟アーティアの合法性・必須スキルを Python-MIP で判定できるようにする。
2. **独立した純Pythonのコンボ火力評価器**を先に作り、単体テストを確保。
3. MVP では、線形の火力代理指標（攻撃・属性・会心等）で有望候補を探索し、`damage.py` で再評価。**このモードは最適性保証なし**と明記する。攻撃力上位 `N` 件だけで決めない（属性や会心に優れた候補を落とすため）。複数の代理目的・スキルプロファイルを走らせて候補を集める。
4. **厳密最適化が必要になったら**、取り得る攻撃力/会心/倍率等を離散状態化し、補助0-1変数・積の線形化・必要に応じて区分化して真の目的関数をMILP化する。または、コンボダメージの**妥当な上界**を使った分枝限定・完全列挙を実装する。証明済みの場合のみ `optimal` を表示。
5. 丸め込みの `game_exact` がMILPの目的関数と一致しない場合、MILP上の最適解は **厳密ゲームダメージの最適解ではない**。結果に保証の範囲を明示する。

理想護石比較では、特定護石を固定したうえで防具・装飾品・巨戟アーティアを**再最適化**する（固定ビルドの護石だけ差し替えない）。実現不可能な鑑定護石候補を生成してはいけない。

### 実行結果ステータス

- `optimal`: 評価対象の目的関数について最適性を証明。
- `feasible`: 時間制限内の実現可能解、ギャップを表示。
- `heuristic`: 再評価候補の最高値であり、真の火力最適性は未証明。
- `infeasible`: 必須スキル等の制約を満たす装備が存在しない。

## 7. CLI と出力形式

```bash
python main.py --config configs/dual_blades.yaml
python main.py --config configs/dual_blades.yaml --top-k 20
python scripts/download_data.py --source mhdb
python scripts/validate_data.py
```

標準出力 + `results/` に JSON/CSV で保存する。

1. 指定コンボ・肉質・怒り・鬼人身躱し・バフ等の前提条件。
2. 順位、期待コンボ総ダメージ、物理/属性内訳、最適化ステータス。
3. 防具5部位、各装飾品の配置、護石の全スキル/レベル/スロット、巨戟アーティアの全構成。
4. 有効スキル一覧、要求スキルの充足状況、シリーズ/グループスキル。
5. 第1候補比の火力割合、理想護石と妥協護石の差分。
6. 実行環境、データバージョン、未検証データの警告、ソルバーギャップ。

## 8. ディレクトリ構成案

```text
mhwilds_optimizer/
  README.md
  pyproject.toml
  main.py
  configs/
    dual_blades.yaml
  data/
    raw/
    normalized/
    overrides/
    manifest.json
  scripts/
    download_data.py
    normalize_data.py
    validate_data.py
  src/mhwilds_optimizer/
    models.py
    data_loader.py
    skill_effects.py
    artian_rules.py
    charm_rules.py
    damage.py
    constraints.py
    optimizer.py
    reporting.py
  tests/
    test_data_validation.py
    test_skill_constraints.py
    test_slots.py
    test_artian_legality.py
    test_charm_legality.py
    test_damage.py
    test_optimizer_toy.py
```

## 9. 作業順序（Codex への依頼）

### Phase 1 — データ調査・取得

- `mhdb-wilds-data` を調べ、実際のファイル名とJSONスキーマを確認する。
- 防具、装飾品、スキル、通常護石について正規化・検証スクリプトを実装する。
- `manifest.json` にゲームバージョン、取得日時、出典、検証状態を保存。
- 未収録・欠損・重複・不整合をレポートする。**取得元の構造を見ずにフィールド名を仮定しない。**

### Phase 2 — 戦闘状態・ダメージ計算

- 乱舞 I～III の各ヒット情報を出典付きでデータ化する。
- 斬撃/属性肉質、鬼人身躱し、怒り補正、会心、スキル、斬れ味を導入。
- `continuous_approx` / `game_exact` の差を明示し、実測に基づく回帰テストを書く。

### Phase 3 — Python-MIP の制約モデル

- まず小さな人工データで防具・装飾品・護石の選択が正しいかテスト。
- スロットサイズ・種別、必須スキル、部位セット効果のテスト。
- 候補生成とダメージ再評価、Top N出力を構築。

### Phase 4 — 巨戟アーティアと鑑定護石

- 巨戟アーティアの合法構成、抽選護石の合法組合せをデータとして定義。
- 武器/護石/防具/装飾品の同時探索を可能にする。
- 理想護石と代替護石は各々で全装備を再最適化。

### Phase 5 — 精度・探索性能改善

- ゲーム内ダメージ照合、丸め順序の修正、未知の補正の埋め込み。
- 支配的に劣る候補の削除（安全な条件でのみ）。
- 必要ならMILPの非線形項を厳密に線形化し、真の期待コンボダメージに対する最適性保証を目指す。

## 10. 受け入れ条件

- `python main.py --config ...` で再現可能に実行できる。
- 必須スキル・肉質・怒り・鬼人身躱し ON/OFF を変えると適切に再計算される。
- 武器/防具スロット、鑑定護石、巨戟アーティアの**違法構成が候補として出ない**。
- 乱舞 I～III の全ヒットを足し上げ、物理/属性の内訳を表示できる。
- 最適化の「証明済み」と「候補内ベスト/近似」を混同しない。
- データ出典と検証状況が追跡できる。
- 単体テストに加えて、小さな人工データセットでは全探索結果と一致する。

## 11. Codex に最初に与える指示

> この仕様に沿って Python CLI の Monster Hunter Wilds 火力最適化スクリプトを実装してください。最初に MHDB Wilds Data の実際の構造を調査し、防具・装飾品・スキル・通常護石の取得と正規化、出典記録、バリデーションを完成させてください。その後、双剣の乱舞 I～III の各ヒットデータと戦闘状態・肉質を扱う独立したダメージ計算モジュールを作り、Python-MIP の制約モデルへ接続してください。巨戟アーティア・鑑定護石の合法性が確認できない部分は推測で実装せず、未実装の制約と必要ソースを明示してください。近似的な探索結果を厳密最適解と表示しないでください。テストとREADMEを整備し、各Phaseで動く状態を維持してください。

