import type { Bot } from "../types";
export default function Relationships({
  bots,
  values,
  locks,
  onChange,
}: {
  bots: Bot[];
  values: Record<string, number>;
  locks: Record<string, boolean>;
  onChange: (
    values: Record<string, number>,
    locks: Record<string, boolean>,
  ) => void;
}) {
  return (
    <section className="relationship-editor">
      <h3>Friends, enemies & neutral pairs</h3>
      <p className="help">
        Starting scores influence dialogue when Personality Clashes is enabled.
        Lock a pair to keep its score fixed.
      </p>
      {bots.flatMap((a, i) =>
        bots.slice(i + 1).map((b) => {
          const key = [a.id, b.id].sort().join("|");
          const score = values[key] || 0;
          return (
            <div className="relationship-row" key={key}>
              <span>
                {a.name} ↔ {b.name}
              </span>
              <select
                aria-label={`${a.name} and ${b.name} relationship`}
                value={
                  score >= 25 ? "friend" : score <= -25 ? "enemy" : "neutral"
                }
                onChange={(e) =>
                  onChange(
                    {
                      ...values,
                      [key]:
                        e.target.value === "friend"
                          ? 50
                          : e.target.value === "enemy"
                            ? -50
                            : 0,
                    },
                    locks,
                  )
                }
              >
                <option value="friend">Friends (+50)</option>
                <option value="neutral">Neutral (0)</option>
                <option value="enemy">Enemies (−50)</option>
              </select>
              <label>
                <input
                  type="checkbox"
                  checked={Boolean(locks[key])}
                  onChange={(e) =>
                    onChange(values, { ...locks, [key]: e.target.checked })
                  }
                />{" "}
                Lock
              </label>
              <small>{score}</small>
            </div>
          );
        }),
      )}
    </section>
  );
}
