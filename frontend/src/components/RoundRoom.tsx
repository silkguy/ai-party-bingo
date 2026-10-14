import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  BarChart3,
  Check,
  Dices,
  Download,
  Flag,
  MessageCircle,
  Pause,
  Play,
  RotateCcw,
  Save,
  ShieldCheck,
  Shuffle,
  SkipForward,
  Sparkles,
  Square,
  Timer,
  Users,
  Volume2,
  Zap,
} from "lucide-react";
import { api } from "../api";
import { lines } from "../game";
import { formatTime } from "../timer";
import {
  cancelSpeech,
  pauseSpeech,
  resumeSpeech,
  sound,
  speak,
} from "../speech";
import type { Round, Settings, State } from "../types";

type Props = {
  state: State;
  settings: Settings;
  onSnapshot: (round: Round) => void;
  onError: (message: string) => void;
  onSettings: (settings: Partial<Settings>) => void;
  onPanel: (name: string) => void;
  onSave: () => void;
  onLoad: () => void;
  onNew: () => void;
  onReplay: () => void;
  onExport: () => void;
};
const ended = (r: Round | null) =>
  Boolean(r && ["won", "lost"].includes(r.status));
export default function RoundRoom(props: Props) {
  const [round, setRound] = useState<Round | null>(null),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState("Loading round…"),
    [revealed, setRevealed] = useState(10000),
    [question, setQuestion] = useState(""),
    [target, setTarget] = useState("all"),
    [accuseSquare, setAccuseSquare] = useState<number | null>(null),
    [suspect, setSuspect] = useState(""),
    [accuseTouch, setAccuseTouch] = useState(false),
    [replyHighlight, setReplyHighlight] = useState(""),
    [eliminationNotice, setEliminationNotice] = useState("");
  const setupKey = useRef(crypto.randomUUID());
  const current = useRef<Round | null>(null),
    alive = useRef(true),
    inFlight = useRef(false),
    playing = useRef(false),
    epoch = useRef(0),
    starting = useRef(false),
    scheduled = useRef<ReturnType<typeof setTimeout> | null>(null),
    chat = useRef<HTMLDivElement>(null),
    follow = useRef(true),
    config = useRef(props.settings),
    revealFinish = useRef<(() => void) | null>(null),
    skipAudio = useRef(false),
    speaking = useRef(false),
    activeBot = useRef(""),
    oneShot = useRef(false),
    serverConfig = useRef(""),
    propsRef = useRef(props);
  propsRef.current = props;
  config.current = props.settings;
  function desiredConfiguration() {
    const p = propsRef.current;
    return {
      settings: p.settings,
      bots: p.state.bots,
      relationships: p.state.relationships,
      locks: p.state.relationshipLocks,
    };
  }
  function apply(next: Round) {
    if (!alive.current) return;
    const previous = current.current;
    current.current = next;
    sessionStorage.setItem("bingo-session", next.sessionId);
    setRound(next);
    playing.current = next.running;
    if (!next.running) clearSchedule();
    const desired = desiredConfiguration();
    const dirty = Boolean(
      serverConfig.current && JSON.stringify(desired) !== serverConfig.current,
    );
    if (dirty) {
      // A periodic snapshot must not erase edits while their PATCH is pending.
      propsRef.current.onSnapshot({
        ...next,
        bots: desired.bots,
        relationships: desired.relationships,
        relationshipLocks: desired.locks,
      });
    } else {
      serverConfig.current = JSON.stringify({
        settings: desired.settings,
        bots: next.bots,
        relationships: next.relationships,
        locks: next.relationshipLocks,
      });
      propsRef.current.onSnapshot(next);
    }
    if (previous && next.eliminated.length > previous.eliminated.length) {
      const names = next.bots
        .filter(
          (b) =>
            next.eliminated.includes(b.id) &&
            !previous.eliminated.includes(b.id),
        )
        .map((b) => b.name);
      setEliminationNotice(
        names.join(", ") + " was an impostor and is eliminated.",
      );
      if (config.current.sounds) sound(850);
      setTimeout(() => setEliminationNotice(""), 5000);
    }
    if (ended(next)) {
      setAccuseSquare(null);
      setAccuseTouch(false);
      epoch.current++;
      cancelSpeech();
      revealFinish.current?.();
      setRevealed(10000);
      setStatus(next.status === "won" ? "Victory" : "Round lost");
      if (previous && !ended(previous) && config.current.sounds)
        sound(next.status === "won" ? 980 : 220);
    } else if (!inFlight.current && !speaking.current)
      setStatus(
        next.status === "waiting_for_speaker"
          ? "Choose the next speaker"
          : next.running
            ? "Live"
            : "Paused",
      );
  }
  function clearSchedule() {
    if (scheduled.current) clearTimeout(scheduled.current);
    scheduled.current = null;
  }
  useEffect(() => {
    alive.current = true;
    void (async () => {
      try {
        let result: Round;
        if (props.state.sessionId)
          result =
            sessionStorage.getItem("bingo-session") === props.state.sessionId
              ? await api("rounds/" + props.state.sessionId + "/control", {
                  action: "restore",
                })
              : await api("rounds/" + props.state.sessionId + "/fork", {});
        else
          result = await api("rounds", {
            state: props.state,
            settings: props.settings,
            requestId: setupKey.current,
          });
        serverConfig.current = JSON.stringify({
          settings: props.settings,
          bots: result.bots,
          relationships: result.relationships,
          locks: result.relationshipLocks,
        });
        apply(result);
      } catch (e) {
        propsRef.current.onError((e as Error).message);
        setStatus("Unable to open this round");
      }
    })();
    return () => {
      alive.current = false;
      playing.current = false;
      epoch.current++;
      clearSchedule();
      cancelSpeech();
      revealFinish.current?.();
    };
  }, []);
  // UI polling only displays time; Python's monotonic clock decides losses, even in background tabs.
  useEffect(() => {
    const poll = setInterval(() => {
      if (!current.current) return;
      void api("rounds/" + current.current.sessionId)
        .then((r: Round) => {
          apply(r);
          if (
            !scheduled.current &&
            !inFlight.current &&
            r.running &&
            !r.awaitingPlayback &&
            !r.generating
          )
            schedule();
        })
        .catch((e) => propsRef.current.onError(e.message));
    }, 1000);
    return () => clearInterval(poll);
  }, []);
  const signature = JSON.stringify({
    settings: props.settings,
    bots: props.state.bots,
    relationships: props.state.relationships,
    locks: props.state.relationshipLocks,
  });
  useEffect(() => {
    if (!current.current || signature === serverConfig.current) return;
    const timer = setTimeout(() => {
      const baseline = JSON.parse(serverConfig.current || "{}");
      const relationshipEdits = Object.fromEntries(
        Object.entries(props.state.relationships).filter(
          ([key, value]) => baseline.relationships?.[key] !== value,
        ),
      );
      const lockEdits = Object.fromEntries(
        Object.entries(props.state.relationshipLocks).filter(
          ([key, value]) => baseline.locks?.[key] !== value,
        ),
      );
      void api(
        "rounds/" + current.current!.sessionId,
        {
          settings: props.settings,
          bots: props.state.bots,
          relationships: relationshipEdits,
          relationshipLocks: lockEdits,
        },
        "PATCH",
      )
        .then((r: Round) => {
          serverConfig.current = signature;
          apply(r);
          if (
            r.running &&
            !inFlight.current &&
            !r.awaitingPlayback &&
            (!r.settings.manualSpeaker || r.questionQueue.length)
          )
            schedule();
        })
        .catch((e) => propsRef.current.onError(e.message));
    }, 250);
    return () => clearTimeout(timer);
  }, [signature, round?.sessionId]);
  useEffect(() => {
    if (follow.current && chat.current)
      chat.current.scrollTop = chat.current.scrollHeight;
  }, [round?.messages.length, revealed, status]);
  async function control(action: string) {
    if (!current.current) return null;
    const r: Round = await api(
      "rounds/" + current.current.sessionId + "/control",
      { action },
    );
    apply(r);
    return r;
  }
  function schedule() {
    clearSchedule();
    const r = current.current;
    if (
      !r?.running ||
      ended(r) ||
      r.awaitingPlayback ||
      r.generating ||
      inFlight.current
    )
      return;
    if (
      config.current.manualSpeaker &&
      !r.questionQueue.length &&
      !r.pollPending
    ) {
      setStatus("Choose the next speaker");
      return;
    }
    const delay =
      r.settings.tts && r.settings.autoSpeak
        ? 400
        : Math.max(
            700,
            Math.min(14000, (r.messages.at(-1)?.message.length || 100) * 28) /
              Math.max(0.1, r.settings.speed),
          );
    scheduled.current = setTimeout(() => void next(), delay);
  }
  async function reveal(text: string, token: number) {
    let count = 0;
    setRevealed(0);
    await new Promise<void>((resolve) => {
      const interval = setInterval(() => {
        if (token !== epoch.current || count >= text.length) {
          clearInterval(interval);
          resolve();
          return;
        }
        count += Math.ceil(4 * Math.max(0.1, config.current.speed));
        setRevealed(count);
      }, 16);
      revealFinish.current = () => {
        clearInterval(interval);
        setRevealed(10000);
        resolve();
      };
    });
  }
  async function next(botId?: string) {
    const r = current.current;
    if (
      !r ||
      !r.running ||
      ended(r) ||
      inFlight.current ||
      r.generating ||
      r.awaitingPlayback
    )
      return;
    if (
      config.current.manualSpeaker &&
      !botId &&
      !r.questionQueue.length &&
      !r.pollPending
    ) {
      clearSchedule();
      setStatus("Choose the next speaker");
      return;
    }
    clearSchedule();
    inFlight.current = true;
    setBusy(true);
    skipAudio.current = false;
    const token = epoch.current;
    setStatus(r.pollPending ? "Taking a poll…" : "Thinking");
    propsRef.current.onError("");
    try {
      const result: Round = r.pollPending
        ? await api("rounds/" + r.sessionId + "/poll", {})
        : await api("turn", {
            sessionId: r.sessionId,
            botId: botId || (r.settings.manualSpeaker ? "random" : undefined),
            requestId: crypto.randomUUID(),
          });
      if (!alive.current || token !== epoch.current) return;
      apply({ ...result, generating: false });
      if (ended(result)) return;
      const latest = result.messages.at(-1);
      if (!r.pollPending && latest?.kind === "dialogue") {
        activeBot.current = latest.botId;
        setStatus("Reading");
        await reveal(latest.message, token);
        if (token !== epoch.current) return;
        const bot = result.bots.find((b) => b.id === latest.botId);
        if (bot && playing.current && !skipAudio.current) {
          speaking.current = true;
          await speak(latest.message, bot, config.current, setStatus);
          speaking.current = false;
        }
        if (token !== epoch.current) return;
        await control("complete");
        if (oneShot.current) {
          oneShot.current = false;
          await control("pause");
        }
      } else setStatus("Poll results ready");
    } catch (e) {
      propsRef.current.onError((e as Error).message);
      playing.current = false;
      setStatus("Needs attention");
      try {
        await control("pause");
      } catch {
        /* Original error remains visible. */
      }
    } finally {
      inFlight.current = false;
      speaking.current = false;
      if (current.current)
        current.current = { ...current.current, generating: false };
      setBusy(false);
      if (alive.current) {
        if (current.current?.running) schedule();
        else if (!ended(current.current)) setStatus("Paused");
      }
    }
  }
  async function start() {
    if (starting.current || ended(current.current)) return;
    starting.current = true;
    try {
      resumeSpeech();
      if (current.current) {
        const synced: Round = await api(
          "rounds/" + current.current.sessionId,
          { settings: config.current },
          "PATCH",
        );
        apply(synced);
      }
      const r = await control("start");
      if (r && !inFlight.current && !r.awaitingPlayback) {
        if (
          r.settings.manualSpeaker &&
          !r.questionQueue.length &&
          !r.pollPending
        )
          setStatus("Choose the next speaker");
        else void next();
      }
    } catch (e) {
      props.onError((e as Error).message);
    } finally {
      starting.current = false;
    }
  }
  async function pause() {
    clearSchedule();
    pauseSpeech();
    if (config.current.stopOnPause) cancelSpeech();
    try {
      await control("pause");
      setStatus("Paused");
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  async function stop() {
    epoch.current++;
    clearSchedule();
    revealFinish.current?.();
    cancelSpeech();
    setRevealed(10000);
    try {
      await control("stop");
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  function skip() {
    skipAudio.current = true;
    revealFinish.current?.();
    setRevealed(10000);
    cancelSpeech();
  }
  async function choose(botId: string, single = false) {
    oneShot.current = single;
    if (!playing.current) {
      try {
        await control("start");
      } catch (e) {
        props.onError((e as Error).message);
        return;
      }
    }
    void next(botId);
  }
  async function mark(index: number) {
    if (!round || ended(round)) return;
    if (accuseTouch && round.mode === "impostor") {
      void openAccusation(index);
      return;
    }
    try {
      const r: Round = await api("rounds/" + round.sessionId + "/mark", {
        index,
      });
      apply(r);
      if (r.marked[index] && config.current.sounds) sound();
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  async function openAccusation(index: number) {
    if (!round || round.mode !== "impostor" || ended(round)) return;
    setSuspect("");
    setAccuseSquare(index);
    try {
      await control("accusation_open");
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  async function accuse() {
    if (!round || accuseSquare === null || !suspect) return;
    try {
      const r: Round = await api("rounds/" + round.sessionId + "/accuse", {
        index: accuseSquare,
        botId: suspect,
      });
      setAccuseSquare(null);
      setAccuseTouch(false);
      apply(r);
      if (r.eliminated.includes(activeBot.current)) skip();
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  async function cancelAccusation() {
    setAccuseSquare(null);
    try {
      await control("accusation_close");
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  async function ask() {
    if (!round || !question.trim()) return;
    try {
      const r: Round = await api("rounds/" + round.sessionId + "/question", {
        text: question,
        target,
      });
      apply(r);
      setQuestion("");
      if (r.running && !inFlight.current && !r.awaitingPlayback) schedule();
    } catch (e) {
      props.onError((e as Error).message);
    }
  }
  function replyTo(id: string) {
    const node = document.getElementById("message-" + id);
    node?.scrollIntoView({
      behavior: config.current.reduced ? "auto" : "smooth",
      block: "center",
    });
    setReplyHighlight(id);
    setTimeout(() => setReplyHighlight(""), 1800);
  }
  const winLines = lines(round?.marked || Array(25).fill(false)),
    winCells = new Set(winLines.flat());
  const lastSpeaker = round?.messages
    .filter((m) => m.kind === "dialogue")
    .at(-1)?.botId;
  if (!round)
    return (
      <main className="game">
        <section className="panel padded">
          <h2>{status}</h2>
          <p>
            Preparing an isolated local round. Your roles and evidence stay in
            Python.
          </p>
          <button className="btn" onClick={props.onReplay}>
            Back to setup
          </button>
        </section>
      </main>
    );
  return (
    <main className="game">
      <div className="game-heading">
        <div>
          <span className="eyebrow">
            {round.mode === "impostor"
              ? "THE IMPOSTOR"
              : round.mode === "chaos"
                ? "CHAOS PARTY"
                : "NORMAL PARTY"}
          </span>
          <h1>Let the takes fly.</h1>
          <p>
            {round.topic} · {round.bots.length - round.eliminated.length} active
            bots · {round.completedLines} / {round.requiredLines} bingo lines
            {round.mode === "impostor"
              ? ` · ${round.eliminated.length} / ${round.impostorCount} impostors eliminated`
              : ""}
          </p>
        </div>
        <div className="button-row">
          {round.timerRemaining !== null && (
            <div
              className={
                "timer-badge " + (round.timerRemaining <= 30 ? "urgent" : "")
              }
              aria-label="Game timer"
            >
              <Timer size={16} />
              {formatTime(round.timerRemaining)}
            </div>
          )}
          <button className="btn" onClick={() => props.onPanel("stats")}>
            <BarChart3 size={16} />
            Stats
          </button>
          <button
            className="btn"
            onClick={() => props.onPanel("relationships")}
          >
            <Users size={16} />
            Crew
          </button>
          <button className="btn" onClick={props.onSave}>
            <Save size={16} />
            Save
          </button>
        </div>
      </div>
      {eliminationNotice && (
        <section className="elimination-notice" role="status">
          <Flag size={18} />
          {eliminationNotice}
        </section>
      )}
      {ended(round) && (
        <section className={"round-result " + round.status} role="status">
          <ShieldCheck size={30} />
          <div>
            <h2>{round.status === "won" ? "You won!" : "Round lost"}</h2>
            <p>{round.resultReason}</p>
          </div>
          <button className="btn" onClick={props.onReplay}>
            Replay topic
          </button>
          <button className="btn" onClick={props.onNew}>
            New party
          </button>
        </section>
      )}
      <div className="game-layout">
        <section className="panel conversation">
          <div className="panel-header">
            <div>
              <MessageCircle size={18} />
              <h3>The conversation</h3>
            </div>
            <span className="status">
              <span className={round.running ? "live-dot" : "idle-dot"} />
              {status}
            </span>
          </div>
          <div className="cast-strip">
            {round.bots.map((b) => (
              <span
                key={b.id}
                style={{
                  color: b.color,
                  opacity: round.eliminated.includes(b.id) ? 0.4 : 1,
                }}
              >
                <span
                  aria-hidden="true"
                  className="mini-avatar"
                  style={{ background: b.color + "25" }}
                >
                  {b.name.slice(0, 1)}
                </span>
                {b.name}
                {round.eliminated.includes(b.id)
                  ? " · eliminated impostor"
                  : speaking.current && activeBot.current === b.id
                    ? " · speaking"
                    : ""}
              </span>
            ))}
          </div>
          <div
            className="chat"
            ref={chat}
            onScroll={() => {
              const el = chat.current!;
              follow.current =
                el.scrollHeight - el.scrollTop - el.clientHeight < 65;
            }}
          >
            {!round.messages.length && (
              <div className="empty-chat">
                <span className="empty-icon">
                  <MessageCircle size={36} />
                </span>
                <h2>The crew is waiting.</h2>
                <p>
                  Press Start. Listen carefully: an unmentioned square loses the
                  round.
                </p>
              </div>
            )}
            {round.messages.map((m, i) => {
              const original = m.replyToMessageId
                ? round.messages.find((x) => x.id === m.replyToMessageId)
                : null;
              return (
                <article
                  id={"message-" + m.id}
                  key={m.id || i}
                  className={
                    "message " +
                    (m.id === replyHighlight ? "reply-highlight" : "")
                  }
                  style={{ "--bot": m.color } as React.CSSProperties}
                >
                  {m.chaosEvent && config.current.showChaos && (
                    <div className="chaos-note">
                      <Zap size={13} />
                      {m.chaosEvent}
                    </div>
                  )}
                  <span className="avatar">{m.name.slice(0, 1)}</span>
                  <div className="message-body">
                    {original && (
                      <button
                        className="reply-reference"
                        onClick={() => replyTo(original.id!)}
                      >
                        ↳ Replying to {original.name}
                        <small>
                          {original.message.slice(0, 65)}
                          {original.message.length > 65 ? "…" : ""}
                        </small>
                      </button>
                    )}
                    <div className="message-meta">
                      <strong>{m.name}</strong>
                      <span>{m.personality}</span>
                      <small>#{i + 1}</small>
                    </div>
                    <p>
                      {i === round.messages.length - 1 && m.kind === "dialogue"
                        ? m.message.slice(0, revealed)
                        : m.message}
                    </p>
                  </div>
                </article>
              );
            })}
            {round.polls.map((p) => (
              <section className="poll-card" key={p.id}>
                <span className="eyebrow">{p.creatorName} CREATED A POLL</span>
                <h3>{p.question}</h3>
                {p.options.map((option, i) => (
                  <div key={i} className="poll-option">
                    <strong>
                      {option} · {p.totals[i]} votes
                    </strong>
                    <p>
                      {p.votes
                        .filter((v) => v.option === i)
                        .map((v) => v.name)
                        .join(", ") || "No votes"}
                    </p>
                    {p.votes
                      .filter((v) => v.option === i)
                      .map((v) => (
                        <small key={v.botId}>
                          {v.name}: {v.explanation}
                        </small>
                      ))}
                  </div>
                ))}
              </section>
            ))}
          </div>
          <div className="playback">
            <button
              disabled={ended(round)}
              className="btn primary"
              onClick={() => void (round.running ? pause() : start())}
            >
              {round.running ? <Pause size={17} /> : <Play size={17} />}{" "}
              {round.running
                ? "Pause"
                : round.messages.length
                  ? "Resume"
                  : "Start"}
            </button>
            <button
              className="icon"
              title="Next bot"
              disabled={busy || round.awaitingPlayback || ended(round)}
              onClick={() =>
                void choose("random", !round.settings.manualSpeaker)
              }
            >
              <SkipForward size={19} />
            </button>
            <button className="icon" title="Skip message" onClick={skip}>
              <ArrowRight size={19} />
            </button>
            <button className="icon" title="Stop" onClick={() => void stop()}>
              <Square size={16} />
            </button>
            <div className="speed">
              <span>PACE</span>
              <select
                aria-label="Conversation pace"
                value={config.current.speed}
                onChange={(e) =>
                  props.onSettings({ speed: Number(e.target.value) })
                }
              >
                {[0.5, 1, 1.5, 2, 3].map((n) => (
                  <option key={n} value={n}>
                    {n}×
                  </option>
                ))}
              </select>
            </div>
            <button
              className="icon"
              title="Toggle speech"
              onClick={() => {
                props.onSettings({ tts: !config.current.tts });
                cancelSpeech();
              }}
            >
              <Volume2 size={19} />
            </button>
          </div>
          <div className="speaker-panel">
            <div>
              <span className="eyebrow">
                {round.settings.manualSpeaker
                  ? "WHO SPEAKS NEXT?"
                  : "NEXT TURN CONTROLS"}
              </span>
              <button
                className={"btn " + (round.forceNextSubject ? "primary" : "")}
                disabled={ended(round) || busy}
                onClick={() =>
                  void control("force_subject").catch((e) =>
                    props.onError(e.message),
                  )
                }
              >
                <Shuffle size={14} /> Change subject next turn
                {round.forceNextSubject ? " · ON" : ""}
              </button>
            </div>
            {round.settings.manualSpeaker && (
              <div className="speaker-buttons">
                {round.bots
                  .filter(
                    (b) =>
                      !round.eliminated.includes(b.id) && b.id !== lastSpeaker,
                  )
                  .map((b) => (
                    <button
                      disabled={busy || round.awaitingPlayback || ended(round)}
                      className="btn"
                      key={b.id}
                      onClick={() => void choose(b.id)}
                    >
                      <span
                        aria-hidden="true"
                        className="mini-avatar"
                        style={{ background: b.color + "25", color: b.color }}
                      >
                        {b.name.slice(0, 1)}
                      </span>
                      {b.name}
                    </button>
                  ))}
                <button
                  className="btn"
                  disabled={busy || round.awaitingPlayback || ended(round)}
                  onClick={() => void choose("random")}
                >
                  <Shuffle size={14} />
                  RANDOM
                </button>
              </div>
            )}
          </div>
          <form
            className="question-form"
            onSubmit={(e) => {
              e.preventDefault();
              void ask();
            }}
          >
            <label>
              ASK THE BOTS
              <input
                maxLength={600}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Which character design do you like most?"
                disabled={ended(round)}
              />
            </label>
            <div>
              <select
                aria-label="Question recipient"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              >
                <option value="all">All bots</option>
                {round.bots
                  .filter((b) => !round.eliminated.includes(b.id))
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
              </select>
              <button
                className="btn"
                disabled={ended(round) || !question.trim()}
                type="submit"
              >
                Ask
              </button>
            </div>
            {round.questionQueue.length > 0 && (
              <small>
                {round.questionQueue.length} individual answers queued · Resume
                to hear them
              </small>
            )}
          </form>
        </section>
        <section className="panel bingo">
          <div className="panel-header">
            <div>
              <Dices size={19} />
              <h3>Your bingo card</h3>
            </div>
            <span className="line-count">
              {round.completedLines} / {round.requiredLines}
              <small>LINES</small>
            </span>
          </div>
          <div className="bingo-letters">
            {"BINGO".split("").map((l) => (
              <span key={l}>{l}</span>
            ))}
          </div>
          <div className="bingo-grid">
            {round.board.map((n, i) => (
              <button
                key={i}
                className={
                  "square " +
                  (round.marked[i] ? "marked " : "") +
                  (round.flagged[i] ? "flagged " : "") +
                  (winCells.has(i) ? "win" : "")
                }
                disabled={ended(round)}
                aria-pressed={round.marked[i]}
                onClick={() => void mark(i)}
                onContextMenu={(e) => {
                  e.preventDefault();
                  if (round.mode === "impostor") void openAccusation(i);
                }}
              >
                <small>{String(i + 1).padStart(2, "0")}</small>
                {round.marked[i] && (
                  <Check className="square-check" size={15} />
                )}
                <span>{n}</span>
                {round.flagged[i] && <Flag size={15} />}
              </button>
            ))}
          </div>
          <div className="bingo-progress">
            <span>{round.marked.filter(Boolean).length} / 25 marked</span>
            <span>Listen. Decide. Mark.</span>
          </div>
          <p className="bingo-rule">
            {round.mode === "impostor"
              ? "Left-click: trust an innocent mention. Right-click: accuse a specific deceptive bot."
              : "Only mark an entry after a bot mentions it. A wrong mark loses immediately."}
          </p>
          {round.mode === "impostor" && (
            <div className="impostor-progress">
              <span>
                {round.eliminated.length} / {round.impostorCount} impostors
                eliminated
              </span>
              <button
                className={"btn " + (accuseTouch ? "primary" : "")}
                disabled={ended(round)}
                onClick={() => setAccuseTouch(!accuseTouch)}
              >
                <Flag size={14} />
                {accuseTouch ? "Tap a square to accuse" : "Accuse (touch)"}
              </button>
            </div>
          )}
          <div className="board-actions">
            <button className="btn" onClick={props.onExport}>
              <Download size={15} />
              Export board
            </button>
            <button className="btn" onClick={props.onReplay}>
              <RotateCcw size={15} />
              Replay / new board
            </button>
          </div>
        </section>
      </div>
      <footer className="game-footer">
        <span>
          Local Ollama · {config.current.model} · {round.mode} mode
        </span>
        <div>
          <button onClick={props.onNew}>New party</button>
          <button onClick={props.onLoad}>Load game</button>
        </div>
      </footer>
      {accuseSquare !== null && (
        <div className="overlay">
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label="Who was the impostor?"
          >
            <h2>Who was the impostor?</h2>
            <p>
              Selected square: <strong>{round.board[accuseSquare]}</strong>
            </p>
            <p className="help">
              Choose the specific bot who made a deliberate deceptive mention.
              An incorrect accusation loses immediately.
            </p>
            <div className="suspect-list">
              {round.bots
                .filter((b) => !round.eliminated.includes(b.id))
                .map((b) => (
                  <button
                    className={
                      "suspect " + (suspect === b.id ? "selected" : "")
                    }
                    key={b.id}
                    onClick={() => setSuspect(b.id)}
                  >
                    <span
                      className="avatar"
                      style={{ "--bot": b.color } as React.CSSProperties}
                    >
                      {b.name.slice(0, 1)}
                    </span>
                    <span>
                      {b.name}
                      <small>{b.personality}</small>
                    </span>
                  </button>
                ))}
            </div>
            <div className="button-row">
              <button
                className="btn primary"
                disabled={!suspect}
                onClick={() => void accuse()}
              >
                Confirm accusation
              </button>
              <button className="btn" onClick={() => void cancelAccusation()}>
                Cancel
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}
