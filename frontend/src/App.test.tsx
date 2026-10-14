// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { initial, defaults } from "./types";
const speech = vi.hoisted(() => ({
  cancelSpeech: vi.fn(),
  pauseSpeech: vi.fn(),
  resumeSpeech: vi.fn(),
  sound: vi.fn(),
  speak: vi.fn(async () => {}),
}));
vi.mock("./speech", () => speech);
const bots = Array.from({ length: 3 }, (_, i) => ({
  id: "b" + i,
  name: ["Nova", "Byte", "Moxie"][i],
  personality: "Nerd",
  description: "An enthusiastic expert.",
  color: "#ae85ff",
  voice: "",
}));
beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem(
    "bingo-settings",
    JSON.stringify({ ...defaults, sounds: false }),
  );
  vi.stubGlobal("speechSynthesis", {
    getVoices: () => [],
    addEventListener: () => {},
    removeEventListener: () => {},
    cancel: () => {},
  });
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => {
      const data = url.endsWith("/catalog")
        ? {
            personalities: {
              Nerd: "Expert",
              Hater: "Critical",
              Fan: "Excited",
            },
            topics: ["Pokémon"],
          }
        : url.endsWith("/health")
          ? { ok: true, message: "Ready", models: ["qwen3:4b", "qwen3:latest"] }
          : url.endsWith("/spin")
            ? { count: 3 }
            : url.endsWith("/voices")
              ? {
                  piperAvailable: true,
                  voices: [
                    "en_US-lessac-medium",
                    "en_US-ryan-medium",
                    "en_GB-alan-medium",
                  ],
                  labels: {
                    "en_US-lessac-medium": "Lessac · English (US)",
                    "en_US-ryan-medium": "Ryan · English (US)",
                    "en_GB-alan-medium": "Alan · English (UK)",
                  },
                }
              : {};
      return Promise.resolve(new Response(JSON.stringify(data)));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
describe("preserved setup and new rules", () => {
  it("spin uses POST and the next screen is mode selection", async () => {
    render(<App />);
    const button = screen.getByRole("button", { name: "SPIN THE WHEEL" });
    await waitFor(() => expect(button.hasAttribute("disabled")).toBe(false));
    vi.useFakeTimers();
    fireEvent.click(button);
    await act(async () => {});
    expect(fetch).toHaveBeenCalledWith(
      "/api/spin",
      expect.objectContaining({ method: "POST" }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3600);
    });
    fireEvent.click(screen.getByRole("button", { name: /Choose your mode/ }));
    expect(screen.getByText("Three ways to party.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /The Impostor/ }));
    expect(JSON.parse(localStorage.getItem("bingo-game")!).mode).toBe(
      "impostor",
    );
    fireEvent.click(screen.getByRole("button", { name: /Meet your bots/ }));
    expect(screen.getByText("Meet the group chat.")).toBeTruthy();
  });
  it("offers installed Ollama models and the three real English Piper choices", async () => {
    localStorage.setItem(
      "bingo-game",
      JSON.stringify({ ...initial, stage: 2, bots }),
    );
    render(<App />);
    fireEvent.click(screen.getByTitle("Settings"));
    await waitFor(() =>
      expect(screen.getByLabelText("Downloaded Ollama models")).toBeTruthy(),
    );
    fireEvent.change(screen.getByLabelText("Downloaded Ollama models"), {
      target: { value: "qwen3:latest" },
    });
    expect((screen.getByLabelText("Model") as HTMLInputElement).value).toBe(
      "qwen3:latest",
    );
    fireEvent.click(screen.getByRole("button", { name: "Bots" }));
    await waitFor(() =>
      expect(
        screen.getAllByRole("option", { name: "Piper · Lessac · English (US)" })
          .length,
      ).toBeGreaterThan(0),
    );
    expect(
      screen.getAllByRole("option", { name: "Piper · Ryan · English (US)" })
        .length,
    ).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("option", { name: "Piper · Alan · English (UK)" })
        .length,
    ).toBeGreaterThan(0);
  });
  it("required lines support all twelve and the timer is opt-in", () => {
    localStorage.setItem(
      "bingo-game",
      JSON.stringify({ ...initial, stage: 4, bots }),
    );
    render(<App />);
    const select = screen.getByLabelText(
      "Required bingo lines",
    ) as HTMLSelectElement;
    expect(select.options.length).toBe(12);
    fireEvent.change(select, { target: { value: "3" } });
    expect(JSON.parse(localStorage.getItem("bingo-game")!).requiredLines).toBe(
      3,
    );
    expect(
      (screen.getByLabelText("Enable round timer") as HTMLInputElement).checked,
    ).toBe(false);
    expect(screen.queryByText("Highlight mentions")).toBeNull();
    expect(screen.queryByText("Automatically mark")).toBeNull();
  });
  it("friends/enemies and fixed locks are saved during customization", () => {
    localStorage.setItem(
      "bingo-game",
      JSON.stringify({ ...initial, stage: 2, bots }),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText("Nova and Byte relationship"), {
      target: { value: "enemy" },
    });
    const locks = screen.getAllByLabelText("Lock");
    fireEvent.click(locks[0]);
    const saved = JSON.parse(localStorage.getItem("bingo-game")!);
    expect(saved.relationships["b0|b1"]).toBe(-50);
    expect(saved.relationshipLocks["b0|b1"]).toBe(true);
  });
  it("does not expose a mid-round chaos mode switch in settings", () => {
    render(<App />);
    fireEvent.click(screen.getByTitle("Settings"));
    expect(screen.queryByRole("button", { name: "Chaos" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Gameplay" }));
    expect(screen.getByLabelText("Manual Speaker Selection")).toBeTruthy();
    expect(screen.getByLabelText("Allow Bot Polls")).toBeTruthy();
  });
  it("rejects placeholder names when importing an editable topic pool", () => {
    localStorage.setItem(
      "bingo-game",
      JSON.stringify({ ...initial, stage: 3, bots }),
    );
    render(<App />);
    fireEvent.change(screen.getByLabelText("Topic pool import"), {
      target: { value: "name\nPikachu\npikachu\nEevee | Eevee" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply edited list" }));
    expect(
      JSON.parse(localStorage.getItem("bingo-game")!).pool.map(
        (e: { name: string }) => e.name,
      ),
    ).toEqual(["Pikachu", "Eevee"]);
    expect(screen.getByText("2 entries")).toBeTruthy();
  });
});
