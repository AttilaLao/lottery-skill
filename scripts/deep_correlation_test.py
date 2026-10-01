#!/usr/bin/env python3
"""Deep correlation analysis: autocorrelation, gap distribution, pairwise, Markov."""

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


def load_csv(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_ssq(rows):
    results = []
    for r in sorted(rows, key=lambda x: x["issue"]):
        red = sorted(int(r[f"num{i}"]) for i in range(1, 7) if r.get(f"num{i}", "").strip())
        blue = int(r["num7"]) if r.get("num7", "").strip() else None
        if red and blue is not None:
            results.append({"red": red, "blue": blue, "issue": r["issue"]})
    return results


def parse_dlt(rows):
    results = []
    for r in sorted(rows, key=lambda x: x["issue"]):
        front = sorted(int(r[f"num{i}"]) for i in range(1, 6) if r.get(f"num{i}", "").strip())
        back = sorted(int(r[f"num{i}"]) for i in range(6, 8) if r.get(f"num{i}", "").strip())
        if front and back:
            results.append({"front": front, "back": back, "issue": r["issue"]})
    return results


def gap_analysis(draws, num_range, field, total_numbers):
    """Analyze gap (omission) distribution vs theoretical geometric."""
    last_seen = {}
    gaps = []
    for i, draw in enumerate(draws):
        nums = draw[field] if isinstance(draw[field], list) else [draw[field]]
        for n in num_range:
            if n in nums:
                if n in last_seen:
                    gaps.append(i - last_seen[n])
                last_seen[n] = i
    if not gaps:
        return {}
    # Theoretical: geometric distribution with p = total_numbers / len(num_range)
    p = total_numbers / len(num_range)
    theoretical_mean = 1 / p
    actual_mean = sum(gaps) / len(gaps)
    actual_median = sorted(gaps)[len(gaps) // 2]
    actual_max = max(gaps)

    # Bucket distribution
    buckets = [(0, 5), (6, 10), (11, 20), (21, 30), (31, 50), (51, 100), (101, 999)]
    bucket_counts = []
    for lo, hi in buckets:
        count = sum(1 for g in gaps if lo <= g <= hi)
        theoretical_p = math.exp(-p * (lo - 1)) - math.exp(-p * hi) if lo > 0 else 1 - math.exp(-p * hi)
        theoretical_count = theoretical_p * len(gaps)
        bucket_counts.append({
            "range": f"{lo}-{hi}",
            "actual": count,
            "theoretical": round(theoretical_count, 1),
        })

    return {
        "total_gaps": len(gaps),
        "theoretical_mean_gap": round(theoretical_mean, 2),
        "actual_mean_gap": round(actual_mean, 2),
        "actual_median_gap": actual_median,
        "actual_max_gap": actual_max,
        "gap_distribution": bucket_counts,
    }


def autocorrelation(draws, field, lag=1):
    """Check if consecutive draws share more/fewer numbers than expected by chance."""
    overlaps = []
    for i in range(lag, len(draws)):
        prev_nums = set(draws[i - lag][field])
        curr_nums = set(draws[i][field])
        overlap = len(prev_nums & curr_nums)
        overlaps.append(overlap)
    avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
    # Theoretical: for SSQ, P(a specific number repeats) = 6/33 * 6/33 * 33 = 6*6/33
    # Expected overlap = total_numbers * (pick / pool)^2 * pool = pick^2 / pool
    pick = len(draws[0][field]) if draws else 0
    pool = max(draws[0][field]) if draws else 0
    expected = pick * pick / pool
    return {
        "lag": lag,
        "avg_overlap": round(avg_overlap, 4),
        "theoretical_overlap": round(expected, 4),
        "overlap_distribution": {str(k): v for k, v in sorted(Counter(overlaps).items())},
        "difference": round(avg_overlap - expected, 4),
    }


def pairwise_cooccurrence(draws, field, num_range):
    """Check if certain number pairs co-occur more/less than expected."""
    pair_counts = Counter()
    total_draws = len(draws)
    pick = len(draws[0][field]) if draws else 0
    pool_size = len(num_range)

    # Expected co-occurrence per pair per draw: C(pick,2) / C(pool,2)
    from math import comb
    expected_per_pair = comb(pick, 2) / comb(pool_size, 2) if pool_size > 1 else 0
    expected_total = expected_per_pair * total_draws

    for draw in draws:
        nums = draw[field]
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair = (min(nums[i], nums[j]), max(nums[i], nums[j]))
                pair_counts[pair] += 1

    if not pair_counts:
        return {}

    counts = list(pair_counts.values())
    avg = sum(counts) / len(counts)
    mn = min(counts)
    mx = max(counts)

    # Find most extreme pairs
    sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)
    top_5 = [{"pair": f"{p[0]},{p[1]}", "count": c, "expected": round(expected_total, 1)} for p, c in sorted_pairs[:5]]
    bottom_5 = [{"pair": f"{p[0]},{p[1]}", "count": c, "expected": round(expected_total, 1)} for p, c in sorted_pairs[-5:]]

    return {
        "total_unique_pairs": len(pair_counts),
        "expected_co_occurrence_per_pair": round(expected_total, 2),
        "actual_avg": round(avg, 2),
        "actual_min": mn,
        "actual_max": mx,
        "top_5_co_occurring": top_5,
        "bottom_5_co_occurring": bottom_5,
    }


def markov_transition(draws, field, num_range, position=0):
    """Check if certain numbers tend to follow position-specific numbers."""
    if position >= len(draws[0][field]):
        return {}
    transitions = defaultdict(Counter)
    for i in range(1, len(draws)):
        prev_num = draws[i - 1][field][position] if position < len(draws[i - 1][field]) else None
        curr_nums = set(draws[i][field])
        if prev_num is not None:
            for n in num_range:
                transitions[prev_num][n] += (1 if n in curr_nums else 0)

    # Check if transition probabilities deviate from uniform
    results = {}
    for src in list(transitions.keys())[:5]:  # Sample first 5
        counts = transitions[src]
        total = sum(counts.values())
        expected = total / len(num_range)
        if total > 0:
            chi2 = sum((counts.get(n, 0) - expected) ** 2 / expected for n in num_range) if expected > 0 else 0
            top = counts.most_common(3)
            results[str(src)] = {
                "total_transitions": total,
                "expected_per_number": round(expected, 2),
                "chi2": round(chi2, 2),
                "top_3_followers": [{"number": n, "count": c} for n, c in top],
            }
    return results


def consecutive_number_analysis(draws, field):
    """Analyze consecutive numbers (e.g., 7,8 appearing together)."""
    has_consecutive = 0
    consecutive_counts = Counter()
    for draw in draws:
        nums = sorted(draw[field])
        consec = 0
        for i in range(len(nums) - 1):
            if nums[i + 1] - nums[i] == 1:
                consec += 1
        if consec > 0:
            has_consecutive += 1
        consecutive_counts[consec] += 1

    total = len(draws)
    pick = len(draws[0][field]) if draws else 0
    pool = max(max(d[field]) for d in draws) if draws else 0

    # Theoretical P(at least 1 consecutive pair) for k numbers from n
    # Approximate: 1 - C(n-k+1, k) / C(n, k)
    from math import comb
    p_no_consec = comb(pool - pick + 1, pick) / comb(pool, pick) if pool >= pick else 0
    p_at_least_one = 1 - p_no_consec

    return {
        "total_draws": total,
        "draws_with_consecutive": has_consecutive,
        "pct_with_consecutive": round(has_consecutive / total * 100, 2) if total else 0,
        "theoretical_pct": round(p_at_least_one * 100, 2),
        "distribution": {str(k): v for k, v in sorted(consecutive_counts.items())},
    }


def main():
    results = {}

    # SSQ
    ssq_rows = load_csv(Path("data/processed/ssq_history_official_500.csv"))
    ssq_draws = parse_ssq(ssq_rows)

    results["ssq"] = {
        "gap_red": gap_analysis(ssq_draws, range(1, 34), "red", 6),
        "gap_blue": gap_analysis(ssq_draws, range(1, 17), "blue", 1),
        "autocorrelation_lag1": autocorrelation(ssq_draws, "red", 1),
        "autocorrelation_lag2": autocorrelation(ssq_draws, "red", 2),
        "pairwise_red": pairwise_cooccurrence(ssq_draws, "red", range(1, 34)),
        "consecutive_red": consecutive_number_analysis(ssq_draws, "red"),
        "markov_position0": markov_transition(ssq_draws, "red", range(1, 34), 0),
    }

    # DLT
    dlt_rows = load_csv(Path("data/processed/dlt_history_official_500.csv"))
    dlt_draws = parse_dlt(dlt_rows)

    results["dlt"] = {
        "gap_front": gap_analysis(dlt_draws, range(1, 36), "front", 5),
        "gap_back": gap_analysis(dlt_draws, range(1, 13), "back", 2),
        "autocorrelation_lag1": autocorrelation(dlt_draws, "front", 1),
        "autocorrelation_lag2": autocorrelation(dlt_draws, "front", 2),
        "pairwise_front": pairwise_cooccurrence(dlt_draws, "front", range(1, 36)),
        "consecutive_front": consecutive_number_analysis(dlt_draws, "front"),
        "markov_position0": markov_transition(dlt_draws, "front", range(1, 36), 0),
    }

    out = Path("reports/deep_correlation.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(out)

    # Print summary
    for game in ["ssq", "dlt"]:
        d = results[game]
        print(f"\n===== {game.upper()} =====")

        for gap_key in [k for k in d if k.startswith("gap_")]:
            g = d[gap_key]
            print(f"\n{gap_key}:")
            print(f"  theoretical_mean={g['theoretical_mean_gap']} actual_mean={g['actual_mean_gap']} max_gap={g['actual_max_gap']}")
            for b in g["gap_distribution"]:
                print(f"  gap {b['range']}: actual={b['actual']} theoretical={b['theoretical']}")

        for ac_key in [k for k in d if k.startswith("autocorrelation")]:
            ac = d[ac_key]
            print(f"\n{ac_key}:")
            print(f"  avg_overlap={ac['avg_overlap']} theoretical={ac['theoretical_overlap']} diff={ac['difference']}")

        pw_key = [k for k in d if k.startswith("pairwise")][0]
        pw = d[pw_key]
        print(f"\n{pw_key}:")
        print(f"  expected={pw['expected_co_occurrence_per_pair']} avg={pw['actual_avg']} min={pw['actual_min']} max={pw['actual_max']}")
        print(f"  top: {pw['top_5_co_occurring'][:3]}")
        print(f"  bottom: {pw['bottom_5_co_occurring'][:3]}")

        cc_key = [k for k in d if k.startswith("consecutive")][0]
        cc = d[cc_key]
        print(f"\n{cc_key}:")
        print(f"  actual_pct={cc['pct_with_consecutive']}% theoretical_pct={cc['theoretical_pct']}%")
        print(f"  distribution: {cc['distribution']}")

        mk_key = [k for k in d if k.startswith("markov")][0]
        mk = d[mk_key]
        print(f"\n{mk_key}:")
        for src, info in list(mk.items())[:3]:
            print(f"  after {src}: chi2={info['chi2']} top={info['top_3_followers']}")


if __name__ == "__main__":
    main()
