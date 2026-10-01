#!/usr/bin/env python3
"""Flask server for lottery app."""

import json
import random
import sys
from datetime import datetime
from datetime import timedelta
from pathlib import Path

from flask import Flask, render_template, jsonify, Response

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from fresh_pick_v2 import (
    fetch_ssq, fetch_dlt, get_ssq_signals, get_dlt_signals,
    build_ssq_combos_filtered, build_dlt_combos_filtered,
)
import fresh_pick_v2
fresh_pick_v2.PYPDF2_AVAILABLE = False  # skip per-draw PDF download; ball_set not used by signals

# SSQ draws on Tue(1)/Thu(3)/Sun(6), DLT draws on Mon(0)/Wed(2)/Sat(5)
SSQ_DAYS = {1, 3, 6}
DLT_DAYS = {0, 2, 5}

def next_draw_date(latest_date_str, draw_days):
    latest = datetime.strptime(latest_date_str, "%Y-%m-%d")
    for delta in range(1, 9):
        nxt = latest + timedelta(days=delta)
        if nxt.weekday() in draw_days:
            return nxt.strftime("%Y-%m-%d")
    return ""


app = Flask(__name__, template_folder="templates", static_folder="static")


@app.route("/")
@app.route("/index.html")
@app.route("/lucky")
@app.route("/lucky/index.html")
def index():
    html = render_template("index.html")
    resp = Response(html, content_type="text/html; charset=utf-8")
    resp.headers["Cache-Control"] = "no-cache, no-transform"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Alt-Svc"] = "clear"
    return resp


@app.route("/api/generate")
@app.route("/lucky/api/generate")
def generate():
    try:
        ssq_draws = fetch_ssq()
        dlt_draws = fetch_dlt()
        rng = random.Random(42)
        ssq_sig = get_ssq_signals(ssq_draws)
        dlt_sig = get_dlt_signals(dlt_draws)
        ssq_combos = build_ssq_combos_filtered(ssq_sig, rng)
        dlt_combos = build_dlt_combos_filtered(dlt_sig, rng)

        return jsonify({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
           "recent_draws": {
               "ssq": [{"issue": d["issue"], "date": d["draw_date"], "red": d["red"], "blue": d["blue"]} for d in ssq_draws[-3:]],
               "dlt": [{"issue": d["issue"], "date": d["draw_date"], "front": d["front"], "back": d["back"]} for d in dlt_draws[-3:]],
           },
            "next_draw": {
                "ssq": next_draw_date(ssq_draws[-1]["draw_date"], SSQ_DAYS),
                "dlt": next_draw_date(dlt_draws[-1]["draw_date"], DLT_DAYS),
            },
           "ssq": {
                "latest_issue": ssq_sig["latest_issue"],
                "total_draws": len(ssq_draws),
                "signals": {
                    "hot_reds": ssq_sig["hot_reds"],
                    "overdue_reds": ssq_sig["overdue_reds"],
                    "hot_blues": ssq_sig["hot_blues"],
                    "overdue_blues": ssq_sig["overdue_blues"],
                    "top_pairs": [{"pair": f"{p[0]},{p[1]}", "count": c} for p, c in ssq_sig["hot_pairs"][:5]],
                },
                "combos": ssq_combos,
            },
            "dlt": {
                "latest_issue": dlt_sig["latest_issue"],
                "total_draws": len(dlt_draws),
                "signals": {
                    "hot_fronts": dlt_sig["hot_fronts"],
                    "overdue_fronts": dlt_sig["overdue_fronts"],
                    "hot_backs": dlt_sig["hot_backs"],
                    "overdue_backs": dlt_sig["overdue_backs"],
                    "top_pairs": [{"pair": f"{p[0]},{p[1]}", "count": c} for p, c in dlt_sig["hot_pairs"][:5]],
                },
                "combos": dlt_combos,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=9090)
