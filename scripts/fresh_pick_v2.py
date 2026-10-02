#!/usr/bin/env python3
"""
Fresh Pick v2: auto-fetch latest data, regenerate signals and combinations.
Adds structural filters: sum value, odd/even ratio, consecutive numbers, zone coverage.
"""

import csv
import json
import io
import re
import subprocess
import sys
import math
import random
from collections import Counter
from datetime import datetime
from pathlib import Path

from math import comb

sys.path.insert(0, str(Path(__file__).parent))
from deep_correlation_test import parse_ssq, parse_dlt

DLT_API = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry"
SSQ_API = "https://www.cwl.gov.cn/cwl_admin/front/cwlkj/search/kjxx/findDrawNotice"
PYPDF2_AVAILABLE = False
try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    pass


def curl(url):
    return subprocess.check_output(["curl", "-L", "--max-time", "80", "-sS", url], stderr=subprocess.DEVNULL)


def fetch_ssq(pages=6, page_size=100):
    rows = []
    today = datetime.now().strftime("%Y-%m-%d")
    start = "2023-06-01"
    from urllib.parse import urlencode
    for page_no in range(1, pages + 1):
        params = urlencode({"name": "ssq", "dayStart": start, "dayEnd": today, "pageNo": page_no, "pageSize": page_size, "systemType": "PC"})
        try:
            data = json.loads(curl(f"{SSQ_API}?{params}"))
        except Exception:
            break
        items = data.get("result", [])
        for item in items:
            red_str = item.get("red", "")
            blue_str = item.get("blue", "")
            red = [int(x.strip()) for x in red_str.split(",") if x.strip()]
            blue = int(blue_str) if blue_str.strip() else None
            if red and blue is not None:
                rows.append({"issue": item.get("code", ""), "draw_date": (item.get("date", "") or "")[:10], "red": sorted(red), "blue": blue})
        if page_no >= int(data.get("pageNum", 1)):
            break
    rows.sort(key=lambda r: r["issue"])
    return rows


def fetch_dlt(pages=5, page_size=100):
    rows = []
    from urllib.parse import urlencode
    for page_no in range(1, pages + 1):
        params = urlencode({"gameNo": 85, "provinceId": 0, "pageSize": page_size, "isVerify": 1, "pageNo": page_no})
        try:
            data = json.loads(curl(f"{DLT_API}?{params}"))
        except Exception:
            break
        items = data.get("value", {}).get("list", [])
        for item in items:
            result = item.get("lotteryDrawResult", "")
            nums = [int(x.strip()) for x in re.split(r"\s+", result.strip()) if x.strip()]
            if len(nums) < 7:
                continue
            front = sorted(nums[:5])
            back = sorted(nums[5:7])
            ball_set = ""
            pdf_url = item.get("drawPdfUrl", "")
            if pdf_url and PYPDF2_AVAILABLE:
                try:
                    raw = curl(pdf_url)
                    text = ""
                    for page in PdfReader(io.BytesIO(raw)).pages:
                        text += page.extract_text() or ""
                    m = re.search(r"本期使用第(.+?)套摇奖球", text)
                    if m:
                        ball_set = m.group(1).strip()
                except Exception:
                    pass
            rows.append({"issue": item.get("lotteryDrawNum", ""), "draw_date": item.get("lotteryDrawTime", ""), "front": front, "back": back, "ball_set": ball_set})
        if not items:
            break
    rows.sort(key=lambda r: r["issue"])
    return rows


# ---- Structural filters ----

def check_sum(nums, lo, hi):
    s = sum(nums)
    return lo <= s <= hi

def check_odd_even(nums, good_ratios):
    odd = sum(1 for n in nums if n % 2 == 1)
    even = len(nums) - odd
    return f"{odd}:{even}" in good_ratios

def check_consecutive(nums):
    """Returns True if at least one consecutive pair exists."""
    sorted_nums = sorted(nums)
    for i in range(len(sorted_nums) - 1):
        if sorted_nums[i + 1] - sorted_nums[i] == 1:
            return True
    return False

