FROM python:3.14-slim

# Install Xvfb and the system libraries Chromium needs.
# These are split into two groups for clarity:
#   1. Xvfb — virtual display for DoorDash's headless=False requirement
#   2. Chromium system deps — what `playwright install --with-deps` would
#      normally apt-get, listed explicitly so the layer is cached separately
#      from the pip install step and won't re-download on every code change.
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    # Chromium runtime dependencies
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgtk-3-0 \
    fonts-liberation \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

ENV PLAYWRIGHT_BROWSERS_PATH=/root/.cache/ms-playwright

WORKDIR /app

# Install Python dependencies first — this layer is cached unless
# requirements.txt changes, keeping rebuilds fast on code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser binary.
# --with-deps is omitted here because we installed the system libs above;
# running it would re-apt-get the same packages and bust the cache.
RUN playwright install chromium

# Copy application code.
COPY . .

# Render injects $PORT at runtime; gunicorn binds to it.
# start.sh launches Xvfb on :99, exports DISPLAY, then execs gunicorn.
CMD ["bash", "start.sh"]
