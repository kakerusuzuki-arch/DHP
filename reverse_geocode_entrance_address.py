#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
駐車場マスタ 入口逆ジオコーディング（Python②）
入口指定の緯度経度 → Google Reverse Geocoding API で住所要素を取得し、
output_reverse.csv に 入口座標の郵便番号 / 都道府県 / 市区町村 / 町域以降 / 建物名 を書き込む。
"""

import csv
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import googlemaps
from dotenv import load_dotenv

# 列名
COL_LAT_ENTRANCE = "緯度_入口指定"
COL_LNG_ENTRANCE = "経度_入口指定"
COL_LAT_REP = "緯度_代表点"
COL_LNG_REP = "経度_代表点"
COL_POSTAL = "入口座標の郵便番号"
COL_PREF = "入口座標の都道府県"
COL_CITY = "入口座標の市区町村"
COL_TOWN = "入口座標の町域以降"
COL_BUILDING = "入口座標の建物名"
COL_RECORD_NO = "レコード番号"

BASE_DIR = Path(__file__).resolve().parent
# Phase 2 完了後の CSV（入口座標が記入された geocode 出力）を入力とする
DATA_IN = BASE_DIR / "data" / "out" / "parking_master_output_geocode.csv"
DATA_OUT = BASE_DIR / "data" / "out" / "parking_master_output_reverse.csv"
LOGS_DIR = BASE_DIR / "logs"

JST = timezone(timedelta(hours=9))


def setup_logging():
    """実行ログを logs/reverse_run_YYYYMMDD.log に出力する。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST).strftime("%Y%m%d")
    log_file = LOGS_DIR / f"reverse_run_{today}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return log_file


def parse_address_components(address_components):
    """
    address_components から以下を抽出する（日本向け）。
    - 郵便番号: postal_code
    - 都道府県: administrative_area_level_1
    - 市区町村: locality または administrative_area_level_2（locality が無い場合）
    - 町域以降: sublocality, sublocality_level_1 および route, street_number など（まとめて町域以降として結合）
    - 建物名: premise または point_of_interest（取れない場合は空で許容）
    """
    def get_by_type(types_wanted, long_name=True):
        for comp in address_components:
            types_ = comp.get("types") or []
            for t in types_wanted:
                if t in types_:
                    return comp.get("long_name" if long_name else "short_name") or ""
        return ""

    postal_code = get_by_type(["postal_code"])
    prefecture = get_by_type(["administrative_area_level_1"])
    # 市区町村: 日本では locality が市、administrative_area_level_2 が郡など
    city = get_by_type(["locality"])
    if not city:
        city = get_by_type(["administrative_area_level_2"])

    # 町域以降: 町名・丁目・番地など。sublocality, route, street_number を結合（日本ではスペースなしで繋がることも多い）
    town_parts = []
    for t in ["sublocality_level_1", "sublocality", "neighborhood"]:
        v = get_by_type([t])
        if v and v not in town_parts:
            town_parts.append(v)
    for t in ["route", "street_number"]:
        v = get_by_type([t])
        if v:
            town_parts.append(v)
    town = "".join(town_parts) if town_parts else get_by_type(["sublocality_level_2", "sublocality_level_3"]) or ""

    building = get_by_type(["premise", "subpremise", "point_of_interest", "establishment"])

    return {
        COL_POSTAL: postal_code,
        COL_PREF: prefecture,
        COL_CITY: city,
        COL_TOWN: town,
        COL_BUILDING: building or "",
    }


def should_process_row(row):
    """
    緯度_入口指定 と 経度_入口指定 が非空 かつ、
    入口座標の郵便番号 / 都道府県 / 市区町村 / 町域以降 / 建物名 のいずれかが空（未処理）の行を対象。
    """
    lat = (row.get(COL_LAT_ENTRANCE) or "").strip()
    lng = (row.get(COL_LNG_ENTRANCE) or "").strip()
    if not lat or not lng:
        return False
    for col in (COL_POSTAL, COL_PREF, COL_CITY, COL_TOWN, COL_BUILDING):
        if col not in row:
            return True
        if not (row.get(col) or "").strip():
            return True
    return False


