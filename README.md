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

If you already have the game installed but see **Model missing**, run `ollama pull qwen3:4b` and wait for it to finish, or double-click the included `install_model.bat`. Then use Settings → AI → Check Ollama / Retry and press Resume. Settings → AI also lets you choose a model already downloaded in Ollama.

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

## Playing the major update

Setup is **spin → mode → bots/relationships → topic/pool → board, line target and optional timer → play**. Choose 1–12 distinct bingo lines to win. Mode, board rules, target and time limit are fixed for a round; Replay/New Party creates another.

### Modes and marking

- **Normal:** personality-driven discussion with no special chaos events. A square can only be marked after a bot actually mentions its entry. An unmentioned mark loses immediately.
- **Chaos:** the same rules with occasional arguments, rankings, alliances and other events. Low/Medium/High frequency is selected on the mode screen (5%/15%/30% per turn).
- **The Impostor:** one hidden impostor with 3–5 bots, two with 6. Python assigns/stores roles privately. Only an **innocent** mention makes a square safe. An impostor-only or unmentioned mark loses immediately.

In Impostor mode, **right-click a square** to accuse a specific bot. On touch devices, enable **Accuse (touch)** and tap a square. The accusation succeeds only if that exact impostor made a deliberately deceptive mention of the selected entry. Accusing an innocent, an impostor without that evidence, or an unmentioned entry loses immediately. Cancel has no penalty. Correct accusations flag the square, reveal/eliminate the impostor, and remove them from future dialogue. Flags do not automatically mark squares. An innocent later mention makes an entry safe without erasing evidence of an earlier lie.

Normal/Chaos victory requires the line target. Impostor victory requires **both the line target and every impostor eliminated**. Remaining innocent bots continue until both are met. Enabled timers cause a loss if victory is incomplete when time expires. Won/lost rounds stop; Replay begins a fresh round.

There are **no mention chips, eligible-square highlights, automatic answer lists or auto-marking**. Python still matches actual text case-insensitively with word boundaries and unambiguous curated/user-supplied aliases. Ellen can match Ellen Joe. Generic first words are not invented aliases: “great” does not mean Great Tusk.

### Playback and speaker choice

Start/Resume runs dialogue. Pause interrupts speech immediately and freezes server time; compatible audio resumes from the same point. Audio → Cancel speech on pause cancels it instead. An in-progress AI request may finish while paused, but no next turn is scheduled. Stop cancels speech and ignores stale results. Skip reveals the text and cancels current speech. Next Bot requests one turn in automatic mode. Only one AI turn/poll runs at a time per round, and normal progression waits for audio completion.

Enable **Manual Speaker Selection** in Gameplay settings or board setup to wait for a choice after each turn. Buttons show active bots except the last ordinary speaker. **RANDOM** selects an eligible bot. Queued player questions still get one individual answer per selected recipient.

**Change subject next turn** works in both modes. It stays enabled after failed generation and clears after a successful different subject. If no alternative exists, the app explains that the pool needs more entries. Default transition weights are 60% close relation, 25% weaker relation and 15% another subject. Evolution/faction/type connections inform choices; overused subjects receive lower probability rather than a permanent ban.

### Questions, polls, relationships and replies

**Ask the bots** targets one active bot or all active bots. Named opinion questions such as “Do you think Nicole is a good leader?” are allowed. Commands such as “Say Charmander,” board/role requests, and factual identification such as “Which Pokémon evolves into Charizard?” are rejected with a rewrite explanation. The validator is a conservative English ruleset, not perfect semantic classification. Answers are queued, preserve personality/history/relationships, then return to regular conversation. Player-written questions themselves never count as bot mentions.

Enable **Allow Bot Polls** in Gameplay settings. After at least six turns since the last poll, each dialogue turn has a 15% chance to schedule one. Polls wait for current TTS to finish. Ollama proposes an opinion poll and each active bot's choice/explanation; Python validates one vote per bot and counts totals. The creator can vote. Results name every voter. Disabled polls produce no new poll requests. Sequential voting may take longer on a CPU.

