"""
Database helpers — thin wrapper around the Supabase client.
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


# ---------------------------------------------------------------------------
# Shows
# ---------------------------------------------------------------------------

def upsert_shows(schedule_slots: list[dict]) -> dict[str, int]:
    """Insert shows (by slug) if they don't exist. Returns {slug: id}."""
    db = get_client()
    seen = {}
    for slot in schedule_slots:
        slug = slot["slug"]
        if slug in seen:
            continue
        seen[slug] = slot["name"]

    result = (
        db.table("shows")
        .upsert(
            [{"name": name, "slug": slug} for slug, name in seen.items()],
            on_conflict="slug",
        )
        .execute()
    )
    rows = db.table("shows").select("id,slug").execute().data
    return {r["slug"]: r["id"] for r in rows}


def upsert_show_schedules(schedule_slots: list[dict], show_id_map: dict[str, int]):
    """Replace all schedule rows for shows we know about."""
    db = get_client()
    rows = []
    for slot in schedule_slots:
        show_id = show_id_map.get(slot["slug"])
        if show_id is None:
            continue
        rows.append({
            "show_id": show_id,
            "day_of_week": list(DAY_INT_TO_NAME.values())[slot["day_int"]],
            "start_time": str(slot["start"]),
            "end_time": str(slot["end"]),
        })
    if rows:
        # Delete existing and re-insert so schedule changes are picked up
        show_ids = list({r["show_id"] for r in rows})
        db.table("show_schedules").delete().in_("show_id", show_ids).execute()
        db.table("show_schedules").insert(rows).execute()


DAY_INT_TO_NAME = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
}


# ---------------------------------------------------------------------------
# Plays
# ---------------------------------------------------------------------------

def insert_plays(plays: list[dict]) -> int:
    """Insert play rows, skipping duplicates. Returns count inserted."""
    if not plays:
        return 0
    db = get_client()
    result = (
        db.table("plays")
        .upsert(plays, on_conflict="artist,song,played_at", ignore_duplicates=True)
        .execute()
    )
    return len(result.data) if result.data else 0


def get_scrape_log(date_str: str) -> dict | None:
    db = get_client()
    rows = db.table("scrape_log").select("*").eq("scrape_date", date_str).execute().data
    return rows[0] if rows else None


def upsert_scrape_log(date_str: str, plays_fetched: int):
    db = get_client()
    db.table("scrape_log").upsert(
        {"scrape_date": date_str, "plays_fetched": plays_fetched},
        on_conflict="scrape_date",
    ).execute()


# ---------------------------------------------------------------------------
# Playlists
# ---------------------------------------------------------------------------

def upsert_playlist(type_: str, year: int, month: int | None, show_id: int | None) -> int:
    """Create or fetch a playlist row. Returns its id."""
    db = get_client()
    name = _playlist_name(type_, year, month, show_id, db)
    row = {"type": type_, "year": year, "month": month, "show_id": show_id, "name": name}
    result = (
        db.table("playlists")
        .upsert(row, on_conflict="type,year,month,show_id")
        .execute()
    )
    # Fetch back the id
    q = db.table("playlists").select("id").eq("type", type_).eq("year", year)
    if month is not None:
        q = q.eq("month", month)
    else:
        q = q.is_("month", "null")
    if show_id is not None:
        q = q.eq("show_id", show_id)
    else:
        q = q.is_("show_id", "null")
    rows = q.execute().data
    return rows[0]["id"]


def _playlist_name(type_, year, month, show_id, db) -> str:
    import calendar
    if type_ == "monthly":
        return f"{calendar.month_name[month]} {year}"
    # show_yearly
    rows = db.table("shows").select("name").eq("id", show_id).execute().data
    show_name = rows[0]["name"] if rows else "Unknown Show"
    return f"{show_name} — {year}"


def sync_playlist_songs(playlist_id: int, songs: list[dict]):
    """Replace playlist contents with the given deduplicated song list."""
    db = get_client()
    db.table("playlist_songs").delete().eq("playlist_id", playlist_id).execute()
    if songs:
        rows = [
            {
                "playlist_id": playlist_id,
                "artist": s["artist"],
                "song": s["song"],
                "album": s.get("album"),
                "first_played_at": s["first_played_at"],
            }
            for s in songs
        ]
        db.table("playlist_songs").insert(rows).execute()
