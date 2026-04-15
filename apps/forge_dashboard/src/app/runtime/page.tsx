"use client";

import { useMemo, useState } from "react";
import { useRuntimeConfig, useRuntimeEvents, useRuntimeStatus } from "@/lib/hooks";
import { restartRuntime, startRuntime, stopRuntime } from "@/lib/api";

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") return Number.isFinite(value) ? value.toFixed(2) : "-";
  return String(value);
}

export default function RuntimePage() {
  const status = useRuntimeStatus(3000);
  const events = useRuntimeEvents(120, 3000);
  const { data: config } = useRuntimeConfig();
  const [busy, setBusy] = useState<"start" | "stop" | "restart" | null>(null);
  const [message, setMessage] = useState<string>("");

  const orderedEvents = useMemo(() => [...events].reverse(), [events]);

  async function handleAction(action: "start" | "stop" | "restart") {
    setBusy(action);
    setMessage("");
    try {
      const response =
        action === "start"
          ? await startRuntime()
          : action === "stop"
          ? await stopRuntime()
          : await restartRuntime();
      setMessage(`Runtime ${response.status.replace("_", " ")}`);
    } catch (error) {
      const text = error instanceof Error ? error.message : "Action failed";
      setMessage(text);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-white">Runtime Control</h2>
          <p className="text-sm text-gray-400 mt-1">
            Monitor and operate the standalone strategy runtime service.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => handleAction("start")}
            disabled={busy !== null}
            className="px-3 py-2 rounded-md bg-green-600/25 text-green-300 hover:bg-green-600/35 disabled:opacity-50 text-sm"
          >
            {busy === "start" ? "Starting..." : "Start"}
          </button>
          <button
            onClick={() => handleAction("stop")}
            disabled={busy !== null}
            className="px-3 py-2 rounded-md bg-red-600/25 text-red-300 hover:bg-red-600/35 disabled:opacity-50 text-sm"
          >
            {busy === "stop" ? "Stopping..." : "Stop"}
          </button>
          <button
            onClick={() => handleAction("restart")}
            disabled={busy !== null}
            className="px-3 py-2 rounded-md bg-blue-600/25 text-blue-300 hover:bg-blue-600/35 disabled:opacity-50 text-sm"
          >
            {busy === "restart" ? "Restarting..." : "Restart"}
          </button>
        </div>
      </div>

      {message ? (
        <div className="rounded-lg border border-gray-800 bg-[#1a1a2e] p-3 text-sm text-gray-300">
          {message}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <section className="rounded-lg border border-gray-800 bg-[#1a1a2e] p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Runtime Status</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="text-gray-500">Running</div>
            <div className={status?.running ? "text-green-400" : "text-gray-300"}>
              {status?.running ? "Yes" : "No"}
            </div>
            <div className="text-gray-500">Provider</div>
            <div className="text-gray-300">{status?.provider ?? "-"}</div>
            <div className="text-gray-500">Symbol</div>
            <div className="text-gray-300">{status?.symbol ?? "-"}</div>
            <div className="text-gray-500">Timeframe</div>
            <div className="text-gray-300">{status?.timeframe ?? "-"}</div>
            <div className="text-gray-500">Strategy</div>
            <div className="text-gray-300">{status?.strategy ?? "-"}</div>
            <div className="text-gray-500">Started At</div>
            <div className="text-gray-300">{status?.started_at ?? "-"}</div>
            <div className="text-gray-500">Pending Orders</div>
            <div className="text-gray-300">{formatValue(status?.pending_orders)}</div>
            <div className="text-gray-500">Cash</div>
            <div className="text-gray-300">{formatValue(status?.portfolio?.cash)}</div>
            <div className="text-gray-500">Equity</div>
            <div className="text-gray-300">{formatValue(status?.portfolio?.equity)}</div>
          </div>

          {status?.last_error ? (
            <div className="mt-3 rounded-md border border-red-900 bg-red-950/30 p-2 text-xs text-red-300">
              {status.last_error}
            </div>
          ) : null}
        </section>

        <section className="rounded-lg border border-gray-800 bg-[#1a1a2e] p-4">
          <h3 className="text-sm font-medium text-gray-400 mb-3">Latest Market Snapshot</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="text-gray-500">Bar Time</div>
            <div className="text-gray-300">{status?.latest_bar?.time ?? "-"}</div>
            <div className="text-gray-500">Open</div>
            <div className="text-gray-300">{formatValue(status?.latest_bar?.open)}</div>
            <div className="text-gray-500">High</div>
            <div className="text-gray-300">{formatValue(status?.latest_bar?.high)}</div>
            <div className="text-gray-500">Low</div>
            <div className="text-gray-300">{formatValue(status?.latest_bar?.low)}</div>
            <div className="text-gray-500">Close</div>
            <div className="text-gray-300">{formatValue(status?.latest_bar?.close)}</div>
            <div className="text-gray-500">Volume</div>
            <div className="text-gray-300">{formatValue(status?.latest_bar?.volume)}</div>
          </div>
          <div className="mt-3 text-xs text-gray-400">
            <div className="font-medium text-gray-300 mb-1">Indicators</div>
            <pre className="overflow-auto max-h-28 rounded bg-[#151528] p-2 border border-gray-800">
              {JSON.stringify(status?.latest_indicators ?? {}, null, 2)}
            </pre>
          </div>
        </section>
      </div>

      <section className="rounded-lg border border-gray-800 bg-[#1a1a2e] p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Runtime Config</h3>
        <pre className="text-xs text-gray-400 overflow-auto max-h-40 rounded bg-[#151528] p-3 border border-gray-800">
          {JSON.stringify(config ?? {}, null, 2)}
        </pre>
      </section>

      <section className="rounded-lg border border-gray-800 bg-[#1a1a2e] p-4">
        <h3 className="text-sm font-medium text-gray-400 mb-3">Recent Events</h3>
        <div className="max-h-[28rem] overflow-auto border border-gray-800 rounded-md">
          <table className="w-full text-xs">
            <thead className="bg-[#151528] sticky top-0">
              <tr>
                <th className="text-left px-3 py-2 text-gray-500">Time</th>
                <th className="text-left px-3 py-2 text-gray-500">Type</th>
                <th className="text-left px-3 py-2 text-gray-500">Payload</th>
              </tr>
            </thead>
            <tbody>
              {orderedEvents.length === 0 ? (
                <tr>
                  <td className="px-3 py-4 text-gray-500" colSpan={3}>
                    No runtime events yet.
                  </td>
                </tr>
              ) : (
                orderedEvents.map((event, idx) => (
                  <tr key={`${event.time}-${event.type}-${idx}`} className="border-t border-gray-900">
                    <td className="px-3 py-2 text-gray-300 align-top">{event.time}</td>
                    <td className="px-3 py-2 text-blue-300 align-top">{event.type}</td>
                    <td className="px-3 py-2 text-gray-400">
                      <pre className="whitespace-pre-wrap break-all">{JSON.stringify(event.payload)}</pre>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
