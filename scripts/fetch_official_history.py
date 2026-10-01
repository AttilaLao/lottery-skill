#!/usr/bin/env python3
"""Fetch official lottery history into a unified CSV."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from PyPDF2 import PdfReader


DLT_API = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
SSQ_API = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"

FIELDS = [
    "game",
    "issue",
    "draw_date",
    "draw_result",
    "num1",
    "num2",
    "num3",
    "num4",
    "num5",
    "num6",
    "num7",
    "ball_set",
    "equipment_count",
    "total_sales",
    "pool_balance",
    "draw_pdf_url",
    "prize_levels",
]

SSQ_PRIZE_NAMES = {
    1: "一等奖",
    2: "二等奖",
    3: "三等奖",
    4: "四等奖",
    5: "五等奖",
    6: "六等奖",
    7: "福运奖",
}


def curl(url: str) -> bytes:
    return subprocess.check_output(
        [
            "curl",
            "-L",
            "--max-time",
            "80",
            "-sS",
            url,
        ],
        stderr=subprocess.DEVNULL,
    )


def parse_numbers(result: str) -> list[str]:
    return [num.strip() for num in re.split(r"\s+", result.strip()) if num.strip()]


def format_prize_levels(levels: list[dict]) -> str:
    parts = []
    for level in levels:
        name = level.get("prizeLevel", "").strip()
        amount = level.get("stakeAmount", "").strip()
        if not amount:
            continue
        parts.append(f"{name}:{amount}")
    return " | ".join(parts)


def extract_dlt_ball_set(pdf_bytes: bytes) -> str:
    text = ""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    for page in reader.pages:
        text += page.extract_text() or ""
    match = re.search(r"本期使用第(.+?)套摇奖球", text)
    return match.group(1).strip() if match else ""


def dlt_rows(pages: int, page_size: int):
    for page_no in range(1, pages + 1):
        params = {
            "gameNo": 85,
            "provinceId": 0,
            "pageSize": page_size,
            "isVerify": 1,
            "pageNo": page_no,
        }
        data = json.loads(curl(DLT_API + "?" + urlencode(params)))
        items = data.get("value", {}).get("list", [])
        for item in items:
            numbers = parse_numbers(item.get("lotteryDrawResult", ""))
            numbers += [""] * (7 - len(numbers))
            pdf_url = item.get("drawPdfUrl") or ""
            ball_set = ""
            if pdf_url:
                try:
                    ball_set = extract_dlt_ball_set(curl(pdf_url))
                except Exception:
                    ball_set = ""
            prize_levels = item.get("prizeLevelList") or []
            yield {
                "game": "dlt",
                "issue": item.get("lotteryDrawNum", ""),
                "draw_date": item.get("lotteryDrawTime", ""),
                "draw_result": item.get("lotteryDrawResult", ""),
                "num1": numbers[0],
                "num2": numbers[1],
                "num3": numbers[2],
                "num4": numbers[3],
                "num5": numbers[4],
                "num6": numbers[5],
                "num7": numbers[6],
                "ball_set": ball_set,
                "equipment_count": item.get("lotteryEquipmentCount", ""),
                "total_sales": item.get("totalSaleAmount", ""),
                "pool_balance": item.get("poolBalanceAfterdraw", ""),
                "draw_pdf_url": pdf_url,
                "prize_levels": format_prize_levels(prize_levels),
            }
        if not items:
            break


def ssq_rows(start_date: str, end_date: str, page_size: int):
    page_no = 1
    while True:
        params = {
            "name": "ssq",
            "issueCount": "",
            "issueStart": "",
            "issueEnd": "",
            "dayStart": start_date,
            "dayEnd": end_date,
            "pageNo": page_no,
            "pageSize": page_size,
            "week": "",
            "systemType": "PC",
        }
        data = json.loads(curl(SSQ_API + "?" + urlencode(params)))
        items = data.get("result", [])
        for item in items:
            red = [x.strip() for x in (item.get("red") or "").split(",") if x.strip()]
            blue = [x.strip() for x in (item.get("blue") or "").split(",") if x.strip()]
            numbers = red + blue
            numbers += [""] * (7 - len(numbers))
            prize_levels = item.get("prizegrades") or []
            normalized_levels = []
            for level in prize_levels:
                type_num = int(level.get("type") or 0)
                normalized_levels.append(
                    {
                        "prizeLevel": SSQ_PRIZE_NAMES.get(type_num, f"奖级{type_num}"),
                        "stakeAmount": level.get("typemoney", ""),
                    }
                )
            yield {
                "game": "ssq",
                "issue": item.get("code", ""),
                "draw_date": (item.get("date", "") or "")[:10],
                "draw_result": ",".join(numbers[:7]).rstrip(","),
                "num1": numbers[0],
                "num2": numbers[1],
                "num3": numbers[2],
                "num4": numbers[3],
                "num5": numbers[4],
                "num6": numbers[5],
                "num7": numbers[6],
                "ball_set": "",
                "equipment_count": "",
                "total_sales": item.get("sales", ""),
                "pool_balance": item.get("poolmoney", ""),
                "draw_pdf_url": "",
                "prize_levels": format_prize_levels(normalized_levels),
            }
        page_num = int(data.get("pageNum") or 1)
        if page_no >= page_num or not items:
            break
        page_no += 1


def write_csv(rows, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", choices=["ssq", "dlt"], required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=30)
    parser.add_argument("--start-date", default="2026-07-01")
    parser.add_argument("--end-date", default="2026-10-01")
    args = parser.parse_args()

    output = args.output or Path("data/processed") / f"{args.game}_history_official.csv"
    if args.game == "dlt":
        rows = dlt_rows(args.pages, args.page_size)
    else:
        rows = ssq_rows(args.start_date, args.end_date, args.page_size)
    write_csv(rows, output)
    print(output)


if __name__ == "__main__":
    main()
