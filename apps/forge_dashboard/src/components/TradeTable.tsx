/* ── Trade journal table with expandable rows ── */

"use client";

import { useState } from "react";
import type { JournalTrade } from "@/lib/types";

interface TradeTableProps {
  trades: JournalTrade[];
  compact?: boolean;
}

function fmtTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    day: "numeric",
  });
}

export default function TradeTable({ trades, compact = false }: TradeTableProps) {
  const [expanded, setExpanded] = useState<string | null>(null);

  if (trades.length === 0) {
    return (
      <div className="text-center text-gray-500 py-8">No trades to display</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500 border-b border-gray-800">
            <th className="py-2 px-2">Symbol</th>
            <th className="py-2 px-2">Side</th>
            <th className="py-2 px-2">Entry</th>
            {!compact && <th className="py-2 px-2">Exit</th>}
            <th className="py-2 px-2 text-right">Price</th>
            <th className="py-2 px-2 text-right">Qty</th>
            <th className="py-2 px-2 text-right">P&L</th>
            <th className="py-2 px-2 text-right">%</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <TradeRow
              key={t.trade_id}
              trade={t}
              compact={compact}
              isExpanded={expanded === t.trade_id}
              onToggle={() =>
                setExpanded(expanded === t.trade_id ? null : t.trade_id)
              }
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeRow({
  trade: t,
  compact,
  isExpanded,
  onToggle,
}: {
  trade: JournalTrade;
  compact: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const pnlColor = t.net_pnl > 0 ? "text-green-400" : t.net_pnl < 0 ? "text-red-400" : "text-gray-400";

  return (
    <>
      <tr
        className="border-b border-gray-800/50 hover:bg-gray-800/30 cursor-pointer"
        onClick={onToggle}
      >
        <td className="py-2 px-2 font-mono text-xs">{t.symbol}</td>
        <td className="py-2 px-2">
          <span
            className={`px-1.5 py-0.5 rounded text-xs font-medium ${
              t.side === "LONG"
                ? "bg-green-900/40 text-green-400"
                : "bg-red-900/40 text-red-400"
            }`}
          >
            {t.side}
          </span>
        </td>
        <td className="py-2 px-2 text-xs text-gray-400">
          {fmtDate(t.entry_time)} {fmtTime(t.entry_time)}
        </td>
        {!compact && (
          <td className="py-2 px-2 text-xs text-gray-400">
            {t.exit_time ? `${fmtDate(t.exit_time)} ${fmtTime(t.exit_time)}` : "Open"}
          </td>
        )}
        <td className="py-2 px-2 text-right font-mono text-xs">
          {t.entry_price.toFixed(2)}
          {t.exit_price != null ? ` → ${t.exit_price.toFixed(2)}` : ""}
        </td>
        <td className="py-2 px-2 text-right">{t.quantity}</td>
        <td className={`py-2 px-2 text-right font-semibold ${pnlColor}`}>
          {t.net_pnl >= 0 ? "+" : ""}
          {t.net_pnl.toFixed(2)}
        </td>
        <td className={`py-2 px-2 text-right ${pnlColor}`}>
          {t.pnl_pct >= 0 ? "+" : ""}
          {t.pnl_pct.toFixed(2)}%
        </td>
      </tr>
      {isExpanded && (
        <tr className="bg-gray-900/40">
          <td colSpan={compact ? 7 : 8} className="px-4 py-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div>
                <span className="text-gray-500">Fees:</span>{" "}
                <span className="text-gray-300">₹{t.fees.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-gray-500">Mode:</span>{" "}
                <span className="text-gray-300">{t.execution_mode}</span>
              </div>
              {t.entry_reason && (
                <div>
                  <span className="text-gray-500">Entry Reason:</span>{" "}
                  <span className="text-gray-300">{t.entry_reason}</span>
                </div>
              )}
              {t.exit_reason && (
                <div>
                  <span className="text-gray-500">Exit Reason:</span>{" "}
                  <span className="text-gray-300">{t.exit_reason}</span>
                </div>
              )}
              {Object.keys(t.indicators_at_entry).length > 0 && (
                <div className="col-span-2">
                  <span className="text-gray-500">Indicators @ Entry:</span>{" "}
                  <span className="text-gray-300 font-mono">
                    {Object.entries(t.indicators_at_entry)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(", ")}
                  </span>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
