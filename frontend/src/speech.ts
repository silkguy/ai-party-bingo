import type { Bot, Settings } from "./types";
let audio: HTMLAudioElement | null = null,
  controller: AbortController | null = null,
  finish: (() => void) | null = null,
  version = 0,
  paused = false;
function playbackTimeout(callback: () => void) {
  let remaining = 120000,
    last = Date.now();
  const timer = setInterval(() => {
    const now = Date.now();
    if (!paused) remaining -= now - last;
    last = now;
    if (remaining <= 0) {
      clearInterval(timer);
      callback();
    }
  }, 1000);
  return () => clearInterval(timer);
}
export function cancelSpeech() {
  paused = false;
  version++;
  controller?.abort();
  controller = null;
  if (audio) {
    audio.pause();
    audio.src = "";
    audio = null;
  }
  window.speechSynthesis?.cancel();
  finish?.();
  finish = null;
}
export function pauseSpeech() {
  paused = true;
  audio?.pause();
  window.speechSynthesis?.pause();
}
export function resumeSpeech() {
  paused = false;
  if (audio) audio.play().catch(() => finish?.());
  window.speechSynthesis?.resume();
}
export async function speak(
  text: string,
  bot: Bot,
  settings: Settings,
  onStatus: (s: string) => void,
) {
  cancelSpeech();
  const token = version;
  if (!settings.tts || !settings.autoSpeak) return;
  if (settings.engine !== "browser" && bot.voice.startsWith("piper:")) {
    try {
      onStatus("Rendering local voice…");
      controller = new AbortController();
      const timeout = setTimeout(() => controller?.abort(), 65000);
      let res: Response;
      try {
        res = await fetch("/api/speech", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            text,
            voice: bot.voice.slice(6),
            rate: settings.rate,
          }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      if (!res.ok) throw Error("Piper unavailable");
      const blob = await res.blob();
      if (token !== version) return;
      const url = URL.createObjectURL(blob);
      audio = new Audio(url);
      audio.volume = settings.volume;
      onStatus("Speaking");
      await new Promise<void>((resolve) => {
        const clear = playbackTimeout(resolve);
        finish = () => {
          clear();
          resolve();
        };
        audio!.onended = finish;
        audio!.onerror = finish;
        if (!paused) audio!.play().catch(() => finish?.());
      });
      URL.revokeObjectURL(url);
      return;
    } catch {
      if (token !== version) return;
      onStatus("Piper unavailable; trying browser voice");
    }
  }
  if (!window.speechSynthesis) {
    onStatus("Speech unavailable; continuing with text");
    return;
  }
  await new Promise<void>((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice =
      speechSynthesis.getVoices().find((v) => v.voiceURI === bot.voice) || null;
    utterance.rate = settings.rate;
    utterance.volume = settings.volume;
    utterance.pitch = settings.pitch;
    const clear = playbackTimeout(() => {
      speechSynthesis.cancel();
      resolve();
    });
    finish = () => {
      clear();
      resolve();
    };
    utterance.onend = finish;
    utterance.onerror = finish;
    onStatus("Speaking");
    speechSynthesis.speak(utterance);
    if (paused) speechSynthesis.pause();
  });
}
export function sound(freq = 650) {
  try {
    const ctx = new AudioContext();
    const osc = ctx.createOscillator(),
      gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.05, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.18);
    osc.start();
    osc.stop(ctx.currentTime + 0.2);
    osc.onended = () => void ctx.close();
  } catch {
    /* Optional sound. */
  }
}
