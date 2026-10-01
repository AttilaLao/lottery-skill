# Lottery Skill

> A data-driven lottery number picker for China's 双色球 (SSQ) and 超级大乐透 (DLT), with 500+ draws of official history analyzed in real time.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Codex Skill](https://img.shields.io/badge/Codex-Skill-blue.svg)](https://codex.ai)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)

## Why this exists

Picking lottery numbers by gut feeling is no fun. This tool pulls **real official draw data** (500+ issues), runs statistical analysis, and generates **5 filtered combinations** per game — each built on a different strategy, all passing structural probability filters.

It does NOT predict the lottery. Nothing can. But it gives you numbers that are statistically better-structured than random picks, and it saves you from manually checking past results.

## Features

- **Real-time data** — fetches latest draws from official APIs (cwl.gov.cn for SSQ, sporttery.cn for DLT)
- **500+ issues analyzed** — hot numbers, overdue numbers, high-co-occurrence pairs, cold numbers
- **5 strategies per game** — pure hot, hot+overdue+cold mix, pair-driven, zone balance, pair-chain
- **Structural filters** — sum range, odd/even ratio, consecutive numbers, zone coverage (all based on historical probability)
- **Recent 3 draws displayed** — no need to check the official website separately
- **Next draw date** — calculated automatically based on draw schedule
- **Export panel** — show clean number list for printing at lottery shops (no analysis logic exposed)
- **Web UI** — silver + gold theme, mobile-friendly, works on iPhone/Android
- **Docker ready** — one command to deploy anywhere

## Games supported

| Game | Format | Draw days |
|------|--------|-----------|
| 双色球 (SSQ) | Red 33→6 + Blue 16→1 | Tue / Thu / Sun |
| 超级大乐透 (DLT) | Front 35→5 + Back 12→2 | Mon / Wed / Sat |

## Quick start

### Run locally

```bash
git clone https://github.com/AttilaLao/lottery-skill.git
cd lottery-skill
pip install flask waitress PyPDF2
python3 app/server.py
```

Open `http://localhost:9090` in your browser.

### Run with Docker

```bash
git clone https://github.com/AttilaLao/lottery-skill.git
cd lottery-skill
docker build -t lottery-app .
docker run -d --name lottery-app --restart unless-stopped -p 9090:9090 lottery-app
```

### Deploy to your server

1. Copy the project to your server
2. Build and run the Docker container (see above)
3. Set up a reverse proxy (nginx, Caddy, etc.) pointing to port 9090
4. Configure your own domain and SSL

## How it works

```
Official API → Fetch 500+ draws → Statistical signals → 5 strategies → Structural filters → Combinations
```

### Statistical signals

- **Hot numbers**: highest frequency in recent 100 draws
- **Overdue numbers**: longest gap since last appearance
- **High-co-occurrence pairs**: pairs appearing >1.3x expected frequency
- **Cold numbers**: lowest frequency across all draws

### Structural filters (based on historical probability)

**SSQ:**
- Red sum 80-120 (theoretical mean 102)
- Odd/even ratio 3:3, 4:2, or 2:4 (~83% combined)
- Consecutive numbers (~66% of draws)
- Three-zone coverage (1-11 / 12-22 / 23-33)

**DLT:**
- Front odd/even ratio 3:2 or 2:3 (~65% combined)
- Consecutive numbers (~48% of draws)
- 3+ zone coverage

## Project structure

```
lottery-skill/
├── SKILL.md              # Codex Skill instructions
├── README.md             # This file
├── LICENSE               # MIT
├── Dockerfile            # Docker build
├── .gitignore
├── agents/
│   └── openai.yaml       # Skill metadata
├── scripts/
│   ├── fresh_pick_v2.py          # Core: fetch data + generate combos
│   ├── deep_correlation_test.py  # Pair analysis helpers
│   ├── fetch_official_history.py # Bulk history fetcher
│   └── stats_analysis.py         # Statistical analysis
├── app/
│   ├── server.py                 # Flask web server
│   └── templates/
│       └── index.html            # Web UI (silver + gold theme)
└── data/                         # Empty, auto-populated at runtime
```

## As a Codex Skill

This project is also a [Codex](https://codex.ai) Skill. Copy it into your skills directory:

```bash
cp -r lottery-skill ~/.codex/skills/
```

Then in any Codex conversation, say "选号" or "生成选号方案" to trigger it.

## Disclaimer

Lottery is a random event with negative expected value. This tool generates statistically structured combinations based on historical data — it does NOT predict lottery numbers, does NOT guarantee winning, and does NOT constitute betting advice. Please gamble responsibly.

## License

MIT — see [LICENSE](LICENSE)
