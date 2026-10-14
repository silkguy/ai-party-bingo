import { ShieldCheck, Zap, ScanEye } from "lucide-react";
import type { GameMode, Settings } from "../types";
export default function ModeSelector({
  mode,
  settings,
  onMode,
  onSettings,
}: {
  mode: GameMode;
  settings: Settings;
  onMode: (mode: GameMode) => void;
  onSettings: (settings: Partial<Settings>) => void;
}) {
  return (
    <>
      <div className="section-heading">
        <div>
          <span className="eyebrow">CHOOSE THE RULES</span>
          <h1>Three ways to party.</h1>
          <p>Your mode stays fixed for this round.</p>
        </div>
      </div>
      <div className="mode-grid">
        {(
          [
            {
              id: "normal",
              name: "Normal",
              icon: ShieldCheck,
              description:
                "Personality-driven conversation. Listen carefully: marking an unmentioned square loses the round.",
            },
            {
              id: "chaos",
              name: "Chaos",
              icon: Zap,
              description:
                "The same bingo rules, with arguments, rankings, alliances and unpredictable twists.",
            },
            {
              id: "impostor",
              name: "The Impostor",
              icon: ScanEye,
              description:
                "Hidden liars are in your crew. Trust innocent mentions, accuse deliberate lies, and eliminate every impostor.",
            },
          ] as const
        ).map((m) => (
          <button
            key={m.id}
            className={"mode-card " + (mode === m.id ? "selected" : "")}
            onClick={() => onMode(m.id)}
          >
            <m.icon size={34} />
            <h2>{m.name}</h2>
            <p>{m.description}</p>
            <span>{mode === m.id ? "Selected" : "Choose mode"}</span>
          </button>
        ))}
      </div>
      {mode === "chaos" && (
        <label className="mode-frequency">
          Chaos frequency
          <select
            value={settings.chaosFrequency}
            onChange={(e) => onSettings({ chaosFrequency: e.target.value })}
          >
            {["low", "medium", "high"].map((n) => (
              <option key={n}>{n}</option>
            ))}
          </select>
        </label>
      )}
      {mode === "impostor" && (
        <p className="help">
          3–5 bots: one impostor. 6 bots: two. An incorrect mark or accusation
          loses immediately. Right-click a square to accuse, or use Accuse on a
          touchscreen. Sourced knowledge is required to produce deliberate,
          checkable lies.
        </p>
      )}
    </>
  );
}
