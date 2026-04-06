/* ── Full-screen chart page ── */

"use client";

import { useState } from "react";
import TradingChart from "@/components/TradingChart";
import { useCandles, useTradeMarkers } from "@/lib/hooks";

export default function ChartPage() {
  const [symbol, setSymbol] = useState("NIFTY");
  const [limit, setLimit] = useState(1000);
  const [showMarkers, setShowMarkers] = useState(true);

  const { data: candles } = useCandles(symbol, limit);
  const { data: markers } = useTradeMarkers();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">Chart</h2>
        <div className="flex items-center gap-3">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm w-28 focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value={200}>200</option>
            <option value={500}>500</option>
            <option value={1000}>1000</option>
            <option value={2000}>2000</option>
          </select>
          <label className="flex items-center gap-1.5 text-sm text-gray-400">
            <input
              type="checkbox"
              checked={showMarkers}
              onChange={(e) => setShowMarkers(e.target.checked)}
              className="accent-blue-600"
            />
            Trades
          </label>
        </div>
      </div>

      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
        <TradingChart
          candles={candles ?? []}
          markers={showMarkers ? (markers ?? []) : []}
          height={600}
        />
      </div>
    </div>
  );
}
