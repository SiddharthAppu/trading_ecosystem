/* ── Full-screen chart page ── */

"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import TradingChart from "@/components/TradingChart";
import { useCandles, useTradeMarkers } from "@/lib/hooks";

export default function ChartPage() {
  const params = useSearchParams();
  const initialSymbol = params.get("symbol") ?? "NIFTY";
  const eventTs = params.get("eventTs") ?? "";
  const eventType = params.get("eventType") ?? "";
  const eventSide = params.get("side") ?? "";
  const deepLinkTvUrl = params.get("tvUrl") ?? "";

  const [symbol, setSymbol] = useState(initialSymbol);
  const [limit, setLimit] = useState(1000);
  const [showMarkers, setShowMarkers] = useState(true);
  const [showTradingView, setShowTradingView] = useState(Boolean(deepLinkTvUrl));

  const { data: candles } = useCandles(symbol, limit);
  const { data: markers } = useTradeMarkers();

  const eventMarker =
    eventTs && eventSide
      ? [
          {
            timestamp: eventTs,
            side: eventSide === "SELL" ? ("SELL" as const) : ("BUY" as const),
            price: 0,
            symbol,
            pnl: null,
            trade_id: `journal-${eventType || "event"}`,
          },
        ]
      : [];

  const visibleMarkers = showMarkers ? [...(markers ?? []), ...eventMarker] : [];

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
          {deepLinkTvUrl ? (
            <label className="flex items-center gap-1.5 text-sm text-gray-400">
              <input
                type="checkbox"
                checked={showTradingView}
                onChange={(e) => setShowTradingView(e.target.checked)}
                className="accent-cyan-600"
              />
              TradingView
            </label>
          ) : null}
        </div>
      </div>

      {eventTs ? (
        <div className="rounded-md border border-cyan-900/70 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-200">
          Focus event: {eventType || "EVENT"} at {new Date(eventTs).toLocaleString("en-IN", { hour12: false })}
        </div>
      ) : null}

      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
        <TradingChart
          candles={candles ?? []}
          markers={visibleMarkers}
          height={600}
        />
      </div>

      {deepLinkTvUrl && showTradingView ? (
        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold text-gray-200">TradingView</h3>
            <a
              href={deepLinkTvUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-cyan-300 hover:text-cyan-200 underline"
            >
              Open in new tab
            </a>
          </div>
          <iframe
            src={deepLinkTvUrl}
            title="TradingView"
            className="w-full h-[560px] rounded border border-gray-800"
          />
        </div>
      ) : null}
    </div>
  );
}
