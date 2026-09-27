"""Start the LeadScout AI web app and open it in the browser.

Used by "Start LeadScout AI.bat" (and run_app.bat). If the app is already
running, it just opens the browser again instead of starting a second copy.
The app is only reachable from this computer (localhost).
"""

import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

PORT = 8501
URL = f"http://localhost:{PORT}"
HEALTH = f"{URL}/_stcore/health"
APP_DIR = Path(__file__).resolve().parent


def _is_running() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def main() -> int:
    if _is_running():
        print("LeadScout AI is already running - opening it in your browser.")
        webbrowser.open(URL)
        return 0

    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.address", "localhost",
         "--server.port", str(PORT), "--browser.gatherUsageStats", "false"],
        cwd=APP_DIR,
    )
    for _ in range(120):  # wait up to 60 seconds for the app to start
        if server.poll() is not None:
            print("LeadScout AI stopped unexpectedly. See the messages above.")
            return server.returncode or 1
        if _is_running():
            print(f"\nLeadScout AI is running at {URL}")
            print("Keep this window open while you use it. Close this window to stop LeadScout AI.\n")
            webbrowser.open(URL)
            break
        time.sleep(0.5)
    else:
        print(f"LeadScout AI is taking long to start. Open {URL} in your browser in a moment.")

    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
