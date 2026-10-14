"""One-time download of three real English Piper voices; runtime remains offline."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
VOICE_PACK = json.loads(Path(__file__).with_name("english_voices.json").read_text())
BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
PIPER_VERSION = "1.4.2"


def verified(path: Path, metadata: dict) -> bool:
    if not path.is_file() or path.stat().st_size != metadata["size_bytes"]:
        return False
    with path.open("rb") as source:
        return hashlib.file_digest(source, "md5").hexdigest() == metadata["md5_digest"]


def download(metadata: dict, directory: Path, opener=urlopen) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / metadata["local"]
    if verified(target, metadata):
        print("Already installed: " + target.name)
        return target
    partial = target.with_name(target.name + ".part")
    print("Downloading: " + target.name, flush=True)
    try:
        request = Request(
            BASE_URL + metadata["remote"],
            headers={"User-Agent": "AI-Bingo-Party-voice-installer/1.0"},
        )
        with opener(request, timeout=120) as response, partial.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
        if not verified(partial, metadata):
            raise ValueError(
                "Download is incomplete or differs from the published Piper catalog: "
                + target.name
            )
        if target.name.endswith(".onnx.json"):
            json.loads(partial.read_text(encoding="utf-8"))
        partial.replace(target)
        return target
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def main() -> int:
    if sys.version_info < (3, 13):
        print("Use the game’s Python 3.13 environment to run this installer.")
        return 1
    directory = Path(os.getenv("PIPER_VOICE_DIR", str(ROOT / "voices"))).resolve()
    print("Installing Piper and three offline English voices: Lessac, Ryan and Alan.")
    print(
        "Internet is needed once. Voice downloads are about 190 MB, plus engine dependencies."
    )
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "piper-tts==" + PIPER_VERSION],
            check=True,
        )
        subprocess.run(
            [sys.executable, "-m", "piper", "--help"],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        for voice in VOICE_PACK:
            print("\n" + voice["label"], flush=True)
            # Retain the publisher's license/model card next to each model.
            for metadata in sorted(
                voice["files"], key=lambda item: item["local"].endswith(".onnx")
            ):
                download(metadata, directory)
        print("\nDone! Restart start.bat (or start.sh), then refresh the browser.")
        print("In Settings > Audio, enable speech and select Auto or Piper.")
        print(
            "In Settings > Bots, assign Piper · Lessac, Piper · Ryan or Piper · Alan."
        )
        print("The three publisher model cards are saved in: " + str(directory))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print("\nInstallation did not finish: " + str(error))
        print(
            "Check your internet connection and rerun this installer. Completed downloads will be reused."
        )
        print("Browser voices and text-only gameplay remain available.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
