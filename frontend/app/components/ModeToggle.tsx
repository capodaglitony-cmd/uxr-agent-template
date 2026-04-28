"use client";

export type Mode = "fast" | "deep" | "wizard";

const MODE_LABELS: Record<Mode, string> = {
  fast: "Fast",
  deep: "Deep",
  wizard: "Wizard",
};

const MODES: Mode[] = ["fast", "deep", "wizard"];

export function ModeToggle({
  active,
  onChange,
}: {
  active: Mode;
  onChange: (mode: Mode) => void;
}) {
  return (
    <div className="inline-flex border border-border2 rounded-md overflow-hidden font-mono text-[11px]">
      {MODES.map((mode, i) => (
        <button
          key={mode}
          type="button"
          onClick={() => onChange(mode)}
          className={[
            "px-3.5 py-1.5 bg-transparent border-none cursor-pointer transition-colors tracking-wider",
            i < MODES.length - 1 ? "border-r border-border2" : "",
            active === mode
              ? "bg-accent-glow text-accent-bright"
              : "text-textdim hover:text-textmuted",
          ].join(" ")}
        >
          {MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  );
}
