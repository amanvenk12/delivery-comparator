#!/usr/bin/env bash
set -e

pip install -r requirements.txt

# Install Playwright's Chromium browser and its OS-level dependencies.
# --with-deps handles the apt packages (libnss, libgbm, etc.) that Chromium needs.
playwright install chromium --with-deps

# Install Xvfb for the virtual display DoorDash requires (headless=False).
apt-get install -y xvfb