def check_zone_coverage(nums, zones, min_zones=3):
    """Check that numbers span at least min_zones zones."""
    hit = set()
    for n in nums:
        for i, (lo, hi) in enumerate(zones):
            if lo <= n <= hi:
                hit.add(i)
                break
    return len(hit) >= min_zones

def check_dlt_zone_coverage(nums, min_zones=3):
    """DLT: 7 zones of 5, check at least 3 zones covered."""
    zones = [(i*5+1, (i+1)*5) for i in range(7)]
    return check_zone_coverage(nums, zones, min_zones)

SSQ_ZONES = [(1, 11), (12, 22), (23, 33)]
SSQ_GOOD_ODD_EVEN = {"3:3", "4:2", "2:4", "3:3"}
SSQ_SUM_LO, SSQ_SUM_HI = 80, 120

DLT_GOOD_ODD_EVEN = {"3:2", "2:3"}
DLT_SUM_LO, DLT_SUM_HI = 60, 110


def validate_ssq(reds, require_consecutive=True):
    """Check SSQ reds against structural filters."""
    if not check_sum(reds, SSQ_SUM_LO, SSQ_SUM_HI):
        return False, "和值不在80-120"
    if not check_odd_even(reds, SSQ_GOOD_ODD_EVEN):
        return False, "奇偶比不在3:3/4:2/2:4"
    if require_consecutive and not check_consecutive(reds):
        return False, "无连号"
    if not check_zone_coverage(reds, SSQ_ZONES, 3):
        return False, "三区未全覆盖"
    return True, "通过"


def validate_dlt(fronts, require_consecutive=False):
    """Check DLT fronts against structural filters."""
    if not check_sum(fronts, DLT_SUM_LO, DLT_SUM_HI):
        return False, "和值不在60-110"
    if not check_odd_even(fronts, DLT_GOOD_ODD_EVEN):
        return False, "奇偶比不在3:2/2:3"
    if require_consecutive and not check_consecutive(fronts):
        return False, "无连号"
    if not check_dlt_zone_coverage(fronts, 3):
        return False, "覆盖少于3区"
    return True, "通过"


def get_ssq_signals(draws):
    recent_100 = draws[-100:]
    red_counts = Counter()
    blue_counts = Counter()
    for d in recent_100:
        for n in d["red"]:
            red_counts[n] += 1
        blue_counts[d["blue"]] += 1
    hot_reds = [n for n, _ in red_counts.most_common(10)]
    all_reds = list(range(1, 34))
    cold_reds = sorted(all_reds, key=lambda n: red_counts.get(n, 0))[:8]
    hot_blues = [n for n, _ in blue_counts.most_common(4)]
    total = len(draws)
    last_seen = {}
    for i, d in enumerate(draws):
        for n in d["red"]:
            last_seen[n] = i
    overdue_reds = sorted(all_reds, key=lambda n: total - 1 - last_seen.get(n, 0), reverse=True)[:8]
    last_seen_blue = {}
    for i, d in enumerate(draws):
        last_seen_blue[d["blue"]] = i
    overdue_blues = sorted(range(1, 17), key=lambda n: total - 1 - last_seen_blue.get(n, 0), reverse=True)[:4]
    pair_counts = Counter()
    for d in draws:
        for i in range(len(d["red"])):
            for j in range(i + 1, len(d["red"])):
                p = (min(d["red"][i], d["red"][j]), max(d["red"][i], d["red"][j]))
                pair_counts[p] += 1
    expected_pair = total * comb(6, 2) / comb(33, 2)
    hot_pairs = [(p, c) for p, c in pair_counts.most_common(20) if c > expected_pair * 1.3]
    long_freq = Counter()
    for d in draws:
        for n in d["red"]:
            long_freq[n] += 1
    return {
        "hot_reds": hot_reds, "cold_reds": cold_reds, "hot_blues": hot_blues,
        "overdue_reds": overdue_reds, "overdue_blues": overdue_blues,
        "hot_pairs": hot_pairs,
        "long_freq": long_freq,
        "latest_issue": draws[-1]["issue"] if draws else "",
        "latest_date": draws[-1]["draw_date"] if draws else "",
    }


