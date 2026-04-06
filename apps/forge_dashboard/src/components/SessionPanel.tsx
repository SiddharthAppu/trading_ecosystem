/* ── Session info panel ── */

"use client";

import type { SystemStatus } from "@/lib/types";

interface SessionPanelProps {
  status: SystemStatus | null;
}

export default function SessionPanel({ status }: SessionPanelProps) {
  if (!status) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500">
        <span className="w-2 h-2 rounded-full bg-gray-600" />
        Connecting...
      </div>
    );
  }

  const isRunning = status.engine_running;

  return (
    <div className="flex items-center gap-4 text-sm">
      <div className="flex items-center gap-2">
        <span
          className={`w-2 h-2 rounded-full ${
            isRunning ? "bg-green-500 animate-pulse" : "bg-gray-600"
          }`}
        />
        <span className={isRunning ? "text-green-400" : "text-gray-500"}>
          {isRunning ? "Running" : "Stopped"}
        </span>
      </div>
      {isRunning && (
        <>
          <div className="text-gray-500">
            Mode: <span className="text-gray-300">{status.mode}</span>
          </div>
          <div className="text-gray-500">
            Strategy: <span className="text-gray-300">{status.strategy}</span>
          </div>
          <div className="text-gray-500 font-mono text-xs">
            {status.session_id}
          </div>
        </>
      )}
    </div>
  );
}
