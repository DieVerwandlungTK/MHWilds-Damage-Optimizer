# 正規化データスキーマ

正規化データは `data/normalized/mhdb/<commit>/` にローカル生成されます。すべての参照は表示名でなく、以下の安定IDを使います。

## 共通規則

- `names`: `ja` と `en` の表示名。説明文とその他の翻訳は含めません。
- スキル参照: `skill:<source_game_id>`。
- `skills`: 正規化スキルIDをキー、付与レベルを値とするオブジェクト。
- スロットレベル: 1から3の整数。
- リストとオブジェクトキーは決定的な順序で出力します。

## skills.json

各要素は次のフィールドを持ちます。

- `id`: `skill:<game_id>`。
- `source_id`: MHDBの `game_id`。
- `names`: 日英名称。
- `kind`: `armor`、`weapon`、`set`、`group` のいずれか。
- `max_level`: 最大ランク番号。
- `ranks`: `level` と、存在する場合のみ `set_pieces_required` を持つ配列。

スキル説明文は効果値として解釈せず、正規化データには含めません。

## armor.json

- `id`: `armor:<source_set_id>:<part>`。MHDBには防具部位個別のIDがないため複合IDです。
- `source_set_id`: 元防具セットの `game_id`。
- `set_names`: 防具セットの日英名称。
- `names`: 防具部位の日英名称。
- `part`: `head`、`chest`、`arms`、`waist`、`legs` のいずれか。
- `rarity`: レア度。
- `slots`: 防具スロットレベルの配列。
- `skills`: 付与スキルとレベル。
- `set_bonus` / `group_bonus`: `null` または `skill_id` と `ranks`。各ランクは必要な `pieces` と発動する `skill_level` を持ちます。

全防具セットが5部位を持つとは限りません。部位不足は補完しません。

## decorations.json

- `id`: `decoration:<game_id>`。
- `source_id`: MHDBの `game_id`。
- `names`: 日英名称。
- `slot_type`: `weapon` または `armor`。
- `required_slot_level`: 必要スロットレベル。
- `rarity`: レア度。
- `skills`: 付与スキルとレベル。

武器用と防具用の装飾品は `slot_type` により区別し、混在させません。

## regular_charms.json

- `id`: `regular_charm:<source_id>:<rank>`。
- `source_id`: 親護石の `game_id`。
- `rank`: 親護石内のランクレベル。
- `names`: ランクごとの日英名称。
- `rarity`: レア度。
- `skills`: 付与スキルとレベル。
- `slots`: 現在のrawデータには通常護石スロットがないため空配列。未知値は推測しません。

`is_random=true` の親レコードは鑑定護石の合法抽選範囲を表さないため、このファイルには含めません。

## validation_report.json

- `counts`: 4種の正規化レコード件数。
- `excluded_random_charm_records`: 通常護石から除外したランダム護石の親レコード件数。
- `warnings`: 非致命的な注意事項。
- `errors`: 正常生成時は空配列。致命的な不整合では完成出力自体を作りません。

## manifest.json

- `schema_version`: 正規化スキーマの版。
- `source`: 出典リポジトリ、固定コミット、raw manifestのSHA-256。
- `generated_at`: UTC生成日時。
- `counts`: 出力件数。
- `files`: manifest自身を除く各出力の名前、バイト数、SHA-256。
