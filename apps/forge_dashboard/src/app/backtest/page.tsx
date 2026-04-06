/* ── Backtest page ── */

"use client";

import { useState } from "react";
import BacktestRunner from "@/components/BacktestRunner";
import PerformanceMetrics from "@/components/PerformanceMetrics";
import TradeTable from "@/components/TradeTable";
import EquityCurve from "@/components/EquityCurve";
import { useBacktestList } from "@/lib/hooks";
import { getBacktestResult } from "@/lib/api";
import type { BacktestResult, JournalTrade } from "@/lib/types";

export default function BacktestPage() {
  const { data: backtests, reload } = useBacktestList();
  const [selected, setSelected] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSelect(runId: string) {
    setLoading(true);
    try {
      const result = await getBacktestResult(runId);
      setSelected(result);
    } finally {
      setLoading(false);
    }
  }

  function handleNewResult(result: BacktestResult) {
    setSelected(result);
    reload();
  }

  return (
    <div className="space-y-6 max-w-[1400px]">
      <h2 className="text-xl font-bold text-white">Backtesting</h2>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left: runner + list */}
        <div className="space-y-4">
          <BacktestRunner onResult={handleNewResult} />

          <div className="bg-[#1a1a2e] rounded-lg border border-gray-800 p-3">
            <h3 className="text-sm font-medium text-gray-400 mb-2">
              Previous Runs
            </h3>
            <div className="space-y-1 max-h-64 overflow-y-auto">
              {(backtests ?? []).map((b) => (
                <button
                  key={b.run_id}
                  onClick={() => handleSelect(b.run_id)}
                  className={`w-full text-left px-3 py-2 rounded text-xs transition-colors ${
                    selected?.run_id === b.run_id
                      ? "bg-blue-600/20 text-blue-400"
                      : "text-gray-400 hover:bg-gray-800"
                  }`}
                >
                  <div className="font-mono">{b.run_id.slice(0, 8)}...</div>
                  <div className="text-[10px] text-gray-600">{b.strategy_name}</div>
                </button>
              ))}
              {(backtests ?? []).length === 0 && (
                <p className="text-xs text-gray-600">No runs yet</p>
              )}
            </div>
          </div>
        </div>

        {/* Right: results */}
        <div className="lg:col-span-3 space-y-4">
          {loading && (
            <p className="text-gray-500 text-sm">Loading results...</p>
          )}
          {selected && !loading && (
            <>
              <PerformanceMetrics
                metrics={selected.metrics as unknown as Record<string, number>}
              />
              <EquityCurve
                data={(selected.equity_curve ?? []).map(([ts, eq]) => ({
                  timestamp: ts,
                  equity: eq,
                }))}
                height={250}
              />
              <div className="bg-[#1a1a2e] rounded-lg p-3 border border-gray-800">
                <h3 className="text-sm font-medium text-gray-400 mb-2">
                  Trades
                </h3>
                <TradeTable
                  trades={(selected.trades ?? []).map((t, i) => ({
                    trade_id: String(i),
                    strategy_name: selected.strategy_name,
                    session_id: selected.session_id,
                    symbol: t.symbol,
                    side: t.side,
                    entry_price: t.entry_price,
                    exit_price: t.exit_price,
                    quantity: t.quantity,
                    pnl: t.pnl,
                    net_pnl: t.net_pnl ?? t.pnl ?? 0,
                    pnl_pct: 0,
                    fees: t.fees ?? 0,
                    entry_time: "",
                    exit_time: null,
                    entry_reason: "",
                    exit_reason: "",
                    execution_mode: "backtest",
                    indicators_at_entry: {},
                    indicators_at_exit: {},
                  } satisfies JournalTrade))}
                />
              </div>
            </>
          )}
          {!selected && !loading && (
            <div className="flex items-center justify-center h-64 text-gray-600 text-sm">
              Run a backtest or select a previous run to view results
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