Meet Your Bots and the Crew panel support friends (+50), enemies (−50) and neutral pairs. Personality Clashes uses those scores in dialogue. Lock a pair to keep its score fixed; unlocked scores change within −100…100 using model-reported agreement/disagreement. Starting choices, dynamic scores and locks persist. This is a game heuristic, not a reliable real-world sentiment classifier.

Directed responses and question answers display a reply reference. Click it to scroll to and highlight the original message. Reply IDs survive saving/loading.

### Pools and sourced knowledge

The ZIP bundles **all 1,025 species in a pinned PokeAPI snapshot**, including default-form types, abilities, generations, species classifications and evolution relationships. Alternate/regional forms are not separate species. Standard Pokémon pools sample 60 entries from that complete offline collection. Regeneration favors entries not in the previous sample, preserves locked board entries in the pool, and makes **no Ollama request**. Pokémon type/generation subtopics, starter filters, Types and Abilities also use local data; empty unsupported filters produce an actionable error. A board samples 25 entries; bots can discuss the whole selected pool, including off-board names.

Other curated media lists are finite. Custom topics build a larger validated cached collection through Ollama. Placeholder names such as “name” are rejected, invalid output gets bounded regeneration, and selection counts reflect actual entries. Regeneration samples from the cache; when an attempted expansion adds no new names, subsequent regeneration reuses that collection. Small datasets necessarily overlap; the app reports the limitation. AI-generated names still need human review and never become verified character biographies automatically.

Before generation, local profiles provide concise facts. Pokémon facts come from the bundled dataset. A smaller curated ZZZ profile/faction map covers Ellen's shark Thiren identity, Ice/Attack role and Victoria Housekeeping membership, Nicole's leadership, and other base-agent facts. It is intentionally partial, not an exhaustive lore database. Innocent prompts use sourced facts; obvious positive type contradictions are checked/retried, but the small model can still make other factual mistakes. Impostor false claims are created by Python from known facts and recorded separately from accidental errors. Internal role/evidence/verification records never appear in ordinary API responses.

Use **Import sourced knowledge (JSON/CSV)** on the topic screen. JSON accepts a list or `{ "entries": [...] }`; each profile needs a nonempty `name` and `source`. Optional lists include `types`, `abilities`, `facts`, `teammates` and `evolutionFamily`; CSV separates list values with `|`. Illustrative formats are in `examples/knowledge.json` and `.csv`—replace them with checked facts. Imports are user-provided, not independently fact-checked. Impostor mode currently derives checkable deliberate claims from sourced `types` or `faction` fields; provide those structured fields for custom topics. Imported profiles cannot override the verified Pokémon types in the bundled snapshot.

### Timer, saves and upgrades

The timer is **off by default**, configured before play as seconds on board setup or hours/minutes/seconds in Settings → Timer. Python measures elapsed monotonic time instead of counting browser ticks, so background throttling cannot grant extra time. Pause freezes the remaining time; Resume continues. Time limits cannot be reset/extended mid-round. At zero, failure to meet every victory condition is a loss.

SQLite persists current/named rounds, hidden roles/evidence, remaining time, relationships/locks, question queues, polls and reply metadata. Browser storage holds public snapshots and an opaque session ID. Refresh restores paused. A fresh tab forks public progress into an independent round without pausing the original tab. Named loading creates a paused isolated copy with the same roles and evidence. **Keep `data/` when updating.** Legacy saves preserve crew/topic/board/settings but open in board setup for a fresh round: old client-owned marks cannot be validated retrospectively under the new rules.

Fullscreen/F11, board presets and setup locks/shuffling/regeneration, PNG export, bot voices, sound effects, font/UI scaling and reduced motion remain available. Escape exits application fullscreen.

## Offline speech

Browser SpeechSynthesis is the zero-install fallback. Install system voices using your OS settings. Local voices are labeled where the browser reports them. Voice availability and offline support vary by browser and OS. No voices? Disable speech; text gameplay still works.

### Install three additional English voices

