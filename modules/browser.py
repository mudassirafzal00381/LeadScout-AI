"""Launch a Playwright browser, falling back through config.BROWSER_CHANNELS."""

import sys

import config

# Containers (Docker, Hugging Face Spaces) often have a tiny /dev/shm, which
# makes Chromium crash; this flag makes it use /tmp instead.
_LINUX_ARGS = ["--disable-dev-shm-usage"] if sys.platform.startswith("linux") else []

BROWSER_NAMES = {
    "chrome": "Google Chrome",
    "msedge": "Microsoft Edge",
    "bundled": "Bundled Chromium",
}


def launch_browser(playwright, headless: bool | None = None):
    """Launch the first available browser from config.BROWSER_CHANNELS.

    Returns (browser, channel). Raises RuntimeError if none can be launched.
    """
    if headless is None:
        headless = config.HEADLESS

    errors = []
    for channel in config.BROWSER_CHANNELS:
        try:
            browser = playwright.chromium.launch(
                channel=None if channel == "bundled" else channel,
                headless=headless,
                args=_LINUX_ARGS,
            )
            return browser, channel
        except Exception as exc:  # noqa: BLE001 - try the next browser
            errors.append(f"{BROWSER_NAMES.get(channel, channel)}: {str(exc).splitlines()[0]}")

    raise RuntimeError("No supported browser could be launched.\n  " + "\n  ".join(errors))
