# Amp — Spotify Connect Dashboard Template

Amp dashboard is a lightweight, responsive Spotify Connect remote control web application designed for kiosk tablets, desktop browsers, or mobile devices.

It operates as a thin, same-origin proxy in front of the Spotify Web API. **Amp never plays audio directly**—it holds OAuth tokens and directs playback on your existing Spotify Connect devices (computers, smartphones, smart speakers, TVs, etc.).

---

## Features

* **Lightweight & Fast:** Built using standard web technologies with zero heavy frontend framework dependencies, keeping it performant on older tablet hardware.


* **OAuth PKCE Authentication:** Secure login using Spotify's Authorization Code Flow with PKCE without needing a client secret.


* **Playback Controls:** Play, pause, skip, seek, toggle shuffle/repeat, adjust volume, and view track progress in real time.


* **Device Management:** View available Spotify Connect devices and transfer active playback between them.


* **Up Next Rail:** View and jump to upcoming queued tracks.


* **Search & Play:** Search across Spotify tracks, albums, artists, and playlists with options to play immediately or queue.


* **Liked Songs Integration:** Save or unsave tracks directly to your Spotify library.


* **PWA & Fullscreen Kiosk Mode:** Includes a Web App Manifest (`manifest.json`) and fullscreen toggle for a native application feel.



---

## File Structure

```text
├── server.py        # Flask application proxy & Spotify Web API OAuth backend
├── index.html       # Single-page interface (HTML/CSS/JS)
├── manifest.json    # Web App Manifest for PWA support
├── icon-192.png     # PWA app icon (192x192)
├── icon-512.png     # PWA app icon (512x512)
└── requirements.txt # Python dependencies (Flask)

```

---

## Setup & Installation

### Prerequisites

* **Termux** if using android device

* **Python 3.8+**
* A **Spotify Account** (Spotify Premium is required for full Spotify Connect playback control via the Web API)

### 1. Install Dependencies

Install Flask using `pip`:

```bash
pip install flask

```

*(Or create a `requirements.txt` file containing `Flask` and run `pip install -r requirements.txt`).*

### 2. Spotify Developer Application Setup

By default, the server uses a pre-configured `CLIENT_ID`. If you want to use your own Spotify Developer App:

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Create an App.
3. Add `[http://127.0.0.1:8080/callback](http://127.0.0.1:8080/callback)` (or your custom callback host) to your app's **Redirect URIs**.
4. Set the environment variables before starting the server.

---

## Configuration & Running

You can configure Amp through environment variables:

| Environment Variable | Default Value | Description |
| --- | --- | --- |
| `SPOTIFY_CLIENT_ID` | `937d5bd53d3b4ee3bb04465511cf7344` | Spotify Client ID

 |
| `SPOTIFY_REDIRECT_URI` | `[http://127.0.0.1:8080/callback](http://127.0.0.1:8080/callback)` | OAuth redirect URI

 |
| `HOST` | `0.0.0.0` | Server host IP

 |
| `PORT` | `8080` | Server listening port

 |
| `SPOTIFY_TOKEN_FILE` | `~/spotify-dashboard/token.json` | Token storage path

### Start the Application

Run `server.py`:

```bash
python server.py

```

Once running, navigate to `[http://127.0.0.1:8080](http://127.0.0.1:8080)` in your web browser.

---

## Usage Instructions

1. **Log In:** Open the interface and click **Connect Spotify**. You will be redirected to authenticate with your Spotify account.


2. **Select a Device:** Tap the device bar at the bottom or the device icon in the top right to select an active Spotify device.


3. **Control Playback:** Use the transport controls to play/pause, skip tracks, adjust volume, or seek within a track.


4. **Search & Queue:** Tap the search icon in the top bar to search Spotify and queue or play tracks/albums/playlists directly.


5. **Fullscreen Mode:** Tap the fullscreen icon to hide browser elements for kiosk use.



---

## API Routes Overview

The backend exposes several lightweight proxy endpoints:

* `GET /login` — Initiates PKCE OAuth login.


* `GET /callback` — Handles Spotify OAuth callback exchange.


* `GET /logout` — Clears cached tokens and logs out.


* `GET /api/session` — Checks authentication status.


* `GET /api/state` — Returns current playback state.


* `POST /api/play-pause` — Toggles play/pause state.


* `POST /api/next` & `POST /api/previous` — Track navigation.


* `POST /api/seek` — Changes playback position.


* `POST /api/volume` — Adjusts active device volume.


* `GET /api/devices` & `POST /api/devices/transfer` — Device listing and playback transfer.


* `GET /api/queue` & `POST /api/queue/add` — Queue management.


* `GET /api/search` & `POST /api/play-item` — Search catalog and initiate playback.


* `GET /api/liked-status` & `POST /api/save` — Library status and saving/unsaving tracks.
