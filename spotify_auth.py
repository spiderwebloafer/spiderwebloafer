"""
One-time Spotify OAuth setup. Run this once to get your refresh token.

  op run --env-file=.env.op -- python spotify_auth.py

Steps:
  1. It prints an authorization URL and opens it in your browser.
  2. Log in to Spotify and click Agree.
  3. Your browser will try to load http://localhost and show an error — that's fine.
  4. Copy the full URL from your browser's address bar and paste it here.
  5. It prints your SPOTIFY_REFRESH_TOKEN to store in 1Password.

Set in 1Password before running:
  SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
  SPOTIFY_REDIRECT_URI = http://localhost
"""

import os
import urllib.parse
import webbrowser
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"


def run():
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    redirect_uri = os.environ.get(
      "SPOTIFY_REDIRECT_URI",
      "https://oxmqxibmwsskhyxolnwc.supabase.co/functions/v1/spotify-callback",
  )

    auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
        })
    )

    print("Opening Spotify authorization in your browser...")
    print("(If it doesn't open, copy and paste this URL manually:)")
    print(f"\n  {auth_url}\n")
    webbrowser.open(auth_url)

    supabase_edge = "supabase.co/functions"
    if supabase_edge in redirect_uri:
        print("After you approve, Spotify will redirect to the Supabase edge function.")
        print("That page will display your refresh token — copy it from there.\n")
        print("Once you have it, add it to 1Password as 'spotify_refresh_token'.")
        print("Then update .env.op and you're done.\n")
        input("Press Enter once you've copied the token from the browser...")
        return

    print("After you approve, your browser will fail to load a page.")
    print("That's expected. Copy the FULL URL from your address bar and paste it below.\n")
    redirected_url = input("Paste the full redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(redirected_url)
    params = urllib.parse.parse_qs(parsed.query)

    if "error" in params:
        print(f"ERROR: Spotify returned: {params['error']}")
        return
    if "code" not in params:
        print("ERROR: No authorization code found in URL. Make sure you copied the full URL.")
        return

    code = params["code"][0]

    # Exchange code for tokens
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Authorization": f"Basic {creds}"},
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\nSuccess! Add this to 1Password as 'spotify_refresh_token':")
    print(f"\n  {tokens['refresh_token']}\n")


if __name__ == "__main__":
    run()
