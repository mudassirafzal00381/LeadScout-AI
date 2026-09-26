# LeadScout AI web app in a container (used by Hugging Face Spaces, also runs locally).
# The official Playwright image already contains Chromium and its system
# libraries. Keep the tag in sync with the playwright version in requirements.txt.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

# - PIP_BREAK_SYSTEM_PACKAGES: allow pip into the image's system Python (Ubuntu 24.04).
# - HOME and LEADSCOUT_*_DIR point at /tmp because Hugging Face runs the container
#   as a non-root user that cannot write inside /app.
ENV PIP_BREAK_SYSTEM_PACKAGES=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/tmp \
    LEADSCOUT_BROWSER_CHANNELS=bundled \
    LEADSCOUT_OUTPUT_DIR=/tmp/leadscout/output \
    LEADSCOUT_LOG_DIR=/tmp/leadscout/logs

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Hugging Face Spaces expects port 7860 (see app_port in README.md).
EXPOSE 7860
CMD ["sh", "-c", "streamlit run app.py --server.port=${PORT:-7860} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
