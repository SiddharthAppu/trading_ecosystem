/* ── Strategy selector dropdown ── */

"use client";

import type { StrategyInfo } from "@/lib/types";

interface StrategySelectorProps {
  strategies: StrategyInfo[];
  current: string;
  onSelect: (name: string) => void;
}

export default function StrategySelector({
  strategies,
  current,
  onSelect,
}: StrategySelectorProps) {
  return (
    <select
      value={current}
      onChange={(e) => onSelect(e.target.value)}
      className="bg-gray-800 text-gray-200 border border-gray-700 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
    >
      {strategies.length === 0 && (
        <option value="">No strategies found</option>
      )}
      {strategies.map((s) => (
        <option key={s.name} value={s.name}>
          {s.name}
        </option>
      ))}
    </select>
  );
}
