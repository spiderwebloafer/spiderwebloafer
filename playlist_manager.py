"""
Builds and updates two kinds of playlists from the plays table:

  monthly     — one per calendar month, unique songs played that month
  show_yearly — one per show per year, unique songs played on that show that year

Pass spotify_client=SpotifyClient() to also create/update the playlists on Spotify.
"""

from db import get_client, upsert_playlist, sync_playlist_songs, save_spotify_playlist_id, get_spotify_playlist_id


def build_monthly_playlists(year: int | None = None, month: int | None = None, spotify_client=None):
    """
    Regenerate monthly playlists. If year/month are given, only that month.
    Otherwise regenerates all months that have plays.
    """
    db = get_client()

    if year and month:
        months = [(year, month)]
    else:
        rows = db.table("plays").select("played_at").execute().data
        seen = set()
        for r in rows:
            dt = r["played_at"][:7]  # "YYYY-MM"
            seen.add(dt)
        months = [(int(s[:4]), int(s[5:])) for s in sorted(seen)]

    for y, m in months:
        songs = _unique_songs_for_month(db, y, m)
        playlist_id = upsert_playlist("monthly", y, m, None)
        name = _month_label(y, m)

        if spotify_client:
            existing_spotify_id = get_spotify_playlist_id(playlist_id)
            spotify_id, uris = spotify_client.sync_playlist(name, songs, existing_spotify_id)
            save_spotify_playlist_id(playlist_id, spotify_id)
            # Annotate songs with their resolved URIs
            for song, uri in zip(songs, _pad_uris(uris, songs)):
                song["spotify_track_uri"] = uri
            print(f"  Monthly: {name} — {len(songs)} songs, {len(uris)} on Spotify → {spotify_id}")
        else:
            print(f"  Monthly: {name} — {len(songs)} unique songs")

        sync_playlist_songs(playlist_id, songs)


def build_show_yearly_playlists(year: int | None = None, spotify_client=None):
    """
    Regenerate yearly-per-show playlists for all shows that have plays.
    If year is given, only that year.
    """
    db = get_client()

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
        show_rows = db.table("shows").select("name").eq("id", show_id).execute().data
        show_name = show_rows[0]["name"] if show_rows else f"show {show_id}"
        name = f"{show_name} — {y}"

        if spotify_client:
            existing_spotify_id = get_spotify_playlist_id(playlist_id)
            spotify_id, uris = spotify_client.sync_playlist(name, songs, existing_spotify_id)
            save_spotify_playlist_id(playlist_id, spotify_id)
            for song, uri in zip(songs, _pad_uris(uris, songs)):
                song["spotify_track_uri"] = uri
            print(f"  Show: {name} — {len(songs)} songs, {len(uris)} on Spotify → {spotify_id}")
        else:
            print(f"  Show: {name} — {len(songs)} unique songs")

        sync_playlist_songs(playlist_id, songs)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _unique_songs_for_month(db, year: int, month: int) -> list[dict]:
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"
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
    return f"WXPN — {calendar.month_name[month]} {year}"


def _pad_uris(uris: list[str], songs: list[dict]) -> list[str | None]:
    """
    search_tracks_bulk returns only found URIs (None-filtered).
    Re-align them to the song list so we can store per-song URIs.
    Since we can't know which songs were skipped, we just return
    the uri list padded with Nones to match len(songs).
    """
    padded = list(uris) + [None] * (len(songs) - len(uris))
    return padded[:len(songs)]
