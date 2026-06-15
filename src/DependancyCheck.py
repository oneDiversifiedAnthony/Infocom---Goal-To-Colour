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

"""Dependency checker -- verifies all required packages are installed and installs missing ones."""

import importlib
import subprocess
import sys

# Maps: import_name -> pip_package_name
DEPENDENCIES = {
    "sacn": "sacn",
    "pygame": "pygame-ce",
    "PIL": "Pillow",
    "numpy": "numpy",            # audio engine mixing
    "sounddevice": "sounddevice",  # multi-device audio output (PortAudio)
}


def check_and_install():
    """Check all dependencies and install any that are missing. Returns True if all OK."""
    missing = []
    for import_name, pip_name in DEPENDENCIES.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append((import_name, pip_name))

    if not missing:
        return True

    print("=" * 60)
    print("  DEPENDENCY CHECK")
    print("=" * 60)
    for import_name, pip_name in missing:
        print(f"  Missing: {import_name} (pip: {pip_name})")
    print()
    print("  Installing missing dependencies...")
    print()

    for import_name, pip_name in missing:
        print(f"  Installing {pip_name}...", end=" ", flush=True)
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", pip_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Verify it actually imports now
            importlib.import_module(import_name)
            print("OK")
        except (subprocess.CalledProcessError, ImportError) as e:
            print(f"FAILED ({e})")
            print(f"\n  ERROR: Could not install {pip_name}.")
            print(f"  Try manually: pip install {pip_name}")
            print("=" * 60)
            return False

    print()
    print("  All dependencies installed successfully.")
    print("=" * 60)
    return True
