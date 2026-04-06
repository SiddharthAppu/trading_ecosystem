/* ── Dashboard page ── */

"use client";

import { useState } from "react";
import TradingChart from "@/components/TradingChart";
import EquityCurve from "@/components/EquityCurve";
import PerformanceMetrics from "@/components/PerformanceMetrics";
import TradeTable from "@/components/TradeTable";
import SessionPanel from "@/components/SessionPanel";
import {
  useSystemStatus,
  useCandles,
  useEquityCurve,
  useTradeMarkers,
  useJournalTrades,
  useSessionSummary,
} from "@/lib/hooks";

export default function DashboardPage() {
  const [symbol] = useState("NIFTY");

  const status = useSystemStatus(5000);
  const { data: candles } = useCandles(symbol, 500);
  const { data: markers } = useTradeMarkers();
  const { data: equity } = useEquityCurve();
  const { data: trades } = useJournalTrades();
  const { data: summary } = useSessionSummary();

  return (
    <div className="space-y-6 max-w-[1400px]">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Dashboard</h2>
        <SessionPanel status={status} />
      </div>

      {/* Performance metrics */}
      {summary && <PerformanceMetrics metrics={summary as unknown as Record<string, number>} />}

      {/* Chart */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
        <h3 className="text-sm font-medium text-gray-400 mb-2">{symbol} – Price</h3>
        <TradingChart
          candles={candles ?? []}
          markers={markers ?? []}
          height={380}
        />
      </div>

      {/* Equity + Recent trades */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <EquityCurve data={equity ?? []} height={220} />
        <div>
          <h3 className="text-sm font-medium text-gray-400 mb-2">
            Recent Trades
          </h3>
          <div className="bg-[#1a1a2e] rounded-lg border border-gray-800 p-3">
            <TradeTable trades={(trades ?? []).slice(0, 10)} compact />
          </div>
        </div>
      </div>
    </div>
  );
}
