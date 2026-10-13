# AI Bingo Party

A free, local character bingo game: 3–6 customizable AI personalities discuss a shared topic while you mark a 5×5 board. Python owns speaker selection, conversation direction, chaos events and relationship scores. Ollama generates real dialogue; there is no scripted or simulated conversation fallback.

## Requirements

- Python **3.13** (tested with 3.13.5).
- Ollama from https://ollama.com/download and the `qwen3:4b` model. A 4B model needs several GB of RAM; speed depends on CPU/GPU and memory.
- A modern browser. No account or paid service required.
- Node.js 22+ only to develop or rebuild the frontend. This download includes the built frontend.

Download dependencies and model once; the game runs offline afterward. Custom pools, personality generation and dialogue need your local Ollama running. Browser speech is offline only when the selected system voice supports it.

## Install — Windows PowerShell

Install Python 3.13 and Ollama using their official installers, then open a terminal in the extracted project folder:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
ollama pull qwen3:4b
.venv\Scripts\python.exe launcher.py
```

Later, double-click `start.bat`. Ollama's desktop app normally starts its server automatically. If it is stopped, run `ollama serve` in a separate terminal.

## Install — Linux / macOS

Install Python 3.13 (python.org or your package manager). Install Ollama using its official instructions: https://ollama.com/download. Then:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
ollama pull qwen3:4b
./start.sh
```

If needed, keep `ollama serve` running in a separate terminal. Open **http://127.0.0.1:8000**. The launcher serves the built frontend through FastAPI; no frontend development server or internet connection is needed during play. Ctrl+C shuts down the game server. Both launchers bind only to loopback.

## Development

```sh
cd frontend
npm ci
npm run dev
```

In another terminal at the project root:

```sh
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Windows: substitute `.venv\Scripts\python.exe`. The Vite development URL is http://localhost:5173 and `/api` is proxied to FastAPI. Rebuild with `npm run build` in `frontend` to update the launcher version.

## Playing

1. Spin the wheel (each of 3, 4, 5 and 6 bots has 25% probability).
2. Customize names, colors, descriptions, roles and voices. Generate custom personalities with Ollama, or choose ten built-in roles.
3. Choose a topic/category and review its pool. Four curated character datasets ship locally. Custom topics use Ollama and are **not fact-checked**. Edit/import one name per line, optionally with aliases separated by `|`.
4. Generate a board, lock squares for regeneration, or clear it and enter 25 unique custom squares. Enable an optional free center. Save/load board presets.
5. Start the conversation. Manually toggle marks or enable separate detection/auto-mark options. Bots can discuss subjects from the whole pool, including names absent from your board.

Settings persist; changing them does not restart the party. Pause allows an in-progress AI request to finish its turn but schedules no further turn; speech pauses immediately and resumes from the same point where supported. Enable Cancel speech on pause in Audio to cancel it instead. Resume continues. Next Bot requests one turn while paused. Skip Message reveals text and stops current speech; it does not cancel Ollama computation. Stop ignores any stale turn response and cancels speech. New Party returns to setup; Replay Topic retains your crew and board. Refresh restores progress paused. All AI turns are serialized on both client and backend.

### Optional countdown timer

Open Settings → Timer and enable the game timer (it is **off by default**). Enter any positive duration using hours, minutes and seconds. The countdown starts with Start/Resume, pauses immediately with playback, and stops dialogue and speech at zero. A live remaining-time indicator and Reset timer button appear in the party room. Timer configuration and remaining time persist in saves; refresh keeps playback paused. Changing the configured duration takes effect on Reset or the next round. Resume after expiry starts a fresh countdown.

Use the fullscreen button or the browser's F11 shortcut. Escape exits application fullscreen. The interface stacks panels on small screens.

## Offline speech

Browser SpeechSynthesis is the zero-install fallback. Install system voices using your OS settings. Local voices are labeled where the browser reports them. Voice availability and offline support vary by browser and OS. No voices? Disable speech; text gameplay still works.

Optional Piper:

1. Install a compatible Piper executable from https://github.com/OHF-Voice/piper1-gpl or use `python -m pip install piper-tts` in a compatible Python environment. Python 3.13 wheel availability varies by platform. Piper can be installed in a separate compatible environment; make its `piper` executable available on PATH when launching the game.
2. Download an `.onnx` voice **and its matching `.onnx.json`** into `voices/` at the project root. Voice downloads: https://huggingface.co/rhasspy/piper-voices. Check each voice's model card/license before using or redistributing it.
3. Restart the app and select a `Piper · …` voice for each bot in Settings → Bots. Choose Auto or Piper in Audio.

Set `PIPER_VOICE_DIR` to a different folder if desired. Piper supports speed/volume; pitch is unsupported. Auto uses Piper for assigned Piper voices and browser synthesis otherwise. Piper errors fall back to browser speech; all speech has a timeout to keep playback moving. Speech rendering is displayed in the status indicator. Last 100 Piper WAVs are cached on disk, never in browser storage. Piper is optional and is not bundled or required.

## Data and privacy

`data/bingo.sqlite3` contains named game saves, board presets and generated pool cache. Browser localStorage holds the current game/settings. `data/audio/` is the bounded audio cache. Set `BINGO_DATA_DIR` to change backend storage location. All AI calls go to the Ollama URL in Settings (default `http://localhost:11434`); all model/voice assets are local. The model prompt includes personalities, subject, recent dialogue, earlier subject recap, relationships and chaos instructions, **never your board**. Mention matching uses actual response text and unambiguous aliases/first names with word boundaries; no fuzzy substring guessing. Model-reported stance influences bounded relationship updates; it is a game heuristic, not a reliable sentiment classifier.

