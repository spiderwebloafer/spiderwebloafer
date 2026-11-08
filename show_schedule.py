"""
Fetches the WXPN show schedule from the XPN WordPress API and maps
any datetime to the show that was airing at that time.
"""

import requests
from datetime import datetime, time


WXPN_PROGRAMS_API = "https://xpn.org/wp-json/wp/v2/program"

DAY_MAP = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
    "Saturday": 5,
    "Sunday": 6,
}


def fetch_schedule() -> list[dict]:
    """Return a flat list of {name, slug, day_int, start, end} dicts."""
    slots = []
    page = 1
    while True:
        resp = requests.get(
            WXPN_PROGRAMS_API,
            params={"per_page": 100, "page": page, "_fields": "id,slug,title,acf"},
            timeout=15,
        )
        resp.raise_for_status()
        programs = resp.json()
        if not programs:
            break
        for prog in programs:
            name = prog["title"]["rendered"]
            slug = prog["slug"]
            for slot in prog.get("acf", {}).get("schedule") or []:
                start = _parse_time(slot.get("start", ""))
                end = _parse_time(slot.get("end", ""))
                if start is None or end is None:
                    continue
                for day_name in slot.get("day_of_the_week") or []:
                    day_int = DAY_MAP.get(day_name)
                    if day_int is None:
                        continue
                    slots.append({
                        "name": name,
                        "slug": slug,
                        "day_int": day_int,
                        "start": start,
                        "end": end,
                    })
        page += 1
        if len(programs) < 100:
            break
    return slots


def _parse_time(value: str) -> time | None:
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


def find_show(played_at: datetime, schedule: list[dict]) -> dict | None:
    """Return the schedule slot whose window contains played_at, or None."""
    day_int = played_at.weekday()
    t = played_at.time()
    for slot in schedule:
        if slot["day_int"] != day_int:
            continue
        start, end = slot["start"], slot["end"]
        # Handle overnight shows where end < start (e.g. 23:00 -> 01:00)
        if end <= start:
            if t >= start or t < end:
                return slot
        else:
            if start <= t < end:
                return slot
    return None
