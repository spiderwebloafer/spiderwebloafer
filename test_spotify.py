"""
Quick Spotify integration test — searches 3 songs and creates a test playlist.
Run this to verify credentials and permissions are working.

  python test_spotify.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

from spotify import SpotifyClient

def run():
    print("Initializing Spotify client...")
    client = SpotifyClient()

    print("Getting user ID...")
    user_id = client.get_user_id()
    print(f"  Logged in as: {user_id}")

    test_songs = [
        {"artist": "The Killers", "song": "Mr. Brightside"},
        {"artist": "Fleetwood Mac", "song": "Dreams"},
        {"artist": "Robert Cray", "song": "Strong Persuader"},
    ]

    print("Searching 3 test tracks...")
    uris = client.search_tracks_bulk(test_songs)
    print(f"  Found {len(uris)}/{len(test_songs)} tracks")
    for uri in uris:
        print(f"    {uri}")

    if uris:
        print("Creating test playlist...")
        playlist_id, _ = client.sync_playlist("WxpnSongTracker Test", test_songs, None)
        print(f"  Playlist created: https://open.spotify.com/playlist/{playlist_id}")
        print("  Check Spotify — delete this playlist after verifying.")
    else:
        print("  No tracks found — Spotify search may still be rate limited.")

    print("Done.")

if __name__ == "__main__":
    run()