Keep this app bound to loopback. It has no authentication and is intended for personal local use, not public server hosting. Saves are JSON in SQLite. Treat downloaded/custom saves as untrusted and do not edit database records manually.

## Troubleshooting

- **Local AI offline:** use Settings → AI → Check Ollama / Retry. Run `ollama serve`; verify URL and download the configured model with `ollama pull qwen3:4b`.
- **Slow generation:** disable thinking, reduce response tokens/history, lower sentences per turn, or run Ollama on supported GPU hardware. The nonstreaming API keeps one whole turn coherent and shows Thinking while waiting (180-second timeout). The UI remains usable.
- **Bad JSON / empty response:** the app shows a retryable error and pauses. Resume retries with a new request. Hidden `<think>` content is removed; it is never rendered.
- **Too few pool entries:** expand the category or import real entries; duplicates are removed. Do not fill a real-media pool with invented names.
- **Speech failure:** choose a local browser voice, install Piper correctly, or disable TTS. Autoplay restrictions may require another click on Start.
- **Save corruption:** named saves with an invalid board are rejected. If the current browser save is damaged, clear this origin's localStorage in browser developer tools (this removes current progress/settings but leaves SQLite saves).
- **Ports occupied:** stop the older instance. The launchers assume port 8000, and Vite proxies to that port.

## Verification

```sh
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

Tests cover probability distributions, nonrepeating speakers, direction selection, all bingo lines, word boundaries and ambiguous aliases, unique pools, chaos frequency/nonrepetition, bounded relationships, SQLite roundtrips, Ollama response validation, prompt board secrecy, concurrent requests, pause/resume, stale results after stop, rapid controls and speech cancellation/timeouts. Tests use a fake Ollama response only in the test suite. Real game dialogue always requires Ollama. See `VERIFICATION.md` for this delivery's actual results and limits.

## Architecture and licenses

- `backend/main.py`: asynchronous API, per-turn orchestration, health, generators, saves, optional Piper and static hosting.
- `backend/services/rules.py`: deterministic-testable game rules and matching.
- `backend/services/ollama.py`: local Ollama adapter.
- `backend/services/storage.py`: SQLite persistence.
- `frontend/src/App.tsx`: setup/game screens with reusable button, toggle and modal components.
- `frontend/src/game.ts`, `speech.ts`, `types.ts`: board utilities, cancellable speech, typed data.

Project code is MIT licensed. React, Vite, TypeScript, Tailwind CSS and Lucide are free open-source dependencies (Lucide: ISC; React/Vite/Tailwind: MIT; TypeScript: Apache-2.0). FastAPI is MIT licensed; Uvicorn and httpx are BSD licensed. Ollama and model weights have their own licenses; review the downloaded model's license. Piper's current implementation is GPL-3.0; optional voice datasets have individual licenses. No external fonts, images or paid assets are used. Sound effects are synthesized locally with Web Audio.
