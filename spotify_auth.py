"""
One-time Spotify OAuth setup. Run this once to get your refresh token.

  python spotify_auth.py

It will open a browser, ask you to log in to Spotify and authorize the app,
then print the refresh token to paste into your .env file.

Requirements in .env before running:
  SPOTIFY_CLIENT_ID=...
  SPOTIFY_CLIENT_SECRET=...
  SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
"""

import os
import urllib.parse
import http.server
import webbrowser
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"


def run():
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

    auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
        })
    )

    # Capture the code via a temporary local HTTP server
    code_holder = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            if "code" in params:
                code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"<h1>Authorization complete! You can close this tab.</h1>")
            else:
                self.send_response(400)
                self.end_headers()

        def log_message(self, *args):
            pass  # silence server logs

    port = int(urllib.parse.urlparse(redirect_uri).port or 8888)
    server = http.server.HTTPServer(("localhost", port), Handler)

    print(f"Opening browser for Spotify authorization...")
    webbrowser.open(auth_url)
    server.handle_request()

    code = code_holder.get("code")
    if not code:
        print("ERROR: No auth code received.")
        return

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

    print("\nAdd this to your .env file:")
    print(f"SPOTIFY_REFRESH_TOKEN={tokens['refresh_token']}")


if __name__ == "__main__":
    run()
