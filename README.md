# 駐車場マスタ 緯度経度抽出プロジェクト（DHP）

大和ハウスパーキング運営の駐車場について、地図表示用の緯度経度データを整備するための Python スクリプトです。

## 処理フロー

1. **Phase 1（Python①）** 住所 → 代表点の緯度経度を取得 → `data/out/parking_master_output_geocode.csv` に出力
2. **Phase 2（人間）** 担当者が地図上で入口を確認し、`緯度_入口指定`・`経度_入口指定`・`確認日_入口指定`・`入口座標フラグ` を CSV に記入
3. **Phase 3（Python②）** 入口座標 → 逆ジオで住所要素を取得 → `data/out/parking_master_output_reverse.csv` に出力

## 必要な環境

- Python 3.8 以上
- Google Maps Geocoding API が利用可能な API キー

## セットアップ

```bash
pip install -r requirements.txt
```

API キーを設定します。

1. プロジェクト直下に `.env` を作成する（`.env.example` をコピーして編集）
2. 次の1行を記入する:  
   `GOOGLE_MAPS_API_KEY=あなたのGoogle_Maps_APIキー`

※ `.env` には API キーが含まれるため、第三者に共有しないでください。

## ディレクトリ構成

```
data/
  in/   PS緯度経度なし一覧.csv   # 入力（レコード番号・地図表示用 所在地 必須）
  out/  parking_master_output_geocode.csv   # Phase1 出力
        parking_master_output_reverse.csv   # Phase3 出力
logs/
  geocode_run_YYYYMMDD.log
  reverse_run_YYYYMMDD.log
  geocode_error_log.csv   # Phase1 でジオコード失敗した行
```

## 実行手順

### Phase 1: 代表点ジオコーディング

```bash
python geocode_representative_point.py
```

- 入力: `data/in/PS緯度経度なし一覧.csv`
- 出力: `data/out/parking_master_output_geocode.csv`（緯度_代表点・経度_代表点・確認日_代表点 を埋める）
- 既に代表点が埋まっている行はスキップ（冪等）

### Phase 2: 人間による入口座標の記入

`parking_master_output_geocode.csv` を開き、地図で入口を確認した行に以下を記入する。

- 緯度_入口指定
- 経度_入口指定
- 確認日_入口指定
- 入口座標フラグ（例: 1）

### Phase 3: 入口の逆ジオコーディング

```bash
python reverse_geocode_entrance_address.py
```

- 入力: `data/out/parking_master_output_geocode.csv`（Phase2 で入口を記入したもの）
- 出力: `data/out/parking_master_output_reverse.csv`（入口座標の郵便番号・都道府県・市区町村・町域以降・建物名 を埋める）

## 仕様概要

- **Python①** 対象行: 「地図表示用 所在地」が非空 かつ 緯度/経度_代表点 が空の行。候補は `ROOFTOP` > `RANGE_INTERPOLATED` > `GEOMETRIC_CENTER` > `APPROXIMATE` の順で採用。`ZERO_RESULTS` はログに記録し行単位で継続。`OVER_QUERY_LIMIT` は指数バックオフでリトライ。
- **Python②** 対象行: 緯度_入口指定・経度_入口指定 が非空 かつ 住所要素のいずれかが空の行。`address_components` から郵便番号・都道府県・市区町村・町域以降・建物名を分解して出力（建物名は取れない場合は空で許容）。

詳細は `コンテキスト.md` を参照してください。

## GitHub にプッシュする

**前提**: [Git for Windows](https://gitforwindows.org/) をインストールし、GitHub アカウントで新規リポジトリを作成しておく。

プロジェクトフォルダ直下で以下を実行する。

```bash
# 初回のみ
git init
git add .
git commit -m "Initial commit: DHP 駐車場マスタ 緯度経度抽出"

# リモートを追加（GitHub で作成したリポジトリの URL に置き換える）
git remote add origin https://github.com/<ユーザー名>/<リポジトリ名>.git
git branch -M main
git push -u origin main
```

**注意**: `.env` は `.gitignore` に含まれており、プッシュされません。本番データ（`data/in/*.csv`）をコミットしたくない場合は、`.gitignore` に `data/in/*.csv` を追加してください。