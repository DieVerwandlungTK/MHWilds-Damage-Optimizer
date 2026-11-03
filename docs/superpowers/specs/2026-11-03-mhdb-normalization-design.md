# MHDB データ正規化・検証設計

## 目的

固定コミットから取得した MHDB Wilds Data の4種のraw JSONを、最適化処理が安定したIDと共通構造で参照できるローカルデータへ変換する。同時に、上流更新によるスキーマ変化、参照欠損、重複、不正なスロットやスキルレベルを検出する。

## 対象範囲

- 入力: `Armor.json`、`Accessory.json`、`Amulet.json`、`Skill.json` とraw manifest。
- 出力: `skills.json`、`armor.json`、`decorations.json`、`regular_charms.json`、`manifest.json`、`validation_report.json`。
- 出力先は `data/normalized/` とし、rawデータと同様にGit管理外とする。
- 変換コード、スキーマ仕様、テスト、利用方法だけをGit管理する。
- 鑑定護石の抽選ルール、スキル効果の数値化、ダメージ計算、最適化モデルは対象外とする。

## 実データから確認した制約

- 防具セットは194件、実防具は714部位であり、全セットが5部位を持つとは限らない。部位不足をエラーにしない。
- 防具部位には独立した `game_id` がないため、`armor:<set_game_id>:<kind>` を安定IDにする。同一セット内の部位重複はエラーにする。
- 装飾品は `allowed_on` により `weapon` と `armor` を分離し、`level` を要求スロットレベルとして保持する。
- 通常護石は親 `game_id` とランクの `level` を使い、`regular_charm:<game_id>:<level>` に平坦化する。
- `is_random=true` の護石4件は鑑定護石の抽選仕様を表しておらず、通常護石出力から除外して件数をレポートする。
- `Charm.json` は外見用チャームなので入力対象にしない。
- スキル参照は表示名でなく `skill:<game_id>` に正規化する。

## 正規化モデル

- `Skill`: `id`, `source_id`, `names`（`ja` / `en`）, `kind`, `max_level`, `ranks`。説明文は保持せず、ランク番号と `set_pieces_required` が存在する場合だけ保持する。
- `Armor`: `id`, `source_set_id`, `set_names`, `names`, `part`, `rarity`, `slots`, `skills`, `set_bonus`, `group_bonus`。防御力・耐性・素材は火力最適化のMVPに不要なので除外する。
- `Decoration`: `id`, `source_id`, `names`, `slot_type`, `required_slot_level`, `rarity`, `skills`。
- `RegularCharm`: `id`, `source_id`, `rank`, `names`, `rarity`, `skills`, `slots`。現rawデータにはスロットがないため空配列にするが、存在しない情報を推測で補わない。

名称はローカル出力に日本語と英語だけを含め、説明文やその他の翻訳は複製しない。IDとリスト順は決定的に生成し、同じ入力から同じ内容を得られるようにする。

## 変換・検証フロー

1. raw downloaderの検証関数で入力manifest、ファイル集合、SHA-256、JSON形状を検証する。
2. 各rawレコードの必須フィールドと型を確認して正規化する。未知フィールドは許容するが、必要フィールドの欠損はエラーにする。
3. 正規化IDの一意性、部位・スロット種別・スロットレベル、正のスキルレベル、スキルID参照、日英名称を検証する。
4. 一時ディレクトリへ全出力を書き、全検証成功後に `data/normalized/mhdb/<commit>/` として確定する。失敗時は完成ディレクトリを作らない。
5. manifestに入力コミット、raw manifestのSHA-256、正規化スキーマバージョン、各出力の件数・サイズ・SHA-256を記録する。
6. validation reportに件数、警告、除外したランダム護石件数を記録する。警告とエラーを区別し、エラー時は非ゼロ終了する。

## CLI

```bash
uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_normalization \
  --input data/raw \
  --output data/normalized
```

変換後に同じコマンドを実行した場合は、既存の正規化manifestと全出力のハッシュを検証する。入力raw manifestのハッシュが異なる場合は、暗黙に再利用せずエラーを報告する。

## 成功条件

- 固定rawデータから `skills=179`、`armor=714`、`decorations=361`、`regular_charms=183` を生成する。
- 2,837件ある現行rawのスキル参照に欠損がないことを検証できる。
- 武器用／防具用装飾品、通常／ランダム護石を混同しない。
- 変換失敗時に部分的な完成出力を残さない。
- `data/normalized/` が `git status` に現れない。

