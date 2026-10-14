"""Discover Piper in the game's Python environment as well as on PATH."""

import importlib.util
import shutil
import sys

VOICE_LABELS = {
    "en_US-lessac-medium": "Lessac · English (US)",
    "en_US-ryan-medium": "Ryan · English (US)",
    "en_GB-alan-medium": "Alan · English (UK)",
}


def piper_command() -> list[str] | None:
    if importlib.util.find_spec("piper") is not None:
        return [sys.executable, "-m", "piper"]
    binary = shutil.which("piper")
    return [binary] if binary else None
