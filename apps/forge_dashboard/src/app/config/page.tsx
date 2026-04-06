/* ── Config page ── */

"use client";

import { useEffect, useState } from "react";
import { getSystemConfig, getSystemStatus } from "@/lib/api";
import { useAvailableStrategies, useActiveStrategy } from "@/lib/hooks";
import StrategySelector from "@/components/StrategySelector";
import ModeSwitch from "@/components/ModeSwitch";
import type { SystemConfig, SystemStatus } from "@/lib/types";

export default function ConfigPage() {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [mode, setMode] = useState("backtest");
  const { data: strategies } = useAvailableStrategies();
  const { data: active } = useActiveStrategy();

  useEffect(() => {
    getSystemConfig().then(setConfig).catch(() => {});
    getSystemStatus().then((s) => {
      setStatus(s);
      if (s.mode) setMode(s.mode.toLowerCase());
    }).catch(() => {});
  }, []);

  return (
    <div className="space-y-6 max-w-3xl">
      <h2 className="text-xl font-bold text-white">Configuration</h2>

      {/* Mode switch */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
        <h3 className="text-sm font-medium text-gray-400 mb-3">
          Execution Mode
        </h3>
        <ModeSwitch current={mode} onChange={setMode} />
      </div>

      {/* Strategy */}
      <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
        <h3 className="text-sm font-medium text-gray-400 mb-3">
          Active Strategy
        </h3>
        <StrategySelector
          strategies={strategies ?? []}
          current={active?.name ?? ""}
          onSelect={() => {}}
        />
      </div>

      {/* System status */}
      {status && (
        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-400 mb-3">
            System Status
          </h3>
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-gray-500">Engine:</span>{" "}
              <span className={status.engine_running ? "text-green-400" : "text-gray-400"}>
                {status.engine_running ? "Running" : "Stopped"}
              </span>
            </div>
            <div>
              <span className="text-gray-500">Mode:</span>{" "}
              <span className="text-gray-300">{status.mode ?? "—"}</span>
            </div>
            <div>
              <span className="text-gray-500">Strategy:</span>{" "}
              <span className="text-gray-300">{status.strategy ?? "—"}</span>
            </div>
            <div>
              <span className="text-gray-500">Session:</span>{" "}
              <span className="text-gray-300 font-mono text-xs">{status.session_id ?? "—"}</span>
            </div>
          </div>
        </div>
      )}

      {/* Raw config */}
      {config && (
        <div className="bg-[#1a1a2e] rounded-lg p-4 border border-gray-800">
          <h3 className="text-sm font-medium text-gray-400 mb-3">
            System Config
          </h3>
          <pre className="text-xs text-gray-400 overflow-auto max-h-64 font-mono">
            {JSON.stringify(config, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