def _run_test_only(api_key, lat=None, lng=None):
    """API を1回だけ呼んで結果を表示（ファイルは書き込まない）"""
    if lat is not None and lng is not None:
        lat_f, lng_f = float(lat), float(lng)
    else:
        if not DATA_IN.exists():
            logging.error("入力ファイルが存在しません: %s", DATA_IN)
            sys.exit(1)
        with open(DATA_IN, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # 入口指定があれば優先、なければ代表点を使用
                lat_s = (row.get(COL_LAT_ENTRANCE) or row.get(COL_LAT_REP) or "").strip()
                lng_s = (row.get(COL_LNG_ENTRANCE) or row.get(COL_LNG_REP) or "").strip()
                if lat_s and lng_s:
                    try:
                        lat_f, lng_f = float(lat_s), float(lng_s)
                        break
                    except (TypeError, ValueError):
                        continue
            else:
                logging.error("緯度・経度が入った行がありません")
                sys.exit(1)
    client = googlemaps.Client(key=api_key)
    logging.info("テスト: API を1回呼び出し（緯度=%s, 経度=%s）", lat_f, lng_f)
    response = client.reverse_geocode((lat_f, lng_f), language="ja")
    results = response if isinstance(response, list) else response.get("results", [])
    if results:
        parsed = parse_address_components(results[0].get("address_components") or [])
        logging.info("結果: %s %s %s %s %s", parsed.get(COL_POSTAL), parsed.get(COL_PREF), parsed.get(COL_CITY), parsed.get(COL_TOWN), parsed.get(COL_BUILDING))
    else:
        logging.warning("結果: ZERO_RESULTS")
    logging.info("テスト完了（ファイルは書き込みません）")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="入口逆ジオコーディング")
    parser.add_argument("--test", action="store_true", help="API を1回だけ呼んでテスト（ファイルは書き込まない）")
    parser.add_argument("--lat", type=float, help="テスト時の緯度（--test と併用）")
    parser.add_argument("--lng", type=float, help="テスト時の経度（--test と併用）")
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("エラー: 環境変数 GOOGLE_MAPS_API_KEY が未設定です。.env に設定してください。")
        sys.exit(1)

    setup_logging()

    if args.test:
        _run_test_only(api_key, lat=args.lat, lng=args.lng)
        return 0

    logging.info("入口逆ジオコーディング開始")

    if not DATA_IN.exists():
        logging.error("入力ファイルが存在しません: %s（先に Python① を実行し、担当者が入口座標を記入した CSV を用意してください）", DATA_IN)
        sys.exit(1)

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)

    client = googlemaps.Client(key=api_key)

    # 入力: 入口座標が記入された geocode 出力
    with open(DATA_IN, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # 再実行時: 既存の output_reverse から住所要素が埋まっている行をコピー（冪等性）
    if DATA_OUT.exists():
        with open(DATA_OUT, "r", encoding="utf-8-sig", newline="") as f:
            out_reader = csv.DictReader(f)
            out_by_key = {str(r.get(COL_RECORD_NO)): r for r in out_reader}
        addr_cols = [COL_POSTAL, COL_PREF, COL_CITY, COL_TOWN, COL_BUILDING]
        for row in rows:
            key = str(row.get(COL_RECORD_NO))
            if key in out_by_key:
                prev = out_by_key[key]
                for c in addr_cols:
                    if (prev.get(c) or "").strip():
                        row[c] = prev.get(c, "")
        logging.info("既存の逆ジオ結果を %s から復元しました", DATA_OUT)

    if not fieldnames:
        logging.error("入力CSVにヘッダーがありません")
        sys.exit(1)

    for col in (COL_POSTAL, COL_PREF, COL_CITY, COL_TOWN, COL_BUILDING):
        if col not in fieldnames:
            fieldnames.append(col)

    for i, row in enumerate(rows):
        if not should_process_row(row):
            continue
        record_no = row.get(COL_RECORD_NO, i + 2)
        try:
            lat = float((row.get(COL_LAT_ENTRANCE) or "").strip())
            lng = float((row.get(COL_LNG_ENTRANCE) or "").strip())
        except (TypeError, ValueError):
            logging.warning("緯度経度が不正: レコード番号=%s", record_no)
            continue

        try:
            response = client.reverse_geocode((lat, lng), language="ja")
        except Exception as e:
            logging.exception("逆ジオコーディング API エラー レコード番号=%s: %s", record_no, e)
            continue

        if isinstance(response, list):
            results = response
        elif isinstance(response, dict):
            results = response.get("results", [])
        else:
            results = []

        if not results:
            logging.warning("ZERO_RESULTS: レコード番号=%s (%s, %s)", record_no, lat, lng)
            continue

        # 先頭結果の address_components を解析（最も詳細な住所が先頭になることが多い）
        first = results[0]
        components = first.get("address_components") or []
        parsed = parse_address_components(components)

        for k, v in parsed.items():
            row[k] = v

        logging.info(
            "逆ジオ完了: レコード番号=%s → %s %s %s %s",
            record_no,
            parsed.get(COL_PREF),
            parsed.get(COL_CITY),
            parsed.get(COL_TOWN),
            parsed.get(COL_POSTAL),
        )

    with open(DATA_OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logging.info("出力ファイル: %s", DATA_OUT)
    logging.info("入口逆ジオコーディング完了")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
