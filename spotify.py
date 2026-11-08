"""
Spotify API client — creates and updates playlists for WxpnSongTracker.

Handles:
  - Token refresh (access tokens expire after 1 hour)
  - Track search by artist + song name
  - Playlist create / update
  - Chunked track replacement (Spotify's 100-URI limit per request)
"""

import os
import time
import base64
import requests
from dotenv import load_dotenv

load_dotenv()

SPOTIFY_API = "https://api.spotify.com/v1"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"


class SpotifyClient:
    def __init__(self):
        self.client_id = os.environ["SPOTIFY_CLIENT_ID"]
        self.client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
        self.refresh_token = os.environ["SPOTIFY_REFRESH_TOKEN"]
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _ensure_token(self):
        if self._access_token and time.time() < self._token_expires_at - 60:
            return
        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        resp = requests.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            headers={"Authorization": f"Basic {creds}"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data["expires_in"]

    def _headers(self) -> dict:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._access_token}"}

    def _get(self, path: str, **params) -> dict:
        resp = requests.get(f"{SPOTIFY_API}/{path}", headers=self._headers(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, json: dict) -> dict:
        resp = requests.post(f"{SPOTIFY_API}/{path}", headers=self._headers(), json=json, timeout=15)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, json: dict):
        resp = requests.put(f"{SPOTIFY_API}/{path}", headers=self._headers(), json=json, timeout=15)
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    def get_user_id(self) -> str:
        return self._get("me")["id"]

    # ------------------------------------------------------------------
    # Track search
    # ------------------------------------------------------------------

    def search_track(self, artist: str, song: str) -> str | None:
        """Return the Spotify URI for the best-matching track, or None."""
        query = f"track:{song} artist:{artist}"
        data = self._get("search", q=query, type="track", limit=1)
        items = data.get("tracks", {}).get("items", [])
        if items:
            return items[0]["uri"]
        # Fallback: looser search
        data = self._get("search", q=f"{artist} {song}", type="track", limit=1)
        items = data.get("tracks", {}).get("items", [])
        return items[0]["uri"] if items else None

    def search_tracks_bulk(self, songs: list[dict]) -> list[str]:
        """Search Spotify for each song. Returns list of URIs (None-filtered).

        Results are cached in Supabase so each (artist, song) is only searched once.
        """
        from db import get_cached_uris, save_cached_uris

        cached = get_cached_uris(songs)
        to_search = [s for s in songs if (s["artist"], s["song"]) not in cached]

        if to_search:
            print(f"    searching {len(to_search)} new tracks ({len(cached)} cached)...")

        new_cache: dict[tuple, str | None] = {}
        for i, s in enumerate(to_search):
            key = (s["artist"], s["song"])
            uri = None
            for attempt in range(4):
                try:
                    uri = self.search_track(s["artist"], s["song"])
                    break
                except requests.HTTPError as e:
                    if e.response.status_code == 429:
                        retry_after = int(e.response.headers.get("Retry-After", 5))
                        print(f"    rate limited, waiting {retry_after}s...")
                        time.sleep(retry_after + 1)
                    else:
                        raise
            new_cache[key] = uri
            time.sleep(0.2)
            if (i + 1) % 50 == 0:
                print(f"    {i + 1}/{len(to_search)} searched...")

        if new_cache:
            save_cached_uris(new_cache)

        all_cache = {**cached, **new_cache}
        return [all_cache[s["artist"], s["song"]] for s in songs if all_cache.get((s["artist"], s["song"]))]

    # ------------------------------------------------------------------
    # Playlists
    # ------------------------------------------------------------------

    def get_or_create_playlist(self, user_id: str, name: str, existing_id: str | None) -> str:
        """Return playlist_id — reuses existing_id if given and still exists."""
        if existing_id:
            try:
                self._get(f"playlists/{existing_id}", fields="id")
                return existing_id
            except requests.HTTPError:
                pass  # playlist was deleted, create a new one

        data = self._post(
            "me/playlists",
            {"name": name, "public": True, "description": "Auto-generated by WxpnSongTracker"},
        )
        return data["id"]

    def replace_playlist_tracks(self, playlist_id: str, uris: list[str]):
        """Replace all tracks in a playlist (handles Spotify's 100-URI limit)."""
        if not uris:
            self._put(f"playlists/{playlist_id}/tracks", {"uris": []})
            return

        # First chunk replaces, subsequent chunks append
        chunks = [uris[i:i + 100] for i in range(0, len(uris), 100)]
        self._put(f"playlists/{playlist_id}/tracks", {"uris": chunks[0]})
        for chunk in chunks[1:]:
            self._post(f"playlists/{playlist_id}/tracks", {"uris": chunk})

    # ------------------------------------------------------------------
    # High-level sync
    # ------------------------------------------------------------------

    def sync_playlist(
        self,
        name: str,
        songs: list[dict],
        existing_spotify_id: str | None,
    ) -> tuple[str, list[str]]:
        """
        Create or update a Spotify playlist with the given songs.
        Returns (spotify_playlist_id, list_of_uris).
        """
        user_id = self.get_user_id()
        playlist_id = self.get_or_create_playlist(user_id, name, existing_spotify_id)
        uris = self.search_tracks_bulk(songs)
        self.replace_playlist_tracks(playlist_id, uris)
        return playlist_id, uris
