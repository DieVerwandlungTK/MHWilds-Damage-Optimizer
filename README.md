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