def get_dlt_signals(draws):
    recent_100 = draws[-100:]
    front_counts = Counter()
    back_counts = Counter()
    for d in recent_100:
        for n in d["front"]:
            front_counts[n] += 1
        for n in d["back"]:
            back_counts[n] += 1
    hot_fronts = [n for n, _ in front_counts.most_common(10)]
    all_fronts = list(range(1, 36))
    cold_fronts = sorted(all_fronts, key=lambda n: front_counts.get(n, 0))[:8]
    hot_backs = [n for n, _ in back_counts.most_common(4)]
    total = len(draws)
    last_seen = {}
    for i, d in enumerate(draws):
        for n in d["front"]:
            last_seen[n] = i
    overdue_fronts = sorted(all_fronts, key=lambda n: total - 1 - last_seen.get(n, 0), reverse=True)[:8]
    last_seen_back = {}
    for i, d in enumerate(draws):
        for n in d["back"]:
            last_seen_back[n] = i
    overdue_backs = sorted(range(1, 13), key=lambda n: total - 1 - last_seen_back.get(n, 0), reverse=True)[:4]
    pair_counts = Counter()
    for d in draws:
        for i in range(len(d["front"])):
            for j in range(i + 1, len(d["front"])):
                p = (min(d["front"][i], d["front"][j]), max(d["front"][i], d["front"][j]))
                pair_counts[p] += 1
    expected_pair = total * comb(5, 2) / comb(35, 2)
    hot_pairs = [(p, c) for p, c in pair_counts.most_common(20) if c > expected_pair * 1.3]
    long_freq = Counter()
    for d in draws:
        for n in d["front"]:
            long_freq[n] += 1
    return {
        "hot_fronts": hot_fronts, "cold_fronts": cold_fronts, "hot_backs": hot_backs,
        "overdue_fronts": overdue_fronts, "overdue_backs": overdue_backs,
        "hot_pairs": hot_pairs,
        "long_freq": long_freq,
        "latest_issue": draws[-1]["issue"] if draws else "",
        "latest_date": draws[-1]["draw_date"] if draws else "",
    }


def fill_to_n(candidates, n, fallback_pool):
    """Take candidates, fill to n from fallback_pool, no duplicates."""
    result = list(candidates)
    for n_val in fallback_pool:
        if n_val not in result:
            result.append(n_val)
        if len(result) >= n:
            break
    return sorted(set(result))[:n]


