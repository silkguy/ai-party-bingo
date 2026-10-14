# Major update verification

Validated on Linux with Python 3.13.5 and Node.js 24.

- **114 backend tests passed**, including the preserved probability/alias/Ollama/TTS tests and new quality, dataset, authoritative-round, question, poll, role, accusation, timer, save and isolation tests.
- **31 frontend tests passed**, including the preserved speech cancellation/pause tests and new setup flow, manual selection, controls, backend loss handling, accusation/touch cancel, reply references, poll display, per-tab isolation, configuration synchronization and TTS-completion scheduling tests.
- TypeScript compile and Vite production build passed. The final built frontend is included in `frontend/dist` and is served by FastAPI without Node.js at play time.
- The bundled Pokédex has **1,025 species** from PokeAPI commit `81d20919845b6a445969b9265aab5cec6b04cece`, with default-form types, abilities, generations and evolution relationships. Dataset scope and BSD attribution are shipped alongside it. Sampling and supported Pokémon subtopics run offline, without Ollama requests.
- API tests explicitly check that private record kinds cannot be read/written through public save endpoints, normal snapshots do not include roles/evidence/lie metadata, modes/timer limits cannot change mid-round, marks/accusations are validated by Python, concurrent requests cannot create overlapping turns in a round, and saved/forked rounds preserve hidden state without mutating another round.
- An archive integrity check confirms the ZIP contains the bundled dataset/license, new modules/components, voice/model installers, documentation and production assets, and excludes runtime databases, credentials, model binaries and caches.

## Investigation and changes

The previous code had no subject cooldown or duplicate-response validator. It repeatedly fed recent full dialogue to new personalities, allowing a catchphrase to become a shared pattern. There was no hardcoded Pidgey joke and no dialogue-response cache; audio caching is separate. The update checks exact/near messages, near-identical sentences, repeated five-word phrases and unrelated overused subjects, adjusts subject probabilities, and uses one bounded quality retry. Ollama receives fresh seeds/repetition penalty as well as the existing bounded invalid-output retry and no-thinking instructions. A turn therefore has at most two quality attempts, each with at most two adapter attempts.

Topic regeneration previously returned the same finite curated list, and custom generation accepted a loose JSON object with placeholder field examples. The update validates a strict entry schema, rejects placeholders/empty names, repairs invalid output with bounded attempts, normalizes cache keys and whitespace, caches a larger collection, preserves eligible locked entries and samples preferentially outside the previous selection. Small collections still overlap honestly; generated custom names are not automatically factual ground truth.

Previously the browser owned marks and the timer and did not record trusted per-message evidence. The update stores isolated rounds in SQLite, uses a server monotonic clock, validates clicks/accusations and both parts of Impostor victory, serializes an explicit public allowlist, deduplicates successful turn IDs, and preserves private evidence/roles during named saves and independent tab forks. Legacy saves preserve setup but enter a fresh validated round rather than trusting old marks.

## Verification limits

- The local `http://127.0.0.1:11434/api/tags` check failed with `ConnectError`, and no Ollama executable is available in this environment. Real qwen3:4b quality/latency and Windows inference were **not** tested. Automated model replies are mocked only in tests; runtime dialogue always uses Ollama.
- No browser-control tool is available here. Real-browser layout/resizing, native fullscreen and physical speech playback still need a smoke test on the user's machine. DOM tests verify the interface and control contracts, including removal of mention chips/highlights.
- Piper engine/CLI compatibility and Windows Python 3.13 package resolution were checked in the earlier delivery. Optional voice downloads/live rendering cannot be verified against the blocked Hugging Face download host here. The installers, voice IDs/checksums, command discovery, caching and speech queue logic remain covered by tests.
- Factual retrieval and contradiction checks reduce hallucinations but cannot verify every statement from a small model. ZZZ facts are a partial curated base-agent/faction map; user imports require their own checked sources. Impostor evidence only records Python-planned, actually asserted false claims, never arbitrary model mistakes.
- English question validation is deliberately conservative and rule-based. Ambiguous semantic intent cannot be classified perfectly; rejected questions get a rewrite explanation.
- Hidden state is private to backend APIs and owner-only files on POSIX. The local machine owner can inspect their own SQLite database; this is not an encrypted or competitive multiplayer service.

## Manual smoke test after updating

Keep `.venv`, runtime `data/`, and `voices/`. Replace application files, including **`backend/data`** and `frontend/dist`; restart `start.bat`/`start.sh`, then hard-refresh the browser.

1. Spin, choose each mode, customize a friend/enemy lock, generate a Pokémon pool twice and confirm a varied selection, then choose a line target/timer.
2. Start a local Ollama conversation; pause/resume speech, choose manual speakers and RANDOM, force a subject change, ask an opinion question and try a rejected factual/forced-answer question.
3. Enable polls, wait for one, inspect each vote/total and click a reply reference.
4. Test a valid mark, an unmentioned mark loss, and timer expiry. In Impostor mode, check an innocent mention, a correct specific accusation, elimination, a wrong accusation and victory requiring both conditions.
5. Save/load and refresh paused; open another tab and confirm it uses an independent copy. Verify old saves open into setup and retain crew/board preferences.
