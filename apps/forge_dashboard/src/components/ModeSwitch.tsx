/* ── Mode switcher: Backtest / Paper / Live ── */

"use client";

interface ModeSwitchProps {
  current: string;
  onChange: (mode: string) => void;
}

const modes = [
  { value: "backtest", label: "Backtest", color: "blue" },
  { value: "paper", label: "Paper", color: "yellow" },
  { value: "live", label: "Live", color: "red" },
];

const activeClass: Record<string, string> = {
  blue: "bg-blue-600 text-white",
  yellow: "bg-yellow-600 text-white",
  red: "bg-red-600 text-white",
};

export default function ModeSwitch({ current, onChange }: ModeSwitchProps) {
  return (
    <div className="flex rounded-lg overflow-hidden border border-gray-700">
      {modes.map((m) => (
        <button
          key={m.value}
          onClick={() => onChange(m.value)}
          className={`px-4 py-1.5 text-xs font-medium transition-colors ${
            current === m.value
              ? activeClass[m.color]
              : "bg-gray-800 text-gray-400 hover:bg-gray-700"
          }`}
        >
          {m.label}
        </button>
      ))}
    </div>
  );
}