def build_ssq_combos_filtered(sig, rng):
    """Build SSQ combos with structural filters."""
    combos = []
    max_attempts = 100

    def try_build(base_reds, blue, name, logic, require_consec=True, weighted=False):
        for _ in range(max_attempts):
            pool = list(set(base_reds))
            if weighted and sig.get("long_freq"):
                freqs = [sig["long_freq"].get(n, 0) + 1 for n in pool]
                picks = list(dict.fromkeys(rng.choices(pool, weights=freqs, k=8)))
                reds = sorted(picks[:6])
            else:
                rng.shuffle(pool)
                reds = sorted(pool[:6])
            if len(reds) < 6:
                reds = fill_to_n(reds, 6, sig["hot_reds"])
            ok, reason = validate_ssq(reds, require_consec)
            if ok:
                combos.append({"name": name, "reds": reds, "blue": blue, "logic": f"{logic} | 过滤: {reason}"})
                return
        # If can't pass all filters, relax consecutive requirement
        for _ in range(max_attempts):
            pool = list(set(base_reds))
            rng.shuffle(pool)
            reds = sorted(pool[:6])
            if len(reds) < 6:
                reds = fill_to_n(reds, 6, sig["hot_reds"])
            ok, reason = validate_ssq(reds, require_consec=False)
            if ok:
                combos.append({"name": name, "reds": reds, "blue": blue, "logic": f"{logic} | 过滤: {reason}(放宽连号)"})
                return
        # Last resort: just use the base
        reds = sorted(set(base_reds))[:6]
        reds = fill_to_n(reds, 6, sig["hot_reds"])
        combos.append({"name": name, "reds": reds, "blue": blue, "logic": f"{logic} | 过滤: 未通过(使用原始)"})

    # 1: Pure hot
    try_build(sig["hot_reds"][:8], sig["hot_blues"][0], "纯热号组合", f"近100期热号 + 最热蓝球{sig['hot_blues'][0]:02d}")

    # 2: 3 hot + 2 overdue + 1 cold
    pool2 = sig["hot_reds"][:5] + sig["overdue_reds"][:4] + sig["cold_reds"][:3]
    blue2 = sig["hot_blues"][1] if len(sig["hot_blues"]) > 1 else sig["hot_blues"][0]
    try_build(pool2, blue2, "热+漏+冷混合", f"3热号+2遗漏+1冷号 + 热蓝球{blue2:02d}")

    # 3: Pair-driven
    pair_nums = set()
    for pair, _ in sig["hot_pairs"][:4]:
        pair_nums.update(pair)
    pair_pool = list(pair_nums) + sig["hot_reds"][:6]
    blue3 = sig["overdue_blues"][0]
    try_build(pair_pool, blue3, "高共现搭档组合", f"高共现号码对提取 + 该出蓝球{blue3:02d}")

    # 4: Zone overdue balance
    z1 = [n for n in sig["overdue_reds"] if n <= 11][:3]
    z2 = [n for n in sig["overdue_reds"] if 12 <= n <= 22][:3]
    z3 = [n for n in sig["overdue_reds"] if n >= 23][:3]
    pool4 = z1 + z2 + z3 + sig["hot_reds"][:5]
    blue4 = sig["overdue_blues"][1] if len(sig["overdue_blues"]) > 1 else sig["overdue_blues"][0]
    try_build(pool4, blue4, "三区遗漏平衡", f"每区遗漏最大·长期频率加权 + 该出蓝球{blue4:02d}", weighted=True)

    # 5: Pair chain
    pf = Counter()
    for pair, count in sig["hot_pairs"]:
        pf[pair[0]] += count
        pf[pair[1]] += count
    chain_pool = [n for n, _ in pf.most_common(8)] + sig["hot_reds"][:5]
    blue5 = sig["hot_blues"][2] if len(sig["hot_blues"]) > 2 else sig["hot_blues"][0]
    try_build(chain_pool, blue5, "搭档链组合", f"高共现网络中心号码 + 热蓝球{blue5:02d}")

    return combos


