"""
Amp - a lightweight Spotify Connect remote control for a kiosk tablet.

This process never plays audio itself. It's a thin, same-origin proxy in
front of the Spotify Web API: it holds the OAuth tokens, and index.html
talks to *this* server instead of talking to Spotify directly. Playback
always happens on one of your existing Spotify Connect devices (a computer,
phone, speaker, etc) - this dashboard just tells that device what to do,
which is why it stays light enough to run comfortably on old tablet hardware.

Dependencies: Flask only (see requirements.txt). Everything else is stdlib,
so there's nothing else to install.

Setup: see README.md.
"""

import base64
import hashlib
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from flask import Flask, jsonify, redirect, request, send_from_directory

app = Flask(__name__)
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# Configuration - every value can be overridden with an environment variable
# of the same name. The defaults match the Spotify app already registered
# for this project, so an existing token.json (and Spotify's consent grant)
# keeps working without you having to re-register anything or click through
# the "Agree" screen again.
# ---------------------------------------------------------------------------
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "937d5bd53d3b4ee3bb04465511cf7344")
REDIRECT_URI = os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8080/callback")
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

# Keep this identical to what the app was originally granted - adding a new
# scope here invalidates any saved token.json and forces a fresh login.
SCOPES = (
    "user-read-currently-playing "
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-library-modify "
    "user-library-read"
)

TOKEN_FILE = os.environ.get(
    "SPOTIFY_TOKEN_FILE", os.path.expanduser("~/spotify-dashboard/token.json")
)
REQUEST_TIMEOUT = 10  # seconds - don't let a flaky network hang the dev server

# In-memory only, valid for the few seconds of a single login round trip.
AUTH_STATE = None
CODE_VERIFIER = None


# ---------------------------------------------------------------------------
# Token storage - one JSON file, mode 600. One user, one tablet, no database.
# ---------------------------------------------------------------------------
def save_tokens(data):
    data = dict(data)
    data["saved_at"] = int(time.time())
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)


def load_tokens():
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def clear_tokens():
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass


# ---------------------------------------------------------------------------
# Auth - Authorization Code with PKCE. No client secret ever exists, so
# there's nothing sensitive to leak from this file besides the token store.
# ---------------------------------------------------------------------------
def pkce_verifier():
    return secrets.token_urlsafe(64)


def pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def refresh_access_token(refresh_token):
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as e:
        message = e.read().decode(errors="replace")
        raise RuntimeError(f"Spotify token refresh failed ({e.code}): {message}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach Spotify: {e.reason}")

    result["refresh_token"] = result.get("refresh_token", refresh_token)
    save_tokens(result)
    return result["access_token"]


def auth_required():
    """Return a valid access token or raise RuntimeError with a message
    that's safe to show directly to the user."""
    tokens = load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Not authenticated")

    expires_at = tokens.get("saved_at", 0) + tokens.get("expires_in", 3600)
    if time.time() < expires_at - 60:
        return tokens["access_token"]

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Not authenticated")
    return refresh_access_token(refresh_token)


# ---------------------------------------------------------------------------
# Spotify Web API helper
# ---------------------------------------------------------------------------
def spotify_request(method, endpoint, token, data=None, query=None):
    url = "https://api.spotify.com/v1" + endpoint
    if query:
        url += "?" + urllib.parse.urlencode(query)

    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read()
            if not raw:
                return response.status, None
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, None
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"error": raw}
    except urllib.error.URLError as e:
        return 599, {"error": f"Could not reach Spotify: {e.reason}"}


def spotify_error(result):
    if isinstance(result, dict):
        error = result.get("error")
        if isinstance(error, dict):
            return error.get("message") or str(error)
        if error:
            return str(error)
    return "Unknown Spotify error"


def pick_image(images, target=300):
    """Pick whichever image is closest to `target` px wide, instead of
    assuming the array's order - keeps hero art crisp and queue thumbnails
    small without ever fetching a needlessly large file."""
    if not images:
        return None
    def distance(img):
        width = img.get("width") or 0
        return abs(width - target) if width else 9999
    return min(images, key=distance).get("url")


