# Optional: run LeadScout AI in Docker (Linux container).
# The official Playwright image already contains Chromium, so no browser
# download happens at build time. Keep the tag in sync with requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV LEADSCOUT_BROWSER_CHANNELS=bundled \
    LEADSCOUT_OUTPUT_DIR=/app/output \
    PYTHONUNBUFFERED=1

ENTRYPOINT ["python", "main.py"]
