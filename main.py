"""
WxpnSongTracker — daily runner.

Usage:
  python main.py                       # Scrape yesterday + today, update playlists
  python main.py --date 2026-11-01     # Scrape one specific date
  python main.py --backfill 2026-01-01 # Backfill from a past date to today
  python main.py --playlists-only      # Rebuild playlists without scraping
  python main.py --no-spotify          # Skip Spotify sync
"""

import argparse
import os
from datetime import date, timedelta

from show_schedule import fetch_schedule
from scraper import scrape_date, scrape_range
from playlist_manager import build_monthly_playlists, build_show_yearly_playlists
from db import upsert_shows, upsert_show_schedules


def setup_shows(schedule: list[dict]) -> dict[str, int]:
    print("Syncing show list...")
    show_id_map = upsert_shows(schedule)
    upsert_show_schedules(schedule, show_id_map)
    print(f"  {len(show_id_map)} shows in database")
    return show_id_map


def run_daily(schedule: list[dict], show_id_map: dict):
    today = date.today()
    yesterday = today - timedelta(days=1)
    for d in [yesterday, today]:
        print(f"Scraping {d}...")
        try:
            n = scrape_date(d, show_id_map, schedule)
            print(f"  {n} plays inserted")
        except Exception as exc:
            print(f"  ERROR: {exc}")


def run_playlists(spotify_client=None):
    print("Building monthly playlists...")
    build_monthly_playlists(spotify_client=spotify_client)
    print("Building show yearly playlists...")
    build_show_yearly_playlists(spotify_client=spotify_client)


def _get_spotify_client():
    if not os.environ.get("SPOTIFY_CLIENT_ID"):
        return None
    if not os.environ.get("SPOTIFY_REFRESH_TOKEN"):
        print("  Spotify: SPOTIFY_REFRESH_TOKEN not set — run spotify_auth.py first")
        return None
    from spotify import SpotifyClient
    return SpotifyClient()


def main():
    parser = argparse.ArgumentParser(description="WxpnSongTracker")
    parser.add_argument("--date", help="Scrape a single date (YYYY-MM-DD)")
    parser.add_argument("--backfill", help="Backfill from this date to today (YYYY-MM-DD)")
    parser.add_argument("--playlists-only", action="store_true", help="Only rebuild playlists")
    parser.add_argument("--skip-playlists", action="store_true", help="Skip playlist rebuild")
    parser.add_argument("--no-spotify", action="store_true", help="Skip Spotify sync")
    args = parser.parse_args()

    print("Fetching WXPN show schedule...")
    schedule = fetch_schedule()
    print(f"  {len(schedule)} schedule slots loaded")

    show_id_map = setup_shows(schedule)

    if not args.playlists_only:
        if args.date:
            target = date.fromisoformat(args.date)
            print(f"Scraping {target}...")
            n = scrape_date(target, show_id_map, schedule)
            print(f"  {n} plays inserted")
        elif args.backfill:
            start = date.fromisoformat(args.backfill)
            end = date.today()
            print(f"Backfilling {start} to {end}...")
            scrape_range(start, end, show_id_map, schedule)
        else:
            run_daily(schedule, show_id_map)

    if not args.skip_playlists:
        spotify = None if args.no_spotify else _get_spotify_client()
        if spotify:
            print("Spotify client ready.")
        run_playlists(spotify_client=spotify)

    print("Done.")


if __name__ == "__main__":
    main()
