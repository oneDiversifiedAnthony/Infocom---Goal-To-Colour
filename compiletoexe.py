import subprocess
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(ROOT, "main.py")
OUT_DIR = os.path.join(ROOT, ".claude")
ASSETS_DIR = os.path.join(ROOT, "assets")

timestamp = datetime.now().strftime("%Y%m%d.%H%M")
exe_name = f"GOOOOOOOOAAAAALLLLLLLLLL_{timestamp}"

data_files = []
for f in os.listdir(ASSETS_DIR):
    if f.endswith(".json"):
        data_files.append(f"--add-data={os.path.join(ASSETS_DIR, f)};assets")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--onefile",
    "--name", exe_name,
    "--distpath", OUT_DIR,
    "--workpath", os.path.join(OUT_DIR, "build"),
    "--specpath", os.path.join(OUT_DIR, "build"),
    *data_files,
    MAIN,
]

print(f"Building {exe_name}.exe ...")
print(f"Output:  {OUT_DIR}")
result = subprocess.run(cmd)
sys.exit(result.returncode)
