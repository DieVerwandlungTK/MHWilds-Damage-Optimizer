# 双剣乱舞ダメージ基盤 設計

更新: 2026-11-03

## 意図

Phase 2 の最初の単位として、双剣の「乱舞 I → 乱舞 II → 乱舞 III」27ヒットを出典付きで保持し、装備探索から独立した純Pythonのダメージ計算器で評価できるようにする。ゲーム定数を推測で補わず、データの対象バージョンと検証状態を計算結果まで伝播させる。

## ゴール

- 乱舞 I（12ヒット）、乱舞 II（4ヒット）、乱舞 III（11ヒット）を個別ヒット列として定義する。
- 各ヒットにモーション値、属性補正、斬撃種別、所属モーション、出典を持たせる。
- 基礎攻撃力、属性値、会心率、斬れ味、肉質、鬼人身躱し、モンスター側補正から、物理・属性・合計の内訳を計算する。
- `continuous_approx` と `game_exact` を別経路にし、丸めの有無と保証範囲を結果に表示する。
- 未検証または対象ゲームバージョン不明の定数を使う場合、`game_exact` を拒否する。
- 人工データの単体テストと、公開されている実測例に基づく回帰テストを用意する。

## 非ゴール

- 防具スキルごとの効果解釈と発動条件。
- 攻撃・属性バフの重複グループや適用順序の網羅。
- コンボ中の斬れ味ゲージ減少と色変化。
- 状態異常蓄積、傷破壊、部位破壊、弾かれ。
- Python-MIP、装備候補、CLIとの接続。
- 鬼人連斬 I・II を挟む35ヒット派生。

これらは計算基盤の後続単位で扱う。今回の入力は、スキル等を解決した後の実効攻撃値・実効属性値・実効会心率を受け取る。

## 調査結果と対象バージョン

2026-11-03 時点の最新ベースゲームは Ver.1.042.00.03。公式更新情報ではこの更新は安定性修正で、双剣のバランス変更は記載されていない。確認できた乱舞の数値変更は Ver.1.020.00 である。

ヒット列は次の2資料が一致することを確認した。

- Kuroyonhon「双剣」: モーションごとのモーション値、属性補正、斬れ味消費量を掲載。
  - https://kuroyonhon.com/mhwilds/memo/6.php
- まかろんのゲームメモ「双剣のモーション値」: Ver.1.020.00 の変更前後を掲載。
  - https://macarongamemo.com/entry/mhwilds-dual_blades-motion

計算式と斬れ味補正は次を採用する。

- まかろんのゲームメモ「ダメージ計算式について」
  - https://macarongamemo.com/entry/mhwilds-damage_calculation
- Kuroyonhon「検証したもの」
  - https://kuroyonhon.com/mhwilds/memo/21.php

公式の最新バージョン確認:

- Monster Hunter Wilds Steam公式ニュース Ver.1.042.00.03
  - https://steamcommunity.com/app/2246340/allnews/

コミュニティ資料のため、出典間一致だけで `verified` にはしない。データは `cross_checked` とし、ゲーム内実測テストを通した定数のみ `verified` へ昇格できる設計にする。最新公式パッチに数値変更の記載がないことは「値が不変」の完全な証明ではないため、その判断もメタデータに残す。

## 検討した方式

### 1. 計算器を人工データで先に作る

構造を早く確定できるが、実データとの不整合を後から直す可能性が高い。

### 2. 出典付きヒットデータを先に固定し、計算器を接続する（採用）

ユーザーが選択した方式。ヒット境界、対象バージョン、検証状態を最初から型とテストに反映でき、仕様の推測を避けられる。

### 3. Phase 2 全体を一括実装する

スキル効果、状態、丸め、データ収集を同時に扱うため、誤差の原因を切り分けにくい。

## データ設計

リポジトリ管理可能な、数値と出典メタデータだけのJSONを `mhwilds_optimizer/data/combos/dual_blades.json` に置く。ゲーム内説明文や画像は含めない。

トップレベル:

