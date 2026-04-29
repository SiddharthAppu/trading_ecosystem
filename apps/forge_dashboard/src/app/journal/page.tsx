/* ── Journal page ── */

"use client";

import { useState } from "react";
import Link from "next/link";
import TradeTable from "@/components/TradeTable";
import { useJournalTrades, useSessionSummary, useRuntimeJournalEvents } from "@/lib/hooks";
import PerformanceMetrics from "@/components/PerformanceMetrics";
import type { JournalFilters } from "@/lib/types";

function fmtEventTs(iso: string): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export default function JournalPage() {
  const [filters, setFilters] = useState<JournalFilters>({});
  const { data: trades } = useJournalTrades(filters);
  const { data: summary } = useSessionSummary();
  const [liveSymbol, setLiveSymbol] = useState("");
  const liveEvents = useRuntimeJournalEvents(
    {
      limit: 100,
      symbol: liveSymbol.trim() || undefined,
    },
    3000
  );
  const recentLiveEvents = liveEvents.slice(-20).reverse();

  return (
    <div className="space-y-6 max-w-[1400px]">
      <h2 className="text-xl font-bold text-white">Trade Journal</h2>

      {/* Summary metrics */}
      {summary && <PerformanceMetrics metrics={summary as unknown as Record<string, number>} />}

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Symbol</label>
          <input
            type="text"
            value={filters.symbol ?? ""}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                symbol: e.target.value || undefined,
              }))
            }
            placeholder="e.g. NIFTY"
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm w-32 focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Side</label>
          <select
            value={filters.side ?? ""}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                side: (e.target.value as "LONG" | "SHORT") || undefined,
              }))
            }
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-600"
          >
            <option value="">All</option>
            <option value="LONG">Long</option>
            <option value="SHORT">Short</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Limit</label>
          <input
            type="number"
            value={filters.limit ?? 100}
            onChange={(e) =>
              setFilters((f) => ({ ...f, limit: parseInt(e.target.value) || 100 }))
            }
            className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-sm w-20 focus:outline-none focus:ring-2 focus:ring-blue-600"
          />
        </div>
        <button
          onClick={() => setFilters({})}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 rounded px-3 py-1.5 text-sm"
        >
          Clear
        </button>
      </div>

      {/* Trade table */}
      <div className="bg-[#1a1a2e] rounded-lg border border-gray-800 p-4">
        <TradeTable trades={trades ?? []} />
      </div>

      {/* Live Event Markers */}
      <div className="bg-[#1a1a2e] rounded-lg border border-gray-800 p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-200">Live Strategy Events</h3>
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={liveSymbol}
              onChange={(e) => setLiveSymbol(e.target.value.toUpperCase())}
              placeholder="Filter symbol"
              className="bg-gray-900 text-gray-200 border border-gray-700 rounded px-3 py-1.5 text-xs w-32 focus:outline-none focus:ring-2 focus:ring-blue-600"
            />
            <span className="text-xs text-gray-500">
              {recentLiveEvents.length} event{recentLiveEvents.length !== 1 ? "s" : ""}
            </span>
          </div>
        </div>

        {recentLiveEvents.length === 0 ? (
          <div className="text-center text-gray-500 py-6 text-xs">
            No live events yet. Start the runtime to see JSONL events here.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="py-2 px-2">Time</th>
                  <th className="py-2 px-2">Event</th>
                  <th className="py-2 px-2">Symbol</th>
                  <th className="py-2 px-2">Side</th>
                  <th className="py-2 px-2">Chart Links</th>
                </tr>
              </thead>
              <tbody>
                {recentLiveEvents.map((row) => (
                  <tr key={row.id} className="border-b border-gray-900 hover:bg-gray-900/30">
                    <td className="py-2 px-2 text-gray-300">{fmtEventTs(row.event_ts)}</td>
                    <td className="py-2 px-2 text-blue-300">{row.event}</td>
                    <td className="py-2 px-2 font-mono text-gray-200">{row.symbol}</td>
                    <td className="py-2 px-2 text-gray-300">{row.side || "-"}</td>
                    <td className="py-2 px-2 space-x-2">
                      <Link
                        href={row.links.local_chart_url}
                        className="inline-block text-emerald-300 hover:text-emerald-200 underline"
                      >
                        Chart
                      </Link>
                      {row.links.tradingview_url && (
                        <a
                          href={row.links.tradingview_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-block text-cyan-300 hover:text-cyan-200 underline"
                        >
                          TV
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="text-xs text-gray-500 pt-2 border-t border-gray-800">
          <Link href="/journal-events" className="text-blue-300 hover:text-blue-200 underline">
            View all events in detail →
          </Link>
        </div>
      </div>
    </div>
  );
}
