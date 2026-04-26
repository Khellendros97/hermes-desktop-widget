"""PyInstaller build script for Hermes Desktop Panel."""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
RESOURCES = PROJECT_ROOT / "hermes_panel" / "resources"

sep = ";" if sys.platform == "win32" else ":"

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--name", "HermesPanel",
    "--onefile",
    "--windowed",
    "--noconsole",
    "--add-data", f"{RESOURCES}{sep}hermes_panel/resources",
    str(PROJECT_ROOT / "main.py"),
]

print("Running PyInstaller...")
subprocess.run(cmd, cwd=str(PROJECT_ROOT))
print("Build complete.")
