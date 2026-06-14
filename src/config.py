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
_CONFIG_PATH = os.path.join(APP_ROOT, "config.ini")

_cfg = configparser.ConfigParser()
_cfg.read(_CONFIG_PATH)

SOUND_DIR = os.path.join(APP_ROOT, _cfg.get("paths", "sound_files", fallback="Sound Files"))
ANTHEMS_DIR = os.path.join(SOUND_DIR, "Anthems")
CALL_LOG_DIR = os.path.join(APP_ROOT, _cfg.get("paths", "call_log", fallback="Call Log"))


def get_webserver_bool(key, fallback=True):
    """Read a boolean from [webserver] section."""
    return _cfg.getboolean("webserver", key, fallback=fallback)


def set_webserver_bool(key, value):
    """Write a boolean to [webserver] section and save config.ini."""
    if not _cfg.has_section("webserver"):
        _cfg.add_section("webserver")
    _cfg.set("webserver", key, str(value).lower())
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        _cfg.write(f)


def get_config(section, key, fallback=""):
    """Read a string from any config section."""
    return _cfg.get(section, key, fallback=fallback)


def set_config(section, key, value):
    """Write a string to any config section and save config.ini."""
    if not _cfg.has_section(section):
        _cfg.add_section(section)
    _cfg.set(section, key, value)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        _cfg.write(f)
