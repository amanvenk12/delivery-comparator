#!/usr/bin/env bash
set -e

# Start a virtual display on :99 so Playwright's headed Chromium (headless=False)
# has a display to render into. DoorDash requires this — Cloudflare Turnstile
# blocks headless Chromium at the TLS/fingerprint level regardless of flags.
Xvfb :99 -screen 0 1280x800x24 &
export DISPLAY=:99

# Give Xvfb a moment to initialize before Flask starts accepting requests.
sleep 1

exec gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT --timeout 120
