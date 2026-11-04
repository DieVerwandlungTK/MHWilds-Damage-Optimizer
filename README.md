# mhwilds-sim

Monster Hunter Wilds のコンボ期待ダメージを最大化する装備構成を探索する、Python CLI プロジェクトです。現在はデータ取得・ダメージ計算と、装備構成の実現可能性判定まで実装しています。

## Python環境

Python 3.11 と [uv](https://docs.astral.sh/uv/) を使用します。依存関係には、固定コミットのPython-MIPとHiGHSが含まれます。

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

## MHDBデータの取得

Python 3.11環境で、リポジトリのルートから次を実行します。

```bash
uv run python -m mhwilds_optimizer.data_download \
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
uv run python -m mhwilds_optimizer.data_normalization \
  --input data/raw \
  --output data/normalized
```

出力先は `data/normalized/mhdb/<commit>/` です。固定コミットでは、スキル179件、防具714件、装飾品361件、通常護石183件を生成し、ランダム護石の親レコード4件を通常護石から除外してレポートします。

再実行時はraw manifestと全正規化ファイルのSHA-256を検証し、正常な既存データを再利用します。正規化データにも日英名称が含まれるため、`data/normalized/` もGit管理外です。フィールド仕様は [`docs/data-schema.md`](docs/data-schema.md) を参照してください。

## 装備構成の実現可能性判定

正規化済みデータから、防具5部位・通常護石1個・防具用装飾品の合法な構成をHiGHSで探索できます。選択した防具が持つシリーズ／グループのタグ数に応じたスキルレベルも発動し、通常スキルと同じく `minimum`、`exact`、`forbidden` の要求対象にできます。スキルIDは `skills.json` に含まれる実際のIDへ置き換えてください。

```python
from pathlib import Path

from mhwilds_optimizer.constraints import solve_feasible_build
from mhwilds_optimizer.equipment_data import load_equipment_catalog
from mhwilds_optimizer.equipment_models import RequirementKind, SkillRequirement

catalog = load_equipment_catalog(
    Path("data/normalized/mhdb/<commit>")
)
result = solve_feasible_build(
    catalog,
    (
        SkillRequirement(
            "skill:<game_id>",
            RequirementKind.MINIMUM,
            3,
        ),
    ),
)

print(result.status, result.build, result.message)
```

結果ステータスの意味は次のとおりです。

- `feasible`: 要求を満たす合法構成を発見した。火力最適性は意味しません。
- `infeasible`: 候補集合では要求を満たす構成が存在しない。
- `error`: ソルバーの初期化・実行・解の復元に失敗した。`message` に原因を含みます。

現段階では火力目的関数、Top N、武器選択と武器スロット、シリーズ／グループスキルの具体的な戦闘効果を扱いません。武器がシリーズスキルの必要部位数へ寄与するルールも未実装です。武器用装飾品は読み込みますが、防具・護石スロットへの配置候補から除外します。

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
