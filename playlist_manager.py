"""
Builds and updates two kinds of playlists from the plays table:

  monthly     — one per calendar month, unique songs played that month
  show_yearly — one per show per year, unique songs played on that show that year
"""

from db import get_client, upsert_playlist, sync_playlist_songs


def build_monthly_playlists(year: int | None = None, month: int | None = None):
    """
    Regenerate monthly playlists. If year/month are given, only that month.
    Otherwise regenerates all months that have plays.
    """
    db = get_client()

    if year and month:
        months = [(year, month)]
    else:
        rows = (
            db.table("plays")
            .select("played_at")
            .execute()
            .data
        )
        seen = set()
        for r in rows:
            dt = r["played_at"][:7]  # "YYYY-MM"
            seen.add(dt)
        months = [(int(s[:4]), int(s[5:])) for s in sorted(seen)]

    for y, m in months:
        songs = _unique_songs_for_month(db, y, m)
        playlist_id = upsert_playlist("monthly", y, m, None)
        sync_playlist_songs(playlist_id, songs)
        print(f"  Monthly playlist: {_month_label(y, m)} — {len(songs)} unique songs")


def build_show_yearly_playlists(year: int | None = None):
    """
    Regenerate yearly-per-show playlists for all shows that have plays.
    If year is given, only that year.
    """
    db = get_client()

    # Find all (show_id, year) combos that have plays
    rows = (
        db.table("plays")
        .select("show_id, played_at")
        .not_.is_("show_id", "null")
        .execute()
        .data
    )
    pairs = set()
    for r in rows:
        y = int(r["played_at"][:4])
        if year and y != year:
            continue
        pairs.add((r["show_id"], y))

    for show_id, y in sorted(pairs):
        songs = _unique_songs_for_show_year(db, show_id, y)
        playlist_id = upsert_playlist("show_yearly", y, None, show_id)
        sync_playlist_songs(playlist_id, songs)
        # Get show name for log
        show_rows = db.table("shows").select("name").eq("id", show_id).execute().data
        show_name = show_rows[0]["name"] if show_rows else f"show {show_id}"
        print(f"  Show playlist: {show_name} {y} — {len(songs)} unique songs")


def _unique_songs_for_month(db, year: int, month: int) -> list[dict]:
    start = f"{year:04d}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1:04d}-01-01"
    else:
        end = f"{year:04d}-{month + 1:02d}-01"

    rows = (
        db.table("plays")
        .select("artist, song, album, played_at")
        .gte("played_at", start)
        .lt("played_at", end)
        .order("played_at")
        .execute()
        .data
    )
    return _deduplicate(rows)


def _unique_songs_for_show_year(db, show_id: int, year: int) -> list[dict]:
    start = f"{year:04d}-01-01"
    end = f"{year + 1:04d}-01-01"
    rows = (
        db.table("plays")
        .select("artist, song, album, played_at")
        .eq("show_id", show_id)
        .gte("played_at", start)
        .lt("played_at", end)
        .order("played_at")
        .execute()
        .data
    )
    return _deduplicate(rows)


def _deduplicate(rows: list[dict]) -> list[dict]:
    """Return first occurrence of each (artist, song) pair, ordered by first play."""
    seen = set()
    result = []
    for r in rows:
        key = (r["artist"].lower(), r["song"].lower())
        if key not in seen:
            seen.add(key)
            result.append({
                "artist": r["artist"],
                "song": r["song"],
                "album": r.get("album"),
                "first_played_at": r["played_at"],
            })
    return result


def _month_label(year: int, month: int) -> str:
    import calendar
    return f"{calendar.month_name[month]} {year}"
