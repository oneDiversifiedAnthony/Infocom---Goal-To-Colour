"""Centralised configuration loaded from config.ini."""

import configparser
import os
import sys


def _app_root():
    """Return the application root directory (works for both script and frozen exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


APP_ROOT = _app_root()

_cfg = configparser.ConfigParser()
_cfg.read(os.path.join(APP_ROOT, "config.ini"))

SOUND_DIR = os.path.join(APP_ROOT, _cfg.get("paths", "sound_files", fallback="Sound Files"))
ANTHEMS_DIR = os.path.join(SOUND_DIR, "Anthems")
CALL_LOG_DIR = os.path.join(APP_ROOT, _cfg.get("paths", "call_log", fallback="Call Log"))
