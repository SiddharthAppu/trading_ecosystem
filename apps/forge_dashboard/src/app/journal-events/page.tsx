"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRuntimeJournalEvents } from "@/lib/hooks";

function fmtTs(iso: string): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("en-IN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function JournalEventsPage() {
  const [symbol, setSymbol] = useState("");
  const [eventType, setEventType] = useState("");
  const [limit, setLimit] = useState(300);

  const events = useRuntimeJournalEvents(
    {
      symbol: symbol.trim() || undefined,
      event: eventType || undefined,
      limit,
    },
    4000
  );

  const ordered = useMemo(() => [...events].reverse(), [events]);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Journal Events</h2>
          <p className="text-sm text-gray-400">
            JSONL is the single source of truth. Open each event in local chart or TradingView.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
            placeholder="Filter symbol"
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm w-36 focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value="">All events</option>
            <option value="INDICATOR_PASSED">INDICATOR_PASSED</option>
            <option value="ORDER_PLACED">ORDER_PLACED</option>
            <option value="ORDER_FILL">ORDER_FILL</option>
          </select>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value={100}>100</option>
            <option value={300}>300</option>
            <option value={1000}>1000</option>
          </select>
        </div>
      </div>

      <div className="rounded-lg border border-gray-800 bg-[#1a1a2e] overflow-auto max-h-[70vh]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-[#151528]">
            <tr>
              <th className="text-left px-3 py-2 text-gray-500">Time</th>
              <th className="text-left px-3 py-2 text-gray-500">Event</th>
              <th className="text-left px-3 py-2 text-gray-500">Symbol</th>
              <th className="text-left px-3 py-2 text-gray-500">Side</th>
              <th className="text-left px-3 py-2 text-gray-500">TF</th>
              <th className="text-right px-3 py-2 text-gray-500">Line</th>
              <th className="text-left px-3 py-2 text-gray-500">Chart</th>
              <th className="text-left px-3 py-2 text-gray-500">TradingView</th>
            </tr>
          </thead>
          <tbody>
            {ordered.length === 0 ? (
              <tr>
                <td className="px-3 py-5 text-gray-500" colSpan={8}>
                  No journal events found.
                </td>
              </tr>
            ) : (
              ordered.map((row) => (
                <tr key={row.id} className="border-t border-gray-900 align-top">
                  <td className="px-3 py-2 text-gray-300">{fmtTs(row.event_ts)}</td>
                  <td className="px-3 py-2 text-blue-300">{row.event}</td>
                  <td className="px-3 py-2 text-gray-200 font-mono">{row.symbol}</td>
                  <td className="px-3 py-2 text-gray-300">{row.side || "-"}</td>
                  <td className="px-3 py-2 text-gray-300">{row.timeframe}</td>
                  <td className="px-3 py-2 text-gray-400 text-right">{row.line_no}</td>
                  <td className="px-3 py-2">
                    <Link
                      href={row.links.local_chart_url}
                      className="text-emerald-300 hover:text-emerald-200 underline"
                    >
                      Local
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {row.links.tradingview_url ? (
                      <a
                        href={row.links.tradingview_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-cyan-300 hover:text-cyan-200 underline"
                      >
                        Open
                      </a>
                    ) : (
                      <span className="text-gray-600">unmapped</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