def simplify_track(item):
    if not item:
        return None
    if item.get("type") == "episode":
        show = item.get("show") or {}
        return {
            "uri": item.get("uri"),
            "title": item.get("name"),
            "artist": show.get("name", ""),
            "album": show.get("name", ""),
            "album_uri": show.get("uri"),
            "art": pick_image(item.get("images") or show.get("images"), 300),
            "duration_ms": item.get("duration_ms", 0),
        }
    album = item.get("album") or {}
    return {
        "uri": item.get("uri"),
        "title": item.get("name"),
        "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "album": album.get("name"),
        "album_uri": album.get("uri"),
        "art": pick_image(album.get("images"), 300),
        "duration_ms": item.get("duration_ms", 0),
    }


def action(endpoint, method="POST", query=None, data=None):
    """Shared body for the simple fire-and-forget player actions below:
    get a token, make one Spotify call, translate the result to JSON."""
    try:
        token = auth_required()
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    status, result = spotify_request(method, endpoint, token, query=query, data=data)
    if 200 <= status < 300:
        return jsonify({"ok": True})
    return jsonify({"error": spotify_error(result)}), status


# ---------------------------------------------------------------------------
# Static files - named routes only, never a wildcard static folder, so
# nothing in this directory (this file, token.json, README) is servable
# except the exact few files below.
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(APP_DIR, "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(APP_DIR, "manifest.json")


@app.route("/icon-192.png")
def icon_192():
    return send_from_directory(APP_DIR, "icon-192.png")


@app.route("/icon-512.png")
def icon_512():
    return send_from_directory(APP_DIR, "icon-512.png")


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login")
def login():
    global AUTH_STATE, CODE_VERIFIER
    AUTH_STATE = secrets.token_urlsafe(32)
    CODE_VERIFIER = pkce_verifier()
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": AUTH_STATE,
        "code_challenge_method": "S256",
        "code_challenge": pkce_challenge(CODE_VERIFIER),
    }
    return redirect("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params))


@app.route("/callback")
def callback():
    global AUTH_STATE, CODE_VERIFIER

    error = request.args.get("error")
    if error:
        return f"Spotify authorization failed: {error}", 400

    state_param = request.args.get("state")
    code = request.args.get("code")
    if not state_param or state_param != AUTH_STATE:
        return "Invalid OAuth state. Start login again from the dashboard.", 400
    if not code or not CODE_VERIFIER:
        return "Missing authorization code. Start login again from the dashboard.", 400

    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "code_verifier": CODE_VERIFIER,
    }).encode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            tokens = json.loads(response.read())
    except urllib.error.HTTPError as e:
        message = e.read().decode(errors="replace")
        return f"Token exchange failed ({e.code}): {message}", 500

    save_tokens(tokens)
    AUTH_STATE = None
    CODE_VERIFIER = None
    return redirect("/")


@app.route("/logout")
def logout():
    clear_tokens()
    return redirect("/")


@app.route("/api/session")
def session():
    try:
        token = auth_required()
    except Exception:
        return jsonify({"authenticated": False})

    display_name = None
    status, me = spotify_request("GET", "/me", token)
    if status == 200 and me:
        display_name = me.get("display_name")
    return jsonify({"authenticated": True, "display_name": display_name})


# ---------------------------------------------------------------------------
# Playback state & transport
# ---------------------------------------------------------------------------
@app.route("/api/state")
def state():
    try:
        token = auth_required()
    except Exception:
        return jsonify({"authenticated": False})

    status, data = spotify_request(
        "GET", "/me/player", token, query={"additional_types": "track,episode"}
    )
    if status == 401:
        return jsonify({"authenticated": False})
    if status == 204 or not data:
        return jsonify({"authenticated": True, "playing": False, "device": None})
    if status != 200:
        return jsonify({"authenticated": True, "error": spotify_error(data)}), status

    device = data.get("device") or {}
    track = simplify_track(data.get("item"))
    return jsonify({
        "authenticated": True,
        "playing": data.get("is_playing", False),
        "progress_ms": data.get("progress_ms", 0),
        "duration_ms": (track or {}).get("duration_ms", 0),
        "shuffle": data.get("shuffle_state", False),
        "repeat": data.get("repeat_state", "off") != "off",
        "track": track,
        "device": ({
            "id": device.get("id"),
            "name": device.get("name"),
            "type": device.get("type"),
            "volume_percent": device.get("volume_percent"),
            "supports_volume": device.get("supports_volume", True),
        } if device else None),
    })


