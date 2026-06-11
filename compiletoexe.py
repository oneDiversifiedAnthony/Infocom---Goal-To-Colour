# Copyright (c) 2026 oneDiversified.
#
#     ..---------.
#   ...         .--.
#  ............   .--            #+ -#.                              -#.  +### ##                +#
# ...........----  .-.           #+                                       #+                     +#
# --     --    --.  ++     -######+ -#  ##   +#  #####+  ####.-####- .# -########  +#####   #######
# --     --    --.  ++    -#-   -#+ -#  .#+ -#- ##---+#+ ##   -##+.  .#.  #+   ## +#+---## ##    ##
# .-     -------.  -+.    .##   +#+ -#   -#+#-  ##.      ##      .## .#   #+   ## -#+      +#-   ##
#  --.   ....     -+-       ######+ -#    ###    +####+  ##   -####+ .#.  #+   ##   #####   -######
#   .--.        -++
#      ------+++-
#
# This software, its source code, and all associated functions, scripts, and
# documentation are the proprietary and confidential property of oneDiversified.
#
# Unauthorized copying, distribution, modification, or disclosure of this software
# is strictly prohibited. This code is provided solely for internal use by authorized
# oneDiversified personnel and may not be shared, published, or distributed externally
# without explicit written permission from oneDiversified.
#
# Use of this software constitutes acceptance of your confidentiality, IP protection,
# and contractual obligations with oneDiversified.


import subprocess
import sys
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__))
MAIN = os.path.join(ROOT, "main.py")
OUT_DIR = os.path.join(ROOT, "Candidates")
ASSETS_DIR = os.path.join(ROOT, "assets")
SOUND_DIR = os.path.join(ROOT, "Sound Files")

timestamp = datetime.now().strftime("%Y%m%d.%H%M")
exe_name = f"GOOOOOOOOAAAAALLLLLLLLLL_{timestamp}"

README = os.path.join(ROOT, "README.md")
CONFIG_INI = os.path.join(ROOT, "config.ini")

data_files = []

# Asset JSON files
for f in os.listdir(ASSETS_DIR):
    if f.endswith(".json"):
        data_files.append(f"--add-data={os.path.join(ASSETS_DIR, f)};assets")

# Schedule JSON files
schedule_dir = os.path.join(ASSETS_DIR, "Schedule")
if os.path.isdir(schedule_dir):
    for f in os.listdir(schedule_dir):
        if f.endswith(".json"):
            data_files.append(f"--add-data={os.path.join(schedule_dir, f)};assets/Schedule")

# Sound files (mp3, wav, ogg, peak)
if os.path.isdir(SOUND_DIR):
    for f in os.listdir(SOUND_DIR):
        fpath = os.path.join(SOUND_DIR, f)
        if os.path.isfile(fpath) and f.lower().endswith((".mp3", ".wav", ".ogg", ".peak", ".json")):
            data_files.append(f"--add-data={fpath};Sound Files")
    # Anthems subfolder
    anthems_dir = os.path.join(SOUND_DIR, "Anthems")
    if os.path.isdir(anthems_dir):
        for f in os.listdir(anthems_dir):
            fpath = os.path.join(anthems_dir, f)
            if os.path.isfile(fpath) and f.lower().endswith((".mp3", ".wav", ".ogg")):
                data_files.append(f"--add-data={fpath};Sound Files/Anthems")

# README and config
data_files.append(f"--add-data={README};.")
data_files.append(f"--add-data={CONFIG_INI};.")

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
print(f"Sound files included from: {SOUND_DIR}")
result = subprocess.run(cmd)
sys.exit(result.returncode)