def build_dlt_combos_filtered(sig, rng):
    """Build DLT combos with structural filters."""
    combos = []
    max_attempts = 100

    def try_build(base_fronts, backs, name, logic, require_consec=False, weighted=False):
        for _ in range(max_attempts):
            pool = list(set(base_fronts))
            if weighted and sig.get("long_freq"):
                freqs = [sig["long_freq"].get(n, 0) + 1 for n in pool]
                picks = list(dict.fromkeys(rng.choices(pool, weights=freqs, k=7)))
                fronts = sorted(picks[:5])
            else:
                rng.shuffle(pool)
                fronts = sorted(pool[:5])
            if len(fronts) < 5:
                fronts = fill_to_n(fronts, 5, sig["hot_fronts"])
            ok, reason = validate_dlt(fronts, require_consec)
            if ok:
                combos.append({"name": name, "fronts": fronts, "backs": backs, "logic": f"{logic} | 过滤: {reason}"})
                return
        for _ in range(max_attempts):
            pool = list(set(base_fronts))
            rng.shuffle(pool)
            fronts = sorted(pool[:5])
            if len(fronts) < 5:
                fronts = fill_to_n(fronts, 5, sig["hot_fronts"])
            ok, reason = validate_dlt(fronts, require_consec=True)
            if ok:
                combos.append({"name": name, "fronts": fronts, "backs": backs, "logic": f"{logic} | 过滤: {reason}(含连号)"})
                return
        fronts = sorted(set(base_fronts))[:5]
        fronts = fill_to_n(fronts, 5, sig["hot_fronts"])
        combos.append({"name": name, "fronts": fronts, "backs": backs, "logic": f"{logic} | 过滤: 未通过(使用原始)"})

    # 1: Pure hot
    try_build(sig["hot_fronts"][:8], sorted(sig["hot_backs"][:2]), "纯热号组合", f"近100期热号 + 最热后区{sorted(sig['hot_backs'][:2])}")

    # 2: 3 hot + 2 overdue
    pool2 = sig["hot_fronts"][:5] + sig["overdue_fronts"][:4]
    try_build(pool2, sorted(sig["hot_backs"][:2]), "热+漏混合", f"3热号+2遗漏 + 热后区")

    # 3: Pair-driven
    pair_nums = set()
    for pair, _ in sig["hot_pairs"][:4]:
        pair_nums.update(pair)
    pair_pool = list(pair_nums) + sig["hot_fronts"][:6]
    backs3 = sorted(sig["overdue_backs"][:2])
    try_build(pair_pool, backs3, "高共现搭档组合", f"高共现号码对提取 + 该出后区{backs3}")

    # 4: Zone overdue balance (5 zones)
    z1 = [n for n in sig["overdue_fronts"] if n <= 7][:2]
    z2 = [n for n in sig["overdue_fronts"] if 8 <= n <= 14][:2]
    z3 = [n for n in sig["overdue_fronts"] if 15 <= n <= 21][:2]
    z4 = [n for n in sig["overdue_fronts"] if 22 <= n <= 28][:2]
    z5 = [n for n in sig["overdue_fronts"] if n >= 29][:2]
    pool4 = z1 + z2 + z3 + z4 + z5 + sig["hot_fronts"][:5]
    backs4 = sorted([sig["overdue_backs"][0], sig["hot_backs"][0]])
    try_build(pool4, backs4, "五区遗漏平衡", f"五区遗漏最大·长期频率加权 + 遗漏后区{backs4[0]:02d}+热后区{backs4[1]:02d}", weighted=True)

    # 5: Pair chain
    pf = Counter()
    for pair, count in sig["hot_pairs"]:
        pf[pair[0]] += count
        pf[pair[1]] += count
    chain_pool = [n for n, _ in pf.most_common(8)] + sig["hot_fronts"][:5]
    try_build(chain_pool, sorted(sig["hot_backs"][:2]), "搭档链组合", f"高共现网络中心号码 + 热后区")

    return combos


