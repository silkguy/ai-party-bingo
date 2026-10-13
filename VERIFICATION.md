# Delivery verification

Validated on Linux with Python 3.13.5 and Node.js 24.

- Backend: **28 tests passed** using pytest. Probability and pure rules use deterministic seeded samples. API tests use FastAPI's test client with mocked Ollama generation; the board secrecy and request serialization contracts are explicitly checked.
- Frontend: **17 tests passed** using Vitest, including React DOM tests for rapid controls, pause/resume, ignoring stale results after Stop, timer pause/expiry and opt-in defaults, immediate speech pause/resume, preserving speech during long pauses, and speech queue cancellation/timeouts.
- TypeScript compile and Vite production build passed. The production bundle is included under `frontend/dist`.
- Static frontend serving through FastAPI verified by integration test.

Verification limits:

- Ollama/qwen3:4b are not installed in the execution environment. Real inference quality/latency and installed-version thinking compatibility were not tested. No production dialogue is mocked; Ollama failures produce a visible, retryable error.
- Piper 1.4.2 was installed on Python 3.13 and its CLI arguments verified. Windows Python 3.13 binary dependency resolution also passed. The three voice IDs, byte counts and checksums were verified against the published Piper catalog. This environment cannot access the Hugging Face download host, so voice model downloads and real audio rendering were not performed here. Installer integrity/retry behavior and cached audio API responses are covered by tests using fixtures. Actual browser/system voices and physical playback still require verification on the user’s computer.
- No browser-control capability is available in this environment. Visual rendering, native fullscreen, actual resizing and OS audio still need a real-browser smoke test on the user's computer.
- The prescribed `/codex/browser/.../output` directory is absent and its ancestor is not writable in this managed workspace. Deliverables are packaged instead in the project's `output/` directory. The complete source and built frontend are published in the connected GitHub repository; no game hosting or AI cloud service is used.

Design choices:

- Ollama responses are nonstreaming; text is progressively revealed only after a validated complete response. Skip reveals all text immediately.
- Old dialogue is compacted in AI context as a deterministic recent-subject recap; the complete saved transcript remains available in the UI.
- Relationship updates use a validated enum-like stance (unknown values update by zero) reported by the model, rather than pretending sentiment is a ground-truth measurement.
- Four curated datasets are intentionally finite and not a claim of an exhaustive up-to-date roster. Custom AI pools require human review.
- The game is intended for a single local party; a server-wide turn lock also protects multiple tabs from overlapping inference.
