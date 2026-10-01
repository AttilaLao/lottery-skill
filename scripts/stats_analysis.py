#!/usr/bin/env python3
"""Basic statistical analysis for SSQ and DLT history data."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path


def load_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def chi_square_uniform(observed):
    n = sum(observed)
    k = len(observed)
    if k < 2 or n == 0:
        return {"chi2": None, "df": None, "p_value": None, "note": "insufficient data"}
    expected = n / k
    chi2 = sum((o - expected) ** 2 / expected for o in observed)
    df = k - 1
    try:
        from scipy import stats
        p_value = 1 - stats.chi2.cdf(chi2, df)
    except ImportError:
        p_value = _chi2_p_approx(chi2, df)
    return {"chi2": round(chi2, 4), "df": df, "p_value": round(p_value, 6) if p_value is not None else None}


def _chi2_p_approx(chi2, df):
    if df <= 0:
        return None
    z = ((chi2 / df) ** (1 / 3) - (1 - 2 / (9 * df))) / math.sqrt(2 / (9 * df))
    if z > 6:
        return 0.0
    if z < -6:
        return 1.0
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def analyze_frequency(rows, game):
    if game == "ssq":
        red_counts = Counter()
        blue_counts = Counter()
        for r in rows:
            for i in range(1, 7):
                v = r.get(f"num{i}", "").strip()
                if v:
                    red_counts[int(v)] += 1
            v = r.get("num7", "").strip()
            if v:
                blue_counts[int(v)] += 1
        red_expected = len(rows) * 6 / 33
        blue_expected = len(rows) / 16
        red_obs = [red_counts.get(i, 0) for i in range(1, 34)]
        blue_obs = [blue_counts.get(i, 0) for i in range(1, 17)]
        return {
            "game": "ssq",
            "red_zone": {
                "range": "1-33",
                "expected_per_number": round(red_expected, 2),
                "observed": {str(k): v for k, v in sorted(red_counts.items())},
                "min": min(red_counts.values()) if red_counts else 0,
                "max": max(red_counts.values()) if red_counts else 0,
                "chi_square": chi_square_uniform(red_obs),
            },
            "blue_zone": {
                "range": "1-16",
                "expected_per_number": round(blue_expected, 2),
                "observed": {str(k): v for k, v in sorted(blue_counts.items())},
                "min": min(blue_counts.values()) if blue_counts else 0,
                "max": max(blue_counts.values()) if blue_counts else 0,
                "chi_square": chi_square_uniform(blue_obs),
            },
        }
    else:
        front_counts = Counter()
        back_counts = Counter()
        for r in rows:
            for i in range(1, 6):
                v = r.get(f"num{i}", "").strip()
                if v:
                    front_counts[int(v)] += 1
            for i in range(6, 8):
                v = r.get(f"num{i}", "").strip()
                if v:
                    back_counts[int(v)] += 1
        front_expected = len(rows) * 5 / 35
        back_expected = len(rows) * 2 / 12
        front_obs = [front_counts.get(i, 0) for i in range(1, 36)]
        back_obs = [back_counts.get(i, 0) for i in range(1, 13)]
        return {
            "game": "dlt",
            "front_zone": {
                "range": "1-35",
                "expected_per_number": round(front_expected, 2),
                "observed": {str(k): v for k, v in sorted(front_counts.items())},
                "min": min(front_counts.values()) if front_counts else 0,
                "max": max(front_counts.values()) if front_counts else 0,
                "chi_square": chi_square_uniform(front_obs),
            },
            "back_zone": {
                "range": "1-12",
                "expected_per_number": round(back_expected, 2),
                "observed": {str(k): v for k, v in sorted(back_counts.items())},
                "min": min(back_counts.values()) if back_counts else 0,
                "max": max(back_counts.values()) if back_counts else 0,
                "chi_square": chi_square_uniform(back_obs),
            },
        }


def analyze_ball_set(rows):
    groups = {}
    for r in rows:
        bs = r.get("ball_set", "").strip()
        if not bs:
            continue
        groups.setdefault(bs, []).append(r)

    group_stats = {}
    for bs, group_rows in sorted(groups.items()):
        front_counts = Counter()
        for r in group_rows:
            for i in range(1, 6):
                v = r.get(f"num{i}", "").strip()
                if v:
                    front_counts[int(v)] += 1
        front_obs = [front_counts.get(i, 0) for i in range(1, 36)]
        chi = chi_square_uniform(front_obs)
        group_stats[bs] = {
            "draws": len(group_rows),
            "front_min": min(front_counts.values()) if front_counts else 0,
            "front_max": max(front_counts.values()) if front_counts else 0,
            "front_chi2": chi,
        }

    sorted_rows = sorted(rows, key=lambda r: r["issue"])
    switches = []
    prev_set = None
    run_length = 0
    for r in sorted_rows:
        bs = r.get("ball_set", "").strip()
        if not bs:
            continue
        if bs == prev_set:
            run_length += 1
        else:
            if prev_set is not None:
                switches.append({"ball_set": prev_set, "run": run_length})
            prev_set = bs
            run_length = 1
    if prev_set is not None:
        switches.append({"ball_set": prev_set, "run": run_length})

    run_lengths = [s["run"] for s in switches]
    avg_run = sum(run_lengths) / len(run_lengths) if run_lengths else 0

    return {
        "total_with_ball_set": sum(len(v) for v in groups.values()),
        "ball_set_groups": {bs: len(v) for bs, v in sorted(groups.items())},
        "group_stats": group_stats,
        "switching": {
            "total_runs": len(switches),
            "avg_run_length": round(avg_run, 2),
            "min_run": min(run_lengths) if run_lengths else 0,
            "max_run": max(run_lengths) if run_lengths else 0,
        },
    }


def analyze_sum_value(rows, game):
    sums = []
    for r in rows:
        if game == "ssq":
            nums = [int(r.get(f"num{i}", "0") or "0") for i in range(1, 7)]
        else:
            nums = [int(r.get(f"num{i}", "0") or "0") for i in range(1, 6)]
        sums.append(sum(nums))
    if not sums:
        return {}
    avg = sum(sums) / len(sums)
    return {
        "min": min(sums),
        "max": max(sums),
        "avg": round(avg, 2),
        "median": sorted(sums)[len(sums) // 2],
    }


def analyze_odd_even(rows, game):
    ratios = Counter()
    for r in rows:
        if game == "ssq":
            nums = [int(r.get(f"num{i}", "0") or "0") for i in range(1, 7)]
        else:
            nums = [int(r.get(f"num{i}", "0") or "0") for i in range(1, 6)]
        odd = sum(1 for n in nums if n % 2 == 1)
        even = len(nums) - odd
        ratios[f"{odd}:{even}"] += 1
    return {k: v for k, v in sorted(ratios.items(), key=lambda x: -x[1])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", choices=["ssq", "dlt"], required=True)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    inp = args.input or Path("data/processed") / f"{args.game}_history_official_500.csv"
    out = args.output or Path("reports") / f"{args.game}_stats.json"
    rows = load_csv(inp)

    result = {
        "game": args.game,
        "total_draws": len(rows),
        "frequency": analyze_frequency(rows, args.game),
        "sum_value": analyze_sum_value(rows, args.game),
        "odd_even": analyze_odd_even(rows, args.game),
    }

    if args.game == "dlt":
        result["ball_set_analysis"] = analyze_ball_set(rows)

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(out)


if __name__ == "__main__":
    main()