def main():
    print("=" * 60)
    print("  Fresh Pick v2 - 含结构过滤的数据驱动选号")
    print("=" * 60)

    print("\n[1/4] 拉取双色球最新开奖数据...")
    ssq_draws = fetch_ssq()
    print(f"  完成: {len(ssq_draws)} 期, 最新 {ssq_draws[-1]['issue']} ({ssq_draws[-1]['draw_date']})")

    print("\n[2/4] 拉取大乐透最新开奖数据 (含PDF球组解析)...")
    dlt_draws = fetch_dlt()
    print(f"  完成: {len(dlt_draws)} 期, 最新 {dlt_draws[-1]['issue']} ({dlt_draws[-1]['draw_date']})")

    print("\n[3/4] 分析数据信号 + 结构过滤...")
    ssq_sig = get_ssq_signals(ssq_draws)
    dlt_sig = get_dlt_signals(dlt_draws)
    rng = random.Random(42)
    ssq_combos = build_ssq_combos_filtered(ssq_sig, rng)
    dlt_combos = build_dlt_combos_filtered(dlt_sig, rng)

    print("\n[4/4] 生成组合方案:")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # SSQ
    print(f"\n{'='*60}")
    print(f"  双色球 (数据截至 {ssq_sig['latest_issue']} 期)")
    print(f"{'='*60}")
    print(f"\n核心信号:")
    print(f"  热号: {ssq_sig['hot_reds'][:10]}")
    print(f"  遗漏最大: {ssq_sig['overdue_reds'][:8]}")
    print(f"  热蓝球: {ssq_sig['hot_blues']}")
    print(f"  该出蓝球: {ssq_sig['overdue_blues']}")
    top_pairs_str = [f"{p[0]}-{p[1]}({c}次)" for p, c in ssq_sig['hot_pairs'][:5]]
    print(f"  高共现对: {top_pairs_str}")
    print(f"\n结构过滤条件:")
    print(f"  和值 80-120 | 奇偶 3:3/4:2/2:4 | 有连号 | 三区覆盖")

    for i, c in enumerate(ssq_combos, 1):
        reds_str = " ".join(f"{n:02d}" for n in c["reds"])
        s = sum(c["reds"])
        odd = sum(1 for n in c["reds"] if n % 2 == 1)
        print(f"\n  方案{i}: {c['name']}")
        print(f"  红球: {reds_str}  蓝球: {c['blue']:02d}")
        print(f"  和值:{s} 奇偶:{odd}:{6-odd} | {c['logic']}")

    # DLT
    print(f"\n{'='*60}")
    print(f"  大乐透 (数据截至 {dlt_sig['latest_issue']} 期)")
    print(f"{'='*60}")
    print(f"\n核心信号:")
    print(f"  热号: {dlt_sig['hot_fronts'][:10]}")
    print(f"  遗漏最大: {dlt_sig['overdue_fronts'][:8]}")
    print(f"  热后区: {dlt_sig['hot_backs']}")
    print(f"  该出后区: {dlt_sig['overdue_backs']}")
    top_pairs_str = [f"{p[0]}-{p[1]}({c})" for p, c in dlt_sig['hot_pairs'][:5]]
    print(f"  高共现对: {top_pairs_str}")
    print(f"\n结构过滤条件:")
    print(f"  和值 60-110 | 奇偶 3:2/2:3 | 覆盖3区以上")

    for i, c in enumerate(dlt_combos, 1):
        fronts_str = " ".join(f"{n:02d}" for n in c["fronts"])
        backs_str = " ".join(f"{n:02d}" for n in c["backs"])
        s = sum(c["fronts"])
        odd = sum(1 for n in c["fronts"] if n % 2 == 1)
        print(f"\n  方案{i}: {c['name']}")
        print(f"  前区: {fronts_str}  后区: {backs_str}")
        print(f"  和值:{s} 奇偶:{odd}:{5-odd} | {c['logic']}")

    print(f"\n{'='*60}")
    print(f"  生成时间: {now}")
    print(f"  使用方法: 每次开奖前运行 python3 scripts/fresh_pick_v2.py")
    print(f"  数据自动更新, 组合经过结构过滤")
    print(f"{'='*60}")

    # Save JSON
    out = Path("reports/fresh_pick_v2_latest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "generated_at": now,
        "filters": {
            "ssq": {"sum": "80-120", "odd_even": "3:3/4:2/2:4", "consecutive": True, "zones": 3},
            "dlt": {"sum": "60-110", "odd_even": "3:2/2:3", "consecutive": "optional", "zones": 3},
        },
        "ssq": {
            "latest_issue": ssq_sig["latest_issue"], "total_draws": len(ssq_draws),
            "signals": {
                "hot_reds": ssq_sig["hot_reds"], "overdue_reds": ssq_sig["overdue_reds"],
                "hot_blues": ssq_sig["hot_blues"], "overdue_blues": ssq_sig["overdue_blues"],
                "top_pairs": [{"pair": f"{p[0]},{p[1]}", "count": c} for p, c in ssq_sig["hot_pairs"][:5]],
            },
            "combos": ssq_combos,
        },
        "dlt": {
            "latest_issue": dlt_sig["latest_issue"], "total_draws": len(dlt_draws),
            "signals": {
                "hot_fronts": dlt_sig["hot_fronts"], "overdue_fronts": dlt_sig["overdue_fronts"],
                "hot_backs": dlt_sig["hot_backs"], "overdue_backs": dlt_sig["overdue_backs"],
                "top_pairs": [{"pair": f"{p[0]},{p[1]}", "count": c} for p, c in dlt_sig["hot_pairs"][:5]],
            },
            "combos": dlt_combos,
        },
    }
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out}")


if __name__ == "__main__":
    main()
