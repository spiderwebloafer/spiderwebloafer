"""
One-time Spotify OAuth setup. Run this once to get your refresh token.

  op run --env-file=.env.op -- python spotify_auth.py

Steps:
  1. It opens your browser to Spotify's login page.
  2. Log in and click Agree.
  3. The script catches the callback automatically and prints your refresh token.
  4. Store the refresh token in 1Password as 'spotify_refresh_token'.

Before running, make sure your Spotify app has this redirect URI added:
  http://127.0.0.1:8888/callback
"""

import os
import base64
import urllib.parse
import webbrowser
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from dotenv import load_dotenv

load_dotenv()

REDIRECT_URI = "http://127.0.0.1:8888/callback"
SCOPES = "playlist-modify-public playlist-modify-private playlist-read-private"

_auth_code = None


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Authorization complete! You can close this tab.</h2>")
        elif "error" in params:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            msg = params["error"][0].encode()
            self.wfile.write(b"<h2>Authorization failed: " + msg + b"</h2>")
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass  # silence server logs


def run():
    client_id = os.environ["SPOTIFY_CLIENT_ID"]
    client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]

    auth_url = (
        "https://accounts.spotify.com/authorize?"
        + urllib.parse.urlencode({
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPES,
        })
    )

    print("Make sure your Spotify app has this redirect URI registered:")
    print(f"  {REDIRECT_URI}\n")
    print("Opening Spotify authorization in your browser...")
    print("(If it doesn't open, copy and paste this URL manually:)")
    print(f"\n  {auth_url}\n")
    webbrowser.open(auth_url)

    print("Waiting for Spotify to redirect back...")
    server = HTTPServer(("127.0.0.1", 8888), _CallbackHandler)
    server.handle_request()

    if not _auth_code:
        print("ERROR: No authorization code received.")
        return

    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = requests.post(
        "https://accounts.spotify.com/api/token",
        data={
            "grant_type": "authorization_code",
            "code": _auth_code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={"Authorization": f"Basic {creds}"},
        timeout=15,
    )
    resp.raise_for_status()
    tokens = resp.json()

    print("\nSuccess! Add this to 1Password as 'spotify_refresh_token':")
    print(f"\n  {tokens['refresh_token']}\n")
    print(f"Scopes granted: {tokens.get('scope', 'unknown')}")


if __name__ == "__main__":
    run()
