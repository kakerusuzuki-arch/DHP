#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
駐車場マスタ 代表点ジオコーディング（Python①）
住所（地図表示用 所在地）→ Google Geocoding API で代表点の緯度経度を取得し、
output_geocode.csv に 緯度_代表点 / 経度_代表点 / 確認日_代表点 を書き込む。
"""

import csv
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import googlemaps
from dotenv import load_dotenv

# 定数
LOCATION_TYPE_ORDER = (
    "ROOFTOP",
    "RANGE_INTERPOLATED",
    "GEOMETRIC_CENTER",
    "APPROXIMATE",
)
COL_ADDRESS = "地図表示用 所在地"
COL_LAT = "緯度_代表点"
COL_LNG = "経度_代表点"
COL_CONFIRM_DATE = "確認日_代表点"
COL_RECORD_NO = "レコード番号"

BASE_DIR = Path(__file__).resolve().parent
DATA_IN = BASE_DIR / "data" / "in" / "PS緯度経度なし一覧.csv"
DATA_OUT = BASE_DIR / "data" / "out" / "parking_master_output_geocode.csv"
LOGS_DIR = BASE_DIR / "logs"
ERROR_LOG_CSV = BASE_DIR / "logs" / "geocode_error_log.csv"

JST = timezone(timedelta(hours=9))


def setup_logging():
    """実行ログを logs/geocode_run_YYYYMMDD.log に出力する。"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(JST).strftime("%Y%m%d")
    log_file = LOGS_DIR / f"geocode_run_{today}.log"
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


def get_jst_now_str():
    """JST の現在時刻を YYYY-MM-DD HH:MM:SS+09:00 形式で返す。"""
    return datetime.now(JST).strftime("%Y-%m-%d %H:%M:%S+09:00")


def select_best_candidate(results):
    """
    候補選定ルール:
    (1) location_type 優先順位: ROOFTOP > RANGE_INTERPOLATED > GEOMETRIC_CENTER > APPROXIMATE
    (2) 同一 type なら partial_match == False を優先
    (3) それでも複数なら先頭を採用
    """
    def rank(r):
        loc_type = r.get("geometry", {}).get("location_type", "APPROXIMATE")
        try:
            type_rank = LOCATION_TYPE_ORDER.index(loc_type)
        except ValueError:
            type_rank = len(LOCATION_TYPE_ORDER)
        partial = 1 if r.get("partial_match") else 0
        return (type_rank, partial)

    sorted_results = sorted(results, key=rank)
    return sorted_results[0] if sorted_results else None


def should_process_row(row):
    """地図表示用 所在地 が非空 かつ 緯度_代表点 または 経度_代表点 が空の行を処理対象とする。"""
    addr = (row.get(COL_ADDRESS) or "").strip()
    lat = (row.get(COL_LAT) or "").strip()
    lng = (row.get(COL_LNG) or "").strip()
    return bool(addr) and (not lat or not lng)


def geocode_with_retry(client, address, max_retries=5):
    """
    Geocoding API を呼び出し、OVER_QUERY_LIMIT 時は指数バックオフでリトライする。
    戻り値: (status, results_or_none)
    - status が "OK" のとき results は list
    - それ以外は results は None
    REQUEST_DENIED / INVALID_REQUEST の場合は例外を再送出して処理中断。
    """
    import time
    for attempt in range(max_retries):
        try:
            response = client.geocode(address, region="jp", language="ja")
            if isinstance(response, list):
                return ("OK", response)
            if isinstance(response, dict):
                status = response.get("status", "UNKNOWN")
                results = response.get("results", [])
                if status in ("REQUEST_DENIED", "INVALID_REQUEST"):
                    raise ValueError("API status=%s (設定/入力不備のため中断)" % status)
                return (status, results if status == "OK" else None)
            return ("UNKNOWN", None)
        except ValueError:
            raise
        except Exception as e:
            err_str = str(e).upper()
            if "OVER_QUERY_LIMIT" in err_str or "429" in err_str:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logging.warning("OVER_QUERY_LIMIT: %s 秒待機してリトライします（%d/%d）", wait, attempt + 1, max_retries)
                    time.sleep(wait)
                    continue
                return ("OVER_QUERY_LIMIT", None)
            if "REQUEST_DENIED" in err_str or "INVALID_REQUEST" in err_str:
                logging.error("API エラー（設定/入力不備）: %s", e)
                raise SystemExit(1)
            logging.exception("API 呼び出しエラー: %s", e)
            return ("INVALID_REQUEST", None)
    return ("OVER_QUERY_LIMIT", None)


