# mhwilds-sim

Monster Hunter Wilds のコンボ期待ダメージを最大化する装備構成を探索する、Python CLI プロジェクトです。現在はデータ取得基盤を実装しています。

## MHDBデータの取得

Python 3.12環境で、リポジトリのルートから次を実行します。

```bash
uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_download \
  --source mhdb \
  --output data/raw
```

取得対象は [MHDB Wilds Data](https://github.com/LartTyler/mhdb-wilds-data) のコミット `c50a1eb892f4a1ad9bb35c147801658804be2cc2` に固定しています。次のファイルが `data/raw/mhdb/<commit>/` に保存されます。

- `Armor.json`
- `Accessory.json`
- `Amulet.json`
- `Skill.json`
- `manifest.json`（出典URL、コミット、取得日時、サイズ、SHA-256、ライセンス）

同じコマンドを再実行すると、既存ファイルのサイズ・SHA-256・JSON構造を検証します。検証済みならネットワークから再取得しません。

## データのライセンスとGit管理

MHDB Wilds Data のライセンスは [GPL-3.0](https://github.com/LartTyler/mhdb-wilds-data/blob/c50a1eb892f4a1ad9bb35c147801658804be2cc2/LICENSE) です。また、取得されるJSONにはゲーム由来の名称や説明文など、別の権利が存在し得る内容が含まれます。

このリポジトリからraw JSONを再配布しないため、`data/raw/` はGit管理外です。ダウンロードしたデータとローカルmanifestをコミットしないでください。

## データの正規化

rawデータ取得後、次のコマンドで最適化処理向けのデータを生成します。

```bash
uv run --no-project --python 3.12 python -m mhwilds_optimizer.data_normalization \
  --input data/raw \
  --output data/normalized
```

出力先は `data/normalized/mhdb/<commit>/` です。固定コミットでは、スキル179件、防具714件、装飾品361件、通常護石183件を生成し、ランダム護石の親レコード4件を通常護石から除外してレポートします。

再実行時はraw manifestと全正規化ファイルのSHA-256を検証し、正常な既存データを再利用します。正規化データにも日英名称が含まれるため、`data/normalized/` もGit管理外です。フィールド仕様は [`docs/data-schema.md`](docs/data-schema.md) を参照してください。

## 双剣・乱舞 I〜III のダメージ計算

乱舞 I、II、III の計27ヒットを、装備探索から独立した純Python APIで連続近似できます。入力する攻撃力・属性値・会心率は、スキルやバフを解決した後の実効値です。

```python
from decimal import Decimal

from mhwilds_optimizer.combo_data import load_combo
from mhwilds_optimizer.damage import calculate_combo_damage
from mhwilds_optimizer.damage_models import CombatStats, Sharpness, TargetHitzones

combo = load_combo()
stats = CombatStats(
    raw=Decimal("100"),
    element=Decimal("20"),
    affinity_percent=Decimal("25"),
    positive_critical_modifier=Decimal("1.25"),
    negative_critical_modifier=Decimal("0.75"),
    sharpness=Sharpness.WHITE,
    demon_dodge_buff=True,
)
target = TargetHitzones(
    sever=Decimal("60"),
    element=Decimal("20"),
    monster_damage_modifier=Decimal("1"),
)

result = calculate_combo_damage(combo, stats, target)
print(result.total, result.physical, result.elemental)
print(result.verification_status, result.warnings)
```

乱舞の数値は Ver.1.020.00 の2資料を照合し、公式更新情報を Ver.1.042.00.03 まで確認しています。ただしゲーム内実測による回帰データがまだないため、コンボデータと計算ルールの検証状態は `cross_checked` です。現時点では丸めなしの `continuous_approx` のみ利用でき、`game_exact` はデータとルールの両方が `verified` に昇格するまで `UnverifiedDamageError` で停止します。

出典と保証範囲の詳細は [`双剣乱舞ダメージ基盤 設計`](docs/superpowers/specs/2026-11-03-dual-blades-damage-foundation-design.md) を参照してください。
