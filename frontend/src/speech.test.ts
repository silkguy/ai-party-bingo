// @vitest-environment jsdom
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { cancelSpeech, pauseSpeech, resumeSpeech, speak } from "./speech";
import { defaults } from "./types";
const bot = {
  id: "b",
  name: "Nova",
  description: "Nerd",
  personality: "Nerd",
  color: "#fff",
  voice: "",
};
describe("speech queue", () => {
  const synth = {
    cancel: vi.fn(),
    speak: vi.fn(),
    pause: vi.fn(),
    resume: vi.fn(),
    getVoices: () => [],
  };
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("speechSynthesis", synth);
    vi.stubGlobal(
      "SpeechSynthesisUtterance",
      class {
        onend = null;
        onerror = null;
        constructor(public text: string) {}
      },
    );
  });
  afterEach(() => {
    cancelSpeech();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });
  it("cancellation resolves pending speech and prevents queued overlap", async () => {
    const done = vi.fn();
    const first = speak(
      "First",
      bot,
      { ...defaults, tts: true },
      () => {},
    ).then(done);
    expect(synth.speak).toHaveBeenCalledTimes(1);
    cancelSpeech();
    await first;
    expect(done).toHaveBeenCalledOnce();
    expect(synth.cancel).toHaveBeenCalled();
  });
  it("speaking again cancels previous speech", async () => {
    const first = speak("Old party", bot, { ...defaults, tts: true }, () => {});
    const second = speak(
      "New party",
      bot,
      { ...defaults, tts: true },
      () => {},
    );
    await first;
    expect(synth.speak).toHaveBeenCalledTimes(2);
    cancelSpeech();
    await second;
  });
  it("pauses speaking immediately and resumes the same utterance", async () => {
    const result = speak(
      "In progress",
      bot,
      { ...defaults, tts: true },
      () => {},
    );
    pauseSpeech();
    expect(synth.pause).toHaveBeenCalledOnce();
    resumeSpeech();
    expect(synth.resume).toHaveBeenCalledOnce();
    cancelSpeech();
    await result;
  });
  it("does not discard paused speech during a long pause", async () => {
    let done = false;
    const result = speak(
      "Paused",
      bot,
      { ...defaults, tts: true },
      () => {},
    ).then(() => {
      done = true;
    });
    pauseSpeech();
    await vi.advanceTimersByTimeAsync(130000);
    expect(done).toBe(false);
    resumeSpeech();
    cancelSpeech();
    await result;
  });
  it("disabled TTS is immediately playable", async () => {
    await speak("Text only", bot, defaults, () => {});
    expect(synth.speak).not.toHaveBeenCalled();
  });
  it("voice failure cannot permanently block the game", async () => {
    const result = speak("Silent", bot, { ...defaults, tts: true }, () => {});
    await vi.advanceTimersByTimeAsync(120000);
    await result;
    expect(synth.cancel).toHaveBeenCalled();
  });
});
