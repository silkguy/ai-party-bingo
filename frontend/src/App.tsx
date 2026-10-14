import { useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronDown,
  Dices,
  Download,
  Expand,
  MessageCircle,
  Pause,
  Play,
  RotateCcw,
  Settings as Gear,
  Shuffle,
  SkipForward,
  Sparkles,
  Square,
  Volume2,
  X,
  Zap,
  Timer,
  Save,
  BarChart3,
  Users,
  Lock,
  Unlock,
} from "lucide-react";
import {
  defaults,
  initial,
  type Bot,
  type Entry,
  type Message,
  type Settings,
  type State,
} from "./types";
import { lines, restore, shuffled } from "./game";
import { cancelSpeech, sound } from "./speech";
import { formatTime, timerDuration } from "./timer";
import { api } from "./api";
import ModeSelector from "./components/ModeSelector";
import Relationships from "./components/Relationships";
import RoundRoom from "./components/RoundRoom";
import type { Round } from "./types";
const colors = [
  "#ae85ff",
  "#4bdacb",
  "#ff9f6e",
  "#ef7db7",
  "#79aaff",
  "#dbcc6a",
];
function Button({
  children,
  onClick,
  disabled = false,
  primary = false,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  return (
    <button
      disabled={disabled}
      className={primary ? "btn primary" : "btn"}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
function Toggle({
  label,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  value: boolean;
  disabled?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="toggle-row">
      <span>{label}</span>
      <input
        type="checkbox"
        disabled={disabled}
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
    </label>
  );
}
function Modal({
  title,
  children,
  close,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
}) {
  return (
    <div className="overlay" onClick={close}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <header>
          <h2>{title}</h2>
          <button className="icon" aria-label="Close" onClick={close}>
            <X />
          </button>
        </header>
        {children}
      </section>
    </div>
  );
}
export default function App() {
  const [state, setState] = useState<State>(() => {
    const saved = restore<State>("bingo-game", initial);
    const tabSession = sessionStorage.getItem("bingo-session");
    return Array.isArray(saved.board) &&
      saved.board.length === 25 &&
      Array.isArray(saved.bots) &&
      Array.isArray(saved.pool) &&
      Array.isArray(saved.messages)
      ? {
          ...initial,
          ...saved,
          version: 2,
          stage: tabSession
            ? 5
            : saved.version === 2
              ? saved.stage
              : saved.stage >= 4
                ? 4
                : saved.stage === 0
                  ? 0
                  : saved.stage + 1,
          sessionId:
            tabSession || (saved.version === 2 ? saved.sessionId : undefined),
          marked: saved.version === 2 ? saved.marked : Array(25).fill(false),
        }
      : initial;
  });
  const [settings, setSettings] = useState<Settings>(() => ({
    ...defaults,
    ...restore("bingo-settings", {}),
    detect: false,
    autoMark: false,
  }));
  const [catalog, setCatalog] = useState<{
    personalities: Record<string, string>;
    topics: string[];
  }>({ personalities: {}, topics: [] });
  const [modal, setModal] = useState(""),
    [tab, setTab] = useState("AI"),
    [error, setError] = useState(""),
    [health, setHealth] = useState<{
      ok: boolean;
      message: string;
      models?: string[];
    } | null>(null),
    [busy, setBusy] = useState(false),
    [poolText, setPoolText] = useState(
      state.pool.map((e) => [e.name, ...e.aliases].join(" | ")).join("\n"),
    ),
    [spinAngle, setSpinAngle] = useState(0),
    [spinCount, setSpinCount] = useState<number | null>(null),
    [spinning, setSpinning] = useState(false),
    [voices, setVoices] = useState<{ id: string; name: string }[]>([]),
    [notice, setNotice] = useState(""),
    [voiceEngineReady, setVoiceEngineReady] = useState(false),
    [roundKey, setRoundKey] = useState(0);
  const current = useRef(state),
    config = useRef(settings);
  current.current = state;
  config.current = settings;
  const winLines = lines(state.marked);
  useEffect(() => {
    try {
      localStorage.setItem("bingo-game", JSON.stringify(state));
    } catch {
      setError(
        "Browser storage is full or unavailable. Save the game to SQLite using Save.",
      );
    }
  }, [state]);
  useEffect(() => {
    try {
      localStorage.setItem("bingo-settings", JSON.stringify(settings));
    } catch {
      setError("Browser storage is unavailable; settings cannot persist here.");
    }
  }, [settings]);
  useEffect(() => {
    api("catalog")
      .then(setCatalog)
      .catch(() =>
        setError(
          "Backend unavailable. Start the Python backend using the launcher.",
        ),
      );
    void checkHealth();
    const update = () => {
      void refreshVoices();
    };
    update();
    window.speechSynthesis?.addEventListener("voiceschanged", update);
    return () => {
      window.speechSynthesis?.removeEventListener("voiceschanged", update);
      cancelSpeech();
    };
  }, []);
  useEffect(() => {
    setPoolText(
      state.pool
        .map((e) => [e.name, ...(e.aliases || [])].join(" | "))
        .join("\n"),
    );
  }, [state.pool]);
  async function refreshVoices() {
    const local = window.speechSynthesis?.getVoices() || [];
    const browser = local.map((v) => ({
      id: v.voiceURI,
      name: v.name + (v.localService ? " · local" : " · may need network"),
    }));
    try {
      const result = await api("voices");
      setVoiceEngineReady(Boolean(result.piperAvailable));
      setVoices([
        ...result.voices.map((name: string) => ({
          id: "piper:" + name,
          name:
            "Piper · " +
            (result.labels?.[name] || name) +
            (result.piperAvailable ? "" : " · engine missing"),
        })),
        ...browser,
      ]);
    } catch {
      setVoiceEngineReady(false);
      setVoices(browser);
    }
  }
  async function checkHealth() {
    try {
      setHealth(await api("health", { settings: config.current }));
    } catch {
      setHealth({
        ok: false,
        message: "Start the backend with the launcher, then retry.",
      });
    }
  }
  async function task(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }
  function patch(p: Partial<State>) {
    setState((s) => ({ ...s, ...p }));
  }
  function setting<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettings((s) => ({ ...s, [key]: value }));
  }
  function makeBots(count: number) {
    const names = shuffled(Object.keys(catalog.personalities));
    return Array.from({ length: count }, (_, i) => ({
      id: "bot_" + i,
      name: ["Nova", "Byte", "Moxie", "Echo", "Juno", "Pixel"][i],
      personality: names[i],
      description: catalog.personalities[names[i]],
      color: colors[i],
      voice: voices[i]?.id || "",
    }));
  }
  async function spin() {
    setSpinning(true);
    try {
      const result = await api("spin", undefined, "POST");
      const sector = result.count - 3;
      setSpinAngle(
        (a) => Math.floor(a / 360) * 360 + 1800 + (360 - (sector * 90 + 45)),
      );
      if (settings.sounds) sound(380);
      setTimeout(() => {
        setSpinCount(result.count);
        patch({ bots: makeBots(result.count) });
        setSpinning(false);
        if (settings.sounds) sound(800);
      }, 3600);
    } catch (e) {
      setError((e as Error).message);
      setSpinning(false);
    }
  }
  function randomBots() {
    const roles = shuffled(Object.keys(catalog.personalities));
    patch({
      bots: state.bots.map((b, i) => ({
        ...b,
        personality: roles[i],
        description: catalog.personalities[roles[i]],
      })),
    });
  }
  function editBot(index: number, p: Partial<Bot>) {
    setState((s) => ({
      ...s,
      bots: s.bots.map((b, i) => (i === index ? { ...b, ...p } : b)),
    }));
  }
  async function generatePool(regenerate = false) {
    await task(async () => {
      const topic = state.topic,
        category = state.category;
      const result = await api("pool", {
        settings,
        topic,
        category,
        regenerate,
        locked: state.pool.filter((entry) =>
          state.board.some((name, i) => state.locked[i] && name === entry.name),
        ),
      });
      if (
        current.current.topic !== topic ||
        current.current.category !== category
      )
        throw Error(
          "Topic changed while generating. Generate the pool again for the current topic.",
        );
      patch({ pool: result.entries });
      setPoolText(
        result.entries
          .map((e: Entry) => [e.name, ...e.aliases].join(" | "))
          .join("\n"),
      );
      setNotice(
        result.source +
          (result.warning ? " · " + result.warning : "") +
          ` · ${result.collectionCount} available entries`,
      );
    });
  }
  function importPool() {
    const map = new Map<string, Entry>();
    poolText.split("\n").forEach((row) => {
      const [name, ...aliases] = row.split("|").map((s) => s.trim());
      if (
        name &&
        !["name", "placeholder", "string", "character name"].includes(
          name.toLowerCase(),
        ) &&
        !map.has(name.toLowerCase())
      )
        map.set(name.toLowerCase(), { name, aliases });
    });
    patch({ pool: [...map.values()] });
    setNotice("Imported locally. Review your entries before playing.");
  }
  function generateBoard(pool = state.pool) {
    const old = current.current;
    const locked = old.board.filter(
      (_, i) => old.locked[i] && !(settings.free && i === 12),
    );
    const candidates = shuffled(
      pool.map((e) => e.name).filter((n) => !locked.includes(n)),
    );
    const needed = 25 - locked.length - (settings.free ? 1 : 0);
    if (candidates.length < needed) {
      setError(
        `Need ${needed} available unique entries. Expand or import the pool first.`,
      );
      return false;
    }
    let cursor = 0;
    const board = old.board.map((n, i) =>
      settings.free && i === 12
        ? "FREE"
        : old.locked[i]
          ? n
          : candidates[cursor++],
    );
    patch({ board, marked: board.map((_, i) => settings.free && i === 12) });
    return true;
  }
  function stop() {
    cancelSpeech();
  }
  async function fullscreen() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      setError(
        "Application fullscreen unavailable in this browser. Use F11 or your browser fullscreen menu.",
      );
    }
  }
  async function saveGame() {
    await task(async () => {
      const name = prompt("Save name", "My party");
      if (!name) return;
      if (state.sessionId)
        await api("round-saves", { sessionId: state.sessionId, name });
      else
        await api(
          "saves/game/" + encodeURIComponent(name),
          { state: current.current, settings: config.current },
          "PUT",
        );
      setNotice("Saved on this computer.");
    });
  }
  async function loadGame() {
    await task(async () => {
      const names: string[] = await api("round-saves");
      const legacy: string[] = await api("saves/game");
      const choices = [
        ...names.map((n) => "Round: " + n),
        ...legacy.map((n) => "Legacy: " + n),
      ];
      if (!choices.length) throw Error("No saves yet.");
      const choice = prompt(
        "Enter a saved game:\n" + choices.join("\n"),
        choices[0],
      );
      if (!choice) return;
      stop();
      if (choice.startsWith("Round: ")) {
        const r: Round = await api(
          "round-saves/" + encodeURIComponent(choice.slice(7)) + "/load",
          {},
        );
        sessionStorage.setItem("bingo-session", r.sessionId);
        setState({ ...initial, ...r, stage: 5 });
        setSettings({
          ...defaults,
          ...r.settings,
          detect: false,
          autoMark: false,
        });
      } else {
        sessionStorage.removeItem("bingo-session");
        const data = await api(
          "saves/game/" + encodeURIComponent(choice.replace(/^Legacy: /, "")),
        );
        if (data.state?.board?.length !== 25)
          throw Error("Invalid legacy save.");
        setState({
          ...initial,
          ...data.state,
          version: 2,
          stage: 4,
          sessionId: undefined,
          marked: Array(25).fill(false),
          messages: [],
          mode: data.state.mode || "normal",
        });
        setSettings({
          ...defaults,
          ...data.settings,
          detect: false,
          autoMark: false,
        });
        setNotice(
          "Legacy crew and board loaded. Begin a new validated round; old marks cannot be trusted under the new rules.",
        );
      }
      setRoundKey((k) => k + 1);
      setModal("");
    });
  }
  function syncRound(r: Round) {
    setState((s) => ({
      ...s,
      sessionId: r.sessionId,
      mode: r.mode,
      pool: r.pool,
      board: r.board,
      marked: r.marked,
      flagged: r.flagged,
      bots: r.bots,
      messages: r.messages,
      relationships: r.relationships,
      relationshipLocks: r.relationshipLocks,
      subject: r.subject,
      lastChaos: r.lastChaos,
      timerRemaining: r.timerRemaining,
      eliminated: r.eliminated,
      requiredLines: r.requiredLines,
    }));
  }
  function newParty() {
    sessionStorage.removeItem("bingo-session");
    if (state.sessionId)
      void api("rounds/" + state.sessionId + "/control", {
        action: "stop",
      }).catch(() => {});
    stop();
    setState({ ...initial });
    setSpinCount(null);
    setRoundKey((k) => k + 1);
    setModal("");
  }
  function replay() {
    sessionStorage.removeItem("bingo-session");
    if (state.sessionId)
      void api("rounds/" + state.sessionId + "/control", {
        action: "stop",
      }).catch(() => {});
    stop();
    patch({
      sessionId: undefined,
      stage: 4,
      messages: [],
      marked: Array(25).fill(false),
      flagged: Array(25).fill(false),
      eliminated: [],
      timerRemaining: null,
    });
    setRoundKey((k) => k + 1);
  }
  async function importKnowledge(file: File) {
    await task(async () => {
      const res = await api("knowledge/import", {
        topic: state.topic,
        content: await file.text(),
        format: file.name.toLowerCase().endsWith(".csv") ? "csv" : "json",
      });
      setNotice(
        `Imported ${res.count} sourced knowledge profiles for ${state.topic}.`,
      );
    });
  }
  async function preset(load = false) {
    await task(async () => {
      const names = load ? await api("saves/board") : [];
      const name = prompt(
        load ? "Preset to load: " + names.join(", ") : "Board preset name",
        names[0] || "My board",
      );
      if (!name) return;
      if (load) {
        const saved = await api("saves/board/" + encodeURIComponent(name));
        if (saved.board?.length !== 25) throw Error("Invalid preset");
        patch({
          board: saved.board,
          marked: saved.board.map((_: string, i: number) =>
            Boolean(saved.free && i === 12),
          ),
          locked: Array(25).fill(false),
        });
        setting("free", Boolean(saved.free));
      } else
        await api(
          "saves/board/" + encodeURIComponent(name),
          { board: state.board, free: settings.free },
          "PUT",
        );
    });
  }
  function exportBoard() {
    const canvas = document.createElement("canvas");
    canvas.width = 1000;
    canvas.height = 1100;
    const c = canvas.getContext("2d")!;
    c.fillStyle = "#121320";
    c.fillRect(0, 0, 1000, 1100);
    c.fillStyle = "#bda2ff";
    c.font = "bold 44px sans-serif";
    c.fillText("AI BINGO PARTY", 45, 65);
    c.font = "22px sans-serif";
    c.fillText(state.topic, 45, 105);
    state.board.forEach((name, i) => {
      const x = 45 + (i % 5) * 184,
        y = 140 + Math.floor(i / 5) * 184;
      c.fillStyle = state.marked[i] ? "#7652c2" : "#232538";
      c.fillRect(x, y, 174, 174);
      c.fillStyle = "white";
      c.font = "20px sans-serif";
      name
        .split(" ")
        .reduce((rows: string[], word) => {
          const last = rows.at(-1) || "";
          if ((last + " " + word).length > 13) rows.push(word);
          else if (rows.length) rows[rows.length - 1] = last + " " + word;
          else rows.push(word);
          return rows;
        }, [])
        .forEach((row, j) => c.fillText(row, x + 12, y + 65 + j * 26));
    });
    const link = document.createElement("a");
    link.download = "bingo-board.png";
    link.href = canvas.toDataURL();
    link.click();
  }
  const botCards = (
    <div className="bot-grid">
      {state.bots.map((b, i) => (
        <article
          className="bot-card"
          key={b.id}
          style={{ "--bot": b.color } as React.CSSProperties}
        >
          <div className="bot-card-top">
            <span className="avatar">{b.name.slice(0, 1)}</span>
            <input
              aria-label="Bot name"
              value={b.name}
              onChange={(e) => editBot(i, { name: e.target.value })}
            />
            <input
              aria-label="Avatar color"
              type="color"
              value={b.color}
              onChange={(e) => editBot(i, { color: e.target.value })}
            />
          </div>
          <select
            aria-label="Personality"
            value={b.personality}
            onChange={(e) =>
              editBot(i, {
                personality: e.target.value,
                description:
                  catalog.personalities[e.target.value] || b.description,
              })
            }
          >
            {Object.keys(catalog.personalities).map((p) => (
              <option key={p}>{p}</option>
            ))}
            <option>Custom</option>
          </select>
          <textarea
            aria-label="Personality description"
            rows={3}
            value={b.description}
            onChange={(e) => editBot(i, { description: e.target.value })}
          />
          <select
            aria-label="Bot voice"
            value={b.voice}
            onChange={(e) => editBot(i, { voice: e.target.value })}
          >
            <option value="">System default voice</option>
            {voices.map((v) => (
              <option key={v.id} value={v.id}>
                {v.name}
              </option>
            ))}
          </select>
          <Button
            disabled={busy}
            onClick={() =>
              void task(async () => {
                const p = await api("generate/personality", { settings });
                if (typeof p.description !== "string")
                  throw Error("Invalid personality. Retry.");
                editBot(i, {
                  personality: "Custom",
                  description: p.description,
                });
              })
            }
          >
            <Sparkles size={14} /> Generate personality
          </Button>
        </article>
      ))}
    </div>
  );
  return (
    <div
      className={
        settings.reduced || !settings.animations ? "app reduced" : "app"
      }
      style={
        {
          fontSize: settings.fontSize * settings.scale,
          "--scale": settings.scale,
        } as React.CSSProperties
      }
    >
      <header className="topbar">
        <a className="brand" href="#" onClick={(e) => e.preventDefault()}>
          <span className="logo">
            <Dices />
          </span>
          <span>
            AI BINGO <strong>PARTY</strong>
            <small>LOCAL MINDS. LOUD OPINIONS.</small>
          </span>
        </a>
        <div className="top-topic">
          <span className="live-dot" />
          {state.topic}
          <ChevronDown size={14} />
        </div>
        <div className="top-actions">
          <span
            className={"connection " + (health?.ok ? "online" : "")}
            title={health?.message}
          >
            {health?.ok ? "Ollama connected" : "Local AI offline"}
          </span>
          <button
            className="icon"
            title="Fullscreen"
            onClick={() => void fullscreen()}
          >
            <Expand size={19} />
          </button>
          <button
            className="icon"
            title="Settings"
            onClick={() => setModal("settings")}
          >
            <Gear size={19} />
          </button>
        </div>
      </header>
      {error && (
        <div className="alert" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="Dismiss">
            <X size={16} />
          </button>
        </div>
      )}
      {notice && state.stage !== 3 && (
        <div className="notice" role="status">
          {notice}
          <button
            className="icon"
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {state.stage < 5 ? (
        <main className="setup">
          <div className="steps">
            {[
              "Spin the crew",
              "Choose mode",
              "Meet your bots",
              "Pick a topic",
              "Board & rules",
            ].map((s, i) => (
              <span key={s} className={i === state.stage ? "selected" : ""}>
                {String(i + 1).padStart(2, "0")} <b>{s}</b>
              </span>
            ))}
          </div>
          {state.stage === 0 ? (
            <section className="wheel-screen">
              <span className="eyebrow">LET FATE PICK YOUR PARTY</span>
              <h1>
                A little chaos.
                <br />
                <em>A lot of personality.</em>
              </h1>
              <p>Spin for your crew. Pick a topic. Listen for your squares.</p>
              <div className="wheel-wrap">
                <span className="pointer">▼</span>
                <div
                  className="wheel"
                  style={{ transform: `rotate(${spinAngle}deg)` }}
                >
                  {[3, 4, 5, 6].map((n, i) => (
                    <span
                      key={n}
                      style={{
                        transform: `rotate(${i * 90 + 45}deg) translateY(-112px) rotate(-${i * 90 + 45}deg)`,
                      }}
                    >
                      {n}
                      <small>BOTS</small>
                    </span>
                  ))}
                  <div className="wheel-center">
                    <Dices size={36} />
                  </div>
                </div>
              </div>
              <Button
                primary
                disabled={
                  spinning || !Object.keys(catalog.personalities).length
                }
                onClick={() => void spin()}
              >
                <Dices size={18} />
                {spinning
                  ? "Picking your crew…"
                  : spinCount
                    ? `Spin again · ${spinCount} bots selected`
                    : "SPIN THE WHEEL"}
              </Button>
              {spinCount && (
                <Button onClick={() => patch({ stage: 1 })}>
                  Choose your mode <ArrowRight size={17} />
                </Button>
              )}
              <small>Four outcomes. Equal odds. Entirely local.</small>
            </section>
          ) : state.stage === 1 ? (
            <>
              <ModeSelector
                mode={state.mode}
                settings={settings}
                onMode={(mode) => patch({ mode })}
                onSettings={(p) => setSettings((s) => ({ ...s, ...p }))}
              />
              <div className="setup-footer">
                <Button onClick={() => patch({ stage: 0 })}>Back</Button>
                <Button primary onClick={() => patch({ stage: 2 })}>
                  Meet your bots <ArrowRight size={16} />
                </Button>
              </div>
            </>
          ) : state.stage === 2 ? (
            <>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">THE CAST</span>
                  <h1>Meet the group chat.</h1>
                  <p>
                    Big personalities, questionable takes. Make them your own.
                  </p>
                </div>
                <Button onClick={randomBots}>
                  <Shuffle size={16} /> Randomize all
                </Button>
              </div>
              {botCards}
              <Relationships
                bots={state.bots}
                values={state.relationships}
                locks={state.relationshipLocks}
                onChange={(relationships, relationshipLocks) =>
                  patch({ relationships, relationshipLocks })
                }
              />
              <div className="setup-footer">
                <Button onClick={() => patch({ stage: 1 })}>Back</Button>
                <Button primary onClick={() => patch({ stage: 3 })}>
                  Pick a topic <ArrowRight size={16} />
                </Button>
              </div>
            </>
          ) : state.stage === 3 ? (
            <>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">WHAT'S THE OBSESSION?</span>
                  <h1>Give them something to talk about.</h1>
                  <p>
                    The whole topic pool is fair game. Your board is only a
                    sample.
                  </p>
                </div>
              </div>
              <div className="topic-layout">
                <section className="panel padded">
                  <label>
                    Discussion topic
                    <input
                      value={state.topic}
                      onChange={(e) =>
                        patch({ topic: e.target.value, pool: [] })
                      }
                    />
                  </label>
                  <label>
                    Category
                    <input
                      value={state.category}
                      onChange={(e) =>
                        patch({ category: e.target.value, pool: [] })
                      }
                    />
                  </label>
                  <div className="chips">
                    {catalog.topics.map((t) => (
                      <button
                        className={state.topic === t ? "chip chosen" : "chip"}
                        key={t}
                        onClick={() => patch({ topic: t, pool: [] })}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                  <div className="button-row">
                    <Button
                      disabled={busy}
                      primary
                      onClick={() => void generatePool()}
                    >
                      <Sparkles size={16} />{" "}
                      {busy ? "Generating…" : "Get topic pool"}
                    </Button>
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void task(async () => {
                          const res = await api("generate/topics", {
                            settings,
                          });
                          setNotice("Suggestions: " + res.topics.join(" · "));
                        })
                      }
                    >
                      Suggest topics
                    </Button>
                  </div>
                  <p className="help">
                    Custom topics use Ollama. Curated character lists work
                    offline without generation. AI lists can contain mistakes;
                    review them.
                  </p>
                </section>
                <section className="panel padded">
                  <div className="panel-title">
                    <h3>Topic pool</h3>
                    <span>{state.pool.length} entries</span>
                  </div>
                  <textarea
                    rows={12}
                    aria-label="Topic pool import"
                    placeholder={
                      "One entry per line. Aliases after |\nEllen Joe | Ellen\nNicole Demara | Nicole"
                    }
                    value={poolText}
                    onChange={(e) => setPoolText(e.target.value)}
                  />
                  <div className="button-row">
                    <Button onClick={importPool}>Apply edited list</Button>
                    <Button
                      disabled={busy}
                      onClick={() => void generatePool(true)}
                    >
                      <RotateCcw size={14} /> Regenerate
                    </Button>
                  </div>
                  {state.pool.length < 25 && (
                    <p className="help">
                      At least 25 unique entries are needed (24 with a free
                      center). Expand the category or add entries.
                    </p>
                  )}
                  <label className="knowledge-import">
                    Import sourced knowledge (JSON/CSV)
                    <input
                      type="file"
                      accept=".json,.csv"
                      onChange={(e) => {
                        if (e.target.files?.[0])
                          void importKnowledge(e.target.files[0]);
                      }}
                    />
                  </label>
                </section>
              </div>
              {notice && <p className="help">{notice}</p>}
              <div className="setup-footer">
                <Button onClick={() => patch({ stage: 2 })}>Back</Button>
                <Button
                  primary
                  disabled={state.pool.length < (settings.free ? 24 : 25)}
                  onClick={() => {
                    if (generateBoard()) patch({ stage: 4 });
                  }}
                >
                  Build the board <ArrowRight size={16} />
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="section-heading">
                <div>
                  <span className="eyebrow">YOUR LISTENING CARD</span>
                  <h1>Make it your lucky board.</h1>
                  <p>Edit any square. Lock favorites before regenerating.</p>
                </div>
                <Button onClick={() => generateBoard()}>
                  <Shuffle size={16} /> Generate board
                </Button>
              </div>
              <div className="board-setup">
                <div className="edit-board">
                  {state.board.map((n, i) => (
                    <div key={i}>
                      <input
                        aria-label={`Square ${i + 1}`}
                        value={n}
                        disabled={settings.free && i === 12}
                        onChange={(e) =>
                          patch({
                            board: state.board.map((v, j) =>
                              i === j ? e.target.value : v,
                            ),
                          })
                        }
                      />
                      <button
                        className="icon"
                        aria-label={`Lock square ${i + 1}`}
                        onClick={() =>
                          patch({
                            locked: state.locked.map((v, j) =>
                              i === j ? !v : v,
                            ),
                          })
                        }
                      >
                        {state.locked[i] ? (
                          <Lock size={14} />
                        ) : (
                          <Unlock size={14} />
                        )}
                      </button>
                    </div>
                  ))}
                </div>
                <aside className="panel padded">
                  <h3>Your board, your rules.</h3>
                  <label>
                    Bingo win condition · required lines
                    <select
                      aria-label="Required bingo lines"
                      value={state.requiredLines}
                      onChange={(e) =>
                        patch({ requiredLines: Number(e.target.value) })
                      }
                    >
                      {Array.from({ length: 12 }, (_, i) => (
                        <option key={i + 1} value={i + 1}>
                          {i + 1} line{i ? "s" : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                  <Toggle
                    label="Enable round timer"
                    value={settings.timerEnabled}
                    onChange={(v) => setting("timerEnabled", v)}
                  />
                  {settings.timerEnabled && (
                    <label>
                      Time limit (seconds)
                      <input
                        type="number"
                        min="1"
                        value={settings.timerSeconds}
                        onChange={(e) =>
                          setting(
                            "timerSeconds",
                            Math.max(1, Number(e.target.value)),
                          )
                        }
                      />
                    </label>
                  )}
                  <Toggle
                    label="Manual next-speaker selection"
                    value={settings.manualSpeaker}
                    onChange={(v) => setting("manualSpeaker", v)}
                  />
                  <Toggle
                    label="Allow bot polls"
                    value={settings.pollsEnabled}
                    onChange={(v) => setting("pollsEnabled", v)}
                  />
                  <p className="help">
                    A wrong mark loses immediately.{" "}
                    {state.mode === "impostor"
                      ? "You also need to eliminate every impostor."
                      : "Reach the selected number of distinct lines to win."}
                  </p>
                  <Toggle
                    label="Free center square"
                    value={settings.free}
                    onChange={(v) => {
                      setting("free", v);
                      patch({
                        board: state.board.map((n, i) =>
                          i === 12 ? (v ? "FREE" : "") : n,
                        ),
                        marked: state.marked.map((m, i) => (i === 12 ? v : m)),
                      });
                    }}
                  />
                  <Button
                    onClick={() =>
                      patch({
                        board: (() => {
                          const entries = shuffled(
                            state.board.filter(
                              (_, i) => !(settings.free && i === 12),
                            ),
                          );
                          if (settings.free) entries.splice(12, 0, "FREE");
                          return entries;
                        })(),
                      })
                    }
                  >
                    Shuffle squares
                  </Button>
                  <Button
                    onClick={() =>
                      patch({
                        board: Array(25)
                          .fill("")
                          .map((n, i) =>
                            settings.free && i === 12 ? "FREE" : n,
                          ),
                        locked: Array(25).fill(false),
                      })
                    }
                  >
                    Clear for custom board
                  </Button>
                  <Button onClick={() => void preset()}>Save preset</Button>
                  <Button onClick={() => void preset(true)}>Load preset</Button>
                </aside>
              </div>
              <div className="setup-footer">
                <Button onClick={() => patch({ stage: 3 })}>Back</Button>
                <Button
                  primary
                  disabled={
                    state.board.some((n) => !n.trim()) ||
                    new Set(state.board.map((n) => n.toLowerCase().trim()))
                      .size !== 25
                  }
                  onClick={() => {
                    patch({ stage: 5 });
                  }}
                >
                  Let's party <ArrowRight size={16} />
                </Button>
              </div>
            </>
          )}
        </main>
      ) : (
        <RoundRoom
          key={roundKey}
          state={state}
          settings={settings}
          onSnapshot={syncRound}
          onError={setError}
          onSettings={(p) => setSettings((s) => ({ ...s, ...p }))}
          onPanel={setModal}
          onSave={() => void saveGame()}
          onLoad={() => void loadGame()}
          onNew={newParty}
          onReplay={replay}
          onExport={exportBoard}
        />
      )}
      {modal === "relationships" && (
        <Modal title="The crew & their chemistry" close={() => setModal("")}>
          {botCards}
          <Relationships
            bots={state.bots}
            values={state.relationships}
            locks={state.relationshipLocks}
            onChange={(relationships, relationshipLocks) =>
              patch({ relationships, relationshipLocks })
            }
          />
          {settings.clashes && settings.showRelations ? (
            <div className="relations">
              {Object.entries(state.relationships).map(([pair, score]) => (
                <div key={pair}>
                  <span>
                    {pair
                      .split("|")
                      .map((id) => state.bots.find((b) => b.id === id)?.name)
                      .join(" ↔ ")}
                  </span>
                  <meter min="-100" max="100" value={score} />
                  <b>
                    {score > 0 ? "+" : ""}
                    {score} ·{" "}
                    {score > 25
                      ? "Friends"
                      : score < -25
                        ? "Rivals"
                        : "Neutral"}
                  </b>
                </div>
              ))}
              {!Object.keys(state.relationships).length && (
                <p>Relationships develop as bots respond to each other.</p>
              )}
            </div>
          ) : (
            <p>Relationship indicators are disabled in Settings.</p>
          )}
          <Button onClick={randomBots}>Randomize personalities</Button>
        </Modal>
      )}
      {modal === "stats" && (
        <Modal title="Party statistics" close={() => setModal("")}>
          <div className="stat-grid">
            <div>
              <b>{state.messages.length}</b>Messages
            </div>
            <div>
              <b>{winLines.length}</b>Bingo lines
            </div>
            <div>
              <b>{state.messages.filter((m) => m.chaosEvent).length}</b>Chaos
              events
            </div>
          </div>
          <h3>Mic time</h3>
          {state.bots.map((b) => (
            <p key={b.id}>
              {b.name}{" "}
              <strong>
                {state.messages.filter((m) => m.botId === b.id).length} turns
              </strong>
            </p>
          ))}
        </Modal>
      )}
      {modal === "settings" && (
        <Modal title="Party settings" close={() => setModal("")}>
          <nav className="tabs">
            {[
              "AI",
              "Bots",
              "Clashes",
              "Gameplay",
              "Audio",
              "Timer",
              "Bingo",
              "Display",
              "Saves",
            ].map((t) => (
              <button
                key={t}
                className={tab === t ? "selected" : ""}
                onClick={() => setTab(t)}
              >
                {t}
              </button>
            ))}
          </nav>
          <div className="settings-content">
            {tab === "AI" && (
              <>
                <label>
                  Ollama server URL
                  <input
                    value={settings.url}
                    onChange={(e) => setting("url", e.target.value)}
                  />
                </label>
                <label>
                  Model
                  <input
                    value={settings.model}
                    onChange={(e) => setting("model", e.target.value)}
                  />
                </label>
                {Boolean(health?.models?.length) && (
                  <label>
                    Downloaded Ollama models
                    <select
                      aria-label="Downloaded Ollama models"
                      value=""
                      onChange={(e) => setting("model", e.target.value)}
                    >
                      <option value="" disabled>
                        Choose an installed model…
                      </option>
                      {health?.models?.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                <p className="help">
                  If the selected model is missing, run{" "}
                  <code>ollama pull {settings.model}</code> in a terminal and
                  wait for it to finish, or double-click install_model.bat for
                  qwen3:4b.
                </p>
                <Toggle
                  label="Enable thinking (slower; reasoning stays hidden)"
                  value={settings.thinking}
                  onChange={(v) => setting("thinking", v)}
                />
                {(
                  [
                    "temperature",
                    "maxTokens",
                    "memory",
                    "sentences",
                    "speed",
                  ] as const
                ).map((k) => (
                  <label key={k}>
                    {
                      {
                        temperature: "Temperature",
                        maxTokens: "Generation token budget",
                        memory: "Recent message memory",
                        sentences: "Sentences per turn",
                        speed: "Conversation speed",
                      }[k]
                    }
                    <input
                      type="number"
                      min={k === "temperature" ? 0 : 1}
                      max={
                        k === "sentences"
                          ? 4
                          : k === "memory"
                            ? 50
                            : k === "temperature"
                              ? 2
                              : 2000
                      }
                      step={k === "temperature" || k === "speed" ? 0.1 : 1}
                      value={settings[k]}
                      onChange={(e) => setting(k, Number(e.target.value))}
                    />
                  </label>
                ))}
                <p className="help">
                  The backend reserves at least 512 tokens for dialogue and 2048
                  for generated lists. Empty or incomplete replies get one
                  automatic retry with thinking disabled. Thinking tokens share
                  the generation budget, so leave thinking off for faster
                  conversation.
                </p>
                <h3>Conversation direction weights</h3>
                {["Continue subject", "Respond to a bot", "New subject"].map(
                  (n, i) => (
                    <label key={n}>
                      {n}
                      <input
                        type="number"
                        min="0"
                        value={settings.weights[i]}
                        onChange={(e) =>
                          setting(
                            "weights",
                            settings.weights.map((w, j) =>
                              i === j ? Math.max(0, Number(e.target.value)) : w,
                            ),
                          )
                        }
                      />
                    </label>
                  ),
                )}
                <Button onClick={() => void checkHealth()}>
                  Check Ollama / Retry
                </Button>
                <p className="help">{health?.message}</p>
                <code>
                  ollama serve
                  <br />
                  ollama pull qwen3:4b
                </code>
              </>
            )}
            {tab === "Bots" && (
              <>
                <p className="help">
                  For three extra English voices, run install_english_voices.bat
                  once, restart the game, then choose Piper · Lessac, Ryan or
                  Alan below.
                </p>
                <Button onClick={() => void refreshVoices()}>
                  <RotateCcw size={14} /> Refresh voices
                </Button>
                {botCards}
                <Button onClick={randomBots}>
                  Randomize all personalities
                </Button>
              </>
            )}
            {tab === "Clashes" && (
              <>
                <Toggle
                  label="Personality clashes"
                  value={settings.clashes}
                  onChange={(v) => setting("clashes", v)}
                />
                <Toggle
                  label="Show relationship indicators"
                  value={settings.showRelations}
                  onChange={(v) => setting("showRelations", v)}
                />
                <label>
                  Relationship intensity
                  <input
                    type="range"
                    min="0"
                    max="3"
                    step=".1"
                    value={settings.intensity}
                    onChange={(e) =>
                      setting("intensity", Number(e.target.value))
                    }
                  />
                </label>
                <Button
                  onClick={() =>
                    patch({
                      relationships: Object.fromEntries(
                        Object.keys(state.relationships).map((key) => [key, 0]),
                      ),
                    })
                  }
                >
                  Reset relationships
                </Button>
                <p className="help">
                  Scores reflect model-reported agreement with the previous
                  speaker and are clamped to −100…100. They influence future
                  prompts.
                </p>
              </>
            )}
            {tab === "Gameplay" && (
              <>
                <p className="help">
                  Current mode: {state.mode}. Modes, required lines, and timer
                  limits are chosen before a round.
                </p>
                <Toggle
                  label="Manual Speaker Selection"
                  value={settings.manualSpeaker}
                  onChange={(v) => setting("manualSpeaker", v)}
                />
                <Toggle
                  label="Allow Bot Polls"
                  value={settings.pollsEnabled}
                  onChange={(v) => setting("pollsEnabled", v)}
                />
                <Toggle
                  label="Show chaos notifications"
                  value={settings.showChaos}
                  onChange={(v) => setting("showChaos", v)}
                />
                <h3>Subject transition weights</h3>
                {[
                  "Related subject",
                  "Weaker connection",
                  "Different subject",
                ].map((n, i) => (
                  <label key={n}>
                    {n}
                    <input
                      type="number"
                      min="0"
                      value={settings.transitionWeights[i]}
                      onChange={(e) =>
                        setting(
                          "transitionWeights",
                          settings.transitionWeights.map((w, j) =>
                            i === j ? Math.max(0, Number(e.target.value)) : w,
                          ),
                        )
                      }
                    />
                  </label>
                ))}
              </>
            )}
            {tab === "Timer" && (
              <>
                <Toggle
                  disabled={Boolean(state.sessionId)}
                  label="Enable game timer"
                  value={settings.timerEnabled}
                  onChange={(v) => {
                    if (!state.sessionId) setting("timerEnabled", v);
                  }}
                />
                <p className="help">
                  The timer is optional and configured before the round. Python
                  tracks elapsed time; pausing freezes it. Expiration before
                  victory is an immediate loss. Mid-round limits cannot be
                  changed.
                </p>
                <div className="timer-fields">
                  {["Hours", "Minutes", "Seconds"].map((label, i) => {
                    const values = [
                      Math.floor(settings.timerSeconds / 3600),
                      Math.floor((settings.timerSeconds % 3600) / 60),
                      settings.timerSeconds % 60,
                    ];
                    return (
                      <label key={label}>
                        {label}
                        <input
                          aria-label={"Timer " + label.toLowerCase()}
                          type="number"
                          min="0"
                          step="1"
                          disabled={Boolean(state.sessionId)}
                          value={values[i]}
                          onChange={(e) => {
                            values[i] = Math.max(
                              0,
                              Math.floor(Number(e.target.value) || 0),
                            );
                            setting(
                              "timerSeconds",
                              timerDuration(
                                ...(values as [number, number, number]),
                              ),
                            );
                          }}
                        />
                      </label>
                    );
                  })}
                </div>
                <p className="help">
                  Configured duration: {formatTime(settings.timerSeconds)} ·
                  Remaining:{" "}
                  {formatTime(state.timerRemaining ?? settings.timerSeconds)}
                </p>
              </>
            )}
            {tab === "Audio" && (
              <>
                <p className="help">
                  Three additional offline English voices: Lessac (US), Ryan
                  (US), Alan (UK). On Windows, double-click
                  install_english_voices.bat once, then restart the game and
                  refresh your browser. Assign the new voices under Bots.{" "}
                  {voiceEngineReady
                    ? "Piper engine is installed."
                    : "Piper engine is not installed yet; browser voices remain available."}
                </p>
                <Button onClick={() => void refreshVoices()}>
                  <RotateCcw size={14} /> Refresh voices
                </Button>
                <Toggle
                  label="Enable speech"
                  value={settings.tts}
                  onChange={(v) => {
                    setting("tts", v);
                    cancelSpeech();
                  }}
                />
                <label>
                  Speech engine
                  <select
                    value={settings.engine}
                    onChange={(e) => setting("engine", e.target.value)}
                  >
                    <option value="auto">
                      Auto (selected Piper voice, otherwise browser)
                    </option>
                    <option value="piper">Piper with browser fallback</option>
                    <option value="browser">Browser</option>
                  </select>
                </label>
                {(["rate", "volume", "pitch"] as const).map((k) => (
                  <label key={k}>
                    {k} · {settings[k]}
                    <input
                      type="range"
                      min={k === "volume" ? 0 : 0.5}
                      max={k === "volume" ? 1 : 2}
                      step=".05"
                      disabled={k === "pitch" && settings.engine === "piper"}
                      value={settings[k]}
                      onChange={(e) => setting(k, Number(e.target.value))}
                    />
                  </label>
                ))}
                <p className="help">
                  Piper does not support pitch changes. Browser voices vary by
                  OS; choose a voice labeled local for offline use. Voice
                  assignments are in Bots.
                </p>
                <Toggle
                  label="Automatically speak new messages"
                  value={settings.autoSpeak}
                  onChange={(v) => setting("autoSpeak", v)}
                />
                <Toggle
                  label="Cancel speech on pause (off: pause/resume audio)"
                  value={settings.stopOnPause}
                  onChange={(v) => setting("stopOnPause", v)}
                />
                <Toggle
                  label="Sound effects"
                  value={settings.sounds}
                  onChange={(v) => setting("sounds", v)}
                />
              </>
            )}
            {tab === "Bingo" && (
              <>
                <p className="help">
                  Required lines: {state.requiredLines}. Board rules are locked
                  after starting. Mentions are validated privately; eligible
                  squares are never highlighted or auto-marked.
                </p>
                {!state.sessionId && (
                  <Toggle
                    label="Free center (updates center square)"
                    value={settings.free}
                    onChange={(v) => {
                      setting("free", v);
                      patch({
                        board: state.board.map((n, i) =>
                          i === 12
                            ? v
                              ? "FREE"
                              : state.pool.find(
                                  (p) => !state.board.includes(p.name),
                                )?.name || ""
                            : n,
                        ),
                        marked: state.marked.map((m, i) => (i === 12 ? v : m)),
                      });
                    }}
                  />
                )}
                <Toggle
                  label="Bingo celebrations"
                  value={settings.animations}
                  onChange={(v) => setting("animations", v)}
                />
                <Button onClick={() => void preset()}>Save board preset</Button>
                {!state.sessionId && (
                  <Button onClick={() => void preset(true)}>
                    Load board preset
                  </Button>
                )}
              </>
            )}
            {tab === "Display" && (
              <>
                <Toggle
                  label="Reduced motion"
                  value={settings.reduced}
                  onChange={(v) => setting("reduced", v)}
                />
                <label>
                  Font size
                  <input
                    type="range"
                    min="13"
                    max="20"
                    value={settings.fontSize}
                    onChange={(e) =>
                      setting("fontSize", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  UI scale
                  <input
                    type="range"
                    min=".8"
                    max="1.2"
                    step=".05"
                    value={settings.scale}
                    onChange={(e) => setting("scale", Number(e.target.value))}
                  />
                </label>
                <Button onClick={() => void fullscreen()}>
                  Toggle fullscreen
                </Button>
                <p className="help">
                  F11 remains a browser shortcut. Escape exits application
                  fullscreen.
                </p>
              </>
            )}
            {tab === "Saves" && (
              <>
                <p className="help">
                  Progress and settings restore automatically after refresh.
                  Playback restores paused. Named saves are kept in local
                  SQLite.
                </p>
                <Button onClick={saveGame}>Save game</Button>
                <Button onClick={loadGame}>Load game</Button>
                <Button onClick={exportBoard}>Export board as PNG</Button>
              </>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}
