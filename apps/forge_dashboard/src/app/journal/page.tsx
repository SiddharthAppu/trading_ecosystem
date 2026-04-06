/* ── Journal page ── */

"use client";

import { useState } from "react";
import TradeTable from "@/components/TradeTable";
import { useJournalTrades, useSessionSummary } from "@/lib/hooks";
import PerformanceMetrics from "@/components/PerformanceMetrics";
import type { JournalFilters } from "@/lib/types";

export default function JournalPage() {
  const [filters, setFilters] = useState<JournalFilters>({});
  const { data: trades } = useJournalTrades(filters);
  const { data: summary } = useSessionSummary();

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
    </div>
  );
}