- `schema_version`
- `game_version`: 数値が適用されると確認できた最低バージョン
- `checked_through_version`: 変更記載を確認した最新バージョン
- `verification_status`: `unverified | cross_checked | verified`
- `sources`: URL、資料名、確認日、資料が支える項目
- `combos`

コンボ:

- `id`: `dual_blades:demon_dance_1_3`
- `weapon_type`: `dual_blades`
- `moves`: 乱舞 I、II、III
- `hits`: 27件の平坦な配列

ヒット:

- `index`: コンボ内1始まり連番
- `move_id`: 所属モーション
- `move_hit_index`: モーション内1始まり連番
- `motion_value`
- `element_modifier`
- `damage_type`: `sever`

未記載の属性補正は資料上の標準値1.0として解釈せず、生成時に明示的な1.0へ展開し、その根拠をテストで固定する。

## Pythonモデル

`mhwilds_optimizer/damage_models.py` に不変のdataclassを置く。

- `Hit`
- `Combo`
- `CombatStats`: 実効基礎攻撃力、実効属性値、会心率、会心補正、鬼人身躱し状態
- `TargetHitzones`: 斬・属性肉質、モンスター側ダメージ補正
- `DamageRules`: 斬れ味倍率、鬼人身躱し物理/属性倍率、検証情報
- `HitDamage` / `ComboDamage`: 物理、属性、合計、使用モード、警告、検証状態

入力値は百分率と倍率を混同しない命名にし、会心率と肉質は0〜100、倍率は正の数として境界で検証する。計算は二進浮動小数点による境界誤差を避けるため `Decimal` を使う。

## 計算

物理の連続近似:

```text
effective_raw
  × demon_dodge_raw_modifier
  × motion_value / 100
  × raw_sharpness_modifier
  × physical_hitzone / 100
  × monster_damage_modifier
  × expected_critical_modifier
```

属性の連続近似:

```text
effective_element
  × demon_dodge_element_modifier
  × element_modifier
  × element_sharpness_modifier
  × elemental_hitzone / 100
  × monster_damage_modifier
```

期待会心補正は正会心と負会心を分け、会心率を `[-100, 100]` に制限する。通常会心は物理だけへ適用し、会心撃【属性】は今回扱わない。

`continuous_approx` は各項を丸めずに合計する。`game_exact` は物理と属性を別々に小数第1位へ丸めてから合計する。ただし、期待会心とゲーム内の各ヒット抽選を混ぜた値を「実際の単発表示値」とは呼ばない。`game_exact` は検証済みルールだけで構成される場合に限り実行し、そうでなければ例外で停止する。

## 検証状態と失敗方針

- 状態の強さは `unverified < cross_checked < verified`。
- 結果の状態は、使用した全データ・ルールの最小状態。
- `continuous_approx` は `cross_checked` を許可するが警告を返す。
- `game_exact` は全要素が `verified` の場合だけ許可する。
- 鬼人身躱しの現行値（物理1.15、属性1.3）は公開シミュレーターと更新履歴で一致しているが、ゲーム内回帰値をまだ持たないため最初は `cross_checked` とする。
- 怒りはスキル発動条件と混ぜず、ターゲット側の明示倍率だけを受け取る。

## テスト

- JSONの27ヒット、モーション別件数12/4/11、モーション値・属性補正の配列を完全一致で検証。
- 不正な会心率、肉質、倍率、未知の斬れ味色を拒否。
- 物理のみ、属性のみ、正会心、負会心、鬼人身躱しON/OFF、モンスター倍率を独立に検証。
- ヒット合計がコンボ合計と一致し、物理・属性内訳が失われないことを検証。
- `cross_checked` のまま `game_exact` を要求すると停止することを検証。
- 出典の実測例を、前提を再現できる範囲で回帰テスト化する。前提不明の公開値は期待値へ採用しない。

## 後続への接続

次の作業単位で、スキル効果とバフ適用順序を解決して `CombatStats` を生成する層を追加する。その後、設定ローダーとCLI、Python-MIP候補の再評価器へ同じ純粋計算関数を接続する。コンボデータと計算ロジックを分離するため、別武器・別コンボはJSON追加で拡張できる。