On Windows, double-click **`install_english_voices.bat`** in your existing game folder. It installs optional `piper-tts==1.4.2` in your game's virtual environment and downloads three actual English voice models:

| Voice | Accent | Model |
| --- | --- | --- |
| Lessac | English (US) | `en_US-lessac-medium` |
| Ryan | English (US) | `en_US-ryan-medium` |
| Alan | English (UK) | `en_GB-alan-medium` |

Keep the installer open until it says Done. Download size is about **190 MB for the voices**, plus Piper's dependencies; internet is only required for this installation. The installer verifies each file's size and checksum against the published Piper catalog, retains each publisher model card, and reuses successfully installed files on retry. Model binaries are downloaded from the official Piper voice repository on Hugging Face and are not bundled in the GitHub ZIP. Each voice's license/model card is saved beside it under `voices/`.

Restart `start.bat` and press **Ctrl+F5** in the browser. In Settings → Audio, enable speech and choose **Auto** or **Piper**. In Settings → Bots, assign the new **Piper · Lessac**, **Piper · Ryan**, and **Piper · Alan** voices to your bots. Existing English/Polish system voices remain available. The browser cannot install new Windows system voices by itself; these three additional voices use local Piper audio instead.

Linux/macOS can use the same installer:

```sh
.venv/bin/python scripts/install_english_voices.py
```

The game discovers Piper in its own Python environment without requiring you to activate `.venv`. Windows Python 3.13 package compatibility was checked via dependency resolution; other platforms depend on wheel availability. If installation fails, browser voices remain available and the installer displays the error.

### Other Piper voices

Optional Piper:

1. Install a compatible Piper executable from https://github.com/OHF-Voice/piper1-gpl or use `python -m pip install piper-tts` in a compatible Python environment. Python 3.13 wheel availability varies by platform. Piper can be installed in a separate compatible environment; make its `piper` executable available on PATH when launching the game.
2. Download an `.onnx` voice **and its matching `.onnx.json`** into `voices/` at the project root. Voice downloads: https://huggingface.co/rhasspy/piper-voices. Check each voice's model card/license before using or redistributing it.
3. Restart the app and select a `Piper · …` voice for each bot in Settings → Bots. Choose Auto or Piper in Audio.

Set `PIPER_VOICE_DIR` to a different folder if desired. Piper supports speed/volume; pitch is unsupported. Auto uses Piper for assigned Piper voices and browser synthesis otherwise. Piper errors fall back to browser speech; all speech has a timeout to keep playback moving. Speech rendering is displayed in the status indicator. Last 100 Piper WAVs are cached on disk, never in browser storage. Piper is optional and is not bundled or required.

## Data and privacy

Runtime `data/bingo.sqlite3` holds rounds, caches, presets and imported knowledge. Private backend records contain roles, deliberate claims and per-message mention evidence. APIs serialize an explicit public allowlist and deny private save kinds. POSIX data-directory/database permissions are owner-only; Windows uses the user's folder permissions. The machine owner can inspect their own database: this personal local app is not an encrypted vault or a multiplayer anti-cheat service.

`backend/data/pokedex.json` is bundled **public factual data**, separate from runtime `data/`. Keep it when updating. Its source commit/scope are recorded in the file; `backend/data/POKEAPI_LICENSE.md` includes BSD license and attribution. `scripts/update_pokedex.py` rebuilds the pinned snapshot from free GitHub CSV data when internet is available. Ordinary gameplay never calls PokeAPI.

`data/audio/` is the bounded Piper cache; `voices/` holds optional installed models. Browser storage contains no hidden role keys or generated audio. `BINGO_DATA_DIR` and `PIPER_VOICE_DIR` change runtime storage. All inference uses your Ollama URL (default `http://localhost:11434`). Prompts include subject, personalities, sourced facts, rolling context, questions/polls and selected instructions, **never the bingo board or eligible-square lists**.

Keep the launcher bound to loopback. Opaque round IDs isolate sessions and are private access handles. There is no mandatory account, paid service or public game hosting.

## Troubleshooting

