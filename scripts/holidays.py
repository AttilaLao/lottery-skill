"""中国假期数据，用于跳过停开奖日。

自动从 GitHub NateScarlet/holiday-cn 拉取当年假期数据。
该项目每年根据国务院发布的放假通知自动更新。
失败时回退到内置列表。
"""

import json
import subprocess
from datetime import datetime

# 内置回退数据（API 不可用时使用）
FALLBACK_HOLIDAYS = {
    "2026-01-01", "2026-01-02", "2026-01-03",
    "2026-02-15", "2026-02-16", "2026-02-17", "2026-02-18",
    "2026-02-19", "2026-02-20", "2026-02-21",
    "2026-04-04", "2026-04-05", "2026-04-06",
    "2026-05-01", "2026-05-02", "2026-05-03",
    "2026-06-19", "2026-06-20", "2026-06-21",
    "2026-09-15", "2026-09-16", "2026-09-17",
    "2026-10-01", "2026-10-02", "2026-10-03",
    "2026-10-04", "2026-10-05", "2026-10-06", "2026-10-07",
}

_cache = None
_cache_year = None

def _fetch_holidays_from_github(year):
    """从 NateScarlet/holiday-cn 拉取指定年份的假期。"""
    url = f"https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
    try:
        raw = subprocess.check_output(
            ["curl", "-L", "--max-time", "15", "-sS", url],
            stderr=subprocess.DEVNULL
        )
        data = json.loads(raw)
        holidays = set()
        for day in data.get("days", []):
            if day.get("isOffDay"):
                holidays.add(day["date"])
        return holidays if holidays else None
    except Exception:
        return None

def _get_holidays():
    global _cache, _cache_year
    year = datetime.now().year
    
    if _cache is not None and _cache_year == year:
        return _cache
    
    fetched = _fetch_holidays_from_github(year)
    if fetched is not None and len(fetched) > 0:
        _cache = fetched
    else:
        _cache = FALLBACK_HOLIDAYS
    _cache_year = year
    
    return _cache

def is_holiday(date_str):
    return date_str in _get_holidays()
