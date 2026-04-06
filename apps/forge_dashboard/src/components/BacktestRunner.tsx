/* ── Backtest runner form ── */

"use client";

import { useState } from "react";
import { runBacktest } from "@/lib/api";
import type { BacktestResult } from "@/lib/types";

interface BacktestRunnerProps {
  onResult: (result: BacktestResult) => void;
}

export default function BacktestRunner({ onResult }: BacktestRunnerProps) {
  const [configPath, setConfigPath] = useState("config/backtest.yaml");
  const [basePath, setBasePath] = useState("config/base.yaml");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setRunning(true);
    setError(null);
    try {
      const result = await runBacktest({
        config_path: configPath,
        base_path: basePath || undefined,
      });
      onResult(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Backtest failed";
      setError(msg);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
      <h3 className="text-sm font-medium text-gray-300 mb-3">Run Backtest</h3>
      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Config Path</label>
          <input
            type="text"
            value={configPath}
            onChange={(e) => setConfigPath(e.target.value)}
            className="w-full bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">
            Base Config (optional)
          </label>
          <input
            type="text"
            value={basePath}
            onChange={(e) => setBasePath(e.target.value)}
            className="w-full bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
        </div>
        <button
          onClick={handleRun}
          disabled={running || !configPath}
          className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500 text-white rounded px-4 py-2 text-sm font-medium transition-colors"
        >
          {running ? "Running..." : "Run Backtest ▶"}
        </button>
        {error && (
          <p className="text-red-400 text-xs">{error}</p>
        )}
      </div>
    </div>
  );
}