def _run_test_only(api_key, address=None):
    """API を1回だけ呼んで結果を表示（ファイルは書き込まない）"""
    if address:
        addr = address.strip()
    else:
        if not DATA_IN.exists():
            logging.error("入力ファイルが存在しません: %s", DATA_IN)
            sys.exit(1)
        with open(DATA_IN, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                addr = (row.get(COL_ADDRESS) or "").strip()
                if addr:
                    break
            else:
                logging.error("住所が入った行がありません")
                sys.exit(1)
    client = googlemaps.Client(key=api_key)
    logging.info("テスト: API を1回呼び出し（住所=%s）", addr)
    status, results = geocode_with_retry(client, addr)
    if status == "OK" and results:
        best = select_best_candidate(results)
        loc = best["geometry"]["location"]
        logging.info("結果: 緯度=%s, 経度=%s", loc["lat"], loc["lng"])
    else:
        logging.warning("結果: status=%s, results=%s", status, "あり" if results else "なし")
    logging.info("テスト完了（ファイルは書き込みません）")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="代表点ジオコーディング")
    parser.add_argument("--test", action="store_true", help="API を1回だけ呼んでテスト（ファイルは書き込まない）")
    parser.add_argument("--address", type=str, help="テスト時に使用する住所（--test と併用）")
    args = parser.parse_args()

    load_dotenv(BASE_DIR / ".env")
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not api_key:
        print("エラー: 環境変数 GOOGLE_MAPS_API_KEY が未設定です。.env に設定するか、本READMEを参照してください。")
        sys.exit(1)

    setup_logging()

    if args.test:
        _run_test_only(api_key, address=args.address)
        return 0

    logging.info("代表点ジオコーディング開始")

    if not DATA_IN.exists():
        logging.error("入力ファイルが存在しません: %s", DATA_IN)
        sys.exit(1)

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    client = googlemaps.Client(key=api_key)

    # 入力 CSV を読み込み（UTF-8）
    with open(DATA_IN, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    # 再実行時: 既存の出力から代表点が埋まっている行の値をコピーし、上書きしない（冪等性）
    if DATA_OUT.exists():
        with open(DATA_OUT, "r", encoding="utf-8-sig", newline="") as f:
            out_reader = csv.DictReader(f)
            out_rows_by_key = {str(r.get(COL_RECORD_NO)): r for r in out_reader}
        for row in rows:
            key = str(row.get(COL_RECORD_NO))
            if key in out_rows_by_key:
                prev = out_rows_by_key[key]
                if (prev.get(COL_LAT) or "").strip() and (prev.get(COL_LNG) or "").strip():
                    row[COL_LAT] = prev.get(COL_LAT, "")
                    row[COL_LNG] = prev.get(COL_LNG, "")
                    row[COL_CONFIRM_DATE] = prev.get(COL_CONFIRM_DATE, "")
        logging.info("既存の代表点を %s から復元しました", DATA_OUT)

    if not fieldnames:
        logging.error("入力CSVにヘッダーがありません")
        sys.exit(1)

    # 出力用に必須列がなければ追加（入力が最小列のみの場合は列を足す）
    required_out = [COL_LAT, COL_LNG, COL_CONFIRM_DATE]
    for col in required_out:
        if col not in fieldnames:
            fieldnames = list(fieldnames) + [col]

    confirm_time = get_jst_now_str()
    error_rows = []

    for i, row in enumerate(rows):
        if not should_process_row(row):
            continue
        record_no = row.get(COL_RECORD_NO, i + 2)
        address = (row.get(COL_ADDRESS) or "").strip()

        status, results = geocode_with_retry(client, address)

        if status == "ZERO_RESULTS" or (status == "OK" and not results):
            logging.warning("ZERO_RESULTS: レコード番号=%s 住所=%s", record_no, address)
            error_rows.append({"レコード番号": record_no, "住所": address, "status": status or "ZERO_RESULTS"})
            continue

        if status == "OVER_QUERY_LIMIT":
            logging.error("OVER_QUERY_LIMIT が解消されませんでした。レコード番号=%s", record_no)
            error_rows.append({"レコード番号": record_no, "住所": address, "status": status})
            continue

        if status not in ("OK",) or not results:
            logging.error("API エラー status=%s: レコード番号=%s", status, record_no)
            error_rows.append({"レコード番号": record_no, "住所": address, "status": status})
            continue

        best = select_best_candidate(results)
        if not best:
            error_rows.append({"レコード番号": record_no, "住所": address, "status": "NO_CANDIDATE"})
            continue

        loc = best["geometry"]["location"]
        row[COL_LAT] = loc["lat"]
        row[COL_LNG] = loc["lng"]
        row[COL_CONFIRM_DATE] = confirm_time
        logging.info("代表点取得: レコード番号=%s → (%s, %s)", record_no, row[COL_LAT], row[COL_LNG])

    # 出力 CSV に上書き保存（入力CSVをコピーした上で列を埋めた形）
    with open(DATA_OUT, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    logging.info("出力ファイル: %s", DATA_OUT)

    # エラーログ CSV
    if error_rows:
        with open(ERROR_LOG_CSV, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["レコード番号", "住所", "status"])
            w.writeheader()
            w.writerows(error_rows)
        logging.info("エラーログ: %s (%d 件)", ERROR_LOG_CSV, len(error_rows))

    logging.info("代表点ジオコーディング完了")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
