// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { configure } from "@testing-library/react";
configure({
  getElementError: (message) => new Error(message || "DOM query failed"),
});
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import RoundRoom from "./RoundRoom";
import { useState } from "react";
import { defaults, initial, type Round, type State } from "../types";
const speech = vi.hoisted(() => ({
  cancelSpeech: vi.fn(),
  pauseSpeech: vi.fn(),
  resumeSpeech: vi.fn(),
  sound: vi.fn(),
  speak: vi.fn(async () => {}),
}));
vi.mock("../speech", () => speech);
let round: Round, turns: number, resolveTurn: (response: Response) => void;
const handlers = {
  onSnapshot: vi.fn(),
  onError: vi.fn(),
  onSettings: vi.fn(),
  onPanel: vi.fn(),
  onSave: vi.fn(),
  onLoad: vi.fn(),
  onNew: vi.fn(),
  onReplay: vi.fn(),
  onExport: vi.fn(),
};
const clone = () => JSON.parse(JSON.stringify(round));
function message() {
  return {
    id: "m1",
    kind: "dialogue",
    botId: "b0",
    name: "Nova",
    personality: "Nerd",
    color: "#ae85ff",
    subject: "Ellen Joe",
    conversationAction: "continue",
    message: "Ellen has a striking design. I enjoy those sharp shapes.",
    chaosEvent: null,
    relationships: {},
    replyToMessageId: null,
  };
}
function finishTurn() {
  round.messages.push(message());
  round.awaitingPlayback = true;
  resolveTurn(new Response(JSON.stringify(clone())));
}
function show() {
  return render(
    <RoundRoom
      state={
        {
          ...initial,
          stage: 5,
          bots: round.bots,
          board: round.board,
          pool: round.pool,
        } as State
      }
      settings={round.settings}
      {...handlers}
    />,
  );
}
beforeEach(() => {
  turns = 0;
  sessionStorage.clear();
  round = {
    ...JSON.parse(JSON.stringify(initial)),
    sessionId: "session",
    mode: "normal",
    topic: "Zenless Zone Zero",
    category: "Characters",
    board: Array.from({ length: 25 }, (_, i) =>
      i === 0 ? "Ellen Joe" : "Entry " + i,
    ),
    pool: [{ name: "Ellen Joe", aliases: ["Ellen"] }],
    bots: Array.from({ length: 3 }, (_, i) => ({
      id: "b" + i,
      name: ["Nova", "Byte", "Moxie"][i],
      personality: "Nerd",
      description: "Expert",
      color: "#ae85ff",
      voice: "",
    })),
    status: "paused",
    completedLines: 0,
    resultReason: "",
    polls: [],
    forceNextSubject: false,
    settings: { ...defaults, sounds: false },
    running: false,
    awaitingPlayback: false,
    generating: false,
    questionQueue: [],
    pollPending: false,
    remainingImpostors: 0,
    impostorCount: 0,
    revealedRoles: {},
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      const response = (data: unknown) =>
        Promise.resolve(new Response(JSON.stringify(data)));
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      if (url === "/api/turn") {
        turns++;
        return new Promise<Response>((r) => {
          resolveTurn = r;
        });
      }
      if (url.endsWith("/control")) {
        if (body.action === "start") {
          round.running = true;
          round.status = round.settings.manualSpeaker
            ? "waiting_for_speaker"
            : "playing";
        }
        if (["pause", "stop", "restore"].includes(body.action)) {
          round.running = false;
          round.status = "paused";
        }
        if (["complete", "restore", "stop"].includes(body.action))
          round.awaitingPlayback = false;
        if (body.action === "force_subject")
          round.forceNextSubject = !round.forceNextSubject;
      }
      if (url.endsWith("/mark")) {
        round.status = "lost";
        round.running = false;
        round.resultReason = "That entry had not been mentioned by a bot.";
      }
      if (url.endsWith("/question")) round.questionQueue = ["b0", "b1", "b2"];
      if (url.endsWith("/accuse")) {
        round.eliminated = ["b1"];
        round.revealedRoles = { b1: "impostor" };
        round.remainingImpostors = 0;
        round.flagged[0] = true;
      }
      return response(clone());
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});
describe("authoritative round UI", () => {
  it("rapid start/pause/resume does not overlap requests and stop ignores the stale turn", async () => {
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await screen.findByRole("button", { name: "Pause" });
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(turns).toBe(1);
    fireEvent.click(screen.getByTitle("Stop"));
    await act(async () => {});
    await act(async () => {
      finishTurn();
    });
    expect(screen.queryByText(message().message)).toBeNull();
  });
  it("manual mode waits for a choice and sends the selected bot ID", async () => {
    round.settings.manualSpeaker = true;
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() =>
      expect(screen.getByText("Choose the next speaker")).toBeTruthy(),
    );
    expect(turns).toBe(0);
    fireEvent.click(screen.getByRole("button", { name: "Byte" }));
    await waitFor(() => expect(turns).toBe(1));
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => url === "/api/turn")!;
    expect(JSON.parse(String(call[1]?.body)).botId).toBe("b1");
    await act(async () => {
      finishTurn();
    });
    fireEvent.click(screen.getByTitle("Skip message"));
    await act(async () => {});
    expect(turns).toBe(1);
  });
  it("pauses speech immediately, with no eligible-entry chips or highlights", async () => {
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await screen.findByRole("button", { name: "Pause" });
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    expect(speech.pauseSpeech).toHaveBeenCalled();
    expect(document.querySelector(".mention-list")).toBeNull();
    expect(document.querySelector(".mentioned")).toBeNull();
    await act(async () => {
      finishTurn();
    });
    fireEvent.click(screen.getByTitle("Skip message"));
  });
  it("uses the server mark result for an immediate loss", async () => {
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: /01.*Ellen Joe/ }));
    await screen.findByRole("heading", { name: "Round lost" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/rounds/session/mark",
      expect.objectContaining({ method: "POST" }),
    );
    expect(speech.cancelSpeech).toHaveBeenCalled();
  });
  it("opens specific-suspect accusations only in impostor mode", async () => {
    round.mode = "impostor";
    round.remainingImpostors = 1;
    round.impostorCount = 1;
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.contextMenu(
      screen.getByRole("button", { name: /01.*Ellen Joe/ }),
    );
    await screen.findByRole("dialog", { name: "Who was the impostor?" });
    fireEvent.click(screen.getByRole("button", { name: /Byte.*Nerd/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm accusation" }));
    await waitFor(() =>
      expect(handlers.onSnapshot).toHaveBeenCalledWith(
        expect.objectContaining({ eliminated: ["b1"] }),
      ),
    );
    const call = vi
      .mocked(fetch)
      .mock.calls.find(([url]) => String(url).endsWith("/accuse"))!;
    expect(JSON.parse(String(call[1]?.body))).toEqual({
      index: 0,
      botId: "b1",
    });
  });
  it("server timer expiration ends the round and preserves off-by-default behavior", async () => {
    round.timerRemaining = 2;
    vi.useFakeTimers();
    show();
    await act(async () => {});
    expect(screen.getByLabelText("Game timer").textContent).toContain("0:02");
    round.status = "lost";
    round.resultReason = "Time ran out.";
    round.running = false;
    round.timerRemaining = 0;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(screen.getByRole("heading", { name: "Round lost" })).toBeTruthy();
    expect(screen.getByLabelText("Game timer").textContent).toContain("0:00");
    expect(speech.cancelSpeech).toHaveBeenCalled();
  });
  it("questions are queued with a recipient, and reply references are clickable", async () => {
    round.messages = [
      { ...message(), id: "old" },
      {
        ...message(),
        id: "reply",
        botId: "b1",
        name: "Byte",
        message: "I see that differently.",
        replyToMessageId: "old",
      },
    ];
    show();
    await screen.findByRole("button", { name: "Resume" });
    expect(
      screen.getByRole("button", { name: /Replying to Nova/ }),
    ).toBeTruthy();
    fireEvent.change(
      screen.getByPlaceholderText("Which character design do you like most?"),
      { target: { value: "Do you think Nicole is a good leader?" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        "/api/rounds/session/question",
        expect.objectContaining({
          body: JSON.stringify({
            text: "Do you think Nicole is a good leader?",
            target: "all",
          }),
        }),
      ),
    );
  });
});

describe("playback scheduling", () => {
  it("automatic turns wait for speech completion, then request the next bot once", async () => {
    round.settings.tts = true;
    let endSpeech: () => void = () => {};
    speech.speak.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          endSpeech = resolve;
        }),
    );
    show();
    await screen.findByRole("button", { name: "Start" });
    vi.useFakeTimers();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await act(async () => {});
    await act(async () => {
      finishTurn();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(speech.speak).toHaveBeenCalledOnce();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(turns).toBe(1);
    await act(async () => {
      endSpeech();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(800);
    });
    expect(turns).toBe(2);
    fireEvent.click(screen.getByTitle("Stop"));
    await act(async () => {});
    await act(async () => {
      finishTurn();
    });
  });
});

describe("new controls and privacy", () => {
  it("force-subject toggle is visible in automatic mode and the server owns it", async () => {
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(
      screen.getByRole("button", { name: "Change subject next turn" }),
    );
    await screen.findByRole("button", { name: /Change subject next turn.*ON/ });
    expect(fetch).toHaveBeenCalledWith(
      "/api/rounds/session/control",
      expect.objectContaining({
        body: JSON.stringify({ action: "force_subject" }),
      }),
    );
  });
  it("normal mode right-click does not open accusation controls", async () => {
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.contextMenu(
      screen.getByRole("button", { name: /01.*Ellen Joe/ }),
    );
    expect(
      screen.queryByRole("dialog", { name: "Who was the impostor?" }),
    ).toBeNull();
    expect(screen.queryByText(/eliminated impostor/)).toBeNull();
  });
  it("touch accusation cancel has no validation or loss request", async () => {
    round.mode = "impostor";
    round.impostorCount = 1;
    round.remainingImpostors = 1;
    show();
    await screen.findByRole("button", { name: "Start" });
    fireEvent.click(screen.getByRole("button", { name: "Accuse (touch)" }));
    fireEvent.click(screen.getByRole("button", { name: /01.*Ellen Joe/ }));
    await screen.findByRole("dialog", { name: "Who was the impostor?" });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await act(async () => {});
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(([url]) => String(url).endsWith("/accuse")),
    ).toBe(false);
    expect(screen.queryByRole("heading", { name: "Round lost" })).toBeNull();
  });
  it("poll results show each voter and Python-provided totals", async () => {
    round.polls = [
      {
        id: "poll",
        creatorId: "b0",
        creatorName: "Nova",
        question: "Which design feels better?",
        options: ["Bold", "Subtle"],
        totals: [2, 1],
        votes: [
          {
            botId: "b0",
            name: "Nova",
            option: 0,
            explanation: "I prefer expressive details.",
          },
          {
            botId: "b1",
            name: "Byte",
            option: 0,
            explanation: "Bold forms hold attention.",
          },
          {
            botId: "b2",
            name: "Moxie",
            option: 1,
            explanation: "Subtle details suit my taste.",
          },
        ],
      },
    ];
    show();
    await screen.findByText("Which design feels better?");
    expect(screen.getByText("Bold · 2 votes")).toBeTruthy();
    expect(screen.getByText("Subtle · 1 votes")).toBeTruthy();
    expect(screen.getByText("Nova, Byte")).toBeTruthy();
    expect(
      screen.getByText("Moxie: Subtle details suit my taste."),
    ).toBeTruthy();
  });
});

