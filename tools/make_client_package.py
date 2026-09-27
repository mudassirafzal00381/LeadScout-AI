"""Build the zip you send to clients: dist/LeadScout-AI.zip

    .venv\\Scripts\\python.exe tools\\make_client_package.py

The zip contains the app, the one-click installer and start scripts, and a
branded installation guide. It never contains your virtual environment,
search results, logs, secrets or developer-only files.
"""

import base64
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
ZIP_PATH = DIST / "LeadScout-AI.zip"
TOP = "LeadScout AI"  # folder name the client sees after unzipping

# (source relative to ROOT, path inside the zip folder)
FILES = [
    ("app.py", "app.py"), ("main.py", "main.py"), ("config.py", "config.py"),
    ("dev_tests.py", "dev_tests.py"), ("launch.py", "launch.py"),
    ("requirements.txt", "requirements.txt"),
    (".streamlit/config.toml", ".streamlit/config.toml"),
    ("client/Install LeadScout AI.bat", "Install LeadScout AI.bat"),
    ("client/Start LeadScout AI.bat", "Start LeadScout AI.bat"),
]
FOLDERS = [("modules", "*.py"), ("assets", "*")]


def build_guide() -> str:
    logo = base64.b64encode((ROOT / "assets" / "logo_small.png").read_bytes()).decode("ascii")
    template = (ROOT / "tools" / "guide_template.html").read_text(encoding="utf-8")
    return template.replace("{{LOGO}}", f"data:image/png;base64,{logo}")


def main() -> None:
    DIST.mkdir(exist_ok=True)
    entries = [(ROOT / src, dst) for src, dst in FILES]
    for folder, pattern in FOLDERS:
        entries += [(p, f"{folder}/{p.name}") for p in sorted((ROOT / folder).glob(pattern)) if p.is_file()]

    missing = [str(src) for src, _ in entries if not src.exists()]
    if missing:
        raise SystemExit(f"Missing files: {missing}")

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for src, dst in entries:
            z.write(src, f"{TOP}/{dst}")
        z.writestr(f"{TOP}/Installation Guide.html", build_guide())
        z.writestr(f"{TOP}/output/.keep", "")  # Excel files are saved here
        z.writestr(f"{TOP}/README.txt",
                   "LeadScout AI - Lead Generation Tool\r\n\r\n"
                   "1. Open 'Installation Guide.html' and follow the steps.\r\n"
                   "2. Short version: double-click 'Install LeadScout AI.bat' once,\r\n"
                   "   then use the 'LeadScout AI' icon on your desktop.\r\n")

    size_kb = ZIP_PATH.stat().st_size / 1024
    print(f"Created {ZIP_PATH}  ({size_kb:.0f} KB, {len(entries) + 3} files)")


if __name__ == "__main__":
    main()
