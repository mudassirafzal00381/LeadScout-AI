"""Start the LeadScout AI web app and open it in the browser.

Used by "Start LeadScout AI.bat" (and run_app.bat). If the app is already
running, it just opens the browser again instead of starting a second copy.
If port 8501 is taken by another program, the next free port is used.
The app is only reachable from this computer (localhost).
"""

import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

PORTS = range(8501, 8521)
APP_DIR = Path(__file__).resolve().parent


def _url(port: int) -> str:
    return f"http://localhost:{port}"


def _is_leadscout(port: int) -> bool:
    """True if a LeadScout AI (Streamlit) app already answers on this port."""
    try:
        with urllib.request.urlopen(f"{_url(port)}/_stcore/health", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def _is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main() -> int:
    port = None
    for candidate in PORTS:
        if _is_leadscout(candidate):
            print("LeadScout AI is already running - opening it in your browser.")
            webbrowser.open(_url(candidate))
            return 0
        if _is_free(candidate):
            port = candidate
            break
    if port is None:
        print("No free port found between 8501 and 8520. Close some programs and try again.")
        return 1

    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.address", "localhost",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=APP_DIR,
    )
    for _ in range(180):  # wait up to 90 seconds for the app to start
        if server.poll() is not None:
            print("LeadScout AI stopped unexpectedly. See the messages above.")
            return server.returncode or 1
        if _is_leadscout(port):
            print(f"\nLeadScout AI is running at {_url(port)}")
            print("Keep this window open while you use it. Close this window to stop LeadScout AI.\n")
            webbrowser.open(_url(port))
            break
        time.sleep(0.5)
    else:
        print(f"LeadScout AI is taking long to start. Open {_url(port)} in your browser in a moment.")

    try:
        return server.wait()
    except KeyboardInterrupt:
        server.terminate()
        return 0


if __name__ == "__main__":
    sys.exit(main())