describe("tab isolation", () => {
  it("opening saved progress in a fresh tab forks without pausing the original round", async () => {
    render(
      <RoundRoom
        state={{
          ...initial,
          stage: 5,
          sessionId: "session",
          bots: round.bots,
          board: round.board,
          pool: round.pool,
        }}
        settings={round.settings}
        {...handlers}
      />,
    );
    await screen.findByRole("button", { name: "Start" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/rounds/session/fork",
      expect.objectContaining({ method: "POST" }),
    );
    expect(
      vi
        .mocked(fetch)
        .mock.calls.some(
          ([, init]) => init?.body && String(init.body).includes("restore"),
        ),
    ).toBe(false);
  });
});

describe("configuration synchronization", () => {
  it("periodic snapshots do not erase a friend/enemy edit before its PATCH completes", async () => {
    const original = vi.mocked(fetch).getMockImplementation()!;
    vi.mocked(fetch).mockImplementation((url, init) => {
      if (String(url) === "/api/rounds/session" && init?.method === "PATCH") {
        const body = JSON.parse(String(init.body));
        round.relationships = body.relationships || round.relationships;
      }
      return original(url, init);
    });
    function Harness() {
      const [state, setState] = useState<State>({
        ...initial,
        stage: 5,
        bots: round.bots,
        board: round.board,
        pool: round.pool,
      });
      return (
        <>
          <button
            onClick={() =>
              setState((s) => ({ ...s, relationships: { "b0|b1": -50 } }))
            }
          >
            Set enemy pair
          </button>
          <output data-testid="pair-score">
            {state.relationships["b0|b1"] || 0}
          </output>
          <RoundRoom
            state={state}
            settings={round.settings}
            {...handlers}
            onSnapshot={(snapshot) => setState((s) => ({ ...s, ...snapshot }))}
          />
        </>
      );
    }
    vi.useFakeTimers();
    render(<Harness />);
    await act(async () => {});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });
    fireEvent.click(screen.getByRole("button", { name: "Set enemy pair" }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(150);
    });
    expect(screen.getByTestId("pair-score").textContent).toBe("-50");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(250);
    });
    expect(round.relationships["b0|b1"]).toBe(-50);
  });
});
