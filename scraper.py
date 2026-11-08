"""
Fetches the WXPN daily playlist JSON and saves each play to Supabase.
"""

import requests
from datetime import datetime, timezone, date, timedelta

DAILY_JSON_URL = "https://origin.xpn.org/utils/playlist/json/{date}.json"


def fetch_plays_for_date(target_date: date) -> list[dict]:
    """Fetch raw play records from the WXPN JSON API for a given date."""
    url = DAILY_JSON_URL.format(date=target_date.isoformat())
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    raw = resp.json()
    if not isinstance(raw, list):
        raw = raw.get("xpn") or raw.get("tracks") or raw.get("data") or []
    return raw


def normalize_plays(raw: list[dict], show_id_map: dict, schedule: list[dict]) -> list[dict]:
    """
    Convert raw API records to play dicts ready for Supabase.
    show_id_map: {slug: id}
    schedule: list of slots from show_schedule.fetch_schedule()
    """
    from show_schedule import find_show

    plays = []
    for item in raw:
        artist = (item.get("artist") or item.get("Artist") or "").strip()
        song = (item.get("song") or item.get("Song") or item.get("title") or "").strip()
        album = (item.get("album") or item.get("Album") or "").strip() or None
        raw_date = (
            item.get("timeslice") or item.get("air_date") or
            item.get("datetime") or item.get("played_at") or ""
        ).strip()
        image_url = (item.get("image") or item.get("img") or "").strip() or None

        if not artist or not song or not raw_date:
            continue

        try:
            played_at = datetime.fromisoformat(raw_date)
            if played_at.tzinfo is None:
                played_at = played_at.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        slot = find_show(played_at, schedule)
        show_id = show_id_map.get(slot["slug"]) if slot else None

        plays.append({
            "artist": artist,
            "song": song,
            "album": album,
            "played_at": played_at.isoformat(),
            "show_id": show_id,
            "image_url": image_url,
        })
    return plays


def scrape_date(target_date: date, show_id_map: dict, schedule: list[dict]) -> int:
    """Scrape one date and insert into DB. Returns number of plays inserted."""
    from db import insert_plays, upsert_scrape_log

    raw = fetch_plays_for_date(target_date)
    plays = normalize_plays(raw, show_id_map, schedule)
    inserted = insert_plays(plays)
    upsert_scrape_log(target_date.isoformat(), len(plays))
    return inserted


def scrape_range(start: date, end: date, show_id_map: dict, schedule: list[dict]):
    """Scrape every date in [start, end] inclusive."""
    current = start
    while current <= end:
        try:
            n = scrape_date(current, show_id_map, schedule)
            print(f"  {current}: {n} plays inserted")
        except Exception as exc:
            print(f"  {current}: ERROR — {exc}")
        current += timedelta(days=1)