- **Model missing:** Ollama is running but the selected model is not downloaded. Open a terminal, run `ollama pull qwen3:4b`, and wait for success. On Windows you can also double-click `install_model.bat`. If you already downloaded a different model, choose it in Settings → AI, check Ollama, then Resume.
- **Local AI offline:** use Settings → AI → Check Ollama / Retry. Run `ollama serve`; verify URL and download the configured model with `ollama pull qwen3:4b`.
- **Repeated dialogue:** normalized exact/near-sentence comparison and repeated phrases trigger one quality retry. Subject frequency weighting/cooldown prevents loops. Persistent repetition pauses with a useful error; Resume retries. Dialogue is not cached/reused.
- **Slow generation:** disable thinking, reduce response tokens/history, lower sentences per turn, or run Ollama on supported GPU hardware. The nonstreaming API keeps one whole turn coherent and shows Thinking while waiting (180-second timeout per attempt). Invalid final output gets at most one automatic retry. The UI remains usable.
- **Bad JSON / empty response:** the backend sends both Ollama’s `think: false` flag and Qwen3’s `/no_think` instruction when thinking is disabled. It reserves at least 512 generation tokens for dialogue (2048 for lists) and uses a JSON schema for dialogue. If the final answer is empty, truncated, or invalid, it retries once with thinking disabled and a larger token budget, preserving the selected bot and topic. It never displays `message.thinking` or `<think>` content. If both attempts fail, playback pauses with an explanation. Keep Enable thinking off, update Ollama if necessary, then Resume. Old saved token settings are normalized automatically; you do not need to clear saves.
- **Too few pool entries:** expand the category or import real entries; duplicates are removed. Do not fill a real-media pool with invented names.
- **Speech failure:** choose a local browser voice, install Piper correctly, or disable TTS. Autoplay restrictions may require another click on Start.
- **Save corruption:** named saves with an invalid board are rejected. If the current browser save is damaged, clear this origin's localStorage and sessionStorage in browser developer tools (this removes current progress/settings but leaves SQLite saves).
- **Ports occupied:** stop the older instance. The launchers assume port 8000, and Vite proxies to that port.

## Verification

```sh
.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

Tests use mocked Ollama only in the test suite. Coverage includes quality/catchphrases, cooldown/transitions, complete offline dataset, schema/placeholder repair, varied/locked sampling, aliases/word boundaries, server marks and line targets, role counts/non-disclosure, all accusation branches, multiple impostors, elimination/dual victory, timers, relationship locks, queued questions, polls/vote counting, isolated/deduplicated requests, save/load and TTS synchronization. `VERIFICATION.md` records actual checks and limitations. Live game dialogue always requires Ollama.

## Architecture and licenses

- `backend/main.py`: asynchronous local APIs, voices/audio and static hosting.
- `backend/services/rounds.py`: authoritative sessions, hidden roles/evidence, dialogue, polls/questions, timers, outcomes and saves.
- `quality.py`, `questions.py`: repetition/cooldown and opinion-question rules.
- `topics.py`, `knowledge.py`: validated collections, fresh sampling and sourced retrieval.
- `rules.py`, `ollama.py`, `storage.py`, `tts.py`: matching/lines, inference recovery, SQLite and engine discovery.
- `frontend/src/App.tsx`: preserved setup/settings, customization and legacy save migration.
- `frontend/src/components/`: mode, relationship and round interfaces.
- `speech.ts`, `types.ts`, `api.ts`: cancellable speech, typed public data and API adapter.

Project code is MIT licensed. React, Vite, TypeScript, Tailwind CSS and Lucide are free open-source dependencies (Lucide: ISC; React/Vite/Tailwind: MIT; TypeScript: Apache-2.0). FastAPI is MIT licensed; Uvicorn and httpx are BSD licensed. Ollama and model weights have their own licenses; review the downloaded model's license. Piper's current implementation is GPL-3.0; optional voice datasets have individual licenses. No external fonts, images or paid assets are used. Sound effects are synthesized locally with Web Audio.