@app.route("/api/play-pause", methods=["POST"])
def play_pause():
    try:
        token = auth_required()
    except Exception as e:
        return jsonify({"error": str(e)}), 401

    status, playback = spotify_request("GET", "/me/player", token)
    if status == 204 or not playback:
        return jsonify({
            "error": "No active Spotify device. Open Spotify on a device, "
                     "then choose it from the device picker here."
        }), 409
    if status != 200:
        return jsonify({"error": spotify_error(playback)}), status

    endpoint = "/me/player/pause" if playback.get("is_playing") else "/me/player/play"
    status, result = spotify_request("PUT", endpoint, token)
    if 200 <= status < 300:
        return jsonify({"ok": True})
    return jsonify({"error": spotify_error(result)}), status


@app.route("/api/next", methods=["POST"])
def next_track():
    return action("/me/player/next")


@app.route("/api/previous", methods=["POST"])
def previous_track():
    return action("/me/player/previous")


@app.route("/api/seek", methods=["POST"])
def seek():
    try:
        position_ms = max(0, int((request.json or {}).get("position_ms", 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid position"}), 400
    return action("/me/player/seek", method="PUT", query={"position_ms": position_ms})


@app.route("/api/shuffle", methods=["POST"])
def shuffle():
    enabled = bool((request.json or {}).get("state"))
    return action("/me/player/shuffle", method="PUT", query={"state": str(enabled).lower()})


@app.route("/api/repeat", methods=["POST"])
def repeat():
    enabled = bool((request.json or {}).get("state"))
    return action("/me/player/repeat", method="PUT", query={"state": "context" if enabled else "off"})


@app.route("/api/volume", methods=["POST"])
def volume():
    body = request.json or {}
    value = body.get("volume_percent")
    if value is None:
        return jsonify({"error": "Missing volume_percent"}), 400
    try:
        volume_percent = max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid volume_percent"}), 400

    # device_id is optional - Spotify targets the active device when it's
    # omitted, which is all the main volume slider ever needs.
    query = {"volume_percent": volume_percent}
    if body.get("device_id"):
        query["device_id"] = body["device_id"]
    return action("/me/player/volume", method="PUT", query=query)


# ---------------------------------------------------------------------------
# Devices
# ---------------------------------------------------------------------------
@app.route("/api/devices")
def devices():
    try:
        token = auth_required()
    except Exception:
        return jsonify({"authenticated": False})
    status, result = spotify_request("GET", "/me/player/devices", token)
    if status != 200:
        return jsonify({"error": spotify_error(result)}), status
    return jsonify({"authenticated": True, "devices": result.get("devices", [])})


@app.route("/api/devices/transfer", methods=["POST"])
def transfer_device():
    device_id = (request.json or {}).get("device_id")
    if not device_id:
        return jsonify({"error": "Missing device_id"}), 400
    # play=False preserves whatever is currently playing/paused - it just
    # moves it, rather than forcing playback to start on the new device.
    return action("/me/player", method="PUT", data={"device_ids": [device_id], "play": False})


# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------
@app.route("/api/queue")
def get_queue():
    try:
        token = auth_required()
    except Exception:
        return jsonify({"authenticated": False})
    status, result = spotify_request("GET", "/me/player/queue", token)
    if status != 200:
        return jsonify({"error": spotify_error(result)}), status
    return jsonify({
        "authenticated": True,
        "current": simplify_track(result.get("currently_playing")),
        "queue": [simplify_track(t) for t in result.get("queue", []) if t],
    })


@app.route("/api/queue/add", methods=["POST"])
def add_to_queue():
    uri = (request.json or {}).get("uri")
    if not uri:
        return jsonify({"error": "Missing URI"}), 400
    return action("/me/player/queue", method="POST", query={"uri": uri})


# ---------------------------------------------------------------------------
# Search & playing a search result
# ---------------------------------------------------------------------------
@app.route("/api/search")
def search():
    try:
        token = auth_required()
    except Exception as e:
        return jsonify({"error": str(e)}), 401

    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"tracks": [], "albums": [], "artists": [], "playlists": []})

    status, result = spotify_request(
        "GET", "/search", token,
        # Spotify capped `limit` at 10 (from 50) in Feb 2026 - this is the max.
        query={"q": q, "type": "track,album,artist,playlist", "limit": 10},
    )
    if status != 200:
        return jsonify({"error": spotify_error(result)}), status

    tracks = [simplify_track(t) for t in (result.get("tracks") or {}).get("items", []) if t]

    albums = [{
        "uri": a["uri"],
        "title": a.get("name"),
        "artist": ", ".join(x.get("name", "") for x in a.get("artists", [])),
        "art": pick_image(a.get("images"), 300),
    } for a in (result.get("albums") or {}).get("items", []) if a]

    artists = [{
        "uri": a["uri"],
        "name": a.get("name"),
        "art": pick_image(a.get("images"), 300),
    } for a in (result.get("artists") or {}).get("items", []) if a]

    playlists = [{
        "uri": p["uri"],
        "title": p.get("name"),
        "owner": (p.get("owner") or {}).get("display_name", ""),
        "art": pick_image(p.get("images"), 300),
    } for p in (result.get("playlists") or {}).get("items", []) if p]

    return jsonify({"tracks": tracks, "albums": albums, "artists": artists, "playlists": playlists})


@app.route("/api/play-item", methods=["POST"])
def play_item():
    body = request.json or {}
    context_uri = body.get("context_uri")
    offset_uri = body.get("offset_uri")
    uri = body.get("uri")

    if context_uri:
        data = {"context_uri": context_uri}
        if offset_uri:
            data["offset"] = {"uri": offset_uri}
    elif uri:
        data = {"uris": [uri]}
    else:
        return jsonify({"error": "Nothing to play"}), 400

    return action("/me/player/play", method="PUT", data=data)


# ---------------------------------------------------------------------------
# Library ("Liked Songs")
# ---------------------------------------------------------------------------
@app.route("/api/save", methods=["POST"])
def save_track():
    body = request.json or {}
    uri = body.get("uri")
    if not uri or not uri.startswith("spotify:track:"):
        return jsonify({"error": "Only tracks can be saved"}), 400
    # remove=True unlikes a track that's already in Liked Songs, using the
    # same user-library-modify scope as saving.
    method = "DELETE" if body.get("remove") else "PUT"
    return action("/me/library", method=method, query={"uris": uri})


@app.route("/api/liked-status")
def liked_status():
    """Whether a single track is already in Liked Songs. Requires the
    user-library-read scope - if the current token predates that scope,
    this returns saved=False rather than erroring, so the UI just shows
    the default (unsaved) heart until the user logs in again."""
    try:
        token = auth_required()
    except Exception:
        return jsonify({"authenticated": False})

    uri = request.args.get("uri", "")
    if not uri.startswith("spotify:track:"):
        return jsonify({"authenticated": True, "saved": False})

    track_id = uri.split(":")[-1]
    status, result = spotify_request(
        "GET", "/me/tracks/contains", token, query={"ids": track_id}
    )
    if status != 200 or not isinstance(result, list) or not result:
        return jsonify({"authenticated": True, "saved": False})
    return jsonify({"authenticated": True, "saved": bool(result[0])})


if __name__ == "__main__":
    print(f"Amp running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    app.run(host=HOST, port=PORT, debug=False)
